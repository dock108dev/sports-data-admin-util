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
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import SplitConfig, DEFAULT_SPLIT_CONFIG

if TYPE_CHECKING:
    from ..moments import Moment, MomentType

logger = logging.getLogger(__name__)


# Types that are FORBIDDEN for semantic splits
# These can only originate from boundary detection
FORBIDDEN_SEMANTIC_SPLIT_TYPES: frozenset[str] = frozenset({
    "FLIP",
    "TIE",
})

# Default type to normalize forbidden types to
DEFAULT_SEMANTIC_SPLIT_TYPE = "NEUTRAL"


@dataclass
class SplitPoint:
    """A potential split point within a mega-moment.
    
    Split reasons:
    - tier_change: Lead Ladder tier changed significantly
    - quarter: Quarter boundary transition
    - run_start: A scoring run began
    - pressure_end: Sustained pressure by one team ended
    - timeout_after_swing: Timeout called after momentum swing
    - drought_end: Scoring drought ended
    """

    play_index: int
    split_reason: str
    score_at_split: tuple[int, int] = (0, 0)
    tier_at_split: int = 0
    priority: int = 99  # Lower is higher priority
    
    # Tier change specifics
    tier_before: int = 0
    tier_after: int = 0
    
    # Run specifics
    run_team: str | None = None
    run_points: int = 0
    
    # Quarter specifics
    quarter_before: int = 0
    quarter_after: int = 0
    
    # Pressure specifics
    pressure_team: str | None = None
    pressure_points: int = 0
    pressure_plays: int = 0
    
    # Drought specifics
    drought_plays: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = {
            "play_index": self.play_index,
            "split_reason": self.split_reason,
            "score_at_split": self.score_at_split,
            "tier_at_split": self.tier_at_split,
            "priority": self.priority,
        }
        
        # Add reason-specific fields
        if self.split_reason == "tier_change":
            result["tier_before"] = self.tier_before
            result["tier_after"] = self.tier_after
        elif self.split_reason == "run_start":
            result["run_team"] = self.run_team
            result["run_points"] = self.run_points
        elif self.split_reason == "quarter":
            result["quarter_before"] = self.quarter_before
            result["quarter_after"] = self.quarter_after
        elif self.split_reason == "pressure_end":
            result["pressure_team"] = self.pressure_team
            result["pressure_points"] = self.pressure_points
            result["pressure_plays"] = self.pressure_plays
        elif self.split_reason == "drought_end":
            result["drought_plays"] = self.drought_plays
            
        return result


@dataclass
class SplitSegment:
    """A segment created from splitting a mega-moment."""

    start_play: int
    end_play: int
    play_count: int
    score_before: tuple[int, int] = (0, 0)
    score_after: tuple[int, int] = (0, 0)
    split_reason: str = ""
    parent_moment_id: str = ""
    segment_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_play": self.start_play,
            "end_play": self.end_play,
            "play_count": self.play_count,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "split_reason": self.split_reason,
            "parent_moment_id": self.parent_moment_id,
            "segment_index": self.segment_index,
        }


@dataclass
class MegaMomentSplitResult:
    """Result of splitting a single mega-moment.
    
    Contains detailed diagnostics about:
    - Why splits were applied or skipped
    - Which semantic rules fired
    - Final segment composition
    """

    original_moment_id: str
    original_play_count: int
    was_split: bool = False
    is_large_mega: bool = False  # 80+ plays
    split_points_found: list[SplitPoint] = field(default_factory=list)
    split_points_used: list[SplitPoint] = field(default_factory=list)
    split_points_skipped: list[SplitPoint] = field(default_factory=list)
    segments: list[SplitSegment] = field(default_factory=list)
    skip_reason: str | None = None
    split_reasons_fired: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # Count points found by reason
        found_by_reason: dict[str, int] = {}
        for sp in self.split_points_found:
            found_by_reason[sp.split_reason] = found_by_reason.get(sp.split_reason, 0) + 1
        
        return {
            "original_moment_id": self.original_moment_id,
            "original_play_count": self.original_play_count,
            "was_split": self.was_split,
            "is_large_mega": self.is_large_mega,
            "split_points_found_count": len(self.split_points_found),
            "split_points_found_by_reason": found_by_reason,
            "split_points_used": [sp.to_dict() for sp in self.split_points_used],
            "split_points_skipped_count": len(self.split_points_skipped),
            "segments": [s.to_dict() for s in self.segments],
            "segment_play_counts": [s.play_count for s in self.segments],
            "skip_reason": self.skip_reason,
            "split_reasons_fired": self.split_reasons_fired,
        }


@dataclass
class SemanticSplitTypeNormalization:
    """Record of a type normalization for a semantic split moment.
    
    Tracks when a FLIP or TIE type is corrected to a valid semantic split type.
    This ensures FLIP/TIE moments only originate from boundary detection.
    """
    moment_id: str
    original_type: str
    corrected_type: str
    parent_moment_id: str
    segment_index: int
    reason: str = "forbidden_type_for_semantic_split"

    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "original_type": self.original_type,
            "corrected_type": self.corrected_type,
            "parent_moment_id": self.parent_moment_id,
            "segment_index": self.segment_index,
            "reason": self.reason,
        }


@dataclass
class SplittingResult:
    """Result of mega-moment splitting pass.
    
    Contains summary statistics and detailed results for each mega-moment.
    """

    moments: list["Moment"] = field(default_factory=list)
    mega_moments_found: int = 0
    mega_moments_split: int = 0
    large_mega_moments_found: int = 0
    large_mega_moments_split: int = 0
    total_segments_created: int = 0
    split_results: list[MegaMomentSplitResult] = field(default_factory=list)
    type_normalizations: list[SemanticSplitTypeNormalization] = field(default_factory=list)
    split_reasons_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mega_moments_found": self.mega_moments_found,
            "mega_moments_split": self.mega_moments_split,
            "large_mega_moments_found": self.large_mega_moments_found,
            "large_mega_moments_split": self.large_mega_moments_split,
            "total_segments_created": self.total_segments_created,
            "split_reasons_summary": self.split_reasons_summary,
            "split_results": [r.to_dict() for r in self.split_results],
            "type_normalizations": [n.to_dict() for n in self.type_normalizations],
            "types_normalized_count": len(self.type_normalizations),
        }


def find_split_points(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> list[SplitPoint]:
    """Find semantic split points within a mega-moment.
    
    Scans the moment for natural narrative break points:
    - Tier changes (Lead Ladder crossings)
    - Quarter transitions
    - Scoring runs beginning
    - Sustained pressure periods ending
    - Timeouts after momentum swings
    - Scoring drought endings
    
    Args:
        moment: The mega-moment to analyze
        events: All timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration
    
    Returns:
        List of potential split points, sorted by play index
    """
    from ..lead_ladder import compute_lead_state

    split_points: list[SplitPoint] = []

    # Build list of PBP events within this moment
    moment_events: list[tuple[int, dict[str, Any]]] = []
    for idx in range(moment.start_play, moment.end_play + 1):
        if idx < len(events):
            event = events[idx]
            if event.get("event_type") == "pbp":
                moment_events.append((idx, event))

    if len(moment_events) < config.min_segment_plays * 2:
        logger.debug(
            "split_points_skipped_too_few_events",
            extra={
                "moment_id": moment.id,
                "event_count": len(moment_events),
                "min_required": config.min_segment_plays * 2,
            },
        )
        return []

    # State tracking
    prev_tier = moment.ladder_tier_before
    prev_quarter: int | None = None
    run_tracker: dict[str, int] = {"home": 0, "away": 0}
    last_scorer: str | None = None
    
    # Pressure tracking
    pressure_start_idx: int | None = None
    pressure_start_score: tuple[int, int] = (0, 0)
    pressure_team: str | None = None
    pressure_plays: int = 0
    
    # Drought tracking
    last_scoring_idx: int = 0
    
    for local_idx, (play_idx, event) in enumerate(moment_events):
        # Skip edges to ensure minimum segment size
        if local_idx < config.min_segment_plays:
            continue
        if local_idx > len(moment_events) - config.min_segment_plays:
            continue

        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        state = compute_lead_state(home_score, away_score, thresholds)
        quarter = event.get("quarter", 1) or 1

        # --- Quarter transition detection ---
        if config.enable_quarter_splits and prev_quarter is not None:
            if quarter != prev_quarter:
                split_points.append(
                    SplitPoint(
                        play_index=play_idx,
                        split_reason="quarter",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        priority=config.priority_quarter,
                        quarter_before=prev_quarter,
                        quarter_after=quarter,
                    )
                )
                logger.debug(
                    "split_point_found_quarter",
                    extra={
                        "moment_id": moment.id,
                        "play_index": play_idx,
                        "quarter_before": prev_quarter,
                        "quarter_after": quarter,
                    },
                )
        prev_quarter = quarter

        # --- Tier change detection ---
        if config.enable_tier_splits:
            tier_delta = abs(state.tier - prev_tier)
            if tier_delta >= config.tier_change_min_delta:
                split_points.append(
                    SplitPoint(
                        play_index=play_idx,
                        split_reason="tier_change",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        priority=config.priority_tier_change,
                        tier_before=prev_tier,
                        tier_after=state.tier,
                    )
                )
                logger.debug(
                    "split_point_found_tier_change",
                    extra={
                        "moment_id": moment.id,
                        "play_index": play_idx,
                        "tier_before": prev_tier,
                        "tier_after": state.tier,
                    },
                )
                prev_tier = state.tier

        # --- Run detection ---
        if config.enable_run_splits:
            points_scored = event.get("points_scored", 0) or 0
            scoring_team = event.get("scoring_team")

            if points_scored > 0 and scoring_team:
                run_tracker[scoring_team] = (
                    run_tracker.get(scoring_team, 0) + points_scored
                )
                other_team = "away" if scoring_team == "home" else "home"

                if last_scorer != scoring_team:
                    run_tracker = {scoring_team: points_scored, other_team: 0}

                if run_tracker.get(scoring_team, 0) >= config.run_min_points:
                    split_points.append(
                        SplitPoint(
                            play_index=play_idx,
                            split_reason="run_start",
                            score_at_split=(home_score, away_score),
                            tier_at_split=state.tier,
                            priority=config.priority_run_start,
                            run_team=scoring_team,
                            run_points=run_tracker.get(scoring_team, 0),
                        )
                    )
                    logger.debug(
                        "split_point_found_run",
                        extra={
                            "moment_id": moment.id,
                            "play_index": play_idx,
                            "run_team": scoring_team,
                            "run_points": run_tracker.get(scoring_team, 0),
                        },
                    )
                    run_tracker = {"home": 0, "away": 0}

                last_scorer = scoring_team
                last_scoring_idx = local_idx

        # --- Sustained pressure detection ---
        if config.enable_pressure_splits:
            points_scored = event.get("points_scored", 0) or 0
            scoring_team = event.get("scoring_team")
            
            if points_scored > 0 and scoring_team:
                if pressure_team is None:
                    # Start tracking pressure
                    pressure_start_idx = local_idx
                    pressure_start_score = (home_score - points_scored if scoring_team == "home" else home_score,
                                           away_score - points_scored if scoring_team == "away" else away_score)
                    pressure_team = scoring_team
                    pressure_plays = 1
                elif scoring_team == pressure_team:
                    # Continue pressure
                    pressure_plays += 1
                else:
                    # Pressure ended - check if it was significant
                    if pressure_start_idx is not None:
                        pressure_point_diff = (
                            (home_score - pressure_start_score[0]) if pressure_team == "home"
                            else (away_score - pressure_start_score[1])
                        )
                        
                        if (pressure_plays >= config.pressure_min_plays and
                            pressure_point_diff >= config.pressure_min_point_diff):
                            split_points.append(
                                SplitPoint(
                                    play_index=play_idx,
                                    split_reason="pressure_end",
                                    score_at_split=(home_score, away_score),
                                    tier_at_split=state.tier,
                                    priority=config.priority_pressure,
                                    pressure_team=pressure_team,
                                    pressure_points=pressure_point_diff,
                                    pressure_plays=pressure_plays,
                                )
                            )
                            logger.debug(
                                "split_point_found_pressure_end",
                                extra={
                                    "moment_id": moment.id,
                                    "play_index": play_idx,
                                    "pressure_team": pressure_team,
                                    "pressure_points": pressure_point_diff,
                                    "pressure_plays": pressure_plays,
                                },
                            )
                    
                    # Reset and start new pressure tracking
                    pressure_start_idx = local_idx
                    pressure_start_score = (home_score - points_scored if scoring_team == "home" else home_score,
                                           away_score - points_scored if scoring_team == "away" else away_score)
                    pressure_team = scoring_team
                    pressure_plays = 1

        # --- Timeout after swing detection ---
        if config.enable_timeout_splits:
            event_type = event.get("event_type_detail", "").lower()
            if "timeout" in event_type:
                recent_swing = False
                for j in range(max(0, local_idx - 5), local_idx):
                    _, recent_event = moment_events[j]
                    recent_home = recent_event.get("home_score", 0) or 0
                    recent_away = recent_event.get("away_score", 0) or 0
                    recent_state = compute_lead_state(
                        recent_home, recent_away, thresholds
                    )
                    if abs(recent_state.tier - state.tier) >= 1:
                        recent_swing = True
                        break

                if recent_swing:
                    split_points.append(
                        SplitPoint(
                            play_index=play_idx,
                            split_reason="timeout_after_swing",
                            score_at_split=(home_score, away_score),
                            tier_at_split=state.tier,
                            priority=config.priority_timeout,
                        )
                    )
                    logger.debug(
                        "split_point_found_timeout",
                        extra={
                            "moment_id": moment.id,
                            "play_index": play_idx,
                        },
                    )

        # --- Scoring drought detection ---
        if config.enable_drought_splits:
            plays_since_score = local_idx - last_scoring_idx
            points_scored = event.get("points_scored", 0) or 0
            
            if points_scored > 0 and plays_since_score >= config.drought_min_plays:
                split_points.append(
                    SplitPoint(
                        play_index=play_idx,
                        split_reason="drought_end",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        priority=config.priority_drought,
                        drought_plays=plays_since_score,
                    )
                )
                logger.debug(
                    "split_point_found_drought_end",
                    extra={
                        "moment_id": moment.id,
                        "play_index": play_idx,
                        "drought_plays": plays_since_score,
                    },
                )

        prev_tier = state.tier

    # Deduplicate by play index, keeping highest priority (lowest number)
    unique_points: dict[int, SplitPoint] = {}
    for sp in split_points:
        if sp.play_index not in unique_points:
            unique_points[sp.play_index] = sp
        elif sp.priority < unique_points[sp.play_index].priority:
            unique_points[sp.play_index] = sp

    result = sorted(unique_points.values(), key=lambda sp: sp.play_index)
    
    logger.debug(
        "split_points_found",
        extra={
            "moment_id": moment.id,
            "total_found": len(result),
            "by_reason": _count_by_reason(result),
        },
    )
    
    return result


def _count_by_reason(split_points: list[SplitPoint]) -> dict[str, int]:
    """Count split points by reason for diagnostics."""
    counts: dict[str, int] = {}
    for sp in split_points:
        counts[sp.split_reason] = counts.get(sp.split_reason, 0) + 1
    return counts


def select_best_split_points(
    split_points: list[SplitPoint],
    moment: "Moment",
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> list[SplitPoint]:
    """Select the best split points respecting constraints.
    
    Selection strategy:
    1. For large mega-moments (80+ plays), aim for balanced segment sizes
    2. Prioritize by split reason (tier_change > quarter > run_start > etc.)
    3. Enforce minimum segment sizes and gaps between splits
    
    Args:
        split_points: All candidate split points
        moment: The mega-moment being split
        config: Split configuration
    
    Returns:
        Selected split points, sorted by play index
    """
    if not split_points:
        return []

    is_large_mega = moment.play_count >= config.large_mega_threshold
    
    # For large mega-moments, determine ideal split locations
    ideal_splits: list[int] = []
    if is_large_mega:
        ideal_splits = _compute_ideal_split_locations(moment, config)
    
    # Sort candidates by priority (stored in SplitPoint.priority)
    sorted_points = sorted(
        split_points,
        key=lambda sp: (sp.priority, sp.play_index),
    )
    
    selected: list[SplitPoint] = []
    last_split_idx = moment.start_play

    for sp in sorted_points:
        if len(selected) >= config.max_splits_per_moment:
            break

        # Enforce minimum gap from last split
        if sp.play_index - last_split_idx < config.min_plays_between_splits:
            continue

        # Enforce minimum remaining segment size
        if moment.end_play - sp.play_index < config.min_segment_plays:
            continue

        # For large mega-moments, prefer points near ideal locations
        if is_large_mega and ideal_splits:
            if not _is_near_ideal_location(sp.play_index, ideal_splits, config):
                # Skip unless this is a high-priority point
                if sp.priority > config.priority_quarter:
                    continue

        selected.append(sp)
        last_split_idx = sp.play_index

    # If we didn't find enough splits for a large mega-moment, 
    # try again with relaxed ideal location requirement
    if is_large_mega and len(selected) < min(2, config.max_splits_per_moment):
        selected = _select_fallback_splits(split_points, moment, config, selected)

    result = sorted(selected, key=lambda sp: sp.play_index)
    
    logger.debug(
        "split_points_selected",
        extra={
            "moment_id": moment.id,
            "is_large_mega": is_large_mega,
            "candidates": len(split_points),
            "selected": len(result),
            "selected_reasons": [sp.split_reason for sp in result],
        },
    )
    
    return result


def _compute_ideal_split_locations(
    moment: "Moment",
    config: SplitConfig,
) -> list[int]:
    """Compute ideal split locations for balanced segments.
    
    For a large mega-moment, we want segments of roughly equal size,
    targeting the configured target_segment_plays.
    
    Args:
        moment: The mega-moment being split
        config: Split configuration
    
    Returns:
        List of ideal play indices for splits
    """
    play_count = moment.play_count
    
    # Determine how many segments we want
    if play_count >= config.target_segment_plays * 3:
        # Want 3 segments (2 splits)
        num_splits = 2
    else:
        # Want 2 segments (1 split)
        num_splits = 1
    
    # Compute ideal locations (evenly spaced)
    ideal_locations: list[int] = []
    segment_size = play_count // (num_splits + 1)
    
    for i in range(1, num_splits + 1):
        ideal_idx = moment.start_play + (segment_size * i)
        ideal_locations.append(ideal_idx)
    
    return ideal_locations


def _is_near_ideal_location(
    play_index: int,
    ideal_locations: list[int],
    config: SplitConfig,
) -> bool:
    """Check if a play index is near an ideal split location.
    
    "Near" means within half the minimum segment size.
    """
    tolerance = config.min_segment_plays // 2
    
    for ideal in ideal_locations:
        if abs(play_index - ideal) <= tolerance:
            return True
    
    return False


def _select_fallback_splits(
    split_points: list[SplitPoint],
    moment: "Moment",
    config: SplitConfig,
    already_selected: list[SplitPoint],
) -> list[SplitPoint]:
    """Fallback selection for large mega-moments without ideal splits.
    
    When we don't find splits near ideal locations, try to select
    any valid splits that create reasonably balanced segments.
    """
    already_indices = {sp.play_index for sp in already_selected}
    
    # Sort by how close to ideal segment boundaries
    ideal_locations = _compute_ideal_split_locations(moment, config)
    
    def distance_to_ideal(sp: SplitPoint) -> int:
        if not ideal_locations:
            return 0
        return min(abs(sp.play_index - ideal) for ideal in ideal_locations)
    
    # Sort by distance to ideal (closest first), then by priority
    sorted_points = sorted(
        [sp for sp in split_points if sp.play_index not in already_indices],
        key=lambda sp: (distance_to_ideal(sp), sp.priority),
    )
    
    selected = list(already_selected)
    last_split_idx = moment.start_play
    
    # Update last_split_idx based on already selected
    if already_selected:
        sorted_already = sorted(already_selected, key=lambda sp: sp.play_index)
        last_split_idx = sorted_already[-1].play_index
    
    for sp in sorted_points:
        if len(selected) >= config.max_splits_per_moment:
            break

        if sp.play_index - last_split_idx < config.min_plays_between_splits:
            continue

        if moment.end_play - sp.play_index < config.min_segment_plays:
            continue

        selected.append(sp)
        last_split_idx = sp.play_index

    return selected


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
