"""
Player Prominence: Metrics for player selection in story sections.

PLAYER PROMINENCE SYSTEM:
Used ONLY for player selection - these values are NOT passed to AI.
The AI receives only section-level deltas (points_scored in section).

Selection logic (per team):
1. Rank by section_points → Top 1-2 as "section leaders"
2. Rank by game_points_so_far → Top 1 as "game presence"
3. No duplicates, max 3 per team
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .running_stats import SectionDelta, RunningStatsSnapshot


@dataclass
class PlayerProminence:
    """Player prominence metrics for selection purposes.

    PLAYER PROMINENCE SYSTEM:
    Used ONLY for player selection - these values are NOT passed to AI.
    The AI receives only section-level deltas (points_scored in section).

    Selection logic (per team):
    1. Rank by section_points → Top 1-2 as "section leaders"
    2. Rank by game_points_so_far → Top 1 as "game presence"
    3. No duplicates, max 3 per team

    Attributes:
        player_key: Normalized player identifier
        player_name: Display name
        team_key: Team identifier
        section_points: Points scored in THIS section only
        game_points_so_far: Cumulative game points (for selection only)
        run_involvement_count: Number of run events player was involved in
    """

    player_key: str
    player_name: str
    team_key: str | None = None
    section_points: int = 0
    game_points_so_far: int = 0
    run_involvement_count: int = 0


def compute_player_prominence(
    section_delta: "SectionDelta",
    end_snapshot: "RunningStatsSnapshot | None" = None,
) -> dict[str, PlayerProminence]:
    """Compute prominence metrics for all players in a section.

    Args:
        section_delta: Section-level player statistics
        end_snapshot: Cumulative snapshot at section end (for game totals)

    Returns:
        Dict of player_key -> PlayerProminence
    """
    prominence_map: dict[str, PlayerProminence] = {}

    for player_key, delta in section_delta.players.items():
        # Get game totals from snapshot if available
        game_points = 0
        if end_snapshot and player_key in end_snapshot.players:
            game_points = end_snapshot.players[player_key].points_scored_total

        prominence_map[player_key] = PlayerProminence(
            player_key=delta.player_key,
            player_name=delta.player_name,
            team_key=delta.team_key,
            section_points=delta.points_scored,
            game_points_so_far=game_points,
            run_involvement_count=0,  # Stub for now - can add run tracking later
        )

    return prominence_map


def select_prominent_players(
    prominence_map: dict[str, PlayerProminence],
    max_per_team: int = 3,
) -> set[str]:
    """Select prominent players using prominence-based rules.

    SELECTION RULES (per team):
    1. Top 1-2 by section_points ("section leaders")
    2. Top 1 by game_points_so_far ("game presence") if not already selected
    3. No duplicates, max 3 per team

    Args:
        prominence_map: Player prominence metrics
        max_per_team: Maximum players to select per team (default: 3)

    Returns:
        Set of selected player_keys
    """
    selected: set[str] = set()

    # Group by team
    players_by_team: dict[str, list[PlayerProminence]] = {}
    for p in prominence_map.values():
        team = p.team_key or "unknown"
        if team not in players_by_team:
            players_by_team[team] = []
        players_by_team[team].append(p)

    for team_key, team_players in players_by_team.items():
        team_selected: list[str] = []

        # Step 1: Top 1-2 by section_points (section leaders)
        by_section_points = sorted(
            team_players,
            key=lambda x: (-x.section_points, -x.game_points_so_far, x.player_key),
        )

        # Take up to 2 section leaders
        for p in by_section_points[:2]:
            if p.section_points > 0:  # Only if they actually scored
                team_selected.append(p.player_key)

        # Step 2: Top 1 by game_points_so_far (game presence)
        if len(team_selected) < max_per_team:
            by_game_points = sorted(
                team_players,
                key=lambda x: (-x.game_points_so_far, -x.section_points, x.player_key),
            )

            for p in by_game_points:
                if p.player_key not in team_selected:
                    if p.game_points_so_far > 0:  # Only if they've scored in game
                        team_selected.append(p.player_key)
                        break

        # Ensure we don't exceed max_per_team
        selected.update(team_selected[:max_per_team])

    return selected
