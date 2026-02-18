"""Unified odds synchronization task.

Single Celery task that owns all odds ingestion: mainline + props for all
odds-enabled leagues.  Runs every 5 minutes in production, replacing the
previous trio of ``run_scheduled_odds_sync``, ``poll_active_odds``, and
``run_scheduled_props_sync``.
"""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from sqlalchemy import select

from ..config_sports import get_odds_enabled_leagues, validate_league_code
from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..odds.synchronizer import OddsSynchronizer
from ..utils.datetime_utils import today_et
from ..utils.redis_lock import (
    LOCK_TIMEOUT_5MIN,
    acquire_redis_lock,
    release_redis_lock,
)


@shared_task(
    name="sync_all_odds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def sync_all_odds(league_code: str | None = None) -> dict:
    """Unified odds pipeline: mainline + props for all odds-enabled leagues.

    Args:
        league_code: Optional single league to sync (e.g. ``"NBA"``).
                     When *None*, syncs every odds-enabled league.

    Returns:
        Summary dict with per-league counts.
    """
    if not acquire_redis_lock("lock:sync_all_odds", timeout=LOCK_TIMEOUT_5MIN):
        logger.debug("sync_all_odds_skipped_locked")
        return {"skipped": True, "reason": "locked"}

    try:
        if league_code is not None:
            validate_league_code(league_code)
            leagues = [league_code]
        else:
            leagues = get_odds_enabled_leagues()

        today = today_et()
        end = today + timedelta(days=1)

        sync = OddsSynchronizer()
        results: dict[str, dict] = {}
        total_odds = 0
        total_props = 0

        logger.info(
            "sync_all_odds_start",
            leagues=leagues,
            start_date=str(today),
            end_date=str(end),
        )

        for lc in leagues:
            league_result: dict[str, int | str] = {
                "odds_count": 0,
                "props_count": 0,
                "status": "success",
            }

            # --- Mainline odds (today + 1 day) ---
            try:
                config = IngestionConfig(
                    league_code=lc,
                    start_date=today,
                    end_date=end,
                    odds=True,
                    boxscores=False,
                    social=False,
                    pbp=False,
                )
                odds_count = sync.sync(config)
                league_result["odds_count"] = odds_count
                total_odds += odds_count
                logger.info(
                    "sync_all_odds_mainline_complete",
                    league=lc,
                    odds_count=odds_count,
                )
            except Exception as exc:
                league_result["status"] = "error"
                league_result["error"] = str(exc)
                logger.exception(
                    "sync_all_odds_mainline_failed",
                    league=lc,
                    error=str(exc),
                )
                results[lc] = league_result
                continue  # skip props if mainline failed

            # --- Props for pregame games with event IDs ---
            try:
                with get_session() as session:
                    stmt = (
                        select(db_models.SportsGame)
                        .join(db_models.SportsLeague)
                        .where(
                            db_models.SportsLeague.code == lc,
                            db_models.SportsGame.status.in_(["scheduled", "pregame"]),
                            db_models.SportsGame.external_ids["odds_api_event_id"].astext.isnot(None),
                        )
                    )
                    games = session.execute(stmt).scalars().all()

                    event_ids = [
                        g.external_ids["odds_api_event_id"]
                        for g in games
                        if g.external_ids.get("odds_api_event_id")
                    ]

                if event_ids:
                    props_count = sync.sync_props(lc, event_ids)
                    league_result["props_count"] = props_count
                    league_result["events"] = len(event_ids)
                    total_props += props_count
                    logger.info(
                        "sync_all_odds_props_complete",
                        league=lc,
                        props_count=props_count,
                        events=len(event_ids),
                    )
                else:
                    logger.info("sync_all_odds_props_no_events", league=lc)
            except Exception as exc:
                league_result["props_status"] = "error"
                league_result["props_error"] = str(exc)
                logger.exception(
                    "sync_all_odds_props_failed",
                    league=lc,
                    error=str(exc),
                )

            results[lc] = league_result

        logger.info(
            "sync_all_odds_complete",
            total_odds=total_odds,
            total_props=total_props,
            results=results,
        )

        return {
            "leagues": results,
            "total_odds": total_odds,
            "total_props": total_props,
        }

    finally:
        release_redis_lock("lock:sync_all_odds")
