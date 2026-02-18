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


# Maximum points from a single basketball play (3-pointer).
# A score_delta exceeding this indicates dropped PBP events.
_MAX_SINGLE_PLAY_SCORE = 3


def _apply_basketball_scoring(
    stats: dict[str, int],
    score_delta: int,
) -> bool:
    """Credit a basketball scoring play to a player's stats.

    Returns True if the play was a valid scoring event, False if skipped
    (score_delta exceeds single-play maximum, indicating dropped PBP events).
    """
    if score_delta <= 0:
        return False
    if score_delta > _MAX_SINGLE_PLAY_SCORE:
        return False
    stats["pts"] += score_delta
    if score_delta >= 2:
        stats["fgm"] += 1
    if score_delta == 3:
        stats["3pm"] += 1
    if score_delta == 1:
        stats["ftm"] += 1
    return True


def _extract_assister_from_description(desc: str) -> str | None:
    """Extract assister name from a scoring play description.

    Descriptions like "L. Markkanen 26' 3PT (3 PTS) (A. Bailey 1 AST)"
    should return "A. Bailey".
    """
    # Match patterns like "(A. Bailey 1 AST)" or "(J. Smith AST)"
    match = re.search(r"\(([A-Z]\.\s*[A-Za-z\-\']+(?:\s+[A-Za-z\-\']+)*)\s+\d*\s*AST\)", desc, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _compute_single_team_delta(
    curr_home: int,
    curr_away: int,
    prev_home: int,
    prev_away: int,
    team_abbreviation: str = "",
    home_team_abbrev: str = "",
    away_team_abbrev: str = "",
) -> int:
    """Compute score delta for a single team's scoring play.

    Uses per-team deltas instead of combined total to avoid
    attributing the other team's points to the current player.
    When both teams' scores change (dropped events), uses team
    matching to pick the right delta, or returns 0 if ambiguous.
    """
    home_delta = curr_home - prev_home
    away_delta = curr_away - prev_away

    # Only one team scored — unambiguous
    if home_delta > 0 and away_delta == 0:
        return home_delta
    if away_delta > 0 and home_delta == 0:
        return away_delta

    # Both teams' scores changed — try team matching
    if home_delta > 0 and away_delta > 0:
        if team_abbreviation and home_team_abbrev:
            team_upper = team_abbreviation.upper()
            if team_upper == home_team_abbrev.upper():
                return home_delta
            if team_upper == away_team_abbrev.upper():
                return away_delta
        # Can't determine — skip attribution
        return 0

    # No score change or score decreased
    return 0


def compute_running_player_stats(
    pbp_events: list[dict[str, Any]],
    up_to_play_index: int,
) -> dict[str, dict[str, int]]:
    """Compute running player statistics up to (and including) a given play index.

    Scoring is detected via score deltas (home_score/away_score changes between
    adjacent events), which works reliably across all data sources.

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

    prev_home = 0
    prev_away = 0

    for event in pbp_events:
        if event.get("play_index", 0) > up_to_play_index:
            break

        player = event.get("player_name")
        play_type = (event.get("play_type") or "").lower()
        original_desc = event.get("description") or ""

        # Track scores for delta detection
        curr_home = event.get("home_score")
        if curr_home is None:
            curr_home = prev_home
        curr_away = event.get("away_score")
        if curr_away is None:
            curr_away = prev_away
        score_delta = _compute_single_team_delta(
            curr_home, curr_away, prev_home, prev_away,
        )

        if not player:
            prev_home = curr_home
            prev_away = curr_away
            continue

        if player not in stats:
            stats[player] = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0, "reb": 0, "ast": 0}

        # Scoring detection: use score delta (works for all data sources)
        scored = _apply_basketball_scoring(stats[player], score_delta)

        # Non-scoring stats: play_type matching for reb/ast
        if play_type in ("rebound", "offensive_rebound", "defensive_rebound"):
            stats[player]["reb"] += 1
        elif play_type == "assist":
            stats[player]["ast"] += 1

        # Extract and credit assists from scoring plays
        if scored:
            assister = _extract_assister_from_description(original_desc)
            if assister:
                if assister not in stats:
                    stats[assister] = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0, "reb": 0, "ast": 0}
                stats[assister]["ast"] += 1

        prev_home = curr_home
        prev_away = curr_away

    return stats


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

    # Format is [home, away] per score_detection.py
    home_before, away_before = score_before[0], score_before[1]
    home_after, away_after = score_after[0], score_after[1]

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

    Uses softer language for slim margins (1-2 points) to avoid overstating
    leads in close, back-and-forth games.

    Examples:
    - "edge ahead" (1 point lead)
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

    # Helper: build take-lead description with slim-margin awareness
    def _take_lead_desc(margin: int) -> str:
        if margin <= 1:
            return "edge ahead"
        if margin <= 2:
            return "nudge ahead"
        return f"take a {margin} point lead"

    # Helper: build extend-lead description with slim-margin awareness
    def _extend_lead_desc(margin_before: int, margin_after: int) -> str | None:
        if margin_after >= 10 and margin_before < 10:
            return "go up by double digits"
        # Extending from 1 to 2 (or similar tiny shifts) isn't newsworthy
        if margin_after <= 2:
            return None
        if margin_after <= 4:
            return f"push the lead to {margin_after}"
        return f"extend the lead to {margin_after}"

    # Helper: build cut-deficit description
    def _cut_deficit_desc(margin: int) -> str:
        if margin <= 1:
            return "pull within one"
        if margin <= 2:
            return "pull within 2"
        return f"cut the deficit to {margin}"

    # Home team scored (lead increased or deficit decreased)
    if lead_after > lead_before:
        if lead_before <= 0 and lead_after > 0:
            return _take_lead_desc(abs_after)
        elif lead_before > 0:
            return _extend_lead_desc(abs_before, abs_after)
        else:
            return _cut_deficit_desc(abs_after)

    # Away team scored (lead decreased or deficit increased)
    else:
        if lead_before >= 0 and lead_after < 0:
            return _take_lead_desc(abs_after)
        elif lead_before < 0:
            return _extend_lead_desc(abs_before, abs_after)
        else:
            return _cut_deficit_desc(abs_after)


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


