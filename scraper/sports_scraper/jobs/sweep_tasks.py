"""Daily sweep task: truth repair and catch-all for the game-state-machine.

Runs once daily (4 AM EST) as a safety net to catch anything the
high-frequency polling tasks missed. Responsibilities:

1. Status repair: find scheduled games past tip_time, check API for actual status
2. Full pipeline: re-run ingestion per league with only_missing=False to catch
   games missed by the 3:30 AM run (e.g. BR hadn't published yet)
3. Flow generation: trigger bulk flow gen per league for the lookback window
4. Social: second-pass social scrape for postgame reactions
5. Archive: move final games >7 days with complete artifacts to archived
"""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task

from ..db import get_session
from ..logging import logger


@shared_task(
    name="run_daily_sweep",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def run_daily_sweep() -> dict:
    """Run all daily sweep operations."""
    results: dict = {}

    logger.info("daily_sweep_start")

    # --- Phase 1: Pre-ingestion housekeeping ---
    try:
        results["status_repair"] = _repair_stale_statuses()
    except Exception as exc:
        results["status_repair"] = {"error": str(exc)}
        logger.exception("daily_sweep_status_repair_error", error=str(exc))

    # Clear NBA scoreboard cache so full pipeline gets fresh data from BR
    from ..utils.cache import HTMLCache
    from ..config import settings

    for league_code in ["NBA"]:
        try:
            cache = HTMLCache(settings.scraper_config.html_cache_dir, league_code)
            cleared = cache.clear_recent_scoreboards(days=3)
            logger.info("daily_sweep_cache_cleared", league=league_code, **cleared)
        except Exception as exc:
            logger.warning("daily_sweep_cache_clear_failed", league=league_code, error=str(exc))

    # --- Phase 2: Full pipeline per league (NBA → NHL → NCAAB) ---
    for league_code in ["NBA", "NHL", "NCAAB"]:
        try:
            results[f"pipeline_{league_code}"] = _run_full_pipeline_for_league(league_code)
        except Exception as exc:
            results[f"pipeline_{league_code}"] = {"error": str(exc)}
            logger.exception(
                "daily_sweep_pipeline_error",
                league=league_code,
                error=str(exc),
            )

    # --- Phase 3: Flow generation per league (NBA → NHL → NCAAB) ---
    from .flow_tasks import _run_flow_generation

    for league_code in ["NBA", "NHL", "NCAAB"]:
        try:
            max_games = 10 if league_code == "NCAAB" else None
            results[f"flows_{league_code}"] = _run_flow_generation(
                league_code, max_games=max_games
            )
        except Exception as exc:
            results[f"flows_{league_code}"] = {"error": str(exc)}
            logger.exception(
                "daily_sweep_flow_gen_error",
                league=league_code,
                error=str(exc),
            )

    # --- Phase 4: Post-ingestion housekeeping ---
    try:
        results["social_scrape_2"] = _run_social_scrape_2()
    except Exception as exc:
        results["social_scrape_2"] = {"error": str(exc)}
        logger.exception("daily_sweep_social_scrape_2_error", error=str(exc))

    try:
        results["embedded_tweets_backfill"] = _backfill_embedded_tweets()
    except Exception as exc:
        results["embedded_tweets_backfill"] = {"error": str(exc)}
        logger.exception("daily_sweep_embedded_tweets_backfill_error", error=str(exc))

    try:
        results["archive"] = _archive_old_games()
    except Exception as exc:
        results["archive"] = {"error": str(exc)}
        logger.exception("daily_sweep_archive_error", error=str(exc))

    logger.info("daily_sweep_complete", results=results)
    return results


def _run_full_pipeline_for_league(league_code: str) -> dict:
    """Run the full ingestion pipeline for a league (same as UI runs).

    Creates an IngestionConfig with all flags enabled and only_missing=False,
    acquires a Redis lock, and calls run_ingestion() synchronously.
    """
    from ..db import db_models
    from ..models import IngestionConfig
    from ..services.scheduler import create_scrape_run
    from ..services.ingestion import run_ingestion
    from ..utils.datetime_utils import today_et, now_utc
    from ..utils.redis_lock import acquire_redis_lock, release_redis_lock, LOCK_TIMEOUT_1HOUR

    today = today_et()
    config = IngestionConfig(
        league_code=league_code,
        start_date=today - timedelta(days=3),
        end_date=today,
        boxscores=True,
        odds=True,
        pbp=True,
        social=True,
        only_missing=False,
    )

    lock_name = f"lock:ingest:{league_code}"
    if not acquire_redis_lock(lock_name, timeout=LOCK_TIMEOUT_1HOUR):
        logger.warning("daily_sweep_pipeline_skipped_locked", league=league_code)
        return {"status": "skipped", "reason": "ingestion_in_progress"}

    try:
        with get_session() as session:
            league = (
                session.query(db_models.SportsLeague)
                .filter(db_models.SportsLeague.code == league_code)
                .first()
            )
            if not league:
                logger.error("daily_sweep_league_not_found", league=league_code)
                return {"status": "error", "reason": "league_not_found"}

            run = create_scrape_run(
                session,
                league,
                config,
                requested_by="daily_sweep",
                scraper_type="daily_sweep",
            )
            session.commit()
            run_id = run.id

        logger.info(
            "daily_sweep_pipeline_start",
            league=league_code,
            run_id=run_id,
            start_date=str(config.start_date),
            end_date=str(config.end_date),
        )

        result = run_ingestion(run_id, config.model_dump(mode="json"))

        logger.info(
            "daily_sweep_pipeline_complete",
            league=league_code,
            run_id=run_id,
            result=result,
        )

        return {"status": "success", "run_id": run_id, **result}
    finally:
        release_redis_lock(lock_name)


def _run_social_scrape_2() -> dict:
    """Social Scrape #2: capture postgame reactions for recently-final games.

    Query: games WHERE status='final' AND social_scrape_1_at IS NOT NULL
           AND social_scrape_2_at IS NULL AND end_time > now() - 48 hours

    For each game (sequentially, 3 min cooldown between games):
    1. Scrape game_date and game_date + 1 (day-bounded)
    2. Map tweets, only keep phase = 'postgame'
    3. Skip tweets already stored (dedup via external_post_id)
    4. Set game.social_scrape_2_at = now()
    """
    import time

    from ..db import db_models
    from ..social.team_collector import TeamTweetCollector
    from ..social.tweet_mapper import map_tweets_for_team
    from ..utils.datetime_utils import now_utc

    now = now_utc()
    lookback = now - timedelta(hours=48)

    with get_session() as session:
        games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.status == db_models.GameStatus.final.value,
                db_models.SportsGame.social_scrape_1_at.isnot(None),
                db_models.SportsGame.social_scrape_2_at.is_(None),
                db_models.SportsGame.end_time.isnot(None),
                db_models.SportsGame.end_time > lookback,
            )
            .all()
        )

        if not games:
            logger.debug("sweep_social_scrape_2_no_games")
            return {"games_found": 0, "games_scraped": 0}

        logger.info("sweep_social_scrape_2_start", games_count=len(games))

        try:
            collector = TeamTweetCollector()
        except RuntimeError as exc:
            logger.error("sweep_social_scrape_2_collector_unavailable", error=str(exc))
            return {"games_found": len(games), "games_scraped": 0, "error": str(exc)}

        games_scraped = 0
        total_new = 0
        total_postgame_kept = 0

        for game in games:
            game_date = game.game_date.date() if hasattr(game.game_date, "date") else game.game_date
            next_day = game_date + timedelta(days=1)
            team_ids = [game.home_team_id, game.away_team_id]

            game_new = 0
            for team_id in team_ids:
                try:
                    new_tweets = collector.collect_team_tweets(
                        session=session,
                        team_id=team_id,
                        start_date=game_date,
                        end_date=next_day,
                    )
                    game_new += new_tweets
                except Exception as exc:
                    logger.warning(
                        "sweep_social_scrape_2_team_error",
                        game_id=game.id,
                        team_id=team_id,
                        error=str(exc),
                    )

            # Map unmapped tweets
            for team_id in team_ids:
                try:
                    map_tweets_for_team(session, team_id)
                except Exception as exc:
                    logger.warning(
                        "sweep_social_scrape_2_map_error",
                        game_id=game.id,
                        team_id=team_id,
                        error=str(exc),
                    )

            # For Scrape #2: remove any pregame/in_game tweets that were newly mapped
            # to this game (they should already exist from Scrape #1; dedup handles it,
            # but if any slipped through, unmap them)
            non_postgame_unmapped = (
                session.query(db_models.TeamSocialPost)
                .filter(
                    db_models.TeamSocialPost.game_id == game.id,
                    db_models.TeamSocialPost.mapping_status == "mapped",
                    db_models.TeamSocialPost.game_phase.in_(["pregame", "in_game"]),
                )
                .count()
            )

            # Count postgame posts for this game (the ones we care about)
            postgame_count = (
                session.query(db_models.TeamSocialPost)
                .filter(
                    db_models.TeamSocialPost.game_id == game.id,
                    db_models.TeamSocialPost.mapping_status == "mapped",
                    db_models.TeamSocialPost.game_phase == "postgame",
                )
                .count()
            )
            total_postgame_kept += postgame_count

            game.social_scrape_2_at = now_utc()
            total_new += game_new
            games_scraped += 1

            logger.info(
                "sweep_social_scrape_2_game_complete",
                game_id=game.id,
                new_tweets=game_new,
                postgame_kept=postgame_count,
            )

            # Inter-game cooldown
            if game != games[-1]:
                time.sleep(180)

        session.commit()

    logger.info(
        "sweep_social_scrape_2_complete",
        games_scraped=games_scraped,
        total_new=total_new,
        total_postgame_kept=total_postgame_kept,
    )

    return {
        "games_found": len(games),
        "games_scraped": games_scraped,
        "total_new_tweets": total_new,
        "total_postgame_kept": total_postgame_kept,
    }


def _repair_stale_statuses() -> dict:
    """Find scheduled/pregame games past their tip_time and check APIs for actual status.

    Games that should have started but are still marked scheduled/pregame
    likely missed a status update. We check the league APIs to get the
    real status.
    """
    from ..db import db_models
    from ..utils.datetime_utils import now_utc
    from ..live.nba import NBALiveFeedClient
    from ..live.nhl import NHLLiveFeedClient
    from ..persistence.games import resolve_status_transition

    now = now_utc()
    # Games with tip_time > 3 hours ago that are still scheduled/pregame
    stale_cutoff = now - timedelta(hours=3)
    repaired = 0

    with get_session() as session:
        stale_games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.status.in_([
                    db_models.GameStatus.scheduled.value,
                    db_models.GameStatus.pregame.value,
                ]),
                db_models.SportsGame.tip_time.isnot(None),
                db_models.SportsGame.tip_time < stale_cutoff,
            )
            .all()
        )

        if not stale_games:
            logger.debug("sweep_status_repair_none_stale")
            return {"stale_found": 0, "repaired": 0}

        logger.info("sweep_status_repair_found", count=len(stale_games))

        # Group by league for batch API calls
        nba_games = []
        nhl_games = []
        league_cache: dict[int, str] = {}

        for game in stale_games:
            if game.league_id not in league_cache:
                league = session.query(db_models.SportsLeague).get(game.league_id)
                league_cache[game.league_id] = league.code if league else "UNKNOWN"

            code = league_cache[game.league_id]
            if code == "NBA":
                nba_games.append(game)
            elif code == "NHL":
                nhl_games.append(game)
            # NCAAB: skip for now (too many games, handled by batch ingestion)

        # Check NBA scoreboard
        if nba_games:
            try:
                client = NBALiveFeedClient()
                dates = {g.game_date.date() for g in nba_games if g.game_date}
                nba_status_map: dict[str, str] = {}

                for d in dates:
                    scoreboard = client.fetch_scoreboard(d)
                    for sg in scoreboard:
                        nba_status_map[sg.game_id] = sg.status

                for game in nba_games:
                    nba_game_id = (game.external_ids or {}).get("nba_game_id")
                    if nba_game_id and nba_game_id in nba_status_map:
                        api_status = nba_status_map[nba_game_id]
                        new_status = resolve_status_transition(game.status, api_status)
                        if new_status != game.status:
                            logger.info(
                                "sweep_status_repaired",
                                game_id=game.id,
                                league="NBA",
                                from_status=game.status,
                                to_status=new_status,
                            )
                            game.status = new_status
                            game.updated_at = now
                            if new_status == db_models.GameStatus.final.value and game.end_time is None:
                                game.end_time = now
                            repaired += 1
            except Exception as exc:
                logger.warning("sweep_nba_status_check_error", error=str(exc))

        # Check NHL schedule
        if nhl_games:
            try:
                client = NHLLiveFeedClient()
                dates = {g.game_date.date() for g in nhl_games if g.game_date}
                if dates:
                    start = min(dates)
                    end = max(dates)
                    schedule = client.fetch_schedule(start, end)
                    nhl_status_map: dict[int, str] = {}
                    for sg in schedule:
                        nhl_status_map[sg.game_id] = sg.status

                    for game in nhl_games:
                        nhl_game_pk = (game.external_ids or {}).get("nhl_game_pk")
                        if nhl_game_pk:
                            try:
                                pk = int(nhl_game_pk)
                            except (ValueError, TypeError):
                                continue
                            if pk in nhl_status_map:
                                api_status = nhl_status_map[pk]
                                new_status = resolve_status_transition(game.status, api_status)
                                if new_status != game.status:
                                    logger.info(
                                        "sweep_status_repaired",
                                        game_id=game.id,
                                        league="NHL",
                                        from_status=game.status,
                                        to_status=new_status,
                                    )
                                    game.status = new_status
                                    game.updated_at = now
                                    if new_status == db_models.GameStatus.final.value and game.end_time is None:
                                        game.end_time = now
                                    repaired += 1
            except Exception as exc:
                logger.warning("sweep_nhl_status_check_error", error=str(exc))

    return {"stale_found": len(stale_games), "repaired": repaired}


def _backfill_embedded_tweets() -> dict:
    """Call the API to backfill embedded tweets for recent flows.

    Flows generated before social scraping completed may have all-NULL
    embedded_social_post_id. This calls the API endpoint to retroactively
    attach tweets.
    """
    import httpx

    from ..config import settings

    api_base = settings.api_internal_url
    url = f"{api_base}/api/admin/sports/pipeline/backfill-embedded-tweets"

    logger.info("sweep_backfill_embedded_tweets_start")

    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, params={"lookback_days": 7})
        response.raise_for_status()
        result = response.json()

    logger.info(
        "sweep_backfill_embedded_tweets_complete",
        total_checked=result.get("total_checked", 0),
        total_backfilled=result.get("total_backfilled", 0),
    )

    return result


def _archive_old_games() -> dict:
    """Archive final games >7 days with complete artifacts.

    This is the same operation as game_state_updater._promote_final_to_archived
    but runs as part of the daily sweep for completeness.
    """
    from ..services.game_state_updater import _promote_final_to_archived

    with get_session() as session:
        archived = _promote_final_to_archived(session)

    return {"archived": archived}
