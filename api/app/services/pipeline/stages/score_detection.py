"""Score and lead change detection for moment generation.

This module provides functions to detect scoring plays, lead changes,
and score state transitions.
"""

from __future__ import annotations

from typing import Any


def get_lead_state(home_score: int, away_score: int) -> str:
    """Determine the lead state from scores.

    Returns:
        'HOME' if home leads, 'AWAY' if away leads, 'TIE' if tied
    """
    if home_score > away_score:
        return "HOME"
    elif away_score > home_score:
        return "AWAY"
    return "TIE"


def is_lead_change(
    prev_home: int,
    prev_away: int,
    curr_home: int,
    curr_away: int,
) -> bool:
    """Detect if a lead change occurred between two score states.

    A lead change is when the team with the lead switches.
    Going from tied to a lead is NOT a lead change.
    Going from a lead to tied is NOT a lead change.
    Going from HOME lead to AWAY lead IS a lead change.

    Args:
        prev_home: Previous home score
        prev_away: Previous away score
        curr_home: Current home score
        curr_away: Current away score

    Returns:
        True if a lead change occurred
    """
    prev_lead = get_lead_state(prev_home, prev_away)
    curr_lead = get_lead_state(curr_home, curr_away)

    # Lead change only if both states have a leader and they differ
    if prev_lead in ("HOME", "AWAY") and curr_lead in ("HOME", "AWAY"):
        return prev_lead != curr_lead

    return False


def is_scoring_play(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
) -> bool:
    """Detect if the current play resulted in a score change.

    A scoring play is detected when either home_score or away_score
    differs from the previous play's scores.

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)

    Returns:
        True if score changed, False otherwise
    """
    if previous_event is None:
        # First play: scoring if scores are non-zero
        home = current_event.get("home_score") or 0
        away = current_event.get("away_score") or 0
        return home > 0 or away > 0

    prev_home = previous_event.get("home_score") or 0
    prev_away = previous_event.get("away_score") or 0
    curr_home = current_event.get("home_score") or 0
    curr_away = current_event.get("away_score") or 0

    return curr_home != prev_home or curr_away != prev_away


def is_lead_change_play(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
) -> bool:
    """Detect if this play caused a lead change.

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)

    Returns:
        True if a lead change occurred
    """
    if previous_event is None:
        return False

    prev_home = previous_event.get("home_score") or 0
    prev_away = previous_event.get("away_score") or 0
    curr_home = current_event.get("home_score") or 0
    curr_away = current_event.get("away_score") or 0

    return is_lead_change(prev_home, prev_away, curr_home, curr_away)


def get_score_before_moment(
    events: list[dict[str, Any]],
    moment_start_index: int,
) -> tuple[int, int]:
    """Get the score state BEFORE the first play of a moment.

    The score_before is the score after the play immediately preceding
    the first play of this moment. For the first moment, it's [0, 0].

    Args:
        events: All normalized PBP events
        moment_start_index: Index of first play in this moment

    Returns:
        Tuple of (home_score, away_score) before the moment
    """
    if moment_start_index == 0:
        return (0, 0)

    prev_event = events[moment_start_index - 1]
    home = prev_event.get("home_score") or 0
    away = prev_event.get("away_score") or 0
    return (home, away)


def get_score_after_moment(last_event: dict[str, Any]) -> tuple[int, int]:
    """Get the score state AFTER the last play of a moment.

    Args:
        last_event: The last PBP event in the moment

    Returns:
        Tuple of (home_score, away_score) after the moment
    """
    home = last_event.get("home_score") or 0
    away = last_event.get("away_score") or 0
    return (home, away)
