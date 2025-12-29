"""Play-by-play persistence helpers."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..models import NormalizedPlay


def _resolve_team_id(play: NormalizedPlay, game: db_models.SportsGame | None) -> int | None:
    """Best-effort mapping from play.team_abbreviation to game team ids."""
    if not play.team_abbreviation or not game:
        return None

    abbr = play.team_abbreviation.upper()
    try:
        if game.home_team and game.home_team.abbreviation and game.home_team.abbreviation.upper() == abbr:
            return game.home_team_id
        if game.away_team and game.away_team.abbreviation and game.away_team.abbreviation.upper() == abbr:
            return game.away_team_id
    except Exception:
        return None
    return None


def upsert_plays(session: Session, game_id: int, plays: Sequence[NormalizedPlay]) -> int:
    """Upsert play-by-play events for a game.
    
    Returns the number of plays processed (inserted or updated).
    """
    if not plays:
        return 0

    game = session.get(db_models.SportsGame, game_id)
    processed = 0

    for play in plays:
        team_id = _resolve_team_id(play, game)
        stmt = (
            insert(db_models.SportsGamePlay)
            .values(
                game_id=game_id,
                quarter=play.quarter,
                game_clock=play.game_clock,
                play_index=play.play_index,
                play_type=play.play_type,
                team_id=team_id,
                player_id=play.player_id,
                player_name=play.player_name,
                description=play.description,
                home_score=play.home_score,
                away_score=play.away_score,
                raw_data={**play.raw_data, "team_abbreviation": play.team_abbreviation},
            )
            .on_conflict_do_update(
                constraint="uq_game_play_index",
                set_={
                    "play_type": play.play_type,
                    "team_id": team_id,
                    "player_id": play.player_id,
                    "player_name": play.player_name,
                    "description": play.description,
                    "home_score": play.home_score,
                    "away_score": play.away_score,
                    "raw_data": {**play.raw_data, "team_abbreviation": play.team_abbreviation},
                },
            )
        )
        session.execute(stmt)
        processed += 1

    logger.info("pbp_plays_upserted", game_id=game_id, plays=processed)
    return processed



