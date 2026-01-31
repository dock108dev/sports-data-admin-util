"""Boundary detection for moment generation.

This module handles the detection of moment boundaries, including
hard (non-negotiable) and soft (preferred) boundary conditions.
"""

from __future__ import annotations

from typing import Any

from .moment_types import (
    ABSOLUTE_MAX_PLAYS,
    BoundaryReason,
    MAX_EXPLICIT_PLAYS_PER_MOMENT,
    PREFERRED_EXPLICIT_PLAYS,
    SOFT_CAP_PLAYS,
)
from .play_classification import is_stoppage_play, is_turnover_play
from .score_detection import is_lead_change_play, is_scoring_play
from .explicit_selection import select_explicitly_narrated_plays


def should_force_close_moment(
    current_moment_plays: list[dict[str, Any]],
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> tuple[bool, BoundaryReason | None]:
    """Check if a HARD boundary condition requires closing the moment.

    HARD conditions are non-negotiable and always force closure.

    Args:
        current_moment_plays: Plays currently in the moment (including current)
        current_event: The current event just added
        previous_event: The previous event (None for first play)
        all_events: All events for explicit play counting
        moment_start_idx: Start index of current moment

    Returns:
        (should_close, reason) tuple
    """
    # HARD: Absolute max plays reached (safety valve)
    if len(current_moment_plays) >= ABSOLUTE_MAX_PLAYS:
        return True, BoundaryReason.ABSOLUTE_MAX_PLAYS

    # HARD: Lead change occurred
    if previous_event and is_lead_change_play(current_event, previous_event):
        return True, BoundaryReason.LEAD_CHANGE

    # HARD: Would create >2 explicitly narrated plays
    # Check what the explicit play count would be
    narrated = select_explicitly_narrated_plays(
        current_moment_plays, all_events, moment_start_idx
    )
    if len(narrated) > MAX_EXPLICIT_PLAYS_PER_MOMENT:
        return True, BoundaryReason.EXPLICIT_PLAY_OVERFLOW

    return False, None


def should_prefer_close_moment(
    current_moment_plays: list[dict[str, Any]],
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> tuple[bool, BoundaryReason | None]:
    """Check if a SOFT boundary condition suggests closing the moment.

    SOFT conditions prefer closing but can be overridden by merge eligibility.

    Args:
        current_moment_plays: Plays currently in the moment (including current)
        current_event: The current event just added
        previous_event: The previous event (None for first play)
        all_events: All events for explicit play counting
        moment_start_idx: Start index of current moment

    Returns:
        (should_close, reason) tuple
    """
    # SOFT: Soft cap reached
    if len(current_moment_plays) >= SOFT_CAP_PLAYS:
        return True, BoundaryReason.SOFT_CAP_REACHED

    # SOFT: Scoring play (but not lead change, that's HARD)
    if previous_event and is_scoring_play(current_event, previous_event):
        return True, BoundaryReason.SCORING_PLAY

    # SOFT: Stoppage play
    if is_stoppage_play(current_event):
        return True, BoundaryReason.STOPPAGE

    # SOFT: Turnover / possession change
    if is_turnover_play(current_event):
        return True, BoundaryReason.POSSESSION_CHANGE

    # SOFT: Second explicitly narrated play encountered
    narrated = select_explicitly_narrated_plays(
        current_moment_plays, all_events, moment_start_idx
    )
    if len(narrated) > PREFERRED_EXPLICIT_PLAYS:
        return True, BoundaryReason.SECOND_EXPLICIT_PLAY

    return False, None


def is_merge_eligible(
    current_moment_plays: list[dict[str, Any]],
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    next_event: dict[str, Any] | None,
) -> bool:
    """Check if game flow suggests we should continue merging plays.

    Merge eligibility can override SOFT (but not HARD) boundary conditions.
    Note: SOFT_CAP_REACHED is explicitly excluded from override in the caller,
    so we don't check soft cap here.

    Conditions for merge eligibility:
    - No scoring has occurred in the current moment
    - Game flow appears continuous (not fragmented)

    Args:
        current_moment_plays: Plays currently in the moment
        current_event: The current event
        previous_event: The previous event
        next_event: The next event (for lookahead)

    Returns:
        True if merge should be encouraged
    """
    # Check if any scoring has occurred in this moment
    if len(current_moment_plays) > 1:
        for j in range(1, len(current_moment_plays)):
            prev = current_moment_plays[j - 1]
            curr = current_moment_plays[j]
            if is_scoring_play(curr, prev):
                # Scoring occurred, don't encourage merge
                return False

    # If next event is in the same period and game is flowing, encourage merge
    if next_event:
        curr_period = current_event.get("quarter") or 1
        next_period = next_event.get("quarter") or 1
        if curr_period == next_period:
            # Same period, game is flowing
            return True

    return False
