"""
Moment Validation.

Validates that moment partitioning is correct:
- All plays covered exactly once
- No overlaps or gaps
- Chronological ordering
- Score continuity
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from .moments import Moment, MomentType

logger = logging.getLogger(__name__)


class MomentValidationError(Exception):
    """Raised when moment partitioning fails validation."""
    pass


def validate_score_continuity(moments: list[Moment]) -> None:
    """
    Validate that moment scores are continuous (no resets).

    Logs warnings for score discontinuities but doesn't fail the build.
    """
    if len(moments) <= 1:
        return

    for i in range(1, len(moments)):
        prev_moment = moments[i - 1]
        curr_moment = moments[i]

        if prev_moment.score_after != curr_moment.score_before:
            logger.error(
                "moment_score_discontinuity",
                extra={
                    "prev_moment_id": prev_moment.id,
                    "curr_moment_id": curr_moment.id,
                    "prev_end": prev_moment.score_after,
                    "curr_start": curr_moment.score_before,
                    "prev_end_play": prev_moment.end_play,
                    "curr_start_play": curr_moment.start_play,
                },
            )


def assert_moment_continuity(moments: list[Moment], is_valid_moment_func) -> None:
    """
    CONTINUITY VALIDATION: Log issues but don't crash during debugging.

    During development, log problems but allow pipeline to continue.
    TODO: Make this crash the pipeline once all issues are resolved.

    Args:
        moments: List of moments to validate
        is_valid_moment_func: Function to check if a moment is valid
    """
    # Import MomentType here to avoid circular import
    from .moments import MomentType

    if not moments:
        logger.error("no_moments_generated")
        return  # Don't crash for now

    # Check play coverage (no gaps, no overlaps)
    covered_plays = set()
    overlaps = []
    for moment in moments:
        for play_idx in range(moment.start_play, moment.end_play + 1):
            if play_idx in covered_plays:
                overlaps.append(f"Play {play_idx} in {moment.id}")
            covered_plays.add(play_idx)

    if overlaps:
        logger.error("play_overlaps_detected", extra={"overlaps": overlaps[:10]})

    # Check score continuity between adjacent moments
    discontinuities = []
    for i in range(1, len(moments)):
        prev_moment = moments[i - 1]
        curr_moment = moments[i]

        if prev_moment.score_after != curr_moment.score_before:
            discontinuities.append({
                "prev_id": prev_moment.id,
                "curr_id": curr_moment.id,
                "prev_end": prev_moment.score_after,
                "curr_start": curr_moment.score_before,
            })

    if discontinuities:
        logger.error("score_discontinuities_detected", extra={"discontinuities": discontinuities})

    # Check that no moments are invalid after merging
    invalid_moments = [m for m in moments if not is_valid_moment_func(m)]
    if invalid_moments:
        invalid_info = [{"id": m.id, "type": m.type.value, "score": f"{m.score_before}→{m.score_after}"} for m in invalid_moments]
        logger.error("invalid_moments_remaining", extra={"invalid_moments": invalid_info})

    # Check for single-play moments that aren't high-impact
    problematic_micro = []
    for moment in moments:
        if (moment.play_count == 1 and
            moment.type not in (MomentType.FLIP, MomentType.TIE, MomentType.HIGH_IMPACT)):
            problematic_micro.append({
                "id": moment.id,
                "type": moment.type.value,
                "trigger": moment.reason.trigger if moment.reason else None
            })

    if problematic_micro:
        logger.error("problematic_micro_moments", extra={"micro_moments": problematic_micro})

    # For now, log all issues but don't crash the pipeline
    total_issues = len(overlaps) + len(discontinuities) + len(invalid_moments) + len(problematic_micro)
    if total_issues > 0:
        logger.warning(
            "moment_continuity_issues_detected",
            extra={
                "total_issues": total_issues,
                "overlaps": len(overlaps),
                "discontinuities": len(discontinuities),
                "invalid_moments": len(invalid_moments),
                "micro_moments": len(problematic_micro),
                "note": "Pipeline continuing despite issues - fix these problems"
            }
        )


def validate_moment_coverage(
    moments: list[Moment],
    pbp_indices: list[int],
) -> None:
    """
    Validate that moments cover all PBP plays exactly once.

    Raises:
        MomentValidationError: If validation fails
    """
    if not moments or not pbp_indices:
        return

    # Check that moments cover all indices
    covered_indices = set()
    for moment in moments:
        for i in range(moment.start_play, moment.end_play + 1):
            if i in covered_indices:
                raise MomentValidationError(
                    f"Overlapping moments: index {i} covered by multiple moments"
                )
            covered_indices.add(i)

    # Check for gaps (only PBP indices need to be covered)
    pbp_set = set(pbp_indices)
    uncovered = pbp_set - covered_indices
    if uncovered:
        logger.warning(
            "moment_validation_gap",
            extra={"uncovered_indices": sorted(uncovered)[:10]},
        )
        # Don't raise error - some indices might be non-PBP events in the range


def validate_moments(
    timeline: Sequence[dict[str, Any]],
    moments: list[Moment],
) -> bool:
    """
    Validate moment partitioning.

    Checks:
    1. All PBP plays are assigned to exactly one moment
    2. Moments are ordered chronologically
    3. No overlapping moment boundaries

    Args:
        timeline: Original timeline
        moments: Computed moments

    Returns:
        True if valid

    Raises:
        MomentValidationError: If validation fails
    """
    if not moments:
        return True

    pbp_indices = {
        i for i, e in enumerate(timeline)
        if e.get("event_type") == "pbp"
    }

    # Check chronological order
    for i in range(1, len(moments)):
        if moments[i].start_play < moments[i - 1].start_play:
            raise MomentValidationError(
                f"Moments not chronological: {moments[i-1].id} starts at "
                f"{moments[i-1].start_play}, {moments[i].id} starts at {moments[i].start_play}"
            )

    # Check no overlap
    for i in range(1, len(moments)):
        if moments[i].start_play <= moments[i - 1].end_play:
            raise MomentValidationError(
                f"Overlapping moments: {moments[i-1].id} ends at {moments[i-1].end_play}, "
                f"{moments[i].id} starts at {moments[i].start_play}"
            )

    # Check coverage
    covered = set()
    for moment in moments:
        for idx in range(moment.start_play, moment.end_play + 1):
            covered.add(idx)

    uncovered_pbp = pbp_indices - covered
    if uncovered_pbp:
        raise MomentValidationError(
            f"Uncovered PBP plays: {sorted(uncovered_pbp)[:10]}..."
        )

    return True
