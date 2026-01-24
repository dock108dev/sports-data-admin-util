"""NHL-specific helper functions for sports router."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ... import db_models

from .schemas import NHLDataHealth

logger = logging.getLogger(__name__)


def compute_nhl_data_health(
    game: "db_models.SportsGame",
    player_boxscores: list,
) -> NHLDataHealth | None:
    """Compute NHL-specific data health indicators.

    Returns None for non-NHL games.
    For NHL games, returns health status that distinguishes between:
    - Legitimate empty (game not yet played)
    - Ingestion failure (completed game with missing player data)
    - Schema pollution (non-hockey fields like rebounds/yards present)
    """
    league_code = game.league.code if game.league else None
    if league_code != "NHL":
        return None

    # Count skaters and goalies by checking player_role in raw stats
    skater_count = 0
    goalie_count = 0
    no_role_count = 0
    has_non_hockey_fields = False

    # Non-hockey fields that should never appear in NHL player data
    non_hockey_fields = {"rebounds", "yards", "touchdowns", "trb", "yds", "td"}

    for player in player_boxscores:
        stats = player.stats or {}
        player_role = stats.get("player_role")
        if player_role == "skater":
            skater_count += 1
        elif player_role == "goalie":
            goalie_count += 1
        else:
            no_role_count += 1

        # Check for non-hockey field pollution
        if any(field in stats for field in non_hockey_fields):
            has_non_hockey_fields = True

    # Determine health status
    issues: list[str] = []
    is_healthy = True

    # Game status determines what we expect
    game_status = (game.status or "").lower()
    is_completed = game_status in ("completed", "final", "finished")

    if is_completed:
        # Completed games SHOULD have player data
        if skater_count == 0:
            issues.append("zero_skaters_for_completed_game")
            is_healthy = False
        if goalie_count == 0:
            issues.append("zero_goalies_for_completed_game")
            is_healthy = False

        # Additional sanity checks for NHL
        # Each team should have ~18-20 skaters and 1-2 goalies
        if skater_count > 0 and skater_count < 20:
            issues.append(f"low_skater_count:{skater_count}")
            # Not necessarily unhealthy, but notable

    # Check for players without proper role assignment
    if no_role_count > 0:
        issues.append(f"players_without_role:{no_role_count}")
        is_healthy = False

    # Check for schema pollution (non-hockey fields)
    if has_non_hockey_fields:
        issues.append("non_hockey_fields_detected")
        # This indicates legacy or corrupted data
        is_healthy = False

    # Log issues for visibility
    if issues:
        logger.warning(
            "nhl_data_health_issues",
            game_id=game.id,
            status=game_status,
            skater_count=skater_count,
            goalie_count=goalie_count,
            no_role_count=no_role_count,
            has_non_hockey_fields=has_non_hockey_fields,
            issues=issues,
            is_healthy=is_healthy,
        )

    return NHLDataHealth(
        skater_count=skater_count,
        goalie_count=goalie_count,
        is_healthy=is_healthy,
        issues=issues,
    )
