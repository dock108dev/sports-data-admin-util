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
from .split_detection import (
    find_split_points,
    count_by_reason,
    detect_narrative_dormancy,
    qualify_split_points_contextually,
    filter_redundant_segments,
)

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
    sport: str | None = None,
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
        sport: Sport identifier

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

    # Step 1: Check for narrative dormancy
    dormancy_decision = detect_narrative_dormancy(moment, events, thresholds, config)
    result.dormancy_decision = dormancy_decision
    
    logger.info(
        "mega_moment_dormancy_check",
        extra={
            "moment_id": moment.id,
            "is_dormant": dormancy_decision.is_dormant,
            "reason": dormancy_decision.reason,
            "leader_unchanged": dormancy_decision.leader_unchanged,
            "tier_unchanged": dormancy_decision.tier_unchanged,
            "margin_decided_percentage": dormancy_decision.margin_decided_percentage,
            "max_run_points": dormancy_decision.max_run_points,
        },
    )
    
    # If dormant, only allow splitting at most meaningful point (or skip entirely)
    if dormancy_decision.is_dormant:
        # Find all potential split points
        split_points = find_split_points(moment, events, thresholds, config)
        result.split_points_found = split_points
        
        if not split_points:
            result.skip_reason = f"dormant_no_split_points_{dormancy_decision.reason}"
            logger.info(
                "mega_moment_skip_dormant",
                extra={
                    "moment_id": moment.id,
                    "play_count": moment.play_count,
                    "dormancy_reason": dormancy_decision.reason,
                },
            )
            return result
        
        # For dormant moments, only use the highest priority split point
        # (most meaningful break - typically quarter or significant run)
        split_points.sort(key=lambda sp: sp.priority)
        selected_points = split_points[:1]  # Only one split for dormant moments
        result.split_points_used = selected_points
        result.split_points_skipped = split_points[1:]
        
        logger.info(
            "mega_moment_dormant_minimal_split",
            extra={
                "moment_id": moment.id,
                "split_points_found": len(split_points),
                "split_points_used": len(selected_points),
                "selected_reason": selected_points[0].split_reason if selected_points else None,
            },
        )
    else:
        # Normal flow: find and qualify split points
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

        # Step 2: Qualify split points contextually
        qualified_points = qualify_split_points_contextually(
            split_points, moment, events, thresholds, config
        )
        result.split_points_qualified = qualified_points
        
        logger.info(
            "mega_moment_split_points_qualified",
            extra={
                "moment_id": moment.id,
                "found_count": len(split_points),
                "qualified_count": len(qualified_points),
                "disqualified_count": len(split_points) - len(qualified_points),
            },
        )
        
        if not qualified_points:
            result.skip_reason = "no_qualified_split_points"
            logger.info(
                "mega_moment_no_qualified_splits",
                extra={
                    "moment_id": moment.id,
                    "play_count": moment.play_count,
                },
                )
            return result

        # Step 3: Select best split points
        selected_points = select_best_split_points(qualified_points, moment, config)
        result.split_points_used = selected_points

    # Track which points were skipped (if not already set by dormant path)
    if not result.split_points_skipped:
        used_indices = {sp.play_index for sp in selected_points}
        if result.split_points_qualified:
            result.split_points_skipped = [
                sp for sp in result.split_points_qualified if sp.play_index not in used_indices
            ]
        else:
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
                "candidates": len(split_points) if split_points else 0,
                "reasons_available": result.split_reasons_fired,
            },
        )
        return result

    result.was_split = True

    # Create segments
    segment_starts = [moment.start_play] + [sp.play_index for sp in selected_points]
    segment_ends = [sp.play_index - 1 for sp in selected_points] + [moment.end_play]

    # Import helpers
    from ..moments.helpers import get_score
    from ..lead_ladder import compute_lead_state
    from ..boundary_helpers import is_late_false_drama
    from ..moments import MomentType
    
    all_segments: list[SplitSegment] = []
    current_working_score = moment.score_before

    for i, (start, end) in enumerate(zip(segment_starts, segment_ends)):
        # Get actual scores from events at segment boundaries to ensure continuity
        if i == 0:
            score_before = moment.score_before
        else:
            # For continuity: segment i's score_before MUST equal segment i-1's score_after
            score_before = current_working_score
        
        if end >= 0 and end < len(events):
            score_after = get_score(events[end])
            # Check for score reset (0-0) at quarter boundary within the segment
            if score_after == (0, 0) and score_before != (0, 0):
                score_after = score_before
        else:
            score_after = moment.score_after

        current_working_score = score_after

        split_reason = "" if i == 0 else selected_points[i - 1].split_reason

        # PRE-VALIDATE FALSE DRAMA: Check if this segment should be suppressed
        # If it's a CUT-like segment in decided late game, we'll mark it for merging
        is_false_drama = False
        if moment.type == MomentType.CUT:
            prev_state = compute_lead_state(score_before[0], score_before[1], thresholds)
            curr_state = compute_lead_state(score_after[0], score_after[1], thresholds)
            
            if curr_state.tier < prev_state.tier:
                if start < len(events):
                    false_drama_decision = is_late_false_drama(
                        event=events[start],
                        prev_state=prev_state,
                        curr_state=curr_state,
                        crossing_type="TIER_DOWN",
                        sport=sport,
                    )
                    if false_drama_decision.suppressed:
                        is_false_drama = True
                        logger.info(
                            "segment_pre_suppressed_false_drama",
                            extra={
                                "moment_id": moment.id,
                                "segment_index": i,
                                "reason": false_drama_decision.suppressed_reason,
                            },
                        )

        segment = SplitSegment(
            start_play=start,
            end_play=end,
            play_count=end - start + 1,
            score_before=score_before,
            score_after=score_after,
            split_reason=split_reason,
            parent_moment_id=moment.id,
            segment_index=i,
            is_false_drama=is_false_drama,
        )
        all_segments.append(segment)
    
    # Step 4: Filter redundant and false drama segments
    # The filter function now handles MERGING to preserve continuity
    filtered_segments, redundancy_decisions = filter_redundant_segments(
        all_segments, events, thresholds, moment
    )
    result.segments = filtered_segments
    result.segments_rejected = [
        seg for i, seg in enumerate(all_segments)
        if i < len(redundancy_decisions) and (redundancy_decisions[i].is_redundant or all_segments[i].is_false_drama)
    ]
    result.redundancy_decisions = redundancy_decisions
    
    logger.info(
        "mega_moment_redundancy_filter",
        extra={
            "moment_id": moment.id,
            "segments_before_filter": len(all_segments),
            "segments_after_filter": len(filtered_segments),
            "rejected_count": len(result.segments_rejected),
        },
    )

    logger.info(
        "mega_moment_split_success",
        extra={
            "moment_id": moment.id,
            "original_plays": moment.play_count,
            "is_large_mega": result.is_large_mega,
            "is_dormant": dormancy_decision.is_dormant if dormancy_decision else False,
            "split_points_found": len(result.split_points_found),
            "split_points_qualified": len(result.split_points_qualified),
            "split_points_used": len(result.split_points_used),
            "segments_created": len(result.segments),
            "segments_rejected": len(result.segments_rejected),
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

    STRICT INVARIANT: Semantic splits are STRUCTURAL (readability only), not CAUSAL.
    - Semantic splits MUST inherit the parent moment's type
    - They must NEVER change type based on tier deltas
    - They must NEVER create causal moment types (FLIP, TIE, CLOSING_CONTROL, MOMENTUM_SHIFT)

    If the parent moment has a forbidden type, we normalize to NEUTRAL (structural default).
    This preserves the invariant that causal types only come from boundary detection.

    Args:
        original_type: The type that would be inherited from parent
        parent_moment: The parent moment being split

    Returns:
        A safe MomentType for semantic split usage (always structural, never causal)
    """
    from ..moments import MomentType

    type_value = original_type.value if hasattr(original_type, 'value') else str(original_type)

    # If parent type is forbidden (causal), normalize to NEUTRAL
    # This ensures semantic splits never create causal moments
    if type_value in FORBIDDEN_SEMANTIC_SPLIT_TYPES:
        return MomentType.NEUTRAL

    # Otherwise, inherit the parent type exactly
    # This ensures semantic splits are purely structural - they don't invent narrative
    return original_type


def apply_mega_moment_splitting(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
    sport: str | None = None,
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

        split_result = split_mega_moment(moment, events, thresholds, config, sport)
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

        # Only process segments that weren't merged for redundancy/false-drama
        # (split_result.segments already contains filtered and contiguous segments)
        for i, segment in enumerate(split_result.segments):
            segment_id = f"{moment.id}_seg{i+1}"

            # STRICT INVARIANT: Semantic splits inherit parent type exactly
            # They are STRUCTURAL (readability), not CAUSAL (narrative invention)
            original_type = moment.type
            original_type_value = original_type.value if hasattr(original_type, 'value') else str(original_type)

            if original_type_value in FORBIDDEN_SEMANTIC_SPLIT_TYPES:
                # Normalize forbidden causal types to NEUTRAL (structural default)
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
                # Inherit parent type exactly - no tier-delta logic
                # This ensures semantic splits don't invent narrative events
                segment_type = original_type

            # Calculate tier states for the segment
            # Note: We use parent's tier states, not recalculated from segment scores
            # This ensures semantic splits don't create false tier changes
            segment_tier_before = (
                moment.ladder_tier_before if i == 0 else moment.ladder_tier_after
            )
            segment_tier_after = moment.ladder_tier_after

            new_moment = Moment(
                id=segment_id,
                type=segment_type,
                start_play=segment.start_play,
                end_play=segment.end_play,
                play_count=segment.play_count,
                score_before=segment.score_before,
                score_after=segment.score_after,
                ladder_tier_before=segment_tier_before,
                ladder_tier_after=segment_tier_after,
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
            
            # REQUIRED DIAGNOSTICS: Each semantic split moment must include these fields
            new_moment.importance_factors = {
                "derived_from": moment.id,  # Parent moment ID
                "semantic_inheritance": True,  # Flag indicating type inheritance
                "proportion": round(proportion, 2),
                "segment_index": i,
                "split_reason": segment.split_reason or "start",
            }

            # Record if type was normalized from forbidden type
            if original_type_value in FORBIDDEN_SEMANTIC_SPLIT_TYPES:
                new_moment.importance_factors["type_normalized_from"] = original_type_value

            new_moment.is_chapter = False
            new_moment.chapter_info = {
                "is_split_segment": True,
                "parent_moment_id": moment.id,
                "segment_index": i,
                "total_segments": len(split_result.segments),
                "split_reason": segment.split_reason,
                "derived_from": moment.id,  # Also in chapter_info for consistency
                "semantic_inheritance": True,  # Type inherited from parent
            }

            output_moments.append(new_moment)
            result.total_segments_created += 1

    output_moments.sort(key=lambda m: m.start_play)
    result.moments = output_moments

    # Calculate dormancy and redundancy statistics
    dormant_count = sum(
        1 for sr in result.split_results
        if sr.dormancy_decision and sr.dormancy_decision.is_dormant
    )
    redundant_segments_count = sum(
        len(sr.segments_rejected) for sr in result.split_results
    )
    
    logger.info(
        "mega_moment_splitting_applied",
        extra={
            "mega_moments_found": result.mega_moments_found,
            "mega_moments_split": result.mega_moments_split,
            "large_mega_moments_found": result.large_mega_moments_found,
            "large_mega_moments_split": result.large_mega_moments_split,
            "dormant_moments_detected": dormant_count,
            "total_segments_created": result.total_segments_created,
            "redundant_segments_rejected": redundant_segments_count,
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


def assert_no_semantic_split_causal_types(moments: list["Moment"]) -> None:
    """
    Defensive assertion: Verify no semantic_split moments have causal types.

    This is a sanity check that can be called after construction to ensure
    the invariant is maintained: Causal moment types (FLIP, TIE, CLOSING_CONTROL,
    MOMENTUM_SHIFT) can ONLY originate from boundary detection, never from
    semantic construction.

    Args:
        moments: List of moments to validate

    Raises:
        AssertionError: If any semantic_split moment has a forbidden causal type
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
            "semantic_split_causal_type_invariant_violated",
            extra={
                "violations_count": len(violations),
                "violations": violations,
                "forbidden_types": list(FORBIDDEN_SEMANTIC_SPLIT_TYPES),
            },
        )
        raise AssertionError(
            f"Invariant violated: {len(violations)} semantic_split moment(s) have "
            f"forbidden causal types. Forbidden types: {list(FORBIDDEN_SEMANTIC_SPLIT_TYPES)}. "
            f"First violation: {violations[0]}"
        )
