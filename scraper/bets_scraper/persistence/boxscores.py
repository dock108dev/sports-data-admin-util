"""Boxscore persistence helpers.

Handles team and player boxscore upserts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import cast, Date, literal
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from dataclasses import dataclass

from ..db import db_models
from ..logging import logger
from ..models import NormalizedGame, NormalizedPlayerBoxscore, NormalizedTeamBoxscore
from ..utils.db_queries import get_league_id
from ..utils.datetime_utils import now_utc
from .games import _normalize_status, resolve_status_transition
from .teams import _find_team_by_name, _upsert_team


def _validate_nhl_player_boxscore(payload: NormalizedPlayerBoxscore, game_id: int) -> str | None:
    """Validate NHL player boxscore before insertion.

    Returns None if valid, or a rejection reason string if invalid.
    Logs rejected rows with game_id, team, role, and reason.
    """
    # Only apply NHL-specific validation for NHL
    if payload.team.league_code != "NHL":
        return None

    team_name = payload.team.name or payload.team.abbreviation or "unknown"

    # Check: player name is required
    if not payload.player_name or not payload.player_name.strip():
        reason = "missing_player_name"
        logger.warning(
            "nhl_player_boxscore_rejected",
            game_id=game_id,
            team=team_name,
            role=payload.player_role,
            reason=reason,
            player_id=payload.player_id,
        )
        return reason

    # Check: player role is required for NHL
    if not payload.player_role:
        reason = "missing_player_role"
        logger.warning(
            "nhl_player_boxscore_rejected",
            game_id=game_id,
            team=team_name,
            role=None,
            reason=reason,
            player_name=payload.player_name,
        )
        return reason

    # Check: at least one stat field must be non-null (don't fabricate zeroes)
    # Check role-specific stats based on player_role
    if payload.player_role == "skater":
        has_stats = any([
            payload.minutes is not None,
            payload.goals is not None,
            payload.assists is not None,
            payload.points is not None,
            payload.shots_on_goal is not None,
        ])
    elif payload.player_role == "goalie":
        has_stats = any([
            payload.minutes is not None,
            payload.saves is not None,
            payload.goals_against is not None,
            payload.shots_against is not None,
            payload.save_percentage is not None,
        ])
    else:
        # Unknown role - should not happen due to earlier validation
        has_stats = False

    if not has_stats:
        reason = "all_stats_null"
        logger.warning(
            "nhl_player_boxscore_rejected",
            game_id=game_id,
            team=team_name,
            role=payload.player_role,
            reason=reason,
            player_name=payload.player_name,
        )
        return reason

    return None  # Valid


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
    # Common fields
    if payload.player_role is not None:
        stats["player_role"] = payload.player_role
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
    # NHL skater stats
    if payload.shots_on_goal is not None:
        stats["shots_on_goal"] = payload.shots_on_goal
    if payload.penalties is not None:
        stats["penalties"] = payload.penalties
    if payload.goals is not None:
        stats["goals"] = payload.goals
    # NHL goalie stats
    if payload.saves is not None:
        stats["saves"] = payload.saves
    if payload.goals_against is not None:
        stats["goals_against"] = payload.goals_against
    if payload.shots_against is not None:
        stats["shots_against"] = payload.shots_against
    if payload.save_percentage is not None:
        stats["save_percentage"] = payload.save_percentage
    # Raw stats (includes any additional fields)
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
        # Use literal() for proper parameter binding (avoids SQL injection with apostrophes)
        stats_json = literal(stats, type_=JSONB)
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


def upsert_player_boxscores(
    session: Session, game_id: int, payloads: Sequence[NormalizedPlayerBoxscore]
) -> PlayerBoxscoreStats:
    """Upsert player boxscores for a game.

    Handles errors per player and logs summary statistics.
    NHL rows are validated before insertion - invalid rows are rejected and logged.

    Returns:
        PlayerBoxscoreStats with counts of inserted, rejected, and errored players.
    """
    if not payloads:
        return PlayerBoxscoreStats()

    inserted_count = 0
    rejected_count = 0
    error_count = 0

    updated = False
    for payload in payloads:
        # Pre-insert validation for NHL (rejects broken rows before DB)
        rejection_reason = _validate_nhl_player_boxscore(payload, game_id)
        if rejection_reason:
            rejected_count += 1
            continue  # Skip invalid row

        try:
            league_id = get_league_id(session, payload.team.league_code)
            team_id = _upsert_team(session, league_id, payload.team)
            stats = _build_player_stats(payload)
            # Use literal() for proper parameter binding (avoids SQL injection with apostrophes)
            stats_json = literal(stats, type_=JSONB)
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
        rejected_count=rejected_count,
        error_count=error_count,
    )
    if updated:
        session.query(db_models.SportsGame).filter(db_models.SportsGame.id == game_id).update(
            {db_models.SportsGame.last_ingested_at: now_utc()}
        )

    return PlayerBoxscoreStats(
        inserted=inserted_count,
        rejected=rejected_count,
        errors=error_count,
    )


@dataclass(frozen=True)
class PlayerBoxscoreStats:
    """Statistics from player boxscore upsert operation."""
    inserted: int = 0
    rejected: int = 0
    errors: int = 0

    @property
    def total_processed(self) -> int:
        return self.inserted + self.rejected + self.errors


@dataclass(frozen=True)
class GamePersistResult:
    """Result of boxscore persistence (enrichment-only model).

    Boxscores enrich existing games; they never create new game records.
    Games are created exclusively by Odds API during schedule sync.
    """
    game_id: int | None
    enriched: bool = False
    player_stats: PlayerBoxscoreStats | None = None

    @property
    def has_player_stats(self) -> bool:
        """Returns True if player stats were successfully upserted."""
        return self.player_stats is not None and self.player_stats.inserted > 0


def _find_game_for_boxscore(
    session: Session,
    league_id: int,
    home_team_id: int,
    away_team_id: int,
    game_date: datetime,
) -> db_models.SportsGame | None:
    """Find an existing game by identity (league, teams, date).

    Uses DATE-only matching to handle different time sources (Odds API vs Sports Reference).
    """
    game_date_only = game_date.date()
    return (
        session.query(db_models.SportsGame)
        .filter(db_models.SportsGame.league_id == league_id)
        .filter(db_models.SportsGame.home_team_id == home_team_id)
        .filter(db_models.SportsGame.away_team_id == away_team_id)
        .filter(cast(db_models.SportsGame.game_date, Date) == game_date_only)
        .first()
    )


def _enrich_game_with_boxscore(
    session: Session,
    game: db_models.SportsGame,
    payload: NormalizedGame,
) -> bool:
    """Update an existing game with boxscore data. Returns True if game was updated.

    This enriches a pregame placeholder with final game data:
    - Sets scores, venue, source_game_key
    - Transitions status from scheduled to final
    """
    updated = False

    # Update scores
    if payload.home_score is not None and payload.home_score != game.home_score:
        game.home_score = payload.home_score
        updated = True
    if payload.away_score is not None and payload.away_score != game.away_score:
        game.away_score = payload.away_score
        updated = True

    # Update venue if provided
    if payload.venue and payload.venue != game.venue:
        game.venue = payload.venue
        updated = True

    # Set source_game_key if not already set (important for PBP lookup)
    if payload.identity.source_game_key and not game.source_game_key:
        game.source_game_key = payload.identity.source_game_key
        updated = True

    # Transition status (scheduled → final) with protection against regression
    normalized_status = _normalize_status(payload.status)
    new_status = resolve_status_transition(game.status, normalized_status)
    if new_status != game.status:
        game.status = new_status
        updated = True

    if updated:
        game.updated_at = now_utc()
        game.last_scraped_at = now_utc()
        game.last_ingested_at = now_utc()
        game.scrape_version = (game.scrape_version or 0) + 1
        session.flush()

    return updated


def persist_game_payload(session: Session, payload: NormalizedGame) -> GamePersistResult:
    """Persist boxscore data by enriching an existing game record.

    ENRICHMENT-ONLY: This function does NOT create games. Games must already exist
    (created by Odds API during schedule sync). If no matching game is found,
    this function logs a warning and returns None.

    Returns GamePersistResult with game_id=None if no matching game found.
    """
    league_id = get_league_id(session, payload.identity.league_code)
    home_team_id = _find_team_by_name(
        session, league_id,
        payload.identity.home_team.name,
        payload.identity.home_team.abbreviation,
    )
    away_team_id = _find_team_by_name(
        session, league_id,
        payload.identity.away_team.name,
        payload.identity.away_team.abbreviation,
    )

    # If teams don't exist, we can't match the game
    if home_team_id is None or away_team_id is None:
        logger.warning(
            "boxscore_team_not_found",
            league=payload.identity.league_code,
            home_team=payload.identity.home_team.name,
            away_team=payload.identity.away_team.name,
            home_team_found=home_team_id is not None,
            away_team_found=away_team_id is not None,
            game_date=str(payload.identity.game_date.date()),
            source_game_key=payload.identity.source_game_key,
        )
        return GamePersistResult(game_id=None, enriched=False)

    # Find existing game
    game = _find_game_for_boxscore(
        session, league_id, home_team_id, away_team_id, payload.identity.game_date
    )

    if game is None:
        # No matching game found - this is expected for games not in Odds API
        # Log warning and return gracefully (no-op)
        logger.warning(
            "boxscore_game_not_found",
            league=payload.identity.league_code,
            home_team=payload.identity.home_team.name,
            away_team=payload.identity.away_team.name,
            game_date=str(payload.identity.game_date.date()),
            source_game_key=payload.identity.source_game_key,
            message="Game not found in database. Games must be created via Odds API first.",
        )
        return GamePersistResult(game_id=None, enriched=False)

    # Enrich existing game with boxscore data
    enriched = _enrich_game_with_boxscore(session, game, payload)

    # Attach team boxscores
    upsert_team_boxscores(session, game.id, payload.team_boxscores)

    logger.info(
        "persist_game_payload",
        game_id=game.id,
        game_key=payload.identity.source_game_key,
        enriched=enriched,
        previous_status=game.status,
        team_boxscores_count=len(payload.team_boxscores),
        player_boxscores_count=len(payload.player_boxscores) if payload.player_boxscores else 0,
    )

    # Attach player boxscores
    player_stats: PlayerBoxscoreStats | None = None
    if payload.player_boxscores:
        try:
            logger.info("persisting_player_boxscores", game_id=game.id, count=len(payload.player_boxscores))
            player_stats = upsert_player_boxscores(session, game.id, payload.player_boxscores)
        except Exception as exc:
            logger.error(
                "failed_to_persist_player_boxscores_for_game",
                game_id=game.id,
                game_key=payload.identity.source_game_key,
                error=str(exc),
                exc_info=True,
            )
    else:
        logger.warning("no_player_boxscores_to_persist", game_id=game.id, game_key=payload.identity.source_game_key)

    return GamePersistResult(game_id=game.id, enriched=enriched, player_stats=player_stats)
