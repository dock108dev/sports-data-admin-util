"""Split point detection.

Finds semantic split points within mega-moments based on narrative cues.
Includes narrative dormancy detection and contextual qualification.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence, TYPE_CHECKING

from .config import SplitConfig, DEFAULT_SPLIT_CONFIG
from .split_types import SplitPoint, DormancyDecision, RedundancyDecision, SplitSegment

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


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
                    pressure_start_score = (
                        home_score - points_scored if scoring_team == "home" else home_score,
                        away_score - points_scored if scoring_team == "away" else away_score,
                    )
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

                        if (pressure_plays >= config.pressure_min_plays
                                and pressure_point_diff >= config.pressure_min_point_diff):
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
                    pressure_start_score = (
                        home_score - points_scored if scoring_team == "home" else home_score,
                        away_score - points_scored if scoring_team == "away" else away_score,
                    )
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
            "by_reason": count_by_reason(result),
        },
    )

    return result


def count_by_reason(split_points: list[SplitPoint]) -> dict[str, int]:
    """Count split points by reason for diagnostics."""
    counts: dict[str, int] = {}
    for sp in split_points:
        counts[sp.split_reason] = counts.get(sp.split_reason, 0) + 1
    return counts


def detect_narrative_dormancy(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> DormancyDecision:
    """Detect if a mega-moment is narratively dormant.
    
    A mega-moment is dormant if ALL are true:
    - leader unchanged
    - tier unchanged OR tier oscillation does not persist >= hysteresis
    - margin stays above "decided" threshold for >= X% of the segment
    - no run exceeds meaningful threshold (or run exists but does not change tier)
    
    Args:
        moment: The mega-moment to analyze
        events: All timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration
    
    Returns:
        DormancyDecision with dormancy status and diagnostics
    """
    from ..lead_ladder import compute_lead_state, Leader
    from ...utils.datetime_utils import parse_clock_to_seconds
    
    decision = DormancyDecision(
        is_dormant=False,
        reason="",
    )
    
    # Build list of PBP events within this moment
    moment_events: list[tuple[int, dict[str, Any]]] = []
    for idx in range(moment.start_play, moment.end_play + 1):
        if idx < len(events):
            event = events[idx]
            if event.get("event_type") == "pbp":
                moment_events.append((idx, event))
    
    if len(moment_events) < 10:
        decision.reason = "too_few_events"
        return decision
    
    # Track state changes
    initial_state = compute_lead_state(
        moment.score_before[0], moment.score_before[1], thresholds
    )
    final_state = compute_lead_state(
        moment.score_after[0], moment.score_after[1], thresholds
    )
    
    # Check 1: Leader unchanged
    decision.leader_unchanged = (initial_state.leader == final_state.leader)
    
    # Check 2: Tier unchanged or oscillation doesn't persist
    decision.tier_unchanged = (initial_state.tier == final_state.tier)
    
    # Track tier changes with hysteresis
    tier_changes: list[tuple[int, int, int]] = []  # (play_idx, tier_before, tier_after)
    prev_tier = initial_state.tier
    tier_change_start_idx: int | None = None
    tier_change_start_tier: int | None = None
    
    for local_idx, (play_idx, event) in enumerate(moment_events):
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        state = compute_lead_state(home_score, away_score, thresholds)
        
        if state.tier != prev_tier:
            if tier_change_start_idx is None:
                tier_change_start_idx = local_idx
                tier_change_start_tier = prev_tier
            elif state.tier == tier_change_start_tier:
                # Oscillation - tier returned to original
                tier_changes.append((play_idx, tier_change_start_tier, state.tier))
                tier_change_start_idx = None
                tier_change_start_tier = None
        else:
            # Tier persisted - check if it persisted long enough
            if tier_change_start_idx is not None:
                plays_since_change = local_idx - tier_change_start_idx
                if plays_since_change >= config.dormancy_tier_hysteresis:
                    # Tier change persisted - not an oscillation
                    tier_changes.append((play_idx, tier_change_start_tier, state.tier))
                    tier_change_start_idx = None
                    tier_change_start_tier = None
        
        prev_tier = state.tier
    
    # If tier changed but all changes were oscillations, tier is effectively unchanged
    decision.tier_oscillation_persists = (
        len(tier_changes) > 0 and
        all(abs(tier_after - tier_before) == 0 for _, tier_before, tier_after in tier_changes)
    )
    
    # Check 3: Margin above decided threshold
    decided_count = 0
    total_events = 0
    
    for _, event in moment_events:
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        margin = abs(home_score - away_score)
        
        if margin > config.dormancy_decided_margin_threshold:
            decided_count += 1
        total_events += 1
    
    if total_events > 0:
        decision.margin_decided_percentage = decided_count / total_events
        decision.margin_above_decided_threshold = (
            decision.margin_decided_percentage >= config.dormancy_decided_percentage
        )
    
    # Check 4: Run detection
    run_tracker: dict[str, int] = {"home": 0, "away": 0}
    last_scorer: str | None = None
    max_run = 0
    run_changes_tier = False
    
    prev_tier_for_run = initial_state.tier
    
    for _, event in moment_events:
        points_scored = event.get("points_scored", 0) or 0
        scoring_team = event.get("scoring_team")
        
        if points_scored > 0 and scoring_team:
            home_score = event.get("home_score", 0) or 0
            away_score = event.get("away_score", 0) or 0
            state = compute_lead_state(home_score, away_score, thresholds)
            
            if last_scorer != scoring_team:
                run_tracker = {scoring_team: points_scored, "home" if scoring_team == "away" else "away": 0}
            else:
                run_tracker[scoring_team] = run_tracker.get(scoring_team, 0) + points_scored
            
            current_run = run_tracker.get(scoring_team, 0)
            max_run = max(max_run, current_run)
            
            # Check if run changed tier
            if current_run >= config.dormancy_run_meaningful_threshold:
                if state.tier != prev_tier_for_run:
                    run_changes_tier = True
                    break
            
            last_scorer = scoring_team
            prev_tier_for_run = state.tier
    
    decision.max_run_points = max_run
    decision.run_changes_tier = run_changes_tier
    
    # Determine if dormant
    is_dormant = (
        decision.leader_unchanged and
        (decision.tier_unchanged or decision.tier_oscillation_persists) and
        decision.margin_above_decided_threshold and
        (max_run < config.dormancy_run_meaningful_threshold or not run_changes_tier)
    )
    
    decision.is_dormant = is_dormant
    
    if is_dormant:
        reasons = []
        if decision.leader_unchanged:
            reasons.append("leader_unchanged")
        if decision.tier_unchanged or decision.tier_oscillation_persists:
            reasons.append("tier_stable")
        if decision.margin_above_decided_threshold:
            reasons.append(f"margin_decided_{decision.margin_decided_percentage:.0%}")
        if max_run < config.dormancy_run_meaningful_threshold:
            reasons.append(f"no_meaningful_run_max_{max_run}")
        elif not run_changes_tier:
            reasons.append("run_no_tier_change")
        decision.reason = "_".join(reasons)
    else:
        reasons = []
        if not decision.leader_unchanged:
            reasons.append("leader_changed")
        if not decision.tier_unchanged and not decision.tier_oscillation_persists:
            reasons.append("tier_changed_persistently")
        if not decision.margin_above_decided_threshold:
            reasons.append(f"margin_not_decided_{decision.margin_decided_percentage:.0%}")
        if max_run >= config.dormancy_run_meaningful_threshold and run_changes_tier:
            reasons.append(f"meaningful_run_{max_run}_changes_tier")
        decision.reason = "not_dormant_" + "_".join(reasons)
    
    return decision


def qualify_split_points_contextually(
    split_points: list[SplitPoint],
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> list[SplitPoint]:
    """Qualify split points based on contextual significance.
    
    Rules:
    - run_start: Only eligible if run >= threshold AND (tier change OR margin crosses threat OR late window)
    - tier_change: Only eligible if tier delta persists >= hysteresis AND lasts >= N plays
    
    Args:
        split_points: Candidate split points
        moment: The mega-moment
        events: All timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration
    
    Returns:
        Qualified split points
    """
    from ..lead_ladder import compute_lead_state
    from ...utils.datetime_utils import parse_clock_to_seconds
    
    qualified: list[SplitPoint] = []
    
    for sp in split_points:
        if sp.play_index >= len(events):
            continue
        
        event = events[sp.play_index]
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        state = compute_lead_state(home_score, away_score, thresholds)
        
        # Qualification rule 1: run_start
        if sp.split_reason == "run_start":
            if sp.run_points < config.run_min_points:
                logger.debug(
                    "split_point_disqualified_run_too_small",
                    extra={
                        "play_index": sp.play_index,
                        "run_points": sp.run_points,
                        "threshold": config.run_min_points,
                    },
                )
                continue
            
            # Check if run meets contextual criteria
            qualifies = False
            
            # Criterion 1: Tier change
            if sp.play_index > moment.start_play:
                prev_event = events[sp.play_index - 1]
                prev_home = prev_event.get("home_score", 0) or 0
                prev_away = prev_event.get("away_score", 0) or 0
                prev_state = compute_lead_state(prev_home, prev_away, thresholds)
                
                if state.tier != prev_state.tier:
                    qualifies = True
                    logger.debug(
                        "split_point_qualified_run_tier_change",
                        extra={
                            "play_index": sp.play_index,
                            "tier_before": prev_state.tier,
                            "tier_after": state.tier,
                        },
                    )
            
            # Criterion 2: Margin crosses threat threshold
            margin = abs(home_score - away_score)
            if margin <= config.run_split_threat_margin:
                qualifies = True
                logger.debug(
                    "split_point_qualified_run_threat_margin",
                    extra={
                        "play_index": sp.play_index,
                        "margin": margin,
                        "threat_threshold": config.run_split_threat_margin,
                    },
                )
            
            # Criterion 3: Late window
            clock = event.get("game_clock", "12:00") or "12:00"
            try:
                seconds_remaining = parse_clock_to_seconds(clock)
                quarter = event.get("quarter", 1) or 1
                # Approximate: Q4 or OT with < 5 minutes
                if quarter >= 4 and seconds_remaining <= config.run_split_late_window_seconds:
                    qualifies = True
                    logger.debug(
                        "split_point_qualified_run_late_window",
                        extra={
                            "play_index": sp.play_index,
                            "quarter": quarter,
                            "seconds_remaining": seconds_remaining,
                        },
                    )
            except (ValueError, TypeError):
                # Clock parsing failed (malformed or missing data).
                # Skip the late window criterion; qualification will depend on
                # other criteria (tier change or threat margin).
                pass
            
            if not qualifies:
                logger.debug(
                    "split_point_disqualified_run_no_context",
                    extra={
                        "play_index": sp.play_index,
                        "run_points": sp.run_points,
                    },
                )
                continue
        
        # Qualification rule 2: tier_change
        elif sp.split_reason == "tier_change":
            # Check if tier change persists
            tier_delta = abs(sp.tier_after - sp.tier_before)
            if tier_delta < config.tier_change_min_delta:
                logger.debug(
                    "split_point_disqualified_tier_delta_too_small",
                    extra={
                        "play_index": sp.play_index,
                        "tier_delta": tier_delta,
                        "threshold": config.tier_change_min_delta,
                    },
                )
                continue
            
            # Check persistence: tier must stay changed for N plays
            if sp.play_index + config.tier_change_persistence_plays < len(events):
                future_event = events[sp.play_index + config.tier_change_persistence_plays]
                future_home = future_event.get("home_score", 0) or 0
                future_away = future_event.get("away_score", 0) or 0
                future_state = compute_lead_state(future_home, future_away, thresholds)
                
                if future_state.tier != state.tier:
                    # Tier reverted - not persistent
                    logger.debug(
                        "split_point_disqualified_tier_not_persistent",
                        extra={
                            "play_index": sp.play_index,
                            "tier_at_split": state.tier,
                            "tier_after_persistence": future_state.tier,
                        },
                    )
                    continue
        
        # Other split reasons (quarter, timeout, etc.) are always qualified
        qualified.append(sp)
    
    return qualified


def filter_redundant_segments(
    segments: list[SplitSegment],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    parent_moment: "Moment",
) -> tuple[list[SplitSegment], list[RedundancyDecision]]:
    """Filter out redundant child segments after splitting by merging them.
    
    A segment is redundant if:
    - same type as neighbors AND
    - same tier_before/tier_after AND
    - no unique run/high-impact marker
    
    Redundant segments are MERGED into their neighbors to maintain continuity.
    
    Args:
        segments: Split segments to filter
        events: All timeline events
        thresholds: Lead Ladder thresholds
        parent_moment: The parent moment
    
    Returns:
        Tuple of (merged_segments, redundancy_decisions)
    """
    from ..lead_ladder import compute_lead_state
    from ..boundary_helpers import is_high_impact_event
    
    if not segments:
        return [], []
    if len(segments) <= 1:
        return segments, []
    
    # We'll use a working list and merge into it
    working_segments: list[SplitSegment] = [segments[0]]
    decisions: list[RedundancyDecision] = []
    
    # Track decision for the first segment
    decisions.append(RedundancyDecision(
        segment_index=0,
        is_redundant=False,
        reason="first_segment",
    ))
    
    for i in range(1, len(segments)):
        segment = segments[i]
        decision = RedundancyDecision(
            segment_index=i,
            is_redundant=False,
            reason="",
        )
        
        # Calculate tier states for this segment
        prev_state = compute_lead_state(
            segment.score_before[0], segment.score_before[1], thresholds
        )
        curr_state = compute_lead_state(
            segment.score_after[0], segment.score_after[1], thresholds
        )
        
        segment_tier_before = prev_state.tier
        segment_tier_after = curr_state.tier
        
        # Check neighbors
        prev_orig = segments[i - 1]
        next_orig = segments[i + 1] if i < len(segments) - 1 else None
        
        # Check tier match with neighbors
        # We compare with the original neighbors to decide if this segment added value
        prev_curr_state = compute_lead_state(
            prev_orig.score_after[0], prev_orig.score_after[1], thresholds
        )
        prev_tier_before_state = compute_lead_state(
            prev_orig.score_before[0], prev_orig.score_before[1], thresholds
        )
        
        decision.same_tier_before = (segment_tier_before == prev_curr_state.tier)
        
        # Check if this segment has the same tier characteristics as previous
        # (both tier_before and tier_after match)
        decision.same_type_as_prev = (
            segment_tier_before == prev_curr_state.tier and
            segment_tier_after == prev_tier_before_state.tier
        )
        
        if next_orig:
            next_prev_state = compute_lead_state(
                next_orig.score_before[0], next_orig.score_before[1], thresholds
            )
            next_curr_state = compute_lead_state(
                next_orig.score_after[0], next_orig.score_after[1], thresholds
            )
            decision.same_tier_after = (segment_tier_after == next_prev_state.tier)
            
            # Check if this segment has the same tier characteristics as next
            decision.same_type_as_next = (
                segment_tier_before == next_prev_state.tier and
                segment_tier_after == next_curr_state.tier
            )
        else:
            decision.same_tier_after = (segment_tier_after == parent_moment.ladder_tier_after)
            decision.same_type_as_next = False
        
        # Check for unique markers
        has_high_impact = False
        for idx in range(segment.start_play, min(segment.end_play + 1, len(events))):
            if idx < len(events) and is_high_impact_event(events[idx]):
                has_high_impact = True
                break
        
        decision.has_high_impact = has_high_impact
        
        # Check for significant run by a single team (not combined scoring)
        home_run = abs(segment.score_after[0] - segment.score_before[0])
        away_run = abs(segment.score_after[1] - segment.score_before[1])
        max_run = max(home_run, away_run)
        decision.has_unique_run = (max_run >= 8)  # Significant scoring change by one team
        
        # Determine if redundant or false drama
        # Rule: same tier across boundaries + no special markers OR marked as false drama
        is_redundant = (
            (decision.same_tier_before and
             decision.same_tier_after and
             not decision.has_unique_run and
             not decision.has_high_impact) or
            segment.is_false_drama
        )
        
        decision.is_redundant = is_redundant
        
        if is_redundant:
            reasons = []
            if segment.is_false_drama:
                reasons.append("false_drama")
            elif decision.same_tier_before and decision.same_tier_after:
                reasons.append("no_tier_change")
            
            if not decision.has_unique_run:
                reasons.append("no_unique_run")
            if not decision.has_high_impact:
                reasons.append("no_high_impact")
            decision.reason = "_".join(reasons)
            
            # MERGE into previous segment in working list
            last_seg = working_segments[-1]
            last_seg.end_play = segment.end_play
            last_seg.score_after = segment.score_after
            last_seg.play_count = last_seg.end_play - last_seg.start_play + 1
            
            logger.info(
                "segment_merged_redundant",
                extra={
                    "segment_index": i,
                    "parent_moment_id": parent_moment.id,
                    "reason": decision.reason,
                    "new_play_count": last_seg.play_count,
                },
            )
        else:
            decision.reason = "not_redundant"
            working_segments.append(segment)
        
        decisions.append(decision)
    
    return working_segments, decisions
