"""Diagnostics utilities for ingestion monitoring and guards."""

from __future__ import annotations

from datetime import timedelta
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..utils.datetime_utils import now_utc


PBP_SUPPORTED_LEAGUES = {"NBA", "NHL"}
PBP_MIN_PLAY_COUNT = 1
CONFLICT_OVERLAP_WINDOW_HOURS = 6
EXTERNAL_ID_KEYS: dict[str, str] = {
    "NBA": "nba_game_id",
    "NHL": "nhl_game_pk",
}


def detect_missing_pbp(
    session: Session,
    *,
    league_code: str,
    min_play_count: int = PBP_MIN_PLAY_COUNT,
) -> list[int]:
    """Record games missing PBP despite being live/final."""
    league = session.query(db_models.SportsLeague).filter(db_models.SportsLeague.code == league_code).first()
    if not league:
        return []

    live_status = db_models.GameStatus.live.value
    final_statuses = [db_models.GameStatus.final.value, db_models.GameStatus.completed.value]
    status_filter = [live_status, *final_statuses]
    reason = "not_supported" if league_code not in PBP_SUPPORTED_LEAGUES else "no_feed"
    now = now_utc()

    external_key = EXTERNAL_ID_KEYS.get(league_code)
    external_id_expr = (
        db_models.SportsGame.external_ids[external_key].astext if external_key else None
    )
    select_cols = [
        db_models.SportsGame.id,
        db_models.SportsGame.status,
        func.count(db_models.SportsGamePlay.id).label("play_count"),
    ]
    if external_id_expr is not None:
        select_cols.append(external_id_expr.label("external_id"))

    group_by_cols = [db_models.SportsGame.id]
    if external_id_expr is not None:
        group_by_cols.append(external_id_expr)

    rows = (
        session.query(*select_cols)
        .outerjoin(db_models.SportsGamePlay, db_models.SportsGamePlay.game_id == db_models.SportsGame.id)
        .filter(db_models.SportsGame.league_id == league.id)
        .filter(db_models.SportsGame.status.in_(status_filter))
        .group_by(*group_by_cols)
        .having(func.count(db_models.SportsGamePlay.id) < min_play_count)
        .all()
    )

    missing_ids: list[int] = []
    for row in rows:
        game_id = row[0]
        status = row[1]
        play_count = row[2]
        external_id = row[3] if len(row) > 3 else None
        missing_ids.append(int(game_id))
        stmt = (
            insert(db_models.SportsMissingPbp)
            .values(
                game_id=game_id,
                league_id=league.id,
                status=status,
                reason=reason,
                detected_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_missing_pbp_game",
                set_={
                    "status": status,
                    "reason": reason,
                    "updated_at": now,
                },
            )
        )
        session.execute(stmt)
        logger.warning(
            "pbp_missing_detected",
            league=league_code,
            game_id=game_id,
            external_id=external_id,
            status=status,
            play_count=int(play_count or 0),
            reason=reason,
        )

    if missing_ids:
        logger.info("pbp_missing_summary", league=league_code, missing_count=len(missing_ids))
        session.query(db_models.SportsMissingPbp).filter(
            db_models.SportsMissingPbp.league_id == league.id,
            ~db_models.SportsMissingPbp.game_id.in_(missing_ids),
        ).delete(synchronize_session=False)
    else:
        session.query(db_models.SportsMissingPbp).filter(
            db_models.SportsMissingPbp.league_id == league.id,
        ).delete(synchronize_session=False)
    return missing_ids


def detect_external_id_conflicts(
    session: Session,
    *,
    league_code: str,
    source: str | None = None,
) -> int:
    """Detect duplicate external IDs with overlapping start times or team mismatches."""
    league = session.query(db_models.SportsLeague).filter(db_models.SportsLeague.code == league_code).first()
    if not league:
        return 0

    external_key = EXTERNAL_ID_KEYS.get(league_code)
    if not external_key:
        return 0

    external_id_expr = db_models.SportsGame.external_ids[external_key].astext
    duplicate_ids = (
        session.query(external_id_expr.label("external_id"))
        .filter(db_models.SportsGame.league_id == league.id)
        .filter(external_id_expr.isnot(None))
        .group_by(external_id_expr)
        .having(func.count(db_models.SportsGame.id) > 1)
        .all()
    )

    overlap_window = timedelta(hours=CONFLICT_OVERLAP_WINDOW_HOURS)
    conflicts_created = 0
    source_value = source or external_key

    for (external_id,) in duplicate_ids:
        games = (
            session.query(db_models.SportsGame)
            .filter(db_models.SportsGame.league_id == league.id)
            .filter(external_id_expr == external_id)
            .all()
        )
        for idx, game in enumerate(games):
            for other in games[idx + 1 :]:
                start_delta = abs(game.game_date - other.game_date)
                overlapping_start = start_delta <= overlap_window
                team_mismatch = (game.home_team_id != other.home_team_id) or (game.away_team_id != other.away_team_id)
                if not (overlapping_start or team_mismatch):
                    continue

                # Conflict guard: record duplicate external IDs so snapshot APIs can exclude unsafe games.
                conflict_fields = {
                    "external_id_key": external_key,
                    "start_time_delta_minutes": int(start_delta.total_seconds() // 60),
                    "home_team_id": game.home_team_id,
                    "away_team_id": game.away_team_id,
                    "conflict_home_team_id": other.home_team_id,
                    "conflict_away_team_id": other.away_team_id,
                    "overlapping_start": overlapping_start,
                    "team_mismatch": team_mismatch,
                }
                stmt = (
                    insert(db_models.SportsGameConflict)
                    .values(
                        league_id=league.id,
                        game_id=game.id,
                        conflict_game_id=other.id,
                        external_id=external_id,
                        source=source_value,
                        conflict_fields=conflict_fields,
                    )
                    .on_conflict_do_nothing(constraint="uq_game_conflict")
                )
                result = session.execute(stmt)
                if result.rowcount:
                    conflicts_created += 1
                    logger.error(
                        "game_id_conflict_detected",
                        league=league_code,
                        game_id=game.id,
                        conflict_game_id=other.id,
                        external_id=external_id,
                        source=source_value,
                        conflict_fields=conflict_fields,
                    )

    if conflicts_created:
        logger.info(
            "game_id_conflict_summary",
            league=league_code,
            conflicts_created=conflicts_created,
            external_key=external_key,
        )
    return conflicts_created
