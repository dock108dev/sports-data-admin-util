"""DERIVE_SIGNALS Stage Implementation.

This stage takes normalized PBP events and computes:
- Lead states at each play
- Tier crossings (moment boundaries)
- Scoring runs

Input: NormalizedPBPOutput from NORMALIZE_PBP stage
Output: DerivedSignalsOutput with lead_states, tier_crossings, runs
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ...compact_mode_thresholds import get_sport_thresholds
from ...lead_ladder import (
    LeadState,
    TierCrossing,
    compute_lead_state,
    detect_tier_crossing,
)
from ...moments_runs import detect_runs, DetectedRun
from ..models import DerivedSignalsOutput, StageInput, StageOutput

logger = logging.getLogger(__name__)

# Default thresholds for NBA (fallback)
DEFAULT_NBA_THRESHOLDS = [3, 6, 10, 16]


def _get_score(event: dict[str, Any]) -> tuple[int, int]:
    """Extract (home_score, away_score) from an event."""
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    return (home, away)


def _lead_state_to_dict(state: LeadState) -> dict[str, Any]:
    """Convert LeadState to JSON-serializable dict."""
    return {
        "home_score": state.home_score,
        "away_score": state.away_score,
        "margin": state.margin,
        "leader": state.leader.value,
        "tier": state.tier,
        "tier_label": state.tier_label,
    }


def _tier_crossing_to_dict(crossing: TierCrossing, play_index: int) -> dict[str, Any]:
    """Convert TierCrossing to JSON-serializable dict."""
    return {
        "play_index": play_index,
        "crossing_type": crossing.crossing_type.value,
        "prev_state": _lead_state_to_dict(crossing.prev_state),
        "curr_state": _lead_state_to_dict(crossing.curr_state),
        "tier_delta": crossing.tier_delta,
        "is_significant": crossing.is_significant,
    }


def _detected_run_to_dict(run: DetectedRun) -> dict[str, Any]:
    """Convert DetectedRun to JSON-serializable dict."""
    return {
        "team": run.team,
        "points": run.points,
        "start_idx": run.start_idx,
        "end_idx": run.end_idx,
        "play_ids": run.play_ids,
    }


def compute_lead_states(
    pbp_events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
) -> list[dict[str, Any]]:
    """Compute lead state at each PBP event.
    
    Returns a list of lead states, one per PBP event, with the play_index
    attached for reference.
    """
    lead_states = []
    
    for event in pbp_events:
        if event.get("event_type") != "pbp":
            continue
        
        home_score, away_score = _get_score(event)
        state = compute_lead_state(home_score, away_score, thresholds)
        
        state_dict = _lead_state_to_dict(state)
        state_dict["play_index"] = event.get("play_index", 0)
        lead_states.append(state_dict)
    
    return lead_states


def find_tier_crossings(
    pbp_events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
) -> list[dict[str, Any]]:
    """Find all tier crossings in the PBP stream.
    
    Returns a list of tier crossing events with play indices.
    """
    crossings = []
    prev_state: LeadState | None = None
    
    for event in pbp_events:
        if event.get("event_type") != "pbp":
            continue
        
        home_score, away_score = _get_score(event)
        curr_state = compute_lead_state(home_score, away_score, thresholds)
        
        if prev_state is not None:
            crossing = detect_tier_crossing(prev_state, curr_state)
            if crossing is not None:
                play_index = event.get("play_index", 0)
                crossings.append(_tier_crossing_to_dict(crossing, play_index))
        
        prev_state = curr_state
    
    return crossings


async def execute_derive_signals(
    stage_input: StageInput,
) -> StageOutput:
    """Execute the DERIVE_SIGNALS stage.
    
    Takes normalized PBP events from the previous stage and computes:
    - Lead states at each play
    - Tier crossings (potential moment boundaries)
    - Scoring runs
    
    Args:
        stage_input: Input containing previous_output from NORMALIZE_PBP
        
    Returns:
        StageOutput with DerivedSignalsOutput data
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id
    
    output.add_log(f"Starting DERIVE_SIGNALS for game {game_id}")
    
    # Get input from previous stage
    prev_output = stage_input.previous_output
    if prev_output is None:
        raise ValueError("DERIVE_SIGNALS requires output from NORMALIZE_PBP stage")
    
    pbp_events = prev_output.get("pbp_events", [])
    if not pbp_events:
        raise ValueError("No PBP events in previous stage output")
    
    output.add_log(f"Processing {len(pbp_events)} PBP events")
    
    # Get thresholds for this sport
    # For now, assume NBA. In the future, this should come from game context.
    sport = stage_input.game_context.get("sport", "NBA")
    try:
        thresholds = get_sport_thresholds(sport)
    except Exception:
        output.add_log(f"Could not get thresholds for {sport}, using NBA defaults", "warning")
        thresholds = DEFAULT_NBA_THRESHOLDS
    
    output.add_log(f"Using thresholds: {thresholds}")
    
    # Compute lead states
    lead_states = compute_lead_states(pbp_events, thresholds)
    output.add_log(f"Computed {len(lead_states)} lead states")
    
    # Find tier crossings
    tier_crossings = find_tier_crossings(pbp_events, thresholds)
    output.add_log(f"Found {len(tier_crossings)} tier crossings")
    
    # Detect runs
    runs = detect_runs(pbp_events)
    runs_dict = [_detected_run_to_dict(r) for r in runs]
    output.add_log(f"Detected {len(runs_dict)} scoring runs")
    
    # Log crossing breakdown
    crossing_types = {}
    for crossing in tier_crossings:
        ct = crossing["crossing_type"]
        crossing_types[ct] = crossing_types.get(ct, 0) + 1
    output.add_log(f"Crossing breakdown: {crossing_types}")
    
    # Build output
    signals_output = DerivedSignalsOutput(
        lead_states=lead_states,
        tier_crossings=tier_crossings,
        runs=runs_dict,
        thresholds=list(thresholds),
    )
    
    output.data = signals_output.to_dict()
    output.add_log("DERIVE_SIGNALS completed successfully")
    
    return output
