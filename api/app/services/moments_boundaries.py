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

# Density gating configuration
# Prevents rapid FLIP/TIE sequences from emitting multiple boundaries
DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS = 8  # Min canonical plays between FLIP/TIE boundaries
DENSITY_GATE_LATE_GAME_PROGRESS = 0.85  # Q4 late or OT threshold for override consideration
DENSITY_GATE_OVERRIDE_MAX_TIER = 1  # Max tier to qualify for late-game override

# Late-game outcome threat configuration
# Prevents false drama from cuts that don't materially threaten the result
LATE_GAME_MIN_QUARTER = 4  # Q4 or OT
LATE_GAME_MAX_SECONDS = 150  # 2.5 minutes remaining
LATE_GAME_SAFE_MARGIN = 10  # Points: if margin > this after change, no threat
LATE_GAME_SAFE_TIER = 2  # Tier threshold: if tier >= this after change, no threat


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


@dataclass
class DensityGateDecision:
    """Record of a density gate decision for FLIP/TIE boundaries.
    
    Used for diagnostics to trace why a FLIP or TIE boundary was suppressed.
    """
    event_index: int
    crossing_type: str  # "FLIP" or "TIE"
    density_gate_applied: bool
    reason: str  # e.g., "within_window", "override_late_close", "no_recent_boundary"
    last_flip_tie_index: int | None = None
    last_flip_tie_canonical_pos: int | None = None
    current_canonical_pos: int | None = None
    window_size: int = DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS
    game_progress: float = 0.0
    tier_at_event: int = 0
    override_qualified: bool = False


@dataclass
class LateFalseDramaDecision:
    """Record of a late-game outcome threat decision.
    
    Used for diagnostics to trace why a TIER_DOWN/CUT boundary was suppressed
    due to lack of outcome threat (late-game "false drama").
    
    SPORT-AGNOSTIC: Uses unified phase detection instead of quarter checks.
    
    A boundary is suppressed if ALL are true:
    - is_final_phase == true (Q4/2H/P3 or OT)
    - seconds_remaining <= threshold
    - margin_after_change > SAFE_MARGIN
    - tier_after >= SAFE_TIER
    - no FLIP/TIE involved
    - no HIGH_IMPACT event
    """
    event_index: int
    crossing_type: str  # "TIER_DOWN", "CUT", "RUN"
    suppressed: bool
    suppressed_reason: str  # "late_false_drama" or "outcome_threatening" or specific reason
    
    # Sport-agnostic phase info
    phase_number: int = 0  # Quarter, half, or period number
    phase_label: str = ""  # "Q4", "2H", "P3", "OT"
    is_final_phase: bool = False
    is_overtime: bool = False
    
    seconds_remaining: int = 0
    margin_before: int = 0
    margin_after: int = 0
    tier_before: int = 0
    tier_after: int = 0
    
    # Backward compatibility
    @property
    def quarter(self) -> int:
        """Alias for phase_number (backward compatibility)."""
        return self.phase_number
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "event_index": self.event_index,
            "crossing_type": self.crossing_type,
            "suppressed": self.suppressed,
            "suppressed_reason": self.suppressed_reason,
            "phase_number": self.phase_number,
            "phase_label": self.phase_label,
            "is_final_phase": self.is_final_phase,
            "is_overtime": self.is_overtime,
            "seconds_remaining": self.seconds_remaining,
            "margin_before": self.margin_before,
            "margin_after": self.margin_after,
            "tier_before": self.tier_before,
            "tier_after": self.tier_after,
        }


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


def _is_closing_situation(
    event: dict[str, Any],
    curr_state: LeadState,
    sport: str | None = None,
) -> bool:
    """
    Check if this is a decided closing situation (late game with safe lead).
    
    UNIFIED CLOSING TAXONOMY (SPORT-AGNOSTIC):
    This function returns True for DECIDED_GAME_CLOSING situations,
    which triggers CLOSING_CONTROL instead of regular tier crossing.
    
    Works across all sports:
    - NBA: Q4 or OT with safe lead
    - NCAAB: 2nd half or OT with safe lead
    - NHL: 3rd period or OT with safe lead
    - NFL: Q4 or OT with safe lead
    
    For the full closing classification including CLOSE_GAME_CLOSING,
    use classify_closing_situation() from moments.closing.
    """
    from .moments.closing import classify_closing_situation
    
    classification = classify_closing_situation(event, curr_state, sport=sport)
    
    # CLOSING_CONTROL triggers on decided game closing
    return classification.is_decided_game


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


def _get_seconds_remaining(event: dict[str, Any]) -> int:
    """Get seconds remaining in the current quarter from an event."""
    from ..utils.datetime_utils import parse_clock_to_seconds
    
    clock = event.get("game_clock", "12:00") or "12:00"
    
    try:
        return parse_clock_to_seconds(clock)
    except (ValueError, TypeError):
        return 720  # Default to start of quarter


def _is_late_false_drama(
    event: dict[str, Any],
    prev_state: LeadState,
    curr_state: LeadState,
    crossing_type: str,
    sport: str | None = None,
    safe_margin: int = LATE_GAME_SAFE_MARGIN,
    safe_tier: int = LATE_GAME_SAFE_TIER,
    max_seconds: int = LATE_GAME_MAX_SECONDS,
    min_quarter: int = LATE_GAME_MIN_QUARTER,
) -> LateFalseDramaDecision:
    """
    Check if a TIER_DOWN/CUT boundary should be suppressed as "late false drama".
    
    UNIFIED CLOSING TAXONOMY (SPORT-AGNOSTIC):
    This function uses the unified closing classification. A boundary is
    suppressed when it occurs in DECIDED_GAME_CLOSING situations.
    
    Works across all sports:
    - NBA: Q4 or OT
    - NCAAB: 2nd half or OT
    - NHL: 3rd period or OT
    - NFL: Q4 or OT
    
    In decided game closing:
    - CUT/TIER_DOWN boundaries are suppressed
    - The game is functionally decided
    - Cuts don't threaten the outcome
    
    Args:
        event: Current timeline event
        prev_state: Lead state before the crossing
        curr_state: Lead state after the crossing
        crossing_type: "TIER_DOWN" or "CUT" or "RUN"
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
        safe_margin: Minimum margin to consider "safe" (default 10)
        safe_tier: Minimum tier to consider "safe" (default 2)
        max_seconds: Maximum seconds remaining for late-game check (default 150)
        min_quarter: Minimum quarter for late-game check (default 4)
    
    Returns:
        LateFalseDramaDecision with suppression decision and diagnostics
    """
    from .moments.closing import classify_closing_situation, should_suppress_cut_boundary
    from .moments.game_structure import compute_game_phase_state, get_phase_label
    
    # Compute sport-agnostic phase state
    phase_state = compute_game_phase_state(event, sport)
    
    # Calculate margins
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    margin_after = abs(home - away)
    
    # Estimate margin before (from prev_state or by reversing the change)
    margin_before = prev_state.margin if hasattr(prev_state, 'margin') else margin_after
    
    # Build base decision record with sport-agnostic phase info
    decision = LateFalseDramaDecision(
        event_index=event.get("_original_index", 0),
        crossing_type=crossing_type,
        suppressed=False,
        suppressed_reason="outcome_threatening",
        phase_number=phase_state.phase_number,
        phase_label=get_phase_label(phase_state),
        is_final_phase=phase_state.is_final_phase,
        is_overtime=phase_state.is_overtime,
        seconds_remaining=phase_state.remaining_seconds,
        margin_before=margin_before,
        margin_after=margin_after,
        tier_before=prev_state.tier,
        tier_after=curr_state.tier,
    )
    
    # Use unified closing classification (sport-agnostic)
    classification = classify_closing_situation(event, curr_state, sport=sport)
    
    # Check if we should suppress based on unified taxonomy
    if should_suppress_cut_boundary(classification):
        decision.suppressed = True
        decision.suppressed_reason = f"late_false_drama_{classification.category.value}"
        
        logger.debug(
            "late_false_drama_detected",
            extra={
                "event_index": decision.event_index,
                "crossing_type": crossing_type,
                "closing_category": classification.category.value,
                "phase_label": decision.phase_label,
                "is_final_phase": decision.is_final_phase,
                "seconds_remaining": decision.seconds_remaining,
                "margin_after": margin_after,
                "tier_after": curr_state.tier,
                "sport": sport or "NBA",
                "reason": classification.reason,
            },
        )
    else:
        # Not suppressed - record why
        if not classification.is_closing:
            decision.suppressed_reason = f"not_closing_{classification.reason}"
        elif classification.is_close_game:
            decision.suppressed_reason = "close_game_closing"
        else:
            decision.suppressed_reason = "outcome_threatening"
    
    return decision


def _should_density_gate_flip_tie(
    event: dict[str, Any],
    curr_state: LeadState,
    crossing_type: str,
    current_canonical_pos: int,
    last_flip_tie_canonical_pos: int | None,
    last_flip_tie_index: int | None,
    density_window: int = DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS,
) -> DensityGateDecision:
    """
    Determine if a FLIP or TIE should be suppressed due to density gating.
    
    Density gating prevents rapid-fire FLIP/TIE sequences (common in Q3/Q4)
    from creating too many boundaries. This is applied AFTER early-game gating.
    
    A FLIP/TIE is suppressed if:
    1. A previous FLIP/TIE boundary was emitted within the last N canonical plays
    2. AND the current event does NOT qualify for a late-game override
    
    Late-game override criteria:
    - Game progress >= DENSITY_GATE_LATE_GAME_PROGRESS (late Q4 or OT)
    - Current tier <= DENSITY_GATE_OVERRIDE_MAX_TIER (close game)
    
    Args:
        event: Current timeline event
        curr_state: Current lead state
        crossing_type: "FLIP" or "TIE"
        current_canonical_pos: Position in canonical PBP stream (0-indexed)
        last_flip_tie_canonical_pos: Position of last FLIP/TIE boundary (or None)
        last_flip_tie_index: Timeline index of last FLIP/TIE boundary (or None)
        density_window: Number of canonical plays for the density window
    
    Returns:
        DensityGateDecision with suppression decision and diagnostics
    """
    event_index = event.get("_original_index", 0)  # May need to be passed in
    game_progress = _get_game_progress(event)
    
    # Build base decision record
    decision = DensityGateDecision(
        event_index=event_index,
        crossing_type=crossing_type,
        density_gate_applied=False,
        reason="no_recent_boundary",
        last_flip_tie_index=last_flip_tie_index,
        last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
        current_canonical_pos=current_canonical_pos,
        window_size=density_window,
        game_progress=game_progress,
        tier_at_event=curr_state.tier,
        override_qualified=False,
    )
    
    # If no previous FLIP/TIE boundary, no density gating needed
    if last_flip_tie_canonical_pos is None:
        decision.reason = "no_recent_boundary"
        return decision
    
    # Calculate distance from last FLIP/TIE boundary
    plays_since_last = current_canonical_pos - last_flip_tie_canonical_pos
    
    # If outside the density window, allow the boundary
    if plays_since_last >= density_window:
        decision.reason = "outside_window"
        return decision
    
    # We're inside the density window - check for override
    override_qualified = (
        game_progress >= DENSITY_GATE_LATE_GAME_PROGRESS
        and curr_state.tier <= DENSITY_GATE_OVERRIDE_MAX_TIER
    )
    decision.override_qualified = override_qualified
    
    if override_qualified:
        # Late-game close situation - allow despite density window
        decision.reason = "override_late_close"
        decision.density_gate_applied = False
        return decision
    
    # Suppress this FLIP/TIE boundary
    decision.density_gate_applied = True
    decision.reason = f"within_window_{plays_since_last}_plays"
    
    return decision


def _evaluate_run_for_boundary(
    run: DetectedRun,
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    existing_boundary_indices: set[int],
) -> tuple[RunBoundaryDecision, LateFalseDramaDecision | None]:
    """
    Evaluate whether a detected run should create a MOMENTUM_SHIFT boundary.
    
    A run creates a boundary only if:
    1. Run points >= RUN_BOUNDARY_MIN_POINTS (default 8)
    2. The run causes a tier change (margin crosses a tier boundary)
    3. The run does not overlap with an existing boundary
    4. The run is not late false drama (NEW)
    
    Returns:
        Tuple of (RunBoundaryDecision, LateFalseDramaDecision or None)
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
        ), None
    
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
            ), None
    
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
        ), None
    
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
        ), None
    
    # NEW: Check for late false drama
    # This applies to runs that cut a lead but don't threaten the outcome
    # Only check if this is a tier-down (cut) scenario
    if state_after.tier < state_before.tier or (
        state_after.tier == state_before.tier and 
        state_after.leader != Leader.TIED and
        abs(home_after - away_after) < abs(home_before - away_before)
    ):
        # This is a cut/tier-down scenario - check for late false drama
        false_drama_decision = _is_late_false_drama(
            event=end_event,
            prev_state=state_before,
            curr_state=state_after,
            crossing_type="RUN_CUT",
        )
        
        if false_drama_decision.suppressed:
            return RunBoundaryDecision(
                run_start_idx=run.start_idx,
                run_end_idx=run.end_idx,
                run_points=run.points,
                run_team=run.team,
                created_boundary=False,
                reason="run_late_false_drama",
                tier_before=state_before.tier,
                tier_after=state_after.tier,
            ), false_drama_decision
    
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
    ), None


def detect_run_boundaries(
    events: Sequence[dict[str, Any]],
    runs: list[DetectedRun],
    thresholds: Sequence[int],
    existing_boundaries: list[BoundaryEvent],
) -> tuple[list[BoundaryEvent], list[RunBoundaryDecision], list[LateFalseDramaDecision]]:
    """
    Detect run-based boundaries that should become MOMENTUM_SHIFT moments.
    
    Returns:
        Tuple of (new_boundaries, run_decisions, false_drama_decisions) for diagnostics
    """
    from .moments import MomentType
    
    # Get existing boundary indices for overlap check
    existing_indices = {b.index for b in existing_boundaries}
    
    new_boundaries: list[BoundaryEvent] = []
    run_decisions: list[RunBoundaryDecision] = []
    false_drama_decisions: list[LateFalseDramaDecision] = []
    
    for run in runs:
        decision, false_drama_decision = _evaluate_run_for_boundary(
            run, events, thresholds, existing_indices
        )
        run_decisions.append(decision)
        
        if false_drama_decision is not None:
            false_drama_decisions.append(false_drama_decision)
        
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
    
    # Log summary of late false drama suppression for runs
    if false_drama_decisions:
        suppressed_count = sum(1 for d in false_drama_decisions if d.suppressed)
        if suppressed_count > 0:
            logger.info(
                "run_late_false_drama_summary",
                extra={
                    "total_evaluated": len(false_drama_decisions),
                    "suppressed_count": suppressed_count,
                },
            )
    
    return new_boundaries, run_decisions, false_drama_decisions


def detect_boundaries(
    events: Sequence[dict[str, Any]],
    pbp_indices: list[int],
    thresholds: Sequence[int],
    hysteresis_plays: int = DEFAULT_HYSTERESIS_PLAYS,
    flip_hysteresis_plays: int = DEFAULT_FLIP_HYSTERESIS_PLAYS,
    tie_hysteresis_plays: int = DEFAULT_TIE_HYSTERESIS_PLAYS,
    flip_tie_density_window: int = DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS,
) -> tuple[list[BoundaryEvent], list[DensityGateDecision], list[LateFalseDramaDecision]]:
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

    PHASE 2 ENHANCEMENT:
    - Density gating prevents rapid FLIP/TIE sequences from creating too many boundaries
    - A rolling window ensures adequate spacing between FLIP/TIE boundaries
    - Late-game close situations can override density gating

    PHASE 3 ENHANCEMENT:
    - Late-game outcome threat check prevents "false drama" boundaries
    - TIER_DOWN/CUT boundaries are suppressed when margin remains safe late in the game
    - Only boundaries that materially threaten the outcome are emitted

    OPENER is no longer a moment type.
    
    Returns:
        Tuple of (boundaries, density_gate_decisions, false_drama_decisions) for diagnostics
    """
    from .moments import MomentType
    
    boundaries: list[BoundaryEvent] = []
    density_gate_decisions: list[DensityGateDecision] = []
    false_drama_decisions: list[LateFalseDramaDecision] = []

    if not pbp_indices:
        return boundaries, density_gate_decisions, false_drama_decisions

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
    pending_flip_canonical_pos: int = 0  # Canonical position when pending flip was set
    
    # PHASE 1: Track state for TIE hysteresis
    pending_tie: TierCrossing | None = None
    pending_tie_index: int = 0
    pending_tie_prev_state: LeadState | None = None
    tie_persistence_count: int = 0
    pending_tie_canonical_pos: int = 0  # Canonical position when pending tie was set
    
    # PHASE 2: Track state for density gating
    # Last emitted FLIP/TIE boundary position in canonical stream
    last_flip_tie_canonical_pos: int | None = None
    last_flip_tie_index: int | None = None

    for canonical_pos, i in enumerate(pbp_indices):
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
                    # Apply density gating before emitting boundary
                    pending_flip_event = events[pending_flip_index]
                    
                    density_decision = _should_density_gate_flip_tie(
                        event=pending_flip_event,
                        curr_state=pending_flip.curr_state,
                        crossing_type="FLIP",
                        current_canonical_pos=pending_flip_canonical_pos,
                        last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
                        last_flip_tie_index=last_flip_tie_index,
                        density_window=flip_tie_density_window,
                    )
                    # Update event_index since we now have the actual index
                    density_decision.event_index = pending_flip_index
                    density_gate_decisions.append(density_decision)
                    
                    if density_decision.density_gate_applied:
                        # Suppress this FLIP boundary due to density gating
                        logger.debug(
                            "flip_boundary_density_gated",
                            extra={
                                "index": pending_flip_index,
                                "reason": density_decision.reason,
                                "plays_since_last": (
                                    pending_flip_canonical_pos - last_flip_tie_canonical_pos
                                    if last_flip_tie_canonical_pos is not None else None
                                ),
                            },
                        )
                    else:
                        # Emit the FLIP boundary
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
                        # Update last FLIP/TIE tracking
                        last_flip_tie_canonical_pos = pending_flip_canonical_pos
                        last_flip_tie_index = pending_flip_index
                    
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
                    # Confirmed TIE - apply density gating before emitting
                    pending_tie_event = events[pending_tie_index]
                    
                    density_decision = _should_density_gate_flip_tie(
                        event=pending_tie_event,
                        curr_state=curr_state,
                        crossing_type="TIE",
                        current_canonical_pos=pending_tie_canonical_pos,
                        last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
                        last_flip_tie_index=last_flip_tie_index,
                        density_window=flip_tie_density_window,
                    )
                    density_decision.event_index = pending_tie_index
                    density_gate_decisions.append(density_decision)
                    
                    if density_decision.density_gate_applied:
                        # Suppress this TIE boundary due to density gating
                        logger.debug(
                            "tie_boundary_density_gated",
                            extra={
                                "index": pending_tie_index,
                                "reason": density_decision.reason,
                                "plays_since_last": (
                                    pending_tie_canonical_pos - last_flip_tie_canonical_pos
                                    if last_flip_tie_canonical_pos is not None else None
                                ),
                            },
                        )
                    else:
                        # Emit the TIE boundary
                        boundaries.append(BoundaryEvent(
                            index=pending_tie_index,
                            moment_type=MomentType.TIE,
                            prev_state=pending_tie_prev_state or pending_tie.prev_state,
                            curr_state=curr_state,
                            crossing=pending_tie,
                            note="Game tied (confirmed)",
                        ))
                        # Update last FLIP/TIE tracking
                        last_flip_tie_canonical_pos = pending_tie_canonical_pos
                        last_flip_tie_index = pending_tie_index
                    
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

                # === FLIP: Now with time-aware gating, hysteresis, and density gating ===
                if crossing_type == TierCrossingType.FLIP:
                    # Cancel any pending tier crossing (FLIP supersedes)
                    pending_crossing = None
                    persistence_count = 0
                    
                    # Check if this is a closing situation (always immediate, but still density gated)
                    if _is_closing_situation(event, curr_state):
                        # Cancel any pending flip - this one takes precedence
                        pending_flip = None
                        flip_persistence_count = 0
                        
                        # Apply density gating for closing control flips
                        density_decision = _should_density_gate_flip_tie(
                            event=event,
                            curr_state=curr_state,
                            crossing_type="FLIP",
                            current_canonical_pos=canonical_pos,
                            last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
                            last_flip_tie_index=last_flip_tie_index,
                            density_window=flip_tie_density_window,
                        )
                        density_decision.event_index = i
                        density_gate_decisions.append(density_decision)
                        
                        if density_decision.density_gate_applied:
                            logger.debug(
                                "closing_flip_density_gated",
                                extra={"index": i, "reason": density_decision.reason},
                            )
                        else:
                            boundaries.append(BoundaryEvent(
                                index=i,
                                moment_type=MomentType.CLOSING_CONTROL,
                                prev_state=prev_state,
                                curr_state=curr_state,
                                crossing=crossing,
                                note="Late lead change",
                            ))
                            last_flip_tie_canonical_pos = canonical_pos
                            last_flip_tie_index = i
                    # Check if this flip should be gated (early game, low tier)
                    elif _should_gate_early_flip(event, curr_state, prev_state):
                        # Early game, tier 0 flip - require hysteresis
                        pending_flip = crossing
                        pending_flip_index = i
                        pending_flip_prev_state = prev_state
                        pending_flip_canonical_pos = canonical_pos
                        flip_persistence_count = 1
                    else:
                        # Significant flip or late game - apply density gating
                        pending_flip = None
                        flip_persistence_count = 0
                        
                        density_decision = _should_density_gate_flip_tie(
                            event=event,
                            curr_state=curr_state,
                            crossing_type="FLIP",
                            current_canonical_pos=canonical_pos,
                            last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
                            last_flip_tie_index=last_flip_tie_index,
                            density_window=flip_tie_density_window,
                        )
                        density_decision.event_index = i
                        density_gate_decisions.append(density_decision)
                        
                        if density_decision.density_gate_applied:
                            logger.debug(
                                "flip_boundary_density_gated",
                                extra={"index": i, "reason": density_decision.reason},
                            )
                        else:
                            boundaries.append(BoundaryEvent(
                                index=i,
                                moment_type=MomentType.FLIP,
                                prev_state=prev_state,
                                curr_state=curr_state,
                                crossing=crossing,
                                note="Lead change",
                            ))
                            last_flip_tie_canonical_pos = canonical_pos
                            last_flip_tie_index = i

                # === TIE_REACHED: Now with time-aware gating, hysteresis, and density gating ===
                elif crossing_type == TierCrossingType.TIE_REACHED:
                    pending_crossing = None
                    persistence_count = 0
                    
                    # Check if this tie should be gated (early game, low significance)
                    if _should_gate_early_tie(event, prev_state):
                        # Early game tie at low score - require hysteresis
                        pending_tie = crossing
                        pending_tie_index = i
                        pending_tie_prev_state = prev_state
                        pending_tie_canonical_pos = canonical_pos
                        tie_persistence_count = 1
                    else:
                        # Significant tie or late game - apply density gating
                        pending_tie = None
                        tie_persistence_count = 0
                        
                        density_decision = _should_density_gate_flip_tie(
                            event=event,
                            curr_state=curr_state,
                            crossing_type="TIE",
                            current_canonical_pos=canonical_pos,
                            last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
                            last_flip_tie_index=last_flip_tie_index,
                            density_window=flip_tie_density_window,
                        )
                        density_decision.event_index = i
                        density_gate_decisions.append(density_decision)
                        
                        if density_decision.density_gate_applied:
                            logger.debug(
                                "tie_boundary_density_gated",
                                extra={"index": i, "reason": density_decision.reason},
                            )
                        else:
                            boundaries.append(BoundaryEvent(
                                index=i,
                                moment_type=MomentType.TIE,
                                prev_state=prev_state,
                                curr_state=curr_state,
                                crossing=crossing,
                                note="Game tied",
                            ))
                            last_flip_tie_canonical_pos = canonical_pos
                            last_flip_tie_index = i

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
                                
                                # NEW: Check for late false drama before emitting CUT boundary
                                pending_event = events[pending_index]
                                false_drama_decision = _is_late_false_drama(
                                    event=pending_event,
                                    prev_state=pending_crossing.prev_state,
                                    curr_state=curr_state,
                                    crossing_type="TIER_DOWN",
                                )
                                false_drama_decision.event_index = pending_index
                                false_drama_decisions.append(false_drama_decision)
                                
                                if false_drama_decision.suppressed:
                                    # Suppress this CUT boundary - late false drama
                                    logger.debug(
                                        "cut_boundary_late_false_drama",
                                        extra={
                                            "index": pending_index,
                                            "margin_after": false_drama_decision.margin_after,
                                            "tier_after": curr_state.tier,
                                            "seconds_remaining": false_drama_decision.seconds_remaining,
                                        },
                                    )
                                    pending_crossing = None
                                    persistence_count = 0
                                    continue
                                    
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

    # Log summary of density gating if any decisions were made
    if density_gate_decisions:
        suppressed_count = sum(1 for d in density_gate_decisions if d.density_gate_applied)
        if suppressed_count > 0:
            logger.info(
                "density_gating_summary",
                extra={
                    "total_flip_tie_events": len(density_gate_decisions),
                    "suppressed_count": suppressed_count,
                    "emitted_count": len(density_gate_decisions) - suppressed_count,
                    "window_size": flip_tie_density_window,
                },
            )

    # Log summary of late false drama suppression
    if false_drama_decisions:
        suppressed_count = sum(1 for d in false_drama_decisions if d.suppressed)
        if suppressed_count > 0:
            logger.info(
                "late_false_drama_summary",
                extra={
                    "total_cut_events_evaluated": len(false_drama_decisions),
                    "suppressed_count": suppressed_count,
                    "emitted_count": len(false_drama_decisions) - suppressed_count,
                    "suppression_details": [
                        {
                            "index": d.event_index,
                            "margin": d.margin_after,
                            "tier": d.tier_after,
                            "seconds": d.seconds_remaining,
                        }
                        for d in false_drama_decisions
                        if d.suppressed
                    ],
                },
            )

    return boundaries, density_gate_decisions, false_drama_decisions
