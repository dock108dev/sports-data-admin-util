"""
Story Story Builder: Final assembly of condensed moments into a story.

This module is intentionally minimal. It performs only:
1. Ordering of already-built moments
2. Validation of narrative presence
3. Assembly into StoryOutput

This module does NOT:
- Create moments
- Modify moments
- Generate text
- Add metadata, headers, or summaries

AUTHORITATIVE INPUTS:
- docs/story_contract.md
- docs/pbp_story_assumptions.md
- story/schema.py

If this module feels "too simple," it is working correctly.
"""

from __future__ import annotations

from typing import Sequence

from .schema import (
    CondensedMoment,
    StoryOutput,
    SchemaValidationError,
    validate_story,
    _clock_to_seconds,
)


class AssemblyError(Exception):
    """Raised when story assembly fails."""

    pass


def _moment_sort_key(moment: CondensedMoment) -> tuple[int, int, int]:
    """Generate sort key for a moment.

    Ordering:
    1. period (ascending)
    2. start_clock (descending - higher seconds first, per countdown semantics)
    3. first play_index (ascending - deterministic tiebreaker)

    If clock cannot be parsed, falls back to 0 seconds (sorts last within period).
    This is documented behavior per pbp_story_assumptions.md Section 4.5.
    """
    period = moment.period

    # Parse clock to seconds; None becomes 0 (sorts last)
    clock_seconds = _clock_to_seconds(moment.start_clock)
    if clock_seconds is None:
        clock_seconds = 0

    # Negate clock_seconds for descending order (higher clocks first)
    clock_key = -clock_seconds

    # First play_index as tiebreaker (ascending)
    first_play_index = moment.play_ids[0] if moment.play_ids else 0

    return (period, clock_key, first_play_index)


def _validate_narrative_presence(moments: Sequence[CondensedMoment]) -> None:
    """Validate that every moment has a non-empty narrative.

    Raises AssemblyError if any moment lacks narrative.
    Does NOT attempt to generate or repair text.
    """
    for i, moment in enumerate(moments):
        if not moment.narrative or not moment.narrative.strip():
            raise AssemblyError(
                f"Moment {i} (play_ids={moment.play_ids}) has empty narrative. "
                f"Narrative generation must complete before assembly."
            )


def _validate_no_overlapping_plays(moments: Sequence[CondensedMoment]) -> None:
    """Validate that no play_id appears in multiple moments.

    Raises AssemblyError on overlap.
    """
    seen_play_ids: dict[int, int] = {}

    for i, moment in enumerate(moments):
        for pid in moment.play_ids:
            if pid in seen_play_ids:
                raise AssemblyError(
                    f"play_id {pid} appears in multiple moments: "
                    f"moment {seen_play_ids[pid]} and moment {i}"
                )
            seen_play_ids[pid] = i


def assemble_story(
    moments: Sequence[CondensedMoment],
) -> StoryOutput:
    """Assemble condensed moments into a complete StoryOutput.

    This is a pure assembly function. It:
    - Orders moments by (period, start_clock descending, first play_index)
    - Validates all moments have narratives
    - Returns StoryOutput

    Args:
        moments: Sequence of CondensedMoments with narratives already populated

    Returns:
        StoryOutput containing ordered moments

    Raises:
        AssemblyError: If moments are empty, lack narratives, or have overlapping plays
        SchemaValidationError: If output fails schema validation
    """
    # Validate input is non-empty
    if not moments:
        raise AssemblyError("Cannot assemble story from empty moment list")

    # Validate narrative presence before ordering
    _validate_narrative_presence(moments)

    # Validate no overlapping play_ids
    _validate_no_overlapping_plays(moments)

    # Sort moments by (period, clock descending, first play_index)
    sorted_moments = sorted(moments, key=_moment_sort_key)

    # Convert to tuple for StoryOutput
    moments_tuple = tuple(sorted_moments)

    # Construct output (schema validates on construction)
    try:
        story = StoryOutput(moments=moments_tuple)
    except SchemaValidationError as e:
        raise AssemblyError(f"Schema validation failed: {e}") from e

    # Explicit validation call (idempotent but documents intent)
    validate_story(story)

    return story
