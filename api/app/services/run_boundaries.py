"""Run-based boundary detection.

Detects MOMENTUM_SHIFT boundaries from scoring runs that cause
significant tier changes.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .lead_ladder import Leader, LeadState, compute_lead_state
from .moments_runs import DetectedRun
from .boundary_types import (
    BoundaryEvent,
    RunBoundaryDecision,
    LateFalseDramaDecision,
    RUN_BOUNDARY_MIN_POINTS,
    RUN_BOUNDARY_MIN_TIER_CHANGE,
)
from .boundary_helpers import get_game_progress, is_late_false_drama

logger = logging.getLogger(__name__)


def evaluate_run_for_boundary(
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
    4. The run is not late false drama

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
    game_progress = get_game_progress(end_event)
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

    # Check for late false drama
    # This applies to runs that cut a lead but don't threaten the outcome
    # Only check if this is a tier-down (cut) scenario
    if (state_after.tier < state_before.tier
            or (state_after.tier == state_before.tier
                and state_after.leader != Leader.TIED
                and abs(home_after - away_after) < abs(home_before - away_before))):
        # This is a cut/tier-down scenario - check for late false drama
        false_drama_decision = is_late_false_drama(
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
        decision, false_drama_decision = evaluate_run_for_boundary(
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
