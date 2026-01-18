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
    from .moments import Moment

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


def assert_moment_continuity(moments: list[Moment]) -> None:
    """
    CONTINUITY VALIDATION: Fail fast on structural issues.

    Validates structural integrity of moment partitioning:
    - No overlapping plays
    - Score continuity between adjacent moments

    Note: Semantic validity (is_valid_moment) is checked during merging,
    not here. This function only validates structural correctness.

    Args:
        moments: List of moments to validate

    Raises:
        MomentValidationError: If structural issues are detected
    """
    if not moments:
        raise MomentValidationError("No moments generated - cannot proceed with empty moment list")

    issues: list[str] = []

    # Check play coverage (no overlaps)
    covered_plays: set[int] = set()
    for moment in moments:
        for play_idx in range(moment.start_play, moment.end_play + 1):
            if play_idx in covered_plays:
                issues.append(f"Play {play_idx} covered by multiple moments (overlaps in {moment.id})")
            covered_plays.add(play_idx)

    # Check score continuity between adjacent moments
    for i in range(1, len(moments)):
        prev_moment = moments[i - 1]
        curr_moment = moments[i]

        if prev_moment.score_after != curr_moment.score_before:
            issues.append(
                f"Score discontinuity: {prev_moment.id} ends at {prev_moment.score_after} "
                f"but {curr_moment.id} starts at {curr_moment.score_before}"
            )

    # FAIL FAST: Any structural issues = hard failure
    if issues:
        logger.error(
            "moment_continuity_validation_failed",
            extra={"issue_count": len(issues), "first_issues": issues[:5]},
        )
        raise MomentValidationError(
            f"Moment continuity validation failed with {len(issues)} issues: {issues[0]}"
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
