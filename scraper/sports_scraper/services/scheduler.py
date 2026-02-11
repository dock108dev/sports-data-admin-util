"""Scheduled ingestion orchestration for periodic scraping runs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..utils.datetime_utils import now_utc
from ..config_sports import get_scheduled_leagues, get_league_config
from ..celery_app import DEFAULT_QUEUE


@dataclass(frozen=True)
class ScheduledIngestionSummary:
    runs_created: int
    runs_skipped: int
    run_failures: int
    enqueue_failures: int
    last_run_at: datetime


def build_scheduled_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Build the scheduled ingestion window (96 hours back -> 48 hours forward in UTC)."""
    anchor = now or now_utc()
    start = (anchor - timedelta(hours=96)).replace(tzinfo=timezone.utc)
    end = (anchor + timedelta(hours=48)).replace(tzinfo=timezone.utc)
    return start, end


def _coerce_date(value: datetime | None) -> datetime | None:
    if not value:
        return None
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def create_scrape_run(
    session: Session,
    league: db_models.SportsLeague,
    config: IngestionConfig,
    requested_by: str,
    scraper_type: str = "scheduled_ingestion",
) -> db_models.SportsScrapeRun:
    """Create a scrape run record for a scheduled ingestion."""
    run = db_models.SportsScrapeRun(
        scraper_type=scraper_type,
        league_id=league.id,
        season=config.season,
        season_type=config.season_type,
        start_date=_coerce_date(
            datetime.combine(config.start_date, datetime.min.time(), tzinfo=timezone.utc)
            if config.start_date
            else None
        ),
        end_date=_coerce_date(
            datetime.combine(config.end_date, datetime.min.time(), tzinfo=timezone.utc)
            if config.end_date
            else None
        ),
        status="pending",
        requested_by=requested_by,
        config=config.model_dump(mode="json"),
    )
    session.add(run)
    session.flush()
    return run


def schedule_ingestion_runs(
    *,
    leagues: Iterable[str] | None = None,
    requested_by: str = "scheduler",
    now: datetime | None = None,
) -> ScheduledIngestionSummary:
    """Create scheduled scrape runs and enqueue them for execution."""
    # Use SSOT if no leagues specified
    if leagues is None:
        leagues = get_scheduled_leagues()
    leagues = list(leagues)
    
    start_dt, end_dt = build_scheduled_window(now)
    start_date = start_dt.date()
    end_date = end_dt.date()
    cutoff = now_utc() - timedelta(minutes=14)
    runs_created = 0
    runs_skipped = 0
    run_failures = 0
    enqueue_failures = 0

    logger.info(
        "scheduled_ingestion_start",
        leagues=leagues,
        window_start=str(start_dt),
        window_end=str(end_dt),
    )

    with get_session() as session:
        for league_code in leagues:
            league = (
                session.query(db_models.SportsLeague)
                .filter(db_models.SportsLeague.code == league_code)
                .first()
            )
            if not league:
                logger.warning("scheduled_ingestion_unknown_league", league=league_code)
                runs_skipped += 1
                continue

            recent_run = (
                session.query(db_models.SportsScrapeRun)
                .filter(db_models.SportsScrapeRun.league_id == league.id)
                .filter(db_models.SportsScrapeRun.scraper_type == "scheduled_ingestion")
                .filter(db_models.SportsScrapeRun.created_at >= cutoff)
                .first()
            )
            if recent_run:
                logger.info(
                    "scheduled_ingestion_recent_run_skipped",
                    league=league_code,
                    run_id=recent_run.id,
                    created_at=str(recent_run.created_at),
                )
                runs_skipped += 1
                continue

            # Get per-league config from SSOT
            league_cfg = get_league_config(league_code)

            config = IngestionConfig(
                league_code=league_code,
                start_date=start_date,
                end_date=end_date,
                boxscores=league_cfg.boxscores_enabled,
                odds=league_cfg.odds_enabled,
                social=league_cfg.social_enabled,
                pbp=league_cfg.pbp_enabled,
                only_missing=False,
            )

            try:
                run = create_scrape_run(session, league, config, requested_by=requested_by)
                runs_created += 1
            except Exception as exc:
                run_failures += 1
                logger.exception(
                    "scheduled_ingestion_run_create_failed",
                    league=league_code,
                    error=str(exc),
                )
                continue

            try:
                from ..celery_app import app as celery_app

                async_result = celery_app.send_task(
                    "run_scrape_job",
                    args=[run.id, config.model_dump(mode="json")],
                    queue=DEFAULT_QUEUE,
                    routing_key=DEFAULT_QUEUE,
                )
                run.job_id = async_result.id
                logger.info(
                    "scheduled_ingestion_enqueued",
                    league=league_code,
                    run_id=run.id,
                    job_id=run.job_id,
                )
            except Exception as exc:
                run.status = "error"
                run.error_details = f"Failed to enqueue scheduled ingestion: {exc}"
                enqueue_failures += 1
                logger.exception(
                    "scheduled_ingestion_enqueue_failed",
                    league=league_code,
                    run_id=run.id,
                    error=str(exc),
                )

    summary = ScheduledIngestionSummary(
        runs_created=runs_created,
        runs_skipped=runs_skipped,
        run_failures=run_failures,
        enqueue_failures=enqueue_failures,
        last_run_at=now_utc(),
    )
    logger.info(
        "scheduled_ingestion_complete",
        runs_created=summary.runs_created,
        runs_skipped=summary.runs_skipped,
        run_failures=summary.run_failures,
        enqueue_failures=summary.enqueue_failures,
        last_run_at=str(summary.last_run_at),
    )

    # Note: Timeline generation is triggered at the END of each scrape job,
    # not here. See run_scrape_job task for the trigger.

    return summary


def run_pbp_ingestion_for_league(league_code: str) -> dict:
    """Run PBP ingestion for a single league.

    Called after stats ingestion completes to fetch play-by-play data.

    Args:
        league_code: The league to fetch PBP for (NBA, NHL, NCAAB)

    Returns:
        Dict with pbp_games and pbp_events counts
    """
    from .pbp_ingestion import ingest_pbp_via_nba_api, ingest_pbp_via_nhl_api, ingest_pbp_via_ncaab_api

    start_dt, end_dt = build_scheduled_window()
    start_date = start_dt.date()
    end_date = end_dt.date()

    logger.info(
        "pbp_ingestion_start",
        league=league_code,
        start_date=str(start_date),
        end_date=str(end_date),
    )

    pbp_games = 0
    pbp_events = 0

    with get_session() as session:
        if league_code == "NHL":
            # NHL uses dedicated NHL API
            games, events = ingest_pbp_via_nhl_api(
                session,
                run_id=0,  # No run_id for standalone PBP
                start_date=start_date,
                end_date=end_date,
                only_missing=True,  # Only fetch missing PBP
                updated_before=None,
            )
            pbp_games = games
            pbp_events = events
        elif league_code == "NCAAB":
            # NCAAB uses College Basketball Data API
            games, events = ingest_pbp_via_ncaab_api(
                session,
                run_id=0,
                start_date=start_date,
                end_date=end_date,
                only_missing=True,
                updated_before=None,
            )
            pbp_games = games
            pbp_events = events
        elif league_code == "NBA":
            # NBA uses official NBA API
            games, events = ingest_pbp_via_nba_api(
                session,
                run_id=0,
                start_date=start_date,
                end_date=end_date,
                only_missing=True,
                updated_before=None,
            )
            pbp_games = games
            pbp_events = events

        session.commit()

    logger.info(
        "pbp_ingestion_complete",
        league=league_code,
        pbp_games=pbp_games,
        pbp_events=pbp_events,
    )

    return {
        "league": league_code,
        "pbp_games": pbp_games,
        "pbp_events": pbp_events,
    }


def schedule_single_league_and_wait(
    league_code: str,
    timeout_seconds: int = 300,
    poll_interval: int = 5,
) -> dict:
    """Schedule ingestion for a single league and wait for completion.

    Args:
        league_code: The league to run (e.g., "NBA", "NHL")
        timeout_seconds: Maximum time to wait for completion (default 5 minutes)
        poll_interval: How often to check status (default 5 seconds)

    Returns:
        Dict with run status and summary
    """
    start_dt, end_dt = build_scheduled_window()
    start_date = start_dt.date()
    end_date = end_dt.date()

    with get_session() as session:
        league = (
            session.query(db_models.SportsLeague)
            .filter(db_models.SportsLeague.code == league_code)
            .first()
        )
        if not league:
            logger.warning("schedule_single_league_unknown", league=league_code)
            return {"runs_created": 0, "status": "skipped", "reason": "unknown_league"}

        league_cfg = get_league_config(league_code)

        config = IngestionConfig(
            league_code=league_code,
            start_date=start_date,
            end_date=end_date,
            boxscores=league_cfg.boxscores_enabled,
            odds=league_cfg.odds_enabled,
            social=league_cfg.social_enabled,
            pbp=False,  # PBP runs separately
            only_missing=False,
        )

        run = create_scrape_run(session, league, config, requested_by="scheduler_sequential")

        from ..celery_app import app as celery_app

        async_result = celery_app.send_task(
            "run_scrape_job",
            args=[run.id, config.model_dump(mode="json")],
            queue=DEFAULT_QUEUE,
            routing_key=DEFAULT_QUEUE,
        )
        run.job_id = async_result.id
        session.commit()

        # Store run_id before exiting session context to avoid DetachedInstanceError
        run_id = run.id

        logger.info(
            "schedule_single_league_enqueued",
            league=league_code,
            run_id=run_id,
            job_id=run.job_id,
        )

    # Poll for completion
    elapsed = 0
    while elapsed < timeout_seconds:
        time.sleep(poll_interval)
        elapsed += poll_interval

        with get_session() as session:
            run = session.query(db_models.SportsScrapeRun).get(run_id)
            if run.status in ("success", "completed", "failed", "error", "interrupted"):
                logger.info(
                    "schedule_single_league_finished",
                    league=league_code,
                    run_id=run.id,
                    status=run.status,
                    elapsed_seconds=elapsed,
                )
                return {
                    "runs_created": 1,
                    "status": run.status,
                    "run_id": run.id,
                    "elapsed_seconds": elapsed,
                }

    # Timeout
    logger.warning(
        "schedule_single_league_timeout",
        league=league_code,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
    )
    return {
        "runs_created": 1,
        "status": "timeout",
        "run_id": run_id,
        "elapsed_seconds": elapsed,
    }
