"""Helper functions for resolution admin endpoints."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ...db.sports import SportsGame, SportsGamePlay


def build_live_resolution_analysis(
    plays: Sequence[SportsGamePlay],
    game: SportsGame,
) -> dict[str, Any]:
    """Build a live resolution analysis from current PBP data.

    Analyzes team and player resolution status across all plays,
    identifies unresolved teams, unexpected teams, and top players.

    Args:
        plays: Ordered sequence of game plays
        game: The game record with home/away team relationships loaded

    Returns:
        Analysis dict with teams, players, and issues sections
    """
    team_abbrevs_seen: dict[str, dict[str, Any]] = {}
    player_names_seen: dict[str, dict[str, Any]] = {}

    for play in plays:
        # Team analysis
        raw_team = play.raw_data.get("teamTricode") or play.raw_data.get("team")
        if raw_team:
            if raw_team not in team_abbrevs_seen:
                team_abbrevs_seen[raw_team] = {
                    "source": raw_team,
                    "resolved_id": play.team_id,
                    "resolved_name": play.team.name if play.team else None,
                    "resolved_abbrev": play.team.abbreviation if play.team else None,
                    "status": "success" if play.team_id else "failed",
                    "first_play": play.play_index,
                    "occurrences": 1,
                }
            else:
                team_abbrevs_seen[raw_team]["occurrences"] += 1
                team_abbrevs_seen[raw_team]["last_play"] = play.play_index

        # Player analysis
        if play.player_name:
            name = play.player_name.strip()
            if name not in player_names_seen:
                player_names_seen[name] = {
                    "source": name,
                    "status": "success",
                    "first_play": play.play_index,
                    "occurrences": 1,
                }
            else:
                player_names_seen[name]["occurrences"] += 1

    # Find issues
    unresolved_teams = [
        t for t in team_abbrevs_seen.values() if t["status"] == "failed"
    ]

    # Expected teams from game context
    expected_teams = []
    if game.home_team:
        expected_teams.append(
            {
                "abbrev": game.home_team.abbreviation,
                "name": game.home_team.name,
                "team_id": game.home_team.id,
                "role": "home",
            }
        )
    if game.away_team:
        expected_teams.append(
            {
                "abbrev": game.away_team.abbreviation,
                "name": game.away_team.name,
                "team_id": game.away_team.id,
                "role": "away",
            }
        )

    # Check for unexpected teams
    expected_abbrevs = {t["abbrev"].upper() for t in expected_teams}
    unexpected_teams = [
        t
        for t in team_abbrevs_seen.values()
        if t["source"].upper() not in expected_abbrevs
    ]

    return {
        "game_id": game.id,
        "total_plays": len(plays),
        "expected_teams": expected_teams,
        "analysis": {
            "teams": {
                "unique_abbreviations": len(team_abbrevs_seen),
                "resolved": sum(
                    1 for t in team_abbrevs_seen.values() if t["status"] == "success"
                ),
                "unresolved": len(unresolved_teams),
                "details": list(team_abbrevs_seen.values()),
            },
            "players": {
                "unique_names": len(player_names_seen),
                "top_by_occurrences": sorted(
                    player_names_seen.values(),
                    key=lambda x: x["occurrences"],
                    reverse=True,
                )[:10],
            },
        },
        "issues": {
            "unresolved_teams": unresolved_teams,
            "unexpected_teams": unexpected_teams,
        },
    }
