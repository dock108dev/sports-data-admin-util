"""
Boundary Detection for Moments.

Detects moment boundaries in game timelines based on Lead Ladder tier crossings.
Boundaries represent significant changes in game control that warrant starting
a new narrative moment.

PHASE 1 ENHANCEMENTS:
- FLIP and TIE have configurable hysteresis
- Early-game triggers are gated to reduce noise
- Run-based boundaries for momentum shifts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence, TYPE_CHECKING

from .lead_ladder import (
    Leader,
    LeadState,
    TierCrossing,
    TierCrossingType,
    compute_lead_state,
    detect_tier_crossing,
)
from .moments_runs import DetectedRun

if TYPE_CHECKING:
    from .moments import MomentType

logger = logging.getLogger(__name__)


# Default configuration
DEFAULT_HYSTERESIS_PLAYS = 2
DEFAULT_FLIP_HYSTERESIS_PLAYS = 3
DEFAULT_TIE_HYSTERESIS_PLAYS = 2
RUN_BOUNDARY_MIN_POINTS = 8
RUN_BOUNDARY_MIN_TIER_CHANGE = 1


@dataclass
class BoundaryEvent:
    """
    Represents a detected moment boundary.

    A boundary occurs when game control changes significantly enough
    to warrant starting a new moment.
    """
    index: int  # Index in timeline where boundary occurs
    moment_type: "MomentType"
    prev_state: LeadState
    curr_state: LeadState
    crossing: TierCrossing | None = None
    note: str | None = None


@dataclass
class RunBoundaryDecision:
    """Record of a run boundary decision for diagnostics."""
    run_start_idx: int
    run_end_idx: int
    run_points: int
    run_team: str
    created_boundary: bool
    reason: str  # e.g., "run_created_boundary", "run_no_tier_change", "run_overlaps_existing"
    tier_before: int | None = None
    tier_after: int | None = None


def get_canonical_pbp_indices(
    events: Sequence[dict[str, Any]],
    require_description: bool = True,
) -> list[int]:
    """
    Filter the timeline to find only real, narrative-relevant PBP plays.

    PHASE 1.4: This function now expects score-normalized events.
    Score reset heuristics have been removed - use normalize_scores() before calling.

    Excludes:
    - Non-PBP events
    - Period start/end markers (descriptive only, no game action)
    - Boundary bookkeeping rows (0:00 with no score change)
    
    Includes:
    - All scoring events (even if description is minimal)
    - All events that could affect game state
    
    Args:
        events: Timeline events (should be score-normalized)
        require_description: If False, includes events without descriptions if they have score changes
    """
    indices = []
    prev_home: int | None = None
    prev_away: int | None = None

    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue

        description = (event.get("description") or "").strip()
        description_lower = description.lower()

        # Get score (should be normalized if normalize_scores() was called)
        home_score = event.get("home_score")
        away_score = event.get("away_score")
        
        # Convert None to 0 only for comparison purposes
        home_for_compare = home_score if home_score is not None else 0
        away_for_compare = away_score if away_score is not None else 0

        # Check if this event has a score change
        has_score_change = (
            prev_home is not None
            and (home_for_compare != prev_home or away_for_compare != prev_away)
        )
        
        # 1. Filter explicit period markers (never include these)
        if any(marker in description_lower for marker in [
            "start of", "end of", "beginning of", "start period", "end period",
        ]):
            # Even period markers should update our score tracking
            prev_home = home_for_compare
            prev_away = away_for_compare
            continue
        
        # 2. Filter non-play events that don't affect game state
        if not description and require_description and not has_score_change:
            # No description and no score change - skip
            continue
            
        if any(marker in description_lower for marker in [
            "jump ball", "timeout", "coaches challenge"
        ]):
            # These don't change score/tier, but update tracking
            prev_home = home_for_compare
            prev_away = away_for_compare
            continue

        # 3. Filter boundary markers at 0:00 that aren't actual plays
        clock = event.get("game_clock", "")
        if clock in ("0:00", "0:00.0"):
            # If it's a 0:00 row with no score change, it's likely just a marker
            if not has_score_change:
                if "made" not in description_lower and "miss" not in description_lower:
                    prev_home = home_for_compare
                    prev_away = away_for_compare
                    continue

        indices.append(i)
        prev_home = home_for_compare
        prev_away = away_for_compare

    return indices


def _get_score(event: dict[str, Any]) -> tuple[int, int]:
    """Extract (home_score, away_score) from an event."""
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    return home, away


def _get_game_progress(event: dict[str, Any]) -> float:
    """
    Estimate game progress as 0.0 to 1.0.
    
    Uses quarter and clock to compute rough progress.
    Default assumptions for NBA-style games (4 quarters, 12 min each).
    """
    from ..utils.datetime_utils import parse_clock_to_seconds
    
    quarter = event.get("quarter", 1) or 1
    clock = event.get("game_clock", "12:00")
    
    # Handle OT
    if quarter > 4:
        return 1.0
    
    # Parse clock
    try:
        seconds = parse_clock_to_seconds(clock)
    except (ValueError, TypeError):
        seconds = 720  # Default to start of quarter
    
    # Each quarter is 12 minutes = 720 seconds
    quarter_duration = 720.0
    total_game_seconds = quarter_duration * 4
    
    # Calculate progress
    completed_quarters = (quarter - 1) * quarter_duration
    quarter_elapsed = quarter_duration - seconds
    total_elapsed = completed_quarters + quarter_elapsed
    
    return min(1.0, total_elapsed / total_game_seconds)


def _is_closing_situation(event: dict[str, Any], curr_state: LeadState) -> bool:
    """
    Check if this is a closing situation (late game with lead).
    
    Closing situations occur when:
    1. Game is in Q4 or OT with < 2:00 remaining
    2. Leading team has tier 2+ lead
    
    This triggers CLOSING_CONTROL instead of regular tier crossing.
    """
    from ..utils.datetime_utils import parse_clock_to_seconds
    
    quarter = event.get("quarter", 1) or 1
    clock = event.get("game_clock", "12:00")
    
    # Must be Q4 or OT
    if quarter < 4:
        return False
    
    # Parse clock
    try:
        seconds = parse_clock_to_seconds(clock)
    except (ValueError, TypeError):
        return False
    
    # Must be under 2 minutes
    if seconds > 120:
        return False
    
    # Must have tier 2+ lead
    return curr_state.tier >= 2


def _is_high_impact_event(event: dict[str, Any]) -> bool:
    """Check if event is high-impact (ejection, injury, etc.)."""
    play_type = (event.get("play_type") or "").lower()
    description = (event.get("description") or "").lower()
    
    high_impact_markers = ["ejection", "ejected", "injury", "injured", "flagrant"]
    
    return any(m in play_type or m in description for m in high_impact_markers)


def _should_gate_early_flip(
    event: dict[str, Any],
    curr_state: LeadState,
    prev_state: LeadState,
) -> bool:
    """
    Determine if an early-game FLIP should be gated (require hysteresis).
    
    PHASE 1 SUPPRESSION RULE:
    - In Q1, tier-0 flips require confirmation
    - Flips at higher tiers or later in the game are immediate
    
    Returns True if the flip should be gated (delayed pending confirmation).
    """
    game_progress = _get_game_progress(event)
    
    # First 15% of game = early game
    if game_progress > 0.15:
        return False
    
    # Only gate tier-0 flips (very close games)
    if curr_state.tier > 0 or prev_state.tier > 0:
        return False
    
    return True


def _should_gate_early_tie(
    event: dict[str, Any],
    prev_state: LeadState,
) -> bool:
    """
    Determine if an early-game TIE should be gated (require hysteresis).
    
    PHASE 1 SUPPRESSION RULE:
    - In Q1, ties from tier-0 require confirmation
    - Ties from higher tiers (dramatic comebacks) are immediate
    
    Returns True if the tie should be gated (delayed pending confirmation).
    """
    game_progress = _get_game_progress(event)
    
    # First 15% of game = early game
    if game_progress > 0.15:
        return False
    
    # Only gate if coming from tier-0 (low significance)
    if prev_state.tier > 0:
        return False
    
    return True


def _evaluate_run_for_boundary(
    run: DetectedRun,
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    existing_boundary_indices: set[int],
) -> RunBoundaryDecision:
    """
    Evaluate whether a detected run should create a MOMENTUM_SHIFT boundary.
    
    A run creates a boundary only if:
    1. Run points >= RUN_BOUNDARY_MIN_POINTS (default 8)
    2. The run causes a tier change (margin crosses a tier boundary)
    3. The run does not overlap with an existing boundary
    
    Returns a RunBoundaryDecision with the result and reason.
    """
    # Check minimum points
    if run.points < RUN_BOUNDARY_MIN_POINTS:
        return RunBoundaryDecision(
            run_start_idx=run.start_idx,
            run_end_idx=run.end_idx,
            run_points=run.points,
            run_team=run.team,
            created_boundary=False,
            reason="run_below_threshold",
        )
    
    # Check for overlap with existing boundaries
    for boundary_idx in existing_boundary_indices:
        if run.start_idx <= boundary_idx <= run.end_idx:
            return RunBoundaryDecision(
                run_start_idx=run.start_idx,
                run_end_idx=run.end_idx,
                run_points=run.points,
                run_team=run.team,
                created_boundary=False,
                reason="run_overlaps_existing_boundary",
            )
    
    # Calculate tier change caused by the run
    end_event = events[run.end_idx]
    
    # Get scores at start and end of run
    # Use event before run start for "before" state
    if run.start_idx > 0:
        before_event = events[run.start_idx - 1]
        home_before = before_event.get("home_score", 0) or 0
        away_before = before_event.get("away_score", 0) or 0
    else:
        home_before = 0
        away_before = 0
    
    home_after = end_event.get("home_score", 0) or 0
    away_after = end_event.get("away_score", 0) or 0
    
    # Compute lead states
    state_before = compute_lead_state(home_before, away_before, thresholds)
    state_after = compute_lead_state(home_after, away_after, thresholds)
    
    # Check for tier change
    tier_change = abs(state_after.tier - state_before.tier)
    leader_changed = state_before.leader != state_after.leader
    
    if tier_change < RUN_BOUNDARY_MIN_TIER_CHANGE and not leader_changed:
        return RunBoundaryDecision(
            run_start_idx=run.start_idx,
            run_end_idx=run.end_idx,
            run_points=run.points,
            run_team=run.team,
            created_boundary=False,
            reason="run_no_tier_change",
            tier_before=state_before.tier,
            tier_after=state_after.tier,
        )
    
    # Check for garbage time (very late in game with large margin)
    game_progress = _get_game_progress(end_event)
    if game_progress > 0.9 and state_after.tier >= 3:  # Late game, blowout
        return RunBoundaryDecision(
            run_start_idx=run.start_idx,
            run_end_idx=run.end_idx,
            run_points=run.points,
            run_team=run.team,
            created_boundary=False,
            reason="run_garbage_time",
            tier_before=state_before.tier,
            tier_after=state_after.tier,
        )
    
    # Run qualifies for boundary creation
    return RunBoundaryDecision(
        run_start_idx=run.start_idx,
        run_end_idx=run.end_idx,
        run_points=run.points,
        run_team=run.team,
        created_boundary=True,
        reason="run_created_boundary",
        tier_before=state_before.tier,
        tier_after=state_after.tier,
    )


def detect_run_boundaries(
    events: Sequence[dict[str, Any]],
    runs: list[DetectedRun],
    thresholds: Sequence[int],
    existing_boundaries: list[BoundaryEvent],
) -> tuple[list[BoundaryEvent], list[RunBoundaryDecision]]:
    """
    Detect run-based boundaries that should become MOMENTUM_SHIFT moments.
    
    Returns:
        Tuple of (new_boundaries, decisions) for diagnostics
    """
    from .moments import MomentType
    
    # Get existing boundary indices for overlap check
    existing_indices = {b.index for b in existing_boundaries}
    
    new_boundaries: list[BoundaryEvent] = []
    decisions: list[RunBoundaryDecision] = []
    
    for run in runs:
        decision = _evaluate_run_for_boundary(run, events, thresholds, existing_indices)
        decisions.append(decision)
        
        if decision.created_boundary:
            # Create boundary at start of run
            # Get state before and after
            if run.start_idx > 0:
                before_event = events[run.start_idx - 1]
                home_before = before_event.get("home_score", 0) or 0
                away_before = before_event.get("away_score", 0) or 0
            else:
                home_before = 0
                away_before = 0
            
            home_after = events[run.end_idx].get("home_score", 0) or 0
            away_after = events[run.end_idx].get("away_score", 0) or 0
            
            prev_state = compute_lead_state(home_before, away_before, thresholds)
            curr_state = compute_lead_state(home_after, away_after, thresholds)
            
            boundary = BoundaryEvent(
                index=run.start_idx,
                moment_type=MomentType.MOMENTUM_SHIFT,
                prev_state=prev_state,
                curr_state=curr_state,
                note=f"{run.points}-0 {run.team} run",
            )
            new_boundaries.append(boundary)
            
            # Add to existing indices to prevent duplicate runs creating boundaries
            existing_indices.add(run.start_idx)
    
    return new_boundaries, decisions


def detect_boundaries(
    events: Sequence[dict[str, Any]],
    pbp_indices: list[int],
    thresholds: Sequence[int],
    hysteresis_plays: int = DEFAULT_HYSTERESIS_PLAYS,
    flip_hysteresis_plays: int = DEFAULT_FLIP_HYSTERESIS_PLAYS,
    tie_hysteresis_plays: int = DEFAULT_TIE_HYSTERESIS_PLAYS,
) -> list[BoundaryEvent]:
    """
    Detect all moment boundaries using the canonical PBP stream.

    MOMENTS MUST HAVE CAUSAL TRIGGERS:
    - tier_up / tier_down
    - tie / flip
    - closing_lock
    - high_impact_event

    PHASE 1 ENHANCEMENTS:
    - FLIP and TIE now have configurable hysteresis
    - Early-game triggers are gated to reduce noise
    - Only significant early-game flips (tier 1+) bypass hysteresis

    OPENER is no longer a moment type.
    """
    from .moments import MomentType
    
    boundaries: list[BoundaryEvent] = []

    if not pbp_indices:
        return boundaries

    # Track state for tier crossings (TIER_UP, TIER_DOWN, TIE_BROKEN)
    prev_state: LeadState | None = None
    pending_crossing: TierCrossing | None = None
    pending_index: int = 0
    persistence_count: int = 0
    
    # PHASE 1: Track state for FLIP hysteresis
    pending_flip: TierCrossing | None = None
    pending_flip_index: int = 0
    pending_flip_prev_state: LeadState | None = None
    flip_persistence_count: int = 0
    
    # PHASE 1: Track state for TIE hysteresis
    pending_tie: TierCrossing | None = None
    pending_tie_index: int = 0
    pending_tie_prev_state: LeadState | None = None
    tie_persistence_count: int = 0

    for i in pbp_indices:
        event = events[i]
        home_score, away_score = _get_score(event)
        curr_state = compute_lead_state(home_score, away_score, thresholds)

        # === CHECK PENDING FLIP CONFIRMATION ===
        if pending_flip is not None:
            # Check if the new leader still leads
            if curr_state.leader == pending_flip.curr_state.leader:
                flip_persistence_count += 1
                
                if flip_persistence_count >= flip_hysteresis_plays:
                    # Confirmed FLIP - leader held
                    pending_flip_event = events[pending_flip_index]
                    if _is_closing_situation(pending_flip_event, pending_flip.curr_state):
                        boundaries.append(BoundaryEvent(
                            index=pending_flip_index,
                            moment_type=MomentType.CLOSING_CONTROL,
                            prev_state=pending_flip_prev_state or pending_flip.prev_state,
                            curr_state=curr_state,
                            crossing=pending_flip,
                            note="Late lead change (confirmed)",
                        ))
                    else:
                        boundaries.append(BoundaryEvent(
                            index=pending_flip_index,
                            moment_type=MomentType.FLIP,
                            prev_state=pending_flip_prev_state or pending_flip.prev_state,
                            curr_state=curr_state,
                            crossing=pending_flip,
                            note="Lead change (confirmed)",
                        ))
                    pending_flip = None
                    flip_persistence_count = 0
            else:
                # Leader changed again before confirmation - cancel pending
                # This collapses rapid flip-flip-flip sequences
                pending_flip = None
                flip_persistence_count = 0
        
        # === CHECK PENDING TIE CONFIRMATION ===
        if pending_tie is not None:
            # Check if still tied
            if curr_state.leader == Leader.TIED:
                tie_persistence_count += 1
                
                if tie_persistence_count >= tie_hysteresis_plays:
                    # Confirmed TIE
                    boundaries.append(BoundaryEvent(
                        index=pending_tie_index,
                        moment_type=MomentType.TIE,
                        prev_state=pending_tie_prev_state or pending_tie.prev_state,
                        curr_state=curr_state,
                        crossing=pending_tie,
                        note="Game tied (confirmed)",
                    ))
                    pending_tie = None
                    tie_persistence_count = 0
            else:
                # Tie was broken before confirmation - cancel
                pending_tie = None
                tie_persistence_count = 0

        # === LEAD LADDER CROSSING ===
        if prev_state is not None:
            crossing = detect_tier_crossing(prev_state, curr_state)

            if crossing is not None:
                crossing_type = crossing.crossing_type

                # === FLIP: Now with time-aware gating and hysteresis ===
                if crossing_type == TierCrossingType.FLIP:
                    # Cancel any pending tier crossing (FLIP supersedes)
                    pending_crossing = None
                    persistence_count = 0
                    
                    # Check if this is a closing situation (always immediate)
                    if _is_closing_situation(event, curr_state):
                        # Cancel any pending flip - this one takes precedence
                        pending_flip = None
                        flip_persistence_count = 0
                        boundaries.append(BoundaryEvent(
                            index=i,
                            moment_type=MomentType.CLOSING_CONTROL,
                            prev_state=prev_state,
                            curr_state=curr_state,
                            crossing=crossing,
                            note="Late lead change",
                        ))
                    # Check if this flip should be gated (early game, low tier)
                    elif _should_gate_early_flip(event, curr_state, prev_state):
                        # Early game, tier 0 flip - require hysteresis
                        pending_flip = crossing
                        pending_flip_index = i
                        pending_flip_prev_state = prev_state
                        flip_persistence_count = 1
                    else:
                        # Significant flip or late game - immediate boundary
                        pending_flip = None
                        flip_persistence_count = 0
                        boundaries.append(BoundaryEvent(
                            index=i,
                            moment_type=MomentType.FLIP,
                            prev_state=prev_state,
                            curr_state=curr_state,
                            crossing=crossing,
                            note="Lead change",
                        ))

                # === TIE_REACHED: Now with time-aware gating and hysteresis ===
                elif crossing_type == TierCrossingType.TIE_REACHED:
                    pending_crossing = None
                    persistence_count = 0
                    
                    # Check if this tie should be gated (early game, low significance)
                    if _should_gate_early_tie(event, prev_state):
                        # Early game tie at low score - require hysteresis
                        pending_tie = crossing
                        pending_tie_index = i
                        pending_tie_prev_state = prev_state
                        tie_persistence_count = 1
                    else:
                        # Significant tie or late game - immediate boundary
                        pending_tie = None
                        tie_persistence_count = 0
                        boundaries.append(BoundaryEvent(
                            index=i,
                            moment_type=MomentType.TIE,
                            prev_state=prev_state,
                            curr_state=curr_state,
                            crossing=crossing,
                            note="Game tied",
                        ))

                elif crossing_type in (
                    TierCrossingType.TIE_BROKEN,
                    TierCrossingType.TIER_UP,
                    TierCrossingType.TIER_DOWN,
                ):
                    pending_crossing = crossing
                    pending_index = i
                    persistence_count = 1

            else:
                # No crossing - check if pending crossing should be confirmed
                if pending_crossing is not None:
                    if curr_state.tier == pending_crossing.curr_state.tier:
                        persistence_count += 1

                        if persistence_count >= hysteresis_plays:
                            # Confirm the boundary
                            if pending_crossing.crossing_type == TierCrossingType.TIER_UP:
                                moment_type = MomentType.LEAD_BUILD
                                note = "Lead extended"
                            elif pending_crossing.crossing_type == TierCrossingType.TIER_DOWN:
                                moment_type = MomentType.CUT
                                note = "Lead cut"
                            elif pending_crossing.crossing_type == TierCrossingType.TIE_BROKEN:
                                moment_type = MomentType.LEAD_BUILD
                                note = "Took the lead"
                            else:
                                moment_type = MomentType.NEUTRAL
                                note = None

                            if _is_closing_situation(event, curr_state) and curr_state.tier >= 2:
                                moment_type = MomentType.CLOSING_CONTROL
                                note = "Game control locked"

                            boundaries.append(BoundaryEvent(
                                index=pending_index,
                                moment_type=moment_type,
                                prev_state=pending_crossing.prev_state,
                                curr_state=curr_state,
                                crossing=pending_crossing,
                                note=note,
                            ))
                            pending_crossing = None
                            persistence_count = 0
                    else:
                        pending_crossing = None
                        persistence_count = 0

        # === HIGH-IMPACT EVENTS ===
        if _is_high_impact_event(event):
            boundaries.append(BoundaryEvent(
                index=i,
                moment_type=MomentType.HIGH_IMPACT,
                prev_state=prev_state or curr_state,
                curr_state=curr_state,
                note=event.get("play_type", "High-impact event"),
            ))

        prev_state = curr_state

    return boundaries
