"""Play-by-play persistence utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from sqlalchemy.dialects.postgresql import insert

from ..db import db_models
from ..logging import logger
from ..utils.datetime_utils import utcnow

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..models import NormalizedPlay


def upsert_plays(session: Session, game_id: int, plays: Sequence[NormalizedPlay]) -> int:
    """
    Insert play-by-play events for a game.

    Uses PostgreSQL ON CONFLICT DO NOTHING to append new plays without overwriting.

    Args:
        session: Database session
        game_id: ID of the game
        plays: List of normalized play events

    Returns:
        Number of plays inserted
    """
    if not plays:
        return 0

    # Get the game to look up team IDs
    game = session.query(db_models.SportsGame).filter(
        db_models.SportsGame.id == game_id
    ).first()

    if not game:
        logger.warning("upsert_plays_game_not_found", game_id=game_id)
        return 0

    # Build team abbreviation to ID mapping
    team_map: dict[str, int] = {}
    if game.home_team:
        team_map[game.home_team.abbreviation.upper()] = game.home_team.id
    if game.away_team:
        team_map[game.away_team.abbreviation.upper()] = game.away_team.id

    upserted = 0
    for play in plays:
        # Resolve team_id from abbreviation
        team_id = None
        if play.team_abbreviation:
            team_id = team_map.get(play.team_abbreviation.upper())

        stmt = (
            insert(db_models.SportsGamePlay)
            .values(
                game_id=game_id,
                play_index=play.play_index,
                quarter=play.quarter,
                game_clock=play.game_clock,
                play_type=play.play_type,
                team_id=team_id,
                player_id=play.player_id,
                player_name=play.player_name,
                description=play.description,
                home_score=play.home_score,
                away_score=play.away_score,
                raw_data=play.raw_data,
                updated_at=utcnow(),
            )
            .on_conflict_do_nothing(
                index_elements=["game_id", "play_index"],
            )
        )
        result = session.execute(stmt)
        if result.rowcount:
            upserted += result.rowcount

    logger.info("plays_upserted", game_id=game_id, count=upserted)
    if upserted:
        game.last_pbp_at = utcnow()
        session.flush()
    return upserted
