"""Team stat annotations for game detail view.

Generates human-readable annotations highlighting notable stat advantages
between teams. Uses the same thresholds as both web and iOS clients.
"""

from __future__ import annotations

from typing import Any


def _get_val(stats: dict[str, Any], key: str, *aliases: str) -> int:
    """Extract an int stat value, trying aliases and nested dicts."""
    for k in (key, *aliases):
        val = stats.get(k)
        if val is None:
            continue
        if isinstance(val, dict):
            total = val.get("total")
            if total is not None:
                try:
                    return int(total)
                except (ValueError, TypeError):
                    pass
            continue
        try:
            return int(val)
        except (ValueError, TypeError):
            continue
    return 0


# Annotation rules: (key, aliases, threshold, label_template)
# template uses {team} and {val} placeholders
_RULES: list[tuple[str, tuple[str, ...], int, str]] = [
    ("offensive_rebounds", ("orb", "oreb", "rebounds.offensive"), 5, "{team} dominated the glass (+{val} OREB)"),
    ("turnovers", ("tov", "to"), 2, "{team} forced {val} more turnovers"),
    ("three_pointers_made", ("fg3", "tp", "3pm", "threes", "three_pointers.made"), 4, "{team} hit {val} more threes"),
    ("assists", ("ast",), 6, "{team} shared the ball better (+{val} AST)"),
    ("steals", ("stl",), 3, "{team} had {val} more steals"),
    ("blocks", ("blk",), 3, "{team} blocked {val} more shots"),
    ("free_throws_attempted", ("fta",), 8, "{team} got to the line more (+{val} FTA)"),
]


def compute_team_annotations(
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
    home_abbr: str,
    away_abbr: str,
    league_code: str,
) -> list[dict[str, Any]]:
    """Generate stat annotations highlighting notable advantages.

    Args:
        home_stats: Home team raw boxscore stats.
        away_stats: Away team raw boxscore stats.
        home_abbr: Home team abbreviation.
        away_abbr: Away team abbreviation.
        league_code: League code (currently same rules for all basketball leagues).

    Returns:
        List of annotation dicts with "key" and "text" fields.
    """
    annotations: list[dict[str, Any]] = []

    for key, aliases, threshold, template in _RULES:
        home_val = _get_val(home_stats, key, *aliases)
        away_val = _get_val(away_stats, key, *aliases)
        diff = home_val - away_val

        if abs(diff) >= threshold:
            team = home_abbr if diff > 0 else away_abbr
            annotations.append({
                "key": key,
                "text": template.format(team=team, val=abs(diff)),
            })

    return annotations
