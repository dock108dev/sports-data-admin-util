"""Celery tasks for scrape job execution."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task

from ..logging import logger
from ..services.ingestion import run_ingestion
from ..utils.datetime_utils import today_et


@shared_task(name="run_scrape_job")
def run_scrape_job(run_id: int, config_payload: dict) -> dict:
    """Run a scrape job (data ingestion only).

    Timeline generation is decoupled - call trigger_game_pipelines_task
    after this completes, or use Pipeline API endpoints for manual control.
    """
    from ..utils.redis_lock import acquire_redis_lock, release_redis_lock, LOCK_TIMEOUT_1HOUR
    from ..utils.datetime_utils import now_utc

    league_code = config_payload.get("league_code", "UNKNOWN")
    lock_name = f"lock:ingest:{league_code}"

    if not acquire_redis_lock(lock_name, timeout=LOCK_TIMEOUT_1HOUR):
        logger.warning("scrape_job_skipped_locked", run_id=run_id, league=league_code)
        # Update the run record so UI can surface the skip reason
        from ..services.run_manager import ScrapeRunManager
        mgr = ScrapeRunManager()
        mgr._update_run(
            run_id,
            status="skipped",
            summary="Skipped: ingestion already in progress for this league",
            finished_at=now_utc(),
        )
        return {"status": "skipped", "reason": "ingestion_in_progress", "run_id": run_id}

    try:
        logger.info("scrape_job_started", run_id=run_id)
        result = run_ingestion(run_id, config_payload)
        logger.info("scrape_job_completed", run_id=run_id, result=result)
        return result
    finally:
        release_redis_lock(lock_name)


@shared_task(
    name="run_scheduled_ingestion",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_scheduled_ingestion() -> dict:
    """Trigger the scheduled ingestion pipeline.

    Runs leagues sequentially with PBP after each:
    1. NBA stats → PBP
    2. NHL stats → PBP
    3. NCAAB stats → PBP

    Social collection is dispatched asynchronously to the dedicated
    social-scraper worker after each league's PBP completes.
    This is fire-and-forget - we don't wait for social to complete.
    """
    from ..services.scheduler import (
        schedule_single_league_and_wait,
        run_pbp_ingestion_for_league,
    )

    results = {}

    # Clear recent scoreboard cache before ingestion to avoid stale game discovery.
    # Basketball Reference scoreboards are cached with no TTL; if a previous run cached
    # a page before all games had boxscore links, the 5AM run would reuse stale data.
    from ..utils.cache import HTMLCache
    from ..config import settings

    for league_code in ["NBA"]:
        try:
            cache = HTMLCache(settings.scraper_config.html_cache_dir, league_code)
            cleared = cache.clear_recent_scoreboards(days=3)
            logger.info("pre_ingestion_cache_cleared", league=league_code, **cleared)
        except Exception as exc:
            logger.warning("pre_ingestion_cache_clear_failed", league=league_code, error=str(exc))

    # === NBA ===
    logger.info("scheduled_ingestion_nba_start")
    nba_result = schedule_single_league_and_wait("NBA")
    results["NBA"] = nba_result
    logger.info("scheduled_ingestion_nba_complete", **nba_result)

    logger.info("scheduled_ingestion_nba_pbp_start")
    nba_pbp_result = run_pbp_ingestion_for_league("NBA")
    results["NBA_PBP"] = nba_pbp_result
    logger.info("scheduled_ingestion_nba_pbp_complete", **nba_pbp_result)

    # Social collection is now handled by the two-scrape-per-game model
    # (run_final_whistle_social on FINAL + daily sweep Scrape #2)

    # === NHL ===
    logger.info("scheduled_ingestion_nhl_start")
    nhl_result = schedule_single_league_and_wait("NHL")
    results["NHL"] = nhl_result
    logger.info("scheduled_ingestion_nhl_complete", **nhl_result)

    logger.info("scheduled_ingestion_nhl_pbp_start")
    nhl_pbp_result = run_pbp_ingestion_for_league("NHL")
    results["NHL_PBP"] = nhl_pbp_result
    logger.info("scheduled_ingestion_nhl_pbp_complete", **nhl_pbp_result)

    # === NCAAB ===
    logger.info("scheduled_ingestion_ncaab_start")
    ncaab_result = schedule_single_league_and_wait("NCAAB")
    results["NCAAB"] = ncaab_result
    logger.info("scheduled_ingestion_ncaab_complete", **ncaab_result)

    logger.info("scheduled_ingestion_ncaab_pbp_start")
    ncaab_pbp_result = run_pbp_ingestion_for_league("NCAAB")
    results["NCAAB_PBP"] = ncaab_pbp_result
    logger.info("scheduled_ingestion_ncaab_pbp_complete", **ncaab_pbp_result)

    return {
        "leagues": results,
        "total_runs_created": nba_result["runs_created"] + nhl_result["runs_created"] + ncaab_result["runs_created"],
        "total_pbp_games": nba_pbp_result["pbp_games"] + nhl_pbp_result["pbp_games"] + ncaab_pbp_result["pbp_games"],
    }


@shared_task(
    name="run_scheduled_odds_sync",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_scheduled_odds_sync() -> dict:
    """Sync odds for all in-scope leagues (NBA, NHL, NCAAB).

    Runs every 30 minutes to keep odds fresh for FairBet.
    Fetches live odds for today and tomorrow only (not historical).
    """
    from ..odds.synchronizer import OddsSynchronizer
    from ..models import IngestionConfig

    from ..config_sports import get_odds_enabled_leagues

    leagues = get_odds_enabled_leagues()
    sync = OddsSynchronizer()
    results = {}
    total_odds = 0

    # Sync today + 1 day ahead for upcoming games
    today = today_et()
    end = today + timedelta(days=1)

    logger.info(
        "scheduled_odds_sync_start",
        leagues=leagues,
        start_date=str(today),
        end_date=str(end),
    )

    for league_code in leagues:
        try:
            config = IngestionConfig(
                league_code=league_code,
                start_date=today,
                end_date=end,
                odds=True,
                boxscores=False,
                social=False,
                pbp=False,
            )
            count = sync.sync(config)
            results[league_code] = {"odds_count": count, "status": "success"}
            total_odds += count
            logger.info(
                "scheduled_odds_sync_league_complete",
                league=league_code,
                odds_count=count,
            )
        except Exception as exc:
            results[league_code] = {"odds_count": 0, "status": "error", "error": str(exc)}
            logger.exception(
                "scheduled_odds_sync_league_failed",
                league=league_code,
                error=str(exc),
            )

    logger.info(
        "scheduled_odds_sync_complete",
        total_odds=total_odds,
        results=results,
    )

    return {
        "leagues": results,
        "total_odds": total_odds,
    }


