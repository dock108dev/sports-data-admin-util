"""Game statistics helpers for contextual narrative enhancement.

This module computes running player statistics and game context that can be
included in OpenAI prompts to generate richer narratives like:
- "takes an 8 point lead"
- "hits his 2nd 3 of the game"
- "extends the lead to double digits"
"""

from __future__ import annotations

import re
from typing import Any


def compute_running_player_stats(
    pbp_events: list[dict[str, Any]],
    up_to_play_index: int,
) -> dict[str, dict[str, int]]:
    """Compute running player statistics up to (and including) a given play index.

    Returns a dict mapping player_name to their cumulative stats:
    {
        "Donovan Mitchell": {
            "pts": 12,
            "fgm": 5,
            "3pm": 2,
            "ftm": 0,
            "reb": 3,
            "ast": 4,
        },
        ...
    }
    """
    stats: dict[str, dict[str, int]] = {}

    for event in pbp_events:
        if event.get("play_index", 0) > up_to_play_index:
            break

        player = event.get("player_name")
        if not player:
            continue

        if player not in stats:
            stats[player] = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0, "reb": 0, "ast": 0}

        play_type = (event.get("play_type") or "").lower()
        desc = (event.get("description") or "").lower()

        # Detect made shots from play_type
        if play_type in ("made_shot", "field_goal_made", "2pt_made", "3pt_made"):
            stats[player]["fgm"] += 1
            if _is_three_pointer(play_type, desc):
                stats[player]["3pm"] += 1
                stats[player]["pts"] += 3
            else:
                stats[player]["pts"] += 2
        elif play_type in ("free_throw_made", "ft_made"):
            stats[player]["ftm"] += 1
            stats[player]["pts"] += 1
        elif play_type == "rebound":
            stats[player]["reb"] += 1
        elif play_type == "assist":
            stats[player]["ast"] += 1
        else:
            # Fallback: parse description for shot types
            if "makes" in desc or "made" in desc:
                if "3-pt" in desc or "three" in desc or "3pt" in desc:
                    stats[player]["3pm"] += 1
                    stats[player]["fgm"] += 1
                    stats[player]["pts"] += 3
                elif "free throw" in desc or "ft" in desc:
                    stats[player]["ftm"] += 1
                    stats[player]["pts"] += 1
                elif "dunk" in desc or "layup" in desc or "jumper" in desc or "shot" in desc:
                    stats[player]["fgm"] += 1
                    stats[player]["pts"] += 2

    return stats


def _is_three_pointer(play_type: str, description: str) -> bool:
    """Determine if a made shot is a three-pointer."""
    if "3pt" in play_type or "3-pt" in play_type or "three" in play_type:
        return True
    if "3-pt" in description or "three" in description or "3pt" in description:
        return True
    # Look for distance indicators (e.g., "26 ft" or "27'")
    distance_match = re.search(r"(\d+)\s*(?:ft|\'|foot|feet)", description)
    if distance_match:
        distance = int(distance_match.group(1))
        if distance >= 22:  # NBA 3-point line is ~22-24 feet
            return True
    return False


def compute_lead_context(
    score_before: list[int],
    score_after: list[int],
    home_team: str,
    away_team: str,
) -> dict[str, Any]:
    """Compute lead/deficit context for a moment.

    Args:
        score_before: [away_score, home_score] before the moment
        score_after: [away_score, home_score] after the moment
        home_team: Home team name
        away_team: Away team name

    Returns:
        Dict with lead context:
        {
            "lead_before": 5,  # positive = home leading, negative = away leading
            "lead_after": 8,
            "lead_change": 3,
            "leading_team_before": "Lakers",
            "leading_team_after": "Lakers",
            "is_lead_change": False,
            "is_tie_before": False,
            "is_tie_after": False,
            "margin_description": "extend the lead to 8",  # Human-readable
        }
    """
    if not score_before or len(score_before) < 2:
        score_before = [0, 0]
    if not score_after or len(score_after) < 2:
        score_after = [0, 0]

    away_before, home_before = score_before[0], score_before[1]
    away_after, home_after = score_after[0], score_after[1]

    lead_before = home_before - away_before
    lead_after = home_after - away_after

    def get_leading_team(lead: int) -> str | None:
        if lead > 0:
            return home_team
        elif lead < 0:
            return away_team
        return None

    leading_before = get_leading_team(lead_before)
    leading_after = get_leading_team(lead_after)

    is_lead_change = (
        leading_before is not None
        and leading_after is not None
        and leading_before != leading_after
    )

    # Build human-readable margin description
    margin_desc = _build_margin_description(
        lead_before, lead_after, home_team, away_team
    )

    return {
        "lead_before": lead_before,
        "lead_after": lead_after,
        "lead_change": lead_after - lead_before,
        "leading_team_before": leading_before,
        "leading_team_after": leading_after,
        "is_lead_change": is_lead_change,
        "is_tie_before": lead_before == 0,
        "is_tie_after": lead_after == 0,
        "margin_description": margin_desc,
    }


def _build_margin_description(
    lead_before: int,
    lead_after: int,
    home_team: str,
    away_team: str,
) -> str | None:
    """Build a human-readable description of the margin change.

    Examples:
    - "take a 5 point lead"
    - "extend the lead to 8"
    - "cut the deficit to 3"
    - "tie the game"
    - "go up by double digits"
    """
    abs_before = abs(lead_before)
    abs_after = abs(lead_after)

    # Determine which team is being described (the one that scored)
    if lead_after == lead_before:
        return None  # No scoring change

    if lead_after == 0:
        return "tie the game"

    # Home team scored (lead increased or deficit decreased)
    if lead_after > lead_before:
        team = home_team
        if lead_before <= 0 and lead_after > 0:
            # Took the lead
            return f"take a {abs_after} point lead"
        elif lead_before > 0:
            # Extended lead
            if abs_after >= 10 and abs_before < 10:
                return "go up by double digits"
            return f"extend the lead to {abs_after}"
        else:
            # Cut deficit
            return f"cut the deficit to {abs_after}"

    # Away team scored (lead decreased or deficit increased)
    else:
        team = away_team
        if lead_before >= 0 and lead_after < 0:
            # Took the lead
            return f"take a {abs_after} point lead"
        elif lead_before < 0:
            # Extended lead
            if abs_after >= 10 and abs_before < 10:
                return "go up by double digits"
            return f"extend the lead to {abs_after}"
        else:
            # Cut deficit
            return f"cut the deficit to {abs_after}"


def build_moment_context(
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    all_pbp_events: list[dict[str, Any]],
    home_team: str,
    away_team: str,
) -> dict[str, Any]:
    """Build contextual information for a moment.

    This includes:
    - Lead context (margin changes)
    - Running player stats for players involved in this moment

    Returns a dict that can be used to enhance prompts.
    """
    # Get first play index in this moment
    first_play_index = min(
        (p.get("play_index", 0) for p in moment_plays),
        default=0,
    )

    # Compute running stats up to start of this moment
    running_stats = compute_running_player_stats(all_pbp_events, first_play_index - 1)

    # Get players involved in this moment
    moment_players = set()
    for play in moment_plays:
        if play.get("player_name"):
            moment_players.add(play["player_name"])

    # Filter to just relevant players
    player_context = {
        player: stats
        for player, stats in running_stats.items()
        if player in moment_players
    }

    # Compute lead context
    score_before = moment.get("score_before", [0, 0])
    score_after = moment.get("score_after", [0, 0])
    lead_context = compute_lead_context(score_before, score_after, home_team, away_team)

    return {
        "lead_context": lead_context,
        "player_stats_before": player_context,
    }


def format_player_stat_hint(player: str, stats: dict[str, int]) -> str | None:
    """Format a player's running stats as a prompt hint.

    Returns something like "Mitchell: 12 pts, 2 3PM" or None if no notable stats.
    """
    parts = []

    if stats.get("pts", 0) > 0:
        parts.append(f"{stats['pts']} pts")
    if stats.get("3pm", 0) > 0:
        parts.append(f"{stats['3pm']} 3PM")
    if stats.get("reb", 0) >= 5:
        parts.append(f"{stats['reb']} reb")
    if stats.get("ast", 0) >= 5:
        parts.append(f"{stats['ast']} ast")

    if not parts:
        return None

    # Use last name only
    last_name = player.split()[-1] if " " in player else player
    return f"{last_name}: {', '.join(parts)}"
