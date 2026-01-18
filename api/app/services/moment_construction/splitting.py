"""Task 3.3: Semantic mega-moment splitting.

Splits oversized moments at semantic break points (runs, tier changes,
timeouts) to improve readability.

IMPORTANT INVARIANT:
Semantic splits must NEVER produce FLIP or TIE moments.
FLIP and TIE moments can ONLY originate from boundary detection
(`detect_boundaries()`), never from semantic construction.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence, TYPE_CHECKING

from .config import SplitConfig, DEFAULT_SPLIT_CONFIG

# Re-export types from split_types
from .split_types import (
    SplitPoint,
    SplitSegment,
    MegaMomentSplitResult,
    SemanticSplitTypeNormalization,
    SplittingResult,
    FORBIDDEN_SEMANTIC_SPLIT_TYPES,
    DEFAULT_SEMANTIC_SPLIT_TYPE,
)

# Re-export functions from split_detection
from .split_detection import find_split_points, count_by_reason

# Re-export functions from split_selection
from .split_selection import (
    select_best_split_points,
    compute_ideal_split_locations,
    is_near_ideal_location,
    select_fallback_splits,
)

if TYPE_CHECKING:
    from ..moments import Moment, MomentType

logger = logging.getLogger(__name__)


def split_mega_moment(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> MegaMomentSplitResult:
    """Split a single mega-moment into readable segments.

    Mega-moments (50+ plays) are split into 2-3 readable chapters
    using semantic boundaries. Large mega-moments (80+ plays) get
    more aggressive splitting with balanced segment sizes.

    Args:
        moment: The mega-moment to split
        events: All timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration

    Returns:
        MegaMomentSplitResult with segments and diagnostics
    """
    result = MegaMomentSplitResult(
        original_moment_id=moment.id,
        original_play_count=moment.play_count,
        is_large_mega=moment.play_count >= config.large_mega_threshold,
    )

    if moment.play_count < config.mega_moment_threshold:
        result.skip_reason = "below_threshold"
        logger.debug(
            "mega_moment_skip",
            extra={
                "moment_id": moment.id,
                "play_count": moment.play_count,
                "threshold": config.mega_moment_threshold,
                "reason": "below_threshold",
            },
        )
        return result

    # Find all potential split points
    split_points = find_split_points(moment, events, thresholds, config)
    result.split_points_found = split_points

    # Record which semantic rules fired
    result.split_reasons_fired = list(set(sp.split_reason for sp in split_points))

    if not split_points:
        result.skip_reason = "no_split_points_found"
        logger.info(
            "mega_moment_no_splits_found",
            extra={
                "moment_id": moment.id,
                "play_count": moment.play_count,
                "is_large_mega": result.is_large_mega,
            },
        )
        return result

    # Select best split points
    selected_points = select_best_split_points(split_points, moment, config)
    result.split_points_used = selected_points

    # Track which points were skipped
    used_indices = {sp.play_index for sp in selected_points}
    result.split_points_skipped = [
        sp for sp in split_points if sp.play_index not in used_indices
    ]

    if not selected_points:
        result.skip_reason = "no_valid_split_points"
        logger.info(
            "mega_moment_no_valid_splits",
            extra={
                "moment_id": moment.id,
                "play_count": moment.play_count,
                "candidates": len(split_points),
                "reasons_available": result.split_reasons_fired,
            },
        )
        return result

    result.was_split = True

    # Create segments
    segment_starts = [moment.start_play] + [sp.play_index for sp in selected_points]
    segment_ends = [sp.play_index - 1 for sp in selected_points] + [moment.end_play]

    for i, (start, end) in enumerate(zip(segment_starts, segment_ends)):
        score_before = (
            moment.score_before if i == 0 else selected_points[i - 1].score_at_split
        )
        score_after = (
            selected_points[i].score_at_split
            if i < len(selected_points)
            else moment.score_after
        )

        split_reason = "" if i == 0 else selected_points[i - 1].split_reason

        segment = SplitSegment(
            start_play=start,
            end_play=end,
            play_count=end - start + 1,
            score_before=score_before,
            score_after=score_after,
            split_reason=split_reason,
            parent_moment_id=moment.id,
            segment_index=i,
        )
        result.segments.append(segment)

    logger.info(
        "mega_moment_split_success",
        extra={
            "moment_id": moment.id,
            "original_plays": moment.play_count,
            "is_large_mega": result.is_large_mega,
            "segments_created": len(result.segments),
            "segment_sizes": [s.play_count for s in result.segments],
            "split_reasons_used": [sp.split_reason for sp in selected_points],
        },
    )

    return result


def _get_safe_semantic_split_type(
    original_type: "MomentType",
    parent_moment: "Moment",
) -> "MomentType":
    """
    Get a safe moment type for semantic splits.

    INVARIANT: Semantic splits must NEVER produce FLIP or TIE moments.
    These types can only originate from boundary detection.

    If the parent moment is FLIP or TIE, the semantic split segments
    should be typed based on the tier change direction:
    - If tier increased: LEAD_BUILD
    - If tier decreased: CUT
    - Otherwise: NEUTRAL

    Args:
        original_type: The type that would be inherited from parent
        parent_moment: The parent moment being split

    Returns:
        A safe MomentType for semantic split usage
    """
    from ..moments import MomentType

    type_value = original_type.value if hasattr(original_type, 'value') else str(original_type)

    if type_value not in FORBIDDEN_SEMANTIC_SPLIT_TYPES:
        return original_type

    # Determine replacement type based on tier dynamics
    tier_delta = parent_moment.ladder_tier_after - parent_moment.ladder_tier_before

    if tier_delta > 0:
        return MomentType.LEAD_BUILD
    elif tier_delta < 0:
        return MomentType.CUT
    else:
        return MomentType.NEUTRAL


def apply_mega_moment_splitting(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> SplittingResult:
    """Apply semantic splitting to all mega-moments.

    Splits mega-moments (50+ plays) into 2-3 readable chapters using
    semantic boundaries like runs, tier changes, and quarter transitions.
    Large mega-moments (80+ plays) get more aggressive splitting with
    balanced segment sizes.

    IMPORTANT INVARIANT:
    Semantic splits NEVER produce FLIP or TIE moments.
    If a parent moment has type FLIP or TIE, the split segments
    are normalized to NEUTRAL, LEAD_BUILD, or CUT based on tier dynamics.

    Args:
        moments: Input moments (after selection and quotas)
        events: All timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration

    Returns:
        SplittingResult with split moments and diagnostics
    """
    from ..moments import Moment, MomentType, MomentReason

    result = SplittingResult()
    output_moments: list[Moment] = []

    for moment in moments:
        if moment.play_count < config.mega_moment_threshold:
            output_moments.append(moment)
            continue

        result.mega_moments_found += 1

        # Track large mega-moments separately
        if moment.play_count >= config.large_mega_threshold:
            result.large_mega_moments_found += 1

        split_result = split_mega_moment(moment, events, thresholds, config)
        result.split_results.append(split_result)

        if not split_result.was_split:
            output_moments.append(moment)
            continue

        result.mega_moments_split += 1

        # Track large mega-moments that were successfully split
        if split_result.is_large_mega:
            result.large_mega_moments_split += 1

        # Track which split reasons were used
        for sp in split_result.split_points_used:
            result.split_reasons_summary[sp.split_reason] = (
                result.split_reasons_summary.get(sp.split_reason, 0) + 1
            )

        for i, segment in enumerate(split_result.segments):
            segment_id = f"{moment.id}_seg{i+1}"

            # INVARIANT ENFORCEMENT: Semantic splits must NEVER be FLIP or TIE
            original_type = moment.type
            original_type_value = original_type.value if hasattr(original_type, 'value') else str(original_type)

            if original_type_value in FORBIDDEN_SEMANTIC_SPLIT_TYPES:
                # Normalize the type - FLIP/TIE are forbidden for semantic splits
                safe_type = _get_safe_semantic_split_type(original_type, moment)

                # Record the normalization for diagnostics
                normalization = SemanticSplitTypeNormalization(
                    moment_id=segment_id,
                    original_type=original_type_value,
                    corrected_type=safe_type.value,
                    parent_moment_id=moment.id,
                    segment_index=i,
                    reason=f"semantic_split_cannot_be_{original_type_value}",
                )
                result.type_normalizations.append(normalization)

                logger.info(
                    "semantic_split_type_normalized",
                    extra={
                        "moment_id": segment_id,
                        "original_type": original_type_value,
                        "corrected_type": safe_type.value,
                        "parent_moment_id": moment.id,
                        "segment_index": i,
                    },
                )

                segment_type = safe_type
            else:
                segment_type = original_type

            new_moment = Moment(
                id=segment_id,
                type=segment_type,
                start_play=segment.start_play,
                end_play=segment.end_play,
                play_count=segment.play_count,
                score_before=segment.score_before,
                score_after=segment.score_after,
                ladder_tier_before=(
                    moment.ladder_tier_before if i == 0 else moment.ladder_tier_after
                ),
                ladder_tier_after=moment.ladder_tier_after,
                teams=moment.teams,
                team_in_control=moment.team_in_control,
            )

            if segment.split_reason:
                narrative = {
                    "tier_change": "game dynamics shifted",
                    "quarter": "new quarter began",
                    "run_start": "momentum swing started",
                    "pressure_end": "sustained push concluded",
                    "timeout_after_swing": "regrouping after swing",
                    "drought_end": "scoring resumed",
                }.get(segment.split_reason, "narrative continuation")
            else:
                narrative = "opening phase"

            new_moment.reason = MomentReason(
                trigger="semantic_split",
                control_shift=moment.team_in_control,
                narrative_delta=narrative,
            )

            proportion = segment.play_count / moment.play_count
            new_moment.importance_score = moment.importance_score * proportion
            new_moment.importance_factors = {
                "inherited_from": moment.id,
                "proportion": round(proportion, 2),
                "segment_index": i,
                "split_reason": segment.split_reason or "start",
            }

            # Record if type was normalized
            if original_type_value in FORBIDDEN_SEMANTIC_SPLIT_TYPES:
                new_moment.importance_factors["type_normalized_from"] = original_type_value

            new_moment.is_chapter = False
            new_moment.chapter_info = {
                "is_split_segment": True,
                "parent_moment_id": moment.id,
                "segment_index": i,
                "total_segments": len(split_result.segments),
                "split_reason": segment.split_reason,
            }

            output_moments.append(new_moment)
            result.total_segments_created += 1

    output_moments.sort(key=lambda m: m.start_play)
    result.moments = output_moments

    logger.info(
        "mega_moment_splitting_applied",
        extra={
            "mega_moments_found": result.mega_moments_found,
            "mega_moments_split": result.mega_moments_split,
            "large_mega_moments_found": result.large_mega_moments_found,
            "large_mega_moments_split": result.large_mega_moments_split,
            "total_segments_created": result.total_segments_created,
            "split_reasons_summary": result.split_reasons_summary,
            "types_normalized_count": len(result.type_normalizations),
            "original_count": len(moments),
            "final_count": len(output_moments),
        },
    )

    # Log summary if any types were normalized
    if result.type_normalizations:
        logger.info(
            "semantic_split_type_normalization_summary",
            extra={
                "total_normalized": len(result.type_normalizations),
                "normalizations": [
                    {
                        "moment_id": n.moment_id,
                        "from": n.original_type,
                        "to": n.corrected_type,
                    }
                    for n in result.type_normalizations
                ],
            },
        )

    return result


def assert_no_semantic_split_flip_tie(moments: list["Moment"]) -> None:
    """
    Defensive assertion: Verify no semantic_split moments have FLIP or TIE type.

    This is a sanity check that can be called after construction to ensure
    the invariant is maintained: FLIP and TIE moments can ONLY originate
    from boundary detection, never from semantic construction.

    Args:
        moments: List of moments to validate

    Raises:
        AssertionError: If any semantic_split moment has FLIP or TIE type
    """
    violations: list[dict[str, Any]] = []

    for moment in moments:
        if moment.reason is None:
            continue

        if moment.reason.trigger != "semantic_split":
            continue

        type_value = moment.type.value if hasattr(moment.type, 'value') else str(moment.type)

        if type_value in FORBIDDEN_SEMANTIC_SPLIT_TYPES:
            violations.append({
                "moment_id": moment.id,
                "type": type_value,
                "trigger": moment.reason.trigger,
            })

    if violations:
        logger.error(
            "semantic_split_flip_tie_invariant_violated",
            extra={
                "violations_count": len(violations),
                "violations": violations,
            },
        )
        raise AssertionError(
            f"Invariant violated: {len(violations)} semantic_split moment(s) have "
            f"forbidden type FLIP or TIE. First violation: {violations[0]}"
        )
