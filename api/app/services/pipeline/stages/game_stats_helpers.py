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
        original_desc = event.get("description") or ""

        # Track if this was a scoring play (for assist extraction)
        scored = False

        # Explicit made shot types (confirmed makes)
        if play_type in ("made_shot", "field_goal_made", "2pt_made", "3pt_made"):
            stats[player]["fgm"] += 1
            if _is_three_pointer(play_type, desc):
                stats[player]["3pm"] += 1
                stats[player]["pts"] += 3
            else:
                stats[player]["pts"] += 2
            scored = True
        # Shot attempts ("2pt", "3pt") - must verify from description
        elif play_type in ("2pt", "3pt"):
            if _is_made_shot(desc):
                stats[player]["fgm"] += 1
                if _is_three_pointer(play_type, desc):
                    stats[player]["3pm"] += 1
                    stats[player]["pts"] += 3
                else:
                    stats[player]["pts"] += 2
                scored = True
        elif play_type in ("free_throw_made", "ft_made"):
            stats[player]["ftm"] += 1
            stats[player]["pts"] += 1
            scored = True
        elif play_type == "freethrow":
            if _is_made_shot(desc):
                stats[player]["ftm"] += 1
                stats[player]["pts"] += 1
                scored = True
        elif play_type == "rebound":
            stats[player]["reb"] += 1
        elif play_type == "assist":
            stats[player]["ast"] += 1
        else:
            # Fallback: parse description for shot types (only if made)
            if _is_made_shot(desc):
                if "3-pt" in desc or "three" in desc or "3pt" in desc:
                    stats[player]["3pm"] += 1
                    stats[player]["fgm"] += 1
                    stats[player]["pts"] += 3
                    scored = True
                elif "free throw" in desc or " ft " in desc:
                    stats[player]["ftm"] += 1
                    stats[player]["pts"] += 1
                    scored = True
                elif "dunk" in desc or "layup" in desc or "jumper" in desc or "shot" in desc:
                    stats[player]["fgm"] += 1
                    stats[player]["pts"] += 2
                    scored = True

        # Extract and credit assists from scoring plays
        if scored:
            assister = _extract_assister_from_description(original_desc)
            if assister:
                if assister not in stats:
                    stats[assister] = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0, "reb": 0, "ast": 0}
                stats[assister]["ast"] += 1

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


def compute_cumulative_box_score(
    pbp_events: list[dict[str, Any]],
    up_to_play_index: int,
    home_team: str,
    away_team: str,
    league_code: str = "NBA",
    home_team_abbrev: str = "",
    away_team_abbrev: str = "",
) -> dict[str, Any]:
    """Compute full cumulative box score up to a specific play.

    Returns sport-specific stats for top contributors on each team.

    Args:
        pbp_events: All PBP events for the game
        up_to_play_index: Compute stats up to and including this play index
        home_team: Home team name (for display)
        away_team: Away team name (for display)
        league_code: League code (NBA, NCAAB, NHL)
        home_team_abbrev: Home team abbreviation (for matching, e.g., "GSW")
        away_team_abbrev: Away team abbreviation (for matching, e.g., "LAC")

    Returns:
        Box score dict with home/away team stats:
        {
            "home": {
                "team": "Hawks",
                "score": 45,
                "players": [
                    {"name": "Trae Young", "pts": 12, "reb": 2, "ast": 5, "3pm": 2},
                    ...
                ]
            },
            "away": {
                "team": "Celtics",
                "score": 42,
                "players": [...]
            }
        }

        For NHL:
        {
            "home": {
                "team": "Bruins",
                "score": 3,
                "players": [
                    {"name": "David Pastrnak", "goals": 1, "assists": 1, "sog": 4, "plusMinus": 2},
                    ...
                ],
                "goalie": {"name": "Jeremy Swayman", "saves": 24, "ga": 2, "savePct": 0.923}
            },
            "away": {...}
        }
    """
    # Track stats by player and team
    player_stats: dict[str, dict[str, Any]] = {}
    player_teams: dict[str, str] = {}  # player_name -> team_abbrev

    # Get final scores up to this point
    home_score = 0
    away_score = 0

    for event in pbp_events:
        if event.get("play_index", 0) > up_to_play_index:
            break

        # Track scores
        home_score = event.get("home_score") or home_score
        away_score = event.get("away_score") or away_score

        player = event.get("player_name")
        team_abbrev = event.get("team_abbreviation", "")

        if not player:
            continue

        # Track which team this player is on
        if player not in player_teams and team_abbrev:
            player_teams[player] = team_abbrev

        if player not in player_stats:
            if league_code == "NHL":
                player_stats[player] = {
                    "goals": 0,
                    "assists": 0,
                    "sog": 0,  # shots on goal
                    "plusMinus": 0,
                    "saves": 0,
                    "ga": 0,  # goals against (for goalies)
                    "is_goalie": False,
                }
            else:
                # NBA/NCAAB
                player_stats[player] = {
                    "pts": 0,
                    "reb": 0,
                    "ast": 0,
                    "3pm": 0,
                    "fgm": 0,
                    "ftm": 0,
                }

        play_type = (event.get("play_type") or "").lower()
        desc = (event.get("description") or "").lower()
        original_desc = event.get("description") or ""

        if league_code == "NHL":
            _accumulate_nhl_stats(player_stats[player], play_type, desc)
        else:
            _accumulate_basketball_stats(player_stats[player], play_type, desc)

            # Extract and credit assists from scoring plays (basketball only)
            # Assists are embedded in descriptions like "(A. Bailey 1 AST)"
            # Only credit assists for MADE shots (not misses)
            is_scoring_play = (
                play_type in ("made_shot", "2pt_made", "3pt_made") or
                (play_type in ("2pt", "3pt") and _is_made_shot(desc))
            )
            if is_scoring_play:
                assister = _extract_assister_from_description(original_desc)
                if assister:
                    # Initialize assister stats if needed
                    if assister not in player_stats:
                        player_stats[assister] = {
                            "pts": 0, "reb": 0, "ast": 0, "3pm": 0, "fgm": 0, "ftm": 0
                        }
                    player_stats[assister]["ast"] += 1
                    # Track assister's team (same as scorer's team)
                    if assister not in player_teams and team_abbrev:
                        player_teams[assister] = team_abbrev

    # Determine which players belong to which team
    # Match by abbreviation (preferred) or fall back to name matching
    home_players: list[dict[str, Any]] = []
    away_players: list[dict[str, Any]] = []

    # Normalize abbreviations for matching
    home_abbrev_upper = home_team_abbrev.upper() if home_team_abbrev else ""
    away_abbrev_upper = away_team_abbrev.upper() if away_team_abbrev else ""

    for player_name, stats in player_stats.items():
        team_abbrev = player_teams.get(player_name, "")

        player_entry = {"name": player_name, **stats}

        if not team_abbrev:
            # No team info - skip player
            continue

        team_upper = team_abbrev.upper()

        # Primary matching: abbreviation-to-abbreviation (exact match)
        if home_abbrev_upper and team_upper == home_abbrev_upper:
            home_players.append(player_entry)
        elif away_abbrev_upper and team_upper == away_abbrev_upper:
            away_players.append(player_entry)
        else:
            # Fallback: try name-based matching (for backwards compatibility)
            home_upper = home_team.upper()
            away_upper = away_team.upper()

            if team_upper in home_upper or home_upper.startswith(team_upper):
                home_players.append(player_entry)
            elif team_upper in away_upper or away_upper.startswith(team_upper):
                away_players.append(player_entry)
            # If still no match, skip the player rather than guessing

    # Sort by contribution (points for basketball, goals+assists for hockey)
    def _nhl_sort_key(p: dict[str, Any]) -> tuple[int, int]:
        return (p.get("goals", 0) + p.get("assists", 0), p.get("sog", 0))

    def _basketball_sort_key(p: dict[str, Any]) -> tuple[int, int]:
        return (p.get("pts", 0), p.get("ast", 0))

    sort_key = _nhl_sort_key if league_code == "NHL" else _basketball_sort_key

    home_players.sort(key=sort_key, reverse=True)
    away_players.sort(key=sort_key, reverse=True)

    # Take top 5 contributors per team
    max_players = 5
    home_top = home_players[:max_players]
    away_top = away_players[:max_players]

    # Build result
    result: dict[str, Any] = {
        "home": {
            "team": home_team,
            "score": home_score,
            "players": home_top,
        },
        "away": {
            "team": away_team,
            "score": away_score,
            "players": away_top,
        },
    }

    # For NHL, extract goalie stats
    if league_code == "NHL":
        for side, players in [("home", home_players), ("away", away_players)]:
            goalies = [p for p in players if p.get("is_goalie")]
            if goalies:
                goalie = goalies[0]
                saves = goalie.get("saves", 0)
                ga = goalie.get("ga", 0)
                shots_faced = saves + ga
                save_pct = round(saves / shots_faced, 3) if shots_faced > 0 else 0.0
                result[side]["goalie"] = {
                    "name": goalie["name"],
                    "saves": saves,
                    "ga": ga,
                    "savePct": save_pct,
                }

    return result


def _is_made_shot(desc: str) -> bool:
    """Check if the description indicates a made shot (not a miss)."""
    desc_lower = desc.lower()
    # Check for explicit make indicators
    if "makes" in desc_lower or "made" in desc_lower:
        return True
    # Check for miss indicators (should NOT count)
    if "miss" in desc_lower or "missed" in desc_lower:
        return False
    # Default: if no explicit indicator, assume not made (conservative)
    return False


def _accumulate_basketball_stats(
    stats: dict[str, int],
    play_type: str,
    desc: str,
) -> None:
    """Accumulate basketball stats for a player from a play event.

    IMPORTANT: play_type "2pt" and "3pt" represent ATTEMPTS, not makes.
    We must check the description for "makes"/"made" to confirm it was scored.
    """
    desc_lower = desc.lower()

    # Explicit made shot types (these are confirmed makes)
    if play_type in ("made_shot", "field_goal_made", "2pt_made", "3pt_made"):
        stats["fgm"] += 1
        if _is_three_pointer(play_type, desc):
            stats["3pm"] += 1
            stats["pts"] += 3
        else:
            stats["pts"] += 2
    # Shot attempts ("2pt", "3pt") - must verify from description
    elif play_type in ("2pt", "3pt"):
        if _is_made_shot(desc):
            stats["fgm"] += 1
            if _is_three_pointer(play_type, desc):
                stats["3pm"] += 1
                stats["pts"] += 3
            else:
                stats["pts"] += 2
        # If not made, don't count points (it's a miss)
    elif play_type in ("free_throw_made", "ft_made"):
        stats["ftm"] += 1
        stats["pts"] += 1
    elif play_type == "freethrow":
        # Generic free throw - check if made
        if _is_made_shot(desc):
            stats["ftm"] += 1
            stats["pts"] += 1
    elif play_type == "rebound":
        stats["reb"] += 1
    elif play_type == "assist":
        stats["ast"] += 1
    else:
        # Fallback: parse description for shot types (only if made)
        if _is_made_shot(desc):
            if "3-pt" in desc_lower or "three" in desc_lower or "3pt" in desc_lower:
                stats["3pm"] += 1
                stats["fgm"] += 1
                stats["pts"] += 3
            elif "free throw" in desc_lower or " ft " in desc_lower:
                stats["ftm"] += 1
                stats["pts"] += 1
            elif "dunk" in desc_lower or "layup" in desc_lower or "jumper" in desc_lower or "shot" in desc_lower:
                stats["fgm"] += 1
                stats["pts"] += 2


def _accumulate_nhl_stats(
    stats: dict[str, Any],
    play_type: str,
    desc: str,
) -> None:
    """Accumulate NHL stats for a player from a play event."""
    if play_type in ("goal", "scored"):
        stats["goals"] += 1
    elif play_type == "assist":
        stats["assists"] += 1
    elif play_type in ("shot", "shot_on_goal", "sog"):
        stats["sog"] += 1
    elif play_type == "save":
        stats["saves"] += 1
        stats["is_goalie"] = True
    elif play_type in ("goal_against", "goal_allowed"):
        stats["ga"] += 1
        stats["is_goalie"] = True
    else:
        # Parse description
        if "goal" in desc and "saved" not in desc:
            stats["goals"] += 1
        elif "assist" in desc:
            stats["assists"] += 1
        elif "shot" in desc and "blocked" not in desc:
            stats["sog"] += 1
        elif "save" in desc:
            stats["saves"] += 1
            stats["is_goalie"] = True


def compute_block_mini_box(
    pbp_events: list[dict[str, Any]],
    block_start_play_idx: int,
    block_end_play_idx: int,
    prev_block_end_play_idx: int | None,
    home_team: str,
    away_team: str,
    league_code: str = "NBA",
    home_team_abbrev: str = "",
    away_team_abbrev: str = "",
) -> dict[str, Any]:
    """Compute mini box score for a block with cumulative stats and segment deltas.

    Returns a mini box with:
    - Cumulative stats at end of block (top 3 performers per team)
    - Delta stats showing production during this block segment (+x)
    - Block segment contributors highlighted

    Args:
        pbp_events: All PBP events for the game
        block_start_play_idx: First play index in this block
        block_end_play_idx: Last play index in this block
        prev_block_end_play_idx: Last play index of previous block (None for first block)
        home_team: Home team name
        away_team: Away team name
        league_code: League code (NBA, NCAAB, NHL)
        home_team_abbrev: Home team abbreviation
        away_team_abbrev: Away team abbreviation

    Returns:
        Mini box dict:
        {
            "home": {
                "team": "Hawks",
                "players": [
                    {"name": "Trae Young", "pts": 18, "delta_pts": 6, "reb": 2, "ast": 7},
                    ...
                ]
            },
            "away": {...},
            "block_stars": ["Young", "Mitchell"]  # Top contributors this segment
        }
    """
    # Get cumulative box at end of this block
    cumulative = compute_cumulative_box_score(
        pbp_events,
        block_end_play_idx,
        home_team,
        away_team,
        league_code,
        home_team_abbrev,
        away_team_abbrev,
    )

    # Get cumulative box at end of previous block (for deltas)
    if prev_block_end_play_idx is not None:
        prev_cumulative = compute_cumulative_box_score(
            pbp_events,
            prev_block_end_play_idx,
            home_team,
            away_team,
            league_code,
            home_team_abbrev,
            away_team_abbrev,
        )
    else:
        # First block - no previous stats
        prev_cumulative = {
            "home": {"team": home_team, "score": 0, "players": []},
            "away": {"team": away_team, "score": 0, "players": []},
        }

    # Build lookup for previous stats
    prev_home_stats: dict[str, dict[str, int]] = {
        p["name"]: p for p in prev_cumulative["home"].get("players", [])
    }
    prev_away_stats: dict[str, dict[str, int]] = {
        p["name"]: p for p in prev_cumulative["away"].get("players", [])
    }

    # Key stat for sorting (points for basketball, goals+assists for hockey)
    if league_code == "NHL":
        key_stat = "goals"
        delta_key = "delta_goals"
    else:
        key_stat = "pts"
        delta_key = "delta_pts"

    block_stars: list[str] = []

    # Add deltas to cumulative stats
    for side, prev_stats in [("home", prev_home_stats), ("away", prev_away_stats)]:
        for player in cumulative[side].get("players", []):
            name = player["name"]
            prev = prev_stats.get(name, {})

            # Calculate deltas for key stats
            if league_code == "NHL":
                player["delta_goals"] = player.get("goals", 0) - prev.get("goals", 0)
                player["delta_assists"] = player.get("assists", 0) - prev.get("assists", 0)
                delta_contribution = player["delta_goals"] + player["delta_assists"]
            else:
                player["delta_pts"] = player.get("pts", 0) - prev.get("pts", 0)
                player["delta_reb"] = player.get("reb", 0) - prev.get("reb", 0)
                player["delta_ast"] = player.get("ast", 0) - prev.get("ast", 0)
                delta_contribution = player["delta_pts"]

            # Track block stars (players who contributed significantly this segment)
            if delta_contribution >= 5 or (league_code == "NHL" and delta_contribution >= 1):
                last_name = name.split()[-1] if " " in name else name
                block_stars.append(last_name)

    # Trim to top 3 per team for mini box
    for side in ["home", "away"]:
        players = cumulative[side].get("players", [])
        # Sort by cumulative contribution, then by delta
        players.sort(
            key=lambda p: (p.get(key_stat, 0), p.get(delta_key, 0)),
            reverse=True,
        )
        cumulative[side]["players"] = players[:3]

    # Remove scores from mini_box (already in block score_before/after)
    cumulative["home"].pop("score", None)
    cumulative["away"].pop("score", None)

    # Add block stars (top 2)
    cumulative["block_stars"] = block_stars[:2]

    return cumulative
