"""Odds synchronization tasks.

Two Celery tasks split by update frequency:

- ``sync_mainline_odds`` — mainline odds (spreads, totals, moneyline) every 15 min
- ``sync_prop_odds`` — player/team props every 60 min

Both tasks skip execution during the 3–7 AM ET quiet window (no games in
progress, saves API credits).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from sqlalchemy import select

from ..config_sports import get_odds_enabled_leagues, validate_league_code
from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..odds.synchronizer import OddsSynchronizer
from ..utils.datetime_utils import today_et
from ..utils.redis_lock import (
    LOCK_TIMEOUT_1HOUR,
    LOCK_TIMEOUT_10MIN,
    acquire_redis_lock,
    release_redis_lock,
)

EASTERN = ZoneInfo("America/New_York")

# Quiet window: no odds sync between 3:00 AM and 7:00 AM ET
_QUIET_START_HOUR = 3
_QUIET_END_HOUR = 7


def _in_quiet_window() -> bool:
    """Return True if the current ET hour falls in the 3–7 AM quiet window."""
    now_et = datetime.now(EASTERN)
    return _QUIET_START_HOUR <= now_et.hour < _QUIET_END_HOUR


# ---------------------------------------------------------------------------
# Mainline odds — every 15 minutes
# ---------------------------------------------------------------------------

@shared_task(
    name="sync_mainline_odds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def sync_mainline_odds(league_code: str | None = None) -> dict:
    """Sync mainline odds (spreads, totals, moneyline) for all leagues.

    Runs every 15 minutes.  Skips during the 3–7 AM ET quiet window.
    """
    if _in_quiet_window():
        logger.debug("sync_mainline_odds_quiet_window")
        return {"skipped": True, "reason": "quiet_window"}

    if not acquire_redis_lock("lock:sync_mainline_odds", timeout=LOCK_TIMEOUT_10MIN):
        logger.debug("sync_mainline_odds_skipped_locked")
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

        logger.info(
            "sync_mainline_odds_start",
            leagues=leagues,
            start_date=str(today),
            end_date=str(end),
        )

        for lc in leagues:
            league_result: dict[str, int | str] = {
                "odds_count": 0,
                "status": "success",
            }

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
                    "sync_mainline_odds_league_complete",
                    league=lc,
                    odds_count=odds_count,
                )
            except Exception as exc:
                league_result["status"] = "error"
                league_result["error"] = str(exc)
                logger.exception(
                    "sync_mainline_odds_league_failed",
                    league=lc,
                    error=str(exc),
                )

            results[lc] = league_result

        logger.info(
            "sync_mainline_odds_complete",
            total_odds=total_odds,
            results=results,
        )

        return {
            "leagues": results,
            "total_odds": total_odds,
        }

    finally:
        release_redis_lock("lock:sync_mainline_odds")


# ---------------------------------------------------------------------------
# Prop odds — every 60 minutes
# ---------------------------------------------------------------------------

@shared_task(
    name="sync_prop_odds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def sync_prop_odds(league_code: str | None = None) -> dict:
    """Sync prop odds for pregame events across all leagues.

    Runs every 60 minutes.  Skips during the 3–7 AM ET quiet window.
    """
    if _in_quiet_window():
        logger.debug("sync_prop_odds_quiet_window")
        return {"skipped": True, "reason": "quiet_window"}

    if not acquire_redis_lock("lock:sync_prop_odds", timeout=LOCK_TIMEOUT_1HOUR):
        logger.debug("sync_prop_odds_skipped_locked")
        return {"skipped": True, "reason": "locked"}

    try:
        if league_code is not None:
            validate_league_code(league_code)
            leagues = [league_code]
        else:
            leagues = get_odds_enabled_leagues()

        sync = OddsSynchronizer()
        results: dict[str, dict] = {}
        total_props = 0

        logger.info("sync_prop_odds_start", leagues=leagues)

        for lc in leagues:
            league_result: dict[str, int | str] = {
                "props_count": 0,
                "status": "success",
            }

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
                        "sync_prop_odds_league_complete",
                        league=lc,
                        props_count=props_count,
                        events=len(event_ids),
                    )
                else:
                    logger.info("sync_prop_odds_no_events", league=lc)
            except Exception as exc:
                league_result["status"] = "error"
                league_result["error"] = str(exc)
                logger.exception(
                    "sync_prop_odds_league_failed",
                    league=lc,
                    error=str(exc),
                )

            results[lc] = league_result

        logger.info(
            "sync_prop_odds_complete",
            total_props=total_props,
            results=results,
        )

        return {
            "leagues": results,
            "total_props": total_props,
        }

    finally:
        release_redis_lock("lock:sync_prop_odds")
