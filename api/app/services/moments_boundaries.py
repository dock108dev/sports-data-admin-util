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
from typing import Any, Sequence, TYPE_CHECKING

from .lead_ladder import (
    Leader,
    LeadState,
    TierCrossing,
    TierCrossingType,
    compute_lead_state,
    detect_tier_crossing,
)

# Re-export types and constants from boundary_types
from .boundary_types import (
    BoundaryEvent,
    RunBoundaryDecision,
    DensityGateDecision,
    LateFalseDramaDecision,
    DEFAULT_HYSTERESIS_PLAYS,
    DEFAULT_FLIP_HYSTERESIS_PLAYS,
    DEFAULT_TIE_HYSTERESIS_PLAYS,
    DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS,
)

# Re-export helpers
from .boundary_helpers import (
    get_canonical_pbp_indices,
    get_score,
    get_game_progress,
    is_closing_situation,
    is_high_impact_event,
    should_gate_early_flip,
    should_gate_early_tie,
    is_late_false_drama,
    should_density_gate_flip_tie,
)

# Re-export run boundary detection
from .run_boundaries import (
    evaluate_run_for_boundary,
    detect_run_boundaries,
)

if TYPE_CHECKING:
    from .moments import MomentType

logger = logging.getLogger(__name__)

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
    pending_flip_canonical_pos: int = 0

    # PHASE 1: Track state for TIE hysteresis
    pending_tie: TierCrossing | None = None
    pending_tie_index: int = 0
    pending_tie_prev_state: LeadState | None = None
    tie_persistence_count: int = 0
    pending_tie_canonical_pos: int = 0

    # PHASE 2: Track state for density gating
    last_flip_tie_canonical_pos: int | None = None
    last_flip_tie_index: int | None = None

    for canonical_pos, i in enumerate(pbp_indices):
        event = events[i]
        home_score, away_score = get_score(event)
        curr_state = compute_lead_state(home_score, away_score, thresholds)

        # === CHECK PENDING FLIP CONFIRMATION ===
        if pending_flip is not None:
            if curr_state.leader == pending_flip.curr_state.leader:
                flip_persistence_count += 1

                if flip_persistence_count >= flip_hysteresis_plays:
                    pending_flip_event = events[pending_flip_index]

                    density_decision = should_density_gate_flip_tie(
                        event=pending_flip_event,
                        curr_state=pending_flip.curr_state,
                        crossing_type="FLIP",
                        current_canonical_pos=pending_flip_canonical_pos,
                        last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
                        last_flip_tie_index=last_flip_tie_index,
                        density_window=flip_tie_density_window,
                    )
                    density_decision.event_index = pending_flip_index
                    density_gate_decisions.append(density_decision)

                    if density_decision.density_gate_applied:
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
                        if is_closing_situation(pending_flip_event, pending_flip.curr_state):
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
                        last_flip_tie_canonical_pos = pending_flip_canonical_pos
                        last_flip_tie_index = pending_flip_index

                    pending_flip = None
                    flip_persistence_count = 0
            else:
                pending_flip = None
                flip_persistence_count = 0

        # === CHECK PENDING TIE CONFIRMATION ===
        if pending_tie is not None:
            if curr_state.leader == Leader.TIED:
                tie_persistence_count += 1

                if tie_persistence_count >= tie_hysteresis_plays:
                    pending_tie_event = events[pending_tie_index]

                    density_decision = should_density_gate_flip_tie(
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
                        boundaries.append(BoundaryEvent(
                            index=pending_tie_index,
                            moment_type=MomentType.TIE,
                            prev_state=pending_tie_prev_state or pending_tie.prev_state,
                            curr_state=curr_state,
                            crossing=pending_tie,
                            note="Game tied (confirmed)",
                        ))
                        last_flip_tie_canonical_pos = pending_tie_canonical_pos
                        last_flip_tie_index = pending_tie_index

                    pending_tie = None
                    tie_persistence_count = 0
            else:
                pending_tie = None
                tie_persistence_count = 0

        # === LEAD LADDER CROSSING ===
        if prev_state is not None:
            crossing = detect_tier_crossing(prev_state, curr_state)

            if crossing is not None:
                crossing_type = crossing.crossing_type

                # === FLIP: Now with time-aware gating, hysteresis, and density gating ===
                if crossing_type == TierCrossingType.FLIP:
                    pending_crossing = None
                    persistence_count = 0

                    if is_closing_situation(event, curr_state):
                        pending_flip = None
                        flip_persistence_count = 0

                        density_decision = should_density_gate_flip_tie(
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

                    elif should_gate_early_flip(event, curr_state, prev_state):
                        pending_flip = crossing
                        pending_flip_index = i
                        pending_flip_prev_state = prev_state
                        pending_flip_canonical_pos = canonical_pos
                        flip_persistence_count = 1
                    else:
                        pending_flip = None
                        flip_persistence_count = 0

                        density_decision = should_density_gate_flip_tie(
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

                    if should_gate_early_tie(event, prev_state):
                        pending_tie = crossing
                        pending_tie_index = i
                        pending_tie_prev_state = prev_state
                        pending_tie_canonical_pos = canonical_pos
                        tie_persistence_count = 1
                    else:
                        pending_tie = None
                        tie_persistence_count = 0

                        density_decision = should_density_gate_flip_tie(
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
                            if pending_crossing.crossing_type == TierCrossingType.TIER_UP:
                                moment_type = MomentType.LEAD_BUILD
                                note = "Lead extended"
                            elif pending_crossing.crossing_type == TierCrossingType.TIER_DOWN:
                                moment_type = MomentType.CUT
                                note = "Lead cut"

                                # Check for late false drama before emitting CUT boundary
                                pending_event = events[pending_index]
                                false_drama_decision = is_late_false_drama(
                                    event=pending_event,
                                    prev_state=pending_crossing.prev_state,
                                    curr_state=curr_state,
                                    crossing_type="TIER_DOWN",
                                )
                                false_drama_decision.event_index = pending_index
                                false_drama_decisions.append(false_drama_decision)

                                if false_drama_decision.suppressed:
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
                                    prev_state = curr_state
                                    continue

                            elif pending_crossing.crossing_type == TierCrossingType.TIE_BROKEN:
                                moment_type = MomentType.LEAD_BUILD
                                note = "Took the lead"
                            else:
                                moment_type = MomentType.NEUTRAL
                                note = None

                            if is_closing_situation(event, curr_state) and curr_state.tier >= 2:
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
        if is_high_impact_event(event):
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
