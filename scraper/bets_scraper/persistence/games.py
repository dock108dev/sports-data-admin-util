"""Game persistence helpers."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, literal_column
from sqlalchemy.orm import Session

from ..db import db_models
from ..models import NormalizedGame
from ..utils.db_queries import get_league_id
from ..utils.datetime_utils import utcnow
from .teams import _upsert_team


def _normalize_status(status: str | None) -> str:
    if not status:
        return db_models.GameStatus.scheduled.value
    status_normalized = status.lower()
    if status_normalized in {"final", "completed"}:
        return db_models.GameStatus.final.value
    if status_normalized == db_models.GameStatus.live.value:
        return db_models.GameStatus.live.value
    if status_normalized == db_models.GameStatus.scheduled.value:
        return db_models.GameStatus.scheduled.value
    return db_models.GameStatus.scheduled.value


def upsert_game(session: Session, normalized: NormalizedGame) -> tuple[int, bool]:
    """Upsert a game, creating or updating as needed.

    Returns the game ID and whether it was newly created.
    """
    league_id = get_league_id(session, normalized.identity.league_code)
    home_team_id = _upsert_team(session, league_id, normalized.identity.home_team)
    away_team_id = _upsert_team(session, league_id, normalized.identity.away_team)
    normalized_status = _normalize_status(normalized.status)
    end_time_value = utcnow() if normalized_status == db_models.GameStatus.final.value else None

    conflict_updates = {
        "home_score": normalized.home_score,
        "away_score": normalized.away_score,
        "status": normalized_status,
        "venue": normalized.venue,
        "scrape_version": db_models.SportsGame.scrape_version + 1,
        "last_scraped_at": utcnow(),
        "updated_at": utcnow(),
        "end_time": func.coalesce(
            db_models.SportsGame.end_time,
            end_time_value,
        )
        if end_time_value
        else db_models.SportsGame.end_time,
        # Only set source_game_key if the existing row doesn't have one; avoid clobber.
        "source_game_key": func.coalesce(db_models.SportsGame.source_game_key, normalized.identity.source_game_key),
    }

    base_stmt = insert(db_models.SportsGame).values(
        league_id=league_id,
        season=normalized.identity.season,
        season_type=normalized.identity.season_type,
        game_date=normalized.identity.game_date,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_score=normalized.home_score,
        away_score=normalized.away_score,
        venue=normalized.venue,
        status=normalized_status,
        end_time=end_time_value,
        source_game_key=normalized.identity.source_game_key,
        scrape_version=1,
        last_scraped_at=utcnow(),
        external_ids={},
    )

    # Prefer identity constraint to avoid duplicate-key violations when the same game is seen
    # under a different source_game_key.
    stmt = base_stmt.on_conflict_do_update(
        constraint="uq_game_identity",
        set_=conflict_updates,
    )

    stmt = stmt.returning(
        db_models.SportsGame.id,
        (literal_column("xmax") == 0).label("inserted"),
    )
    result = session.execute(stmt).first()
    if not result:
        raise RuntimeError("Failed to upsert game")
    game_id, inserted = result
    # Idempotent upsert: game_date is immutable, and end_time only set on final status.
    return int(game_id), bool(inserted)
