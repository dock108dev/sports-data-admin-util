"""Explicit play selection for moment generation.

This module handles the selection of plays that must be explicitly
narrated within each moment.
"""

from __future__ import annotations

from typing import Any

from .moment_types import MAX_EXPLICIT_PLAYS_PER_MOMENT
from .play_classification import is_notable_play
from .score_detection import is_scoring_play


def select_explicitly_narrated_plays(
    moment_plays: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> list[int]:
    """Select which plays in a moment must be explicitly narrated.

    SELECTION RULES (deterministic, based on PBP facts only):

    1. SCORING PLAYS: Any play where score differs from the previous play.
       These are the most concrete, verifiable events.

    2. NOTABLE PLAYS: If no scoring plays, select plays with notable
       play_types (blocks, steals, turnovers, etc.).

    3. FALLBACK: If no scoring or notable plays, select the last play.
       Every moment must have at least one narrated play.

    CONSTRAINT (Task 1.1):
    - Maximum MAX_EXPLICIT_PLAYS_PER_MOMENT (2) plays can be narrated
    - If more candidates exist, prefer scoring plays, then most recent

    Args:
        moment_plays: List of PBP events in this moment
        all_events: All PBP events (for score comparison)
        moment_start_idx: Index of first play in all_events

    Returns:
        List of play_index values that must be explicitly narrated.
        Guaranteed to be non-empty, subset of play_ids, and <= MAX_EXPLICIT_PLAYS_PER_MOMENT.
    """
    scoring_ids: list[int] = []
    notable_ids: list[int] = []

    # RULE 1: Identify scoring plays
    for i, play in enumerate(moment_plays):
        # Get the previous event (could be from previous moment or this moment)
        global_idx = moment_start_idx + i
        if global_idx == 0:
            # First play of game - scoring if scores > 0
            home = play.get("home_score") or 0
            away = play.get("away_score") or 0
            if home > 0 or away > 0:
                scoring_ids.append(play["play_index"])
        else:
            prev_event = all_events[global_idx - 1]
            if is_scoring_play(play, prev_event):
                scoring_ids.append(play["play_index"])

    # RULE 2: Identify notable plays (blocks, steals, etc.)
    for play in moment_plays:
        if is_notable_play(play):
            notable_ids.append(play["play_index"])

    # Build candidate list: scoring plays first, then notable plays
    candidates = scoring_ids + [nid for nid in notable_ids if nid not in scoring_ids]

    # If we have candidates, cap at MAX_EXPLICIT_PLAYS_PER_MOMENT
    if candidates:
        # Prefer keeping scoring plays, take most recent if we must cap
        if len(candidates) > MAX_EXPLICIT_PLAYS_PER_MOMENT:
            # Keep the most significant ones (scoring plays preferred)
            if len(scoring_ids) >= MAX_EXPLICIT_PLAYS_PER_MOMENT:
                # Take last N scoring plays (most recent scoring events)
                candidates = scoring_ids[-MAX_EXPLICIT_PLAYS_PER_MOMENT:]
            else:
                # Take all scoring + remaining from notable up to cap
                candidates = candidates[-MAX_EXPLICIT_PLAYS_PER_MOMENT:]
        return candidates

    # RULE 3: Fallback - select the last play
    return [moment_plays[-1]["play_index"]]


def count_explicit_plays_if_added(
    moment_plays: list[dict[str, Any]],
    new_play: dict[str, Any],
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> int:
    """Count how many explicit plays would result if we add new_play to moment.

    This is used to check if adding a play would exceed MAX_EXPLICIT_PLAYS_PER_MOMENT.

    Args:
        moment_plays: Current plays in the moment
        new_play: Play we're considering adding
        all_events: All PBP events
        moment_start_idx: Index of first play in all_events

    Returns:
        Number of explicitly narrated plays that would result
    """
    # Build hypothetical moment
    hypothetical_plays = moment_plays + [new_play]
    narrated = select_explicitly_narrated_plays(
        hypothetical_plays, all_events, moment_start_idx
    )
    return len(narrated)
