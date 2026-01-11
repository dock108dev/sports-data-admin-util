"""Boxscore persistence helpers.

Handles team and player boxscore upserts.
"""

from __future__ import annotations

import json
from typing import Sequence

from sqlalchemy import cast, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from dataclasses import dataclass

from ..db import db_models
from ..logging import logger
from ..models import NormalizedGame, NormalizedPlayerBoxscore, NormalizedTeamBoxscore
from ..utils.db_queries import get_league_id
from ..utils.datetime_utils import now_utc
from .games import upsert_game
from .teams import _upsert_team


def _build_team_stats(payload: NormalizedTeamBoxscore) -> dict:
    """Build stats dict from typed fields + raw_stats, excluding None values."""
    stats = {}
    if payload.points is not None:
        stats["points"] = payload.points
    if payload.rebounds is not None:
        stats["rebounds"] = payload.rebounds
    if payload.assists is not None:
        stats["assists"] = payload.assists
    if payload.turnovers is not None:
        stats["turnovers"] = payload.turnovers
    if payload.passing_yards is not None:
        stats["passing_yards"] = payload.passing_yards
    if payload.rushing_yards is not None:
        stats["rushing_yards"] = payload.rushing_yards
    if payload.receiving_yards is not None:
        stats["receiving_yards"] = payload.receiving_yards
    if payload.hits is not None:
        stats["hits"] = payload.hits
    if payload.runs is not None:
        stats["runs"] = payload.runs
    if payload.errors is not None:
        stats["errors"] = payload.errors
    if payload.shots_on_goal is not None:
        stats["shots_on_goal"] = payload.shots_on_goal
    if payload.penalty_minutes is not None:
        stats["penalty_minutes"] = payload.penalty_minutes
    if payload.raw_stats:
        stats.update(payload.raw_stats)
    return stats


def _build_player_stats(payload: NormalizedPlayerBoxscore) -> dict:
    """Build stats dict from typed fields + raw_stats, excluding None values."""
    stats = {}
    if payload.minutes is not None:
        stats["minutes"] = payload.minutes
    if payload.points is not None:
        stats["points"] = payload.points
    if payload.rebounds is not None:
        stats["rebounds"] = payload.rebounds
    if payload.assists is not None:
        stats["assists"] = payload.assists
    if payload.yards is not None:
        stats["yards"] = payload.yards
    if payload.touchdowns is not None:
        stats["touchdowns"] = payload.touchdowns
    if payload.shots_on_goal is not None:
        stats["shots_on_goal"] = payload.shots_on_goal
    if payload.penalties is not None:
        stats["penalties"] = payload.penalties
    if payload.raw_stats:
        stats.update(payload.raw_stats)
    return stats


def upsert_team_boxscores(session: Session, game_id: int, payloads: Sequence[NormalizedTeamBoxscore]) -> None:
    """Upsert team boxscores for a game."""
    updated = False
    for payload in payloads:
        league_id = get_league_id(session, payload.team.league_code)
        team_id = _upsert_team(session, league_id, payload.team)
        stats = _build_team_stats(payload)
        # psycopg3 requires explicit JSONB casting for dicts in raw SQL
        stats_json = cast(text(f"'{json.dumps(stats)}'"), JSONB)
        stmt = insert(db_models.SportsTeamBoxscore).values(
            game_id=game_id,
            team_id=team_id,
            is_home=payload.is_home,
            raw_stats_json=stats,
            source="sports_reference",
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_team_boxscore_game_team",
            set_={
                "raw_stats_json": stats_json,
                "updated_at": now_utc(),
            },
            where=stmt.excluded.raw_stats_json.is_distinct_from(db_models.SportsTeamBoxscore.stats),
        )
        result = session.execute(stmt)
        if result.rowcount:
            updated = True
    if updated:
        session.query(db_models.SportsGame).filter(db_models.SportsGame.id == game_id).update(
            {db_models.SportsGame.last_ingested_at: now_utc()}
        )


def upsert_player_boxscores(session: Session, game_id: int, payloads: Sequence[NormalizedPlayerBoxscore]) -> None:
    """Upsert player boxscores for a game.
    
    Handles errors per player and logs summary statistics.
    """
    if not payloads:
        return
    
    inserted_count = 0
    error_count = 0
    
    updated = False
    for payload in payloads:
        try:
            league_id = get_league_id(session, payload.team.league_code)
            team_id = _upsert_team(session, league_id, payload.team)
            stats = _build_player_stats(payload)
            # psycopg3 requires explicit JSONB casting for dicts in raw SQL
            stats_json = cast(text(f"'{json.dumps(stats)}'"), JSONB)
            stmt = insert(db_models.SportsPlayerBoxscore).values(
                game_id=game_id,
                team_id=team_id,
                player_external_ref=payload.player_id,
                player_name=payload.player_name,
                raw_stats_json=stats,
                source="sports_reference",
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_player_boxscore_identity",
                set_={
                    "raw_stats_json": stats_json,
                    "updated_at": now_utc(),
                },
                where=stmt.excluded.raw_stats_json.is_distinct_from(db_models.SportsPlayerBoxscore.stats),
            )
            result = session.execute(stmt)
            if result.rowcount:
                updated = True
            inserted_count += 1
        except Exception as exc:
            logger.error(
                "player_boxscore_upsert_failed",
                game_id=game_id,
                player_name=payload.player_name,
                error=str(exc),
                exc_info=True,
            )
            error_count += 1
    
    logger.info(
        "player_boxscores_upsert_complete",
        game_id=game_id,
        inserted_count=inserted_count,
        error_count=error_count,
    )
    if updated:
        session.query(db_models.SportsGame).filter(db_models.SportsGame.id == game_id).update(
            {db_models.SportsGame.last_ingested_at: now_utc()}
        )


@dataclass(frozen=True)
class GamePersistResult:
    game_id: int
    created: bool


def persist_game_payload(session: Session, payload: NormalizedGame) -> GamePersistResult:
    """Persist a complete game payload including game, team boxscores, and player boxscores.
    
    Returns the game ID and creation status.
    """
    game_id, created = upsert_game(session, payload)
    upsert_team_boxscores(session, game_id, payload.team_boxscores)
    
    logger.info(
        "persist_game_payload",
        game_id=game_id,
        game_key=payload.identity.source_game_key,
        team_boxscores_count=len(payload.team_boxscores),
        player_boxscores_count=len(payload.player_boxscores) if payload.player_boxscores else 0,
    )
    
    if payload.player_boxscores:
        try:
            logger.info("persisting_player_boxscores", game_id=game_id, count=len(payload.player_boxscores))
            upsert_player_boxscores(session, game_id, payload.player_boxscores)
        except Exception as exc:
            logger.error(
                "failed_to_persist_player_boxscores_for_game",
                game_id=game_id,
                game_key=payload.identity.source_game_key,
                error=str(exc),
                exc_info=True,
            )
    else:
        logger.warning("no_player_boxscores_to_persist", game_id=game_id, game_key=payload.identity.source_game_key)
    
    return GamePersistResult(game_id=game_id, created=created)
