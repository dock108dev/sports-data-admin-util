"""Game state updater: promote games through lifecycle states.

Pure DB operations — no external API calls. Designed to run every 3 minutes
via Celery beat. State transitions:

- scheduled → pregame: when now() >= tip_time - pregame_window_hours
- scheduled/pregame → final: when tip_time + estimated_game_duration_hours
  + postgame_window_hours < now() (stale timeout safety net)
- final → archived: when game has timeline artifacts AND end_time < now() - 7 days

The live → final transition is NOT handled here — it comes from API responses
in the PBP polling task when the data source reports the game as finished.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import exists
from sqlalchemy.orm import Session

from ..config_sports import LEAGUE_CONFIG
from ..db import db_models
from ..logging import logger
from ..utils.datetime_utils import now_utc

# How many days after final before archiving
_ARCHIVE_AFTER_DAYS = 7


def update_game_states(session: Session) -> dict[str, int]:
    """Run all state promotions. Returns counts of transitions made.

    This function is idempotent and safe to call at any frequency.
    Every transition is logged individually for traceability.
    """
    counts: dict[str, int] = {
        "scheduled_to_pregame": 0,
        "stale_to_final": 0,
        "final_to_archived": 0,
    }

    counts["scheduled_to_pregame"] = _promote_scheduled_to_pregame(session)
    counts["stale_to_final"] = _promote_stale_to_final(session)
    counts["final_to_archived"] = _promote_final_to_archived(session)

    total = sum(counts.values())
    if total > 0:
        logger.info("game_state_updater_transitions", **counts, total=total)
    else:
        logger.debug("game_state_updater_no_transitions")

    return counts


def _promote_scheduled_to_pregame(session: Session) -> int:
    """Promote scheduled games to pregame when within the pregame window.

    Uses per-league pregame_window_hours from config. Games without tip_time
    are skipped (can't compute pregame window without a start time).
    """
    now = now_utc()
    promoted = 0

    # Group by league to apply per-league pregame windows
    for league_code, config in LEAGUE_CONFIG.items():
        cutoff = now + timedelta(hours=config.pregame_window_hours)

        league_id = (
            session.query(db_models.SportsLeague.id)
            .filter(db_models.SportsLeague.code == league_code)
            .scalar()
        )
        if league_id is None:
            continue

        games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.league_id == league_id,
                db_models.SportsGame.status == db_models.GameStatus.scheduled.value,
                db_models.SportsGame.tip_time.isnot(None),
                db_models.SportsGame.tip_time <= cutoff,
            )
            .all()
        )

        for game in games:
            game.status = db_models.GameStatus.pregame.value
            game.updated_at = now
            promoted += 1
            logger.info(
                "game_state_transition",
                game_id=game.id,
                league=league_code,
                from_status="scheduled",
                to_status="pregame",
                tip_time=str(game.tip_time),
            )

    return promoted


def _promote_stale_to_final(session: Session) -> int:
    """Force overdue pregame/scheduled games to final.

    Safety net for when APIs fail to report correct status.
    Uses per-league estimated_game_duration_hours + postgame_window_hours
    as the maximum time a game can remain in pregame before we infer it's over.
    """
    now = now_utc()
    promoted = 0

    for league_code, config in LEAGUE_CONFIG.items():
        max_hours = config.estimated_game_duration_hours + config.postgame_window_hours
        stale_cutoff = now - timedelta(hours=max_hours)

        league_id = (
            session.query(db_models.SportsLeague.id)
            .filter(db_models.SportsLeague.code == league_code)
            .scalar()
        )
        if league_id is None:
            continue

        games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.league_id == league_id,
                db_models.SportsGame.status.in_([
                    db_models.GameStatus.scheduled.value,
                    db_models.GameStatus.pregame.value,
                ]),
                db_models.SportsGame.tip_time.isnot(None),
                db_models.SportsGame.tip_time < stale_cutoff,
            )
            .all()
        )

        for game in games:
            old_status = game.status
            game.status = db_models.GameStatus.final.value
            game.end_time = game.tip_time + timedelta(
                hours=config.estimated_game_duration_hours
            )
            game.updated_at = now
            promoted += 1
            logger.info(
                "game_state_transition",
                game_id=game.id,
                league=league_code,
                from_status=old_status,
                to_status="final",
                tip_time=str(game.tip_time),
                reason="stale_timeout",
            )

    return promoted


def _promote_final_to_archived(session: Session) -> int:
    """Archive final games that are complete and old enough.

    Criteria:
    - status = 'final'
    - end_time is set and > ARCHIVE_AFTER_DAYS days ago
    - Has at least one timeline artifact (flows generated)
    """
    now = now_utc()
    archive_cutoff = now - timedelta(days=_ARCHIVE_AFTER_DAYS)
    promoted = 0

    # Subquery: games with timeline artifacts
    has_artifacts = (
        exists()
        .where(
            db_models.SportsGameTimelineArtifact.game_id == db_models.SportsGame.id
        )
    )

    games = (
        session.query(db_models.SportsGame)
        .filter(
            db_models.SportsGame.status == db_models.GameStatus.final.value,
            db_models.SportsGame.end_time.isnot(None),
            db_models.SportsGame.end_time < archive_cutoff,
            has_artifacts,
            db_models.SportsGame.social_scrape_2_at.isnot(None),
        )
        .all()
    )

    for game in games:
        game.status = db_models.GameStatus.archived.value
        game.closed_at = now
        game.updated_at = now
        promoted += 1
        logger.info(
            "game_state_transition",
            game_id=game.id,
            from_status="final",
            to_status="archived",
            end_time=str(game.end_time),
        )

    return promoted
