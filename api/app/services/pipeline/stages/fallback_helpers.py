"""Fallback classification and generation for narrative rendering.

This module handles the classification and generation of fallback narratives
when OpenAI cannot generate suitable text.
"""

from __future__ import annotations

from typing import Any

from .narrative_types import (
    FallbackReason,
    FallbackType,
    INVALID_FALLBACK_TEMPLATE,
    VALID_FALLBACK_NARRATIVES,
)


def get_valid_fallback_narrative(moment_index: int) -> str:
    """Get a valid low-signal fallback narrative.

    Uses deterministic rotation based on moment index for variety.

    Args:
        moment_index: Index of the moment for deterministic selection

    Returns:
        A valid fallback narrative string
    """
    return VALID_FALLBACK_NARRATIVES[moment_index % len(VALID_FALLBACK_NARRATIVES)]


def get_invalid_fallback_narrative(reason: FallbackReason) -> str:
    """Get an invalid fallback narrative with diagnostic reason.

    Format is intentionally obvious for beta debugging:
    "[Narrative unavailable — {reason}]"

    Args:
        reason: The specific failure reason

    Returns:
        A diagnostic fallback narrative string
    """
    reason_text = reason.value.replace("_", " ")
    return INVALID_FALLBACK_TEMPLATE.format(reason=reason_text)


def is_valid_score_context(moment: dict[str, Any]) -> bool:
    """Check if a moment has valid score context.

    Valid score context means:
    - score_before and score_after are present
    - Both are lists with 2 elements
    - Scores are non-negative
    - Score doesn't decrease (monotonic within moment)

    Args:
        moment: The moment data

    Returns:
        True if score context is valid
    """
    score_before = moment.get("score_before")
    score_after = moment.get("score_after")

    # Must have both scores
    if score_before is None or score_after is None:
        return False

    # Must be lists with 2 elements
    if not isinstance(score_before, (list, tuple)) or len(score_before) != 2:
        return False
    if not isinstance(score_after, (list, tuple)) or len(score_after) != 2:
        return False

    # Scores must be non-negative
    try:
        if score_before[0] < 0 or score_before[1] < 0:
            return False
        if score_after[0] < 0 or score_after[1] < 0:
            return False
    except (TypeError, IndexError):
        return False

    # Score shouldn't decrease within moment (monotonic)
    try:
        if score_after[0] < score_before[0] or score_after[1] < score_before[1]:
            return False
    except (TypeError, IndexError):
        return False

    return True


def has_valid_play_metadata(moment_plays: list[dict[str, Any]]) -> bool:
    """Check if moment plays have required metadata.

    Required fields for narrative generation:
    - play_index
    - description (field must exist, can be empty)

    Args:
        moment_plays: List of PBP events for the moment

    Returns:
        True if all plays have valid metadata
    """
    if not moment_plays:
        return False

    for play in moment_plays:
        if play.get("play_index") is None:
            return False
        if "description" not in play:
            return False

    return True


def classify_empty_narrative_fallback(
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    moment_index: int,
) -> tuple[str, FallbackType, FallbackReason | None]:
    """Classify and generate fallback for empty narrative from OpenAI.

    Classification rules:
    - VALID if: no explicit plays AND valid score context AND valid play metadata
    - INVALID otherwise (with specific reason)

    Args:
        moment: The moment data
        moment_plays: PBP events for the moment
        moment_index: Index for deterministic fallback selection

    Returns:
        Tuple of (narrative_text, fallback_type, fallback_reason)
    """
    explicitly_narrated = moment.get("explicitly_narrated_play_ids", [])
    has_explicit_plays = bool(explicitly_narrated)
    has_valid_scores = is_valid_score_context(moment)
    has_valid_metadata = has_valid_play_metadata(moment_plays)

    # Case 1: Explicit plays exist but narrative is empty -> INVALID
    if has_explicit_plays:
        reason = FallbackReason.EMPTY_NARRATIVE_WITH_EXPLICIT_PLAYS
        return (
            get_invalid_fallback_narrative(reason),
            FallbackType.INVALID,
            reason,
        )

    # Case 2: Score context is invalid -> INVALID
    if not has_valid_scores:
        reason = FallbackReason.SCORE_CONTEXT_INVALID
        return (
            get_invalid_fallback_narrative(reason),
            FallbackType.INVALID,
            reason,
        )

    # Case 3: Play metadata is missing -> INVALID
    if not has_valid_metadata:
        reason = FallbackReason.MISSING_PLAY_METADATA
        return (
            get_invalid_fallback_narrative(reason),
            FallbackType.INVALID,
            reason,
        )

    # Case 4: Valid low-signal gameplay -> VALID
    # No explicit plays, valid scores, valid metadata
    # This is expected basketball behavior (nothing notable happened)
    return (
        get_valid_fallback_narrative(moment_index),
        FallbackType.VALID,
        None,  # No reason needed for valid fallbacks
    )
