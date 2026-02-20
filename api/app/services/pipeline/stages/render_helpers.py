"""Helper functions for RENDER_BLOCKS stage.

Contains overtime detection, play coverage checking, player name normalization,
and play injection sentence generation.
"""

from __future__ import annotations

import re
from typing import Any

# Natural language mappings for play types
PLAY_TYPE_VERBS = {
    "2pt": "scored inside",
    "3pt": "hit a three-pointer",
    "dunk": "threw down a dunk",
    "layup": "finished at the rim",
    "freethrow": "converted from the line",
    "free throw": "converted from the line",
    "steal": "came up with a steal",
    "block": "rejected the shot",
    "rebound": "grabbed the rebound",
    "assist": "delivered the assist",
    "jump shot": "knocked down a jumper",
    "jumper": "knocked down a jumper",
    "hook": "hit a hook shot",
    "tip": "tipped one in",
    "alley oop": "finished the alley-oop",
    "putback": "scored on the putback",
}


def detect_overtime_info(
    block: dict[str, Any],
    league_code: str = "NBA",
) -> dict[str, Any]:
    """Detect if a block involves overtime or shootout periods.

    Args:
        block: Block dict with period_start and period_end
        league_code: Sport code (NBA, NHL, NCAAB)

    Returns:
        Dict with overtime info:
        - has_overtime: bool - block includes OT periods
        - enters_overtime: bool - block transitions FROM regulation TO OT
        - is_shootout: bool - NHL shootout period
        - ot_label: str - Label like "OT", "OT1", "OT2", "SO"
        - regulation_end_period: int - Last regulation period for this sport
    """
    period_start = block.get("period_start", 1)
    period_end = block.get("period_end", period_start)

    # Determine regulation end period by sport
    if league_code == "NHL":
        regulation_end = 3  # NHL has 3 periods
    elif league_code == "NCAAB":
        regulation_end = 2  # NCAAB has 2 halves
    else:
        regulation_end = 4  # NBA has 4 quarters

    has_overtime = period_end > regulation_end
    enters_overtime = period_start <= regulation_end and period_end > regulation_end

    # NHL period structure:
    # - Regular season: Period 4 = OT (5 min), Period 5 = Shootout
    # - Playoffs: Period 4 = OT1, Period 5 = OT2, Period 6 = OT3, etc. (no shootout)
    # We don't have season_type here, so we assume regular season structure.
    # For playoffs, period 5+ would incorrectly show as shootout/OT labels.
    is_shootout = league_code == "NHL" and period_end == 5

    # Generate OT label
    ot_label = ""
    if has_overtime:
        if is_shootout:
            ot_label = "shootout"
        elif league_code == "NHL":
            # NHL regular season: Period 4 is the only OT period
            # (Period 5 is shootout, handled above)
            ot_label = "overtime"
        else:
            # NBA/NCAAB: OT1 = period 5 (NBA) or period 3 (NCAAB)
            ot_num = period_end - regulation_end
            ot_label = f"OT{ot_num}" if ot_num > 1 else "overtime"

    return {
        "has_overtime": has_overtime,
        "enters_overtime": enters_overtime,
        "is_shootout": is_shootout,
        "ot_label": ot_label,
        "regulation_end_period": regulation_end,
    }


def check_play_coverage(
    narrative: str,
    key_play_ids: list[int],
    pbp_events: list[dict[str, Any]],
) -> tuple[list[int], list[dict[str, Any]]]:
    """Check if key plays are referenced in the narrative.

    Explicit play coverage invariant.

    Args:
        narrative: The generated narrative text
        key_play_ids: IDs of plays that must be referenced
        pbp_events: PBP events with play descriptions

    Returns:
        Tuple of (missing_play_ids, missing_play_events)
    """
    if not narrative or not key_play_ids:
        return [], []

    # Build play lookup
    play_lookup: dict[int, dict[str, Any]] = {
        e.get("play_index", e.get("play_id")): e
        for e in pbp_events
        if e.get("play_index") is not None or e.get("play_id") is not None
    }

    narrative_lower = narrative.lower()
    missing_ids: list[int] = []
    missing_events: list[dict[str, Any]] = []

    for play_id in key_play_ids:
        event = play_lookup.get(play_id, {})
        if not event:
            continue

        # Check if play is referenced in narrative
        # Look for player name, action keywords from description
        description = event.get("description", "")
        player_name = event.get("player_name", "")

        # Extract keywords from description
        found = False

        # Check for player name (first or last name)
        if player_name:
            name_parts = player_name.lower().split()
            for part in name_parts:
                if len(part) > 2 and part in narrative_lower:
                    found = True
                    break

        # Check for key action words from description
        if not found and description:
            # Look for key action words (3-pointer, dunk, layup, etc.)
            # Map both description keywords and their narrative equivalents
            action_keyword_pairs = [
                (["three", "3-point", "3pt", "3-pointer"], ["three", "3-point", "three-pointer"]),
                (["dunk"], ["dunk"]),
                (["layup"], ["layup"]),
                (["jumper", "jump shot"], ["jumper", "jump shot"]),
                (["free throw"], ["free throw"]),
                (["steal"], ["steal"]),
                (["block"], ["block"]),
                (["rebound"], ["rebound"]),
                (["assist"], ["assist"]),
            ]
            desc_lower = description.lower()
            for desc_keywords, narr_keywords in action_keyword_pairs:
                desc_has_keyword = any(kw in desc_lower for kw in desc_keywords)
                narr_has_keyword = any(kw in narrative_lower for kw in narr_keywords)
                if desc_has_keyword and narr_has_keyword:
                    found = True
                    break

        if not found:
            missing_ids.append(play_id)
            missing_events.append(event)

    return missing_ids, missing_events


def normalize_player_name(name: str) -> str:
    """Convert 'j. smith' or 'J. Smith' to 'Smith'.

    Handles initial-style names from PBP data to produce cleaner narratives.
    Supports international names with diacritical marks (e.g., Dončić, Schröder).
    """
    if not name:
        return ""
    # Match patterns like "j. smith" or "J. Dončić" - use \S+ for Unicode support
    if re.match(r"^[A-Za-z]\.\s+\S+", name):
        # Strip initial prefix, then extract last name (handles suffixes)
        from .game_stats_helpers import _extract_last_name
        without_initial = re.sub(r"^[A-Za-z]\.\s+", "", name)
        return _extract_last_name(without_initial).title()
    return name.title() if name.islower() else name


def generate_play_injection_sentence(
    event: dict[str, Any],
    game_context: dict[str, str],
) -> str:
    """Generate a natural language sentence for a missing play.

    Recovery strategy when a key play is not referenced.
    Produces SportsCenter-style prose instead of raw PBP artifacts.

    Args:
        event: The PBP event that needs to be mentioned
        game_context: Team abbreviations

    Returns:
        A natural, broadcast-style sentence describing the play
    """
    player_name = normalize_player_name(event.get("player_name", ""))
    play_type = (event.get("play_type") or "").lower()
    description = (event.get("description") or "").lower()

    # Try to find a matching verb from play type
    verb = PLAY_TYPE_VERBS.get(play_type)

    # If no direct match, try to extract from description
    if not verb and description:
        for key, val in PLAY_TYPE_VERBS.items():
            if key in description:
                verb = val
                break

    # Fallback verb
    if not verb:
        verb = "scored"

    if player_name:
        return f"{player_name} {verb}."
    return ""


def check_overtime_mention(
    narrative: str,
    ot_info: dict[str, Any],
) -> bool:
    """Check if narrative properly mentions overtime/shootout.

    Args:
        narrative: The narrative text
        ot_info: Overtime info dict from detect_overtime_info

    Returns:
        True if OT is mentioned or not required, False if missing required mention
    """
    if not ot_info.get("enters_overtime"):
        return True  # No OT transition = no mention required

    narrative_lower = narrative.lower()

    # Check for various OT mention patterns
    ot_patterns = [
        "overtime",
        "extra period",
        " ot ",
        " ot.",
        " ot,",
        "goes to ot",
        "headed to ot",
        "forcing ot",
        "required ot",
        "sending it to",
        "took overtime",
        "into overtime",
    ]

    # NHL-specific patterns
    if ot_info.get("is_shootout"):
        ot_patterns.extend(["shootout", "shoot out", "shoot-out"])

    for pattern in ot_patterns:
        if pattern in narrative_lower:
            return True

    return False


def inject_overtime_mention(
    narrative: str,
    ot_info: dict[str, Any],
) -> str:
    """Inject overtime mention into narrative if missing.

    Args:
        narrative: The narrative text
        ot_info: Overtime info from detect_overtime_info

    Returns:
        Narrative with OT mention injected if it was missing
    """
    if not ot_info.get("enters_overtime"):
        return narrative

    if check_overtime_mention(narrative, ot_info):
        return narrative  # Already has mention

    # Inject OT mention at the end
    narrative = narrative.rstrip()
    if not narrative.endswith("."):
        narrative += "."

    if ot_info.get("is_shootout"):
        injection = " The game headed to a shootout to determine the winner."
    else:
        ot_label = ot_info.get("ot_label", "overtime")
        injection = f" The game headed to {ot_label}."

    return narrative + injection
