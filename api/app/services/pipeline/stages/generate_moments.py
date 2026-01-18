"""GENERATE_MOMENTS Stage Implementation.

This stage takes derived signals and partitions the game into narrative moments.
It wraps the existing partition_game function from the moments module.

Input: DerivedSignalsOutput from DERIVE_SIGNALS stage
Output: GeneratedMomentsOutput with moments, notable_moments, and generation_trace

EXPLAINABILITY
==============
This stage captures a full generation trace including:
- Every moment created (initial)
- Rejection reasons for invalid moments
- Merge history showing which moments were combined
- Signals used for each moment (lead states, tier crossings)
- Validation results for each moment

The trace is stored in the stage output for later inspection.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ...moments import (
    partition_game,
    get_notable_moments,
    Moment,
    MOMENT_BUDGET,
    DEFAULT_MOMENT_BUDGET,
)
from ...moment_trace import (
    GenerationTrace,
    SignalSnapshot,
    create_moment_trace_from_moment,
    validate_moment_and_trace,
)
from ..models import GeneratedMomentsOutput, StageInput, StageOutput

logger = logging.getLogger(__name__)


def _moment_to_dict(moment: Moment) -> dict[str, Any]:
    """Convert Moment to JSON-serializable dict."""
    return moment.to_dict()


def _reconstruct_timeline(
    pbp_events: list[dict[str, Any]],
    lead_states: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct timeline from normalized PBP events.
    
    The partition_game function expects the full timeline format.
    We reconstruct it from the normalized PBP events.
    """
    # PBP events from NORMALIZE_PBP already have the required fields:
    # - event_type: "pbp"
    # - phase, quarter, game_clock
    # - home_score, away_score
    # - description, play_type, player_name
    # The partition_game function can work directly with this format.
    return pbp_events


async def execute_generate_moments(
    stage_input: StageInput,
) -> StageOutput:
    """Execute the GENERATE_MOMENTS stage.
    
    Takes derived signals and partitions the game into narrative moments
    using the Lead Ladder-based algorithm.
    
    Also captures a full generation trace for explainability, including:
    - All moments initially created
    - Rejection reasons for invalid moments
    - Merge history
    - Signals used for each moment
    
    Args:
        stage_input: Input containing previous_output from DERIVE_SIGNALS
        
    Returns:
        StageOutput with GeneratedMomentsOutput data including generation_trace
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id
    start_time = datetime.utcnow()
    
    output.add_log(f"Starting GENERATE_MOMENTS for game {game_id}")
    
    # Get input from previous stage
    prev_output = stage_input.previous_output
    if prev_output is None:
        raise ValueError("GENERATE_MOMENTS requires output from DERIVE_SIGNALS stage")
    
    # We need the PBP events from NORMALIZE_PBP stage
    # The executor should merge outputs from previous stages
    pbp_events = prev_output.get("pbp_events", [])
    lead_states = prev_output.get("lead_states", [])
    tier_crossings = prev_output.get("tier_crossings", [])
    runs = prev_output.get("runs", [])
    thresholds = prev_output.get("thresholds", [3, 6, 10, 16])
    
    if not pbp_events:
        raise ValueError("No PBP events in stage input")
    
    output.add_log(f"Processing {len(pbp_events)} PBP events with {len(lead_states)} lead states")
    
    # Initialize generation trace
    trace = GenerationTrace(
        game_id=game_id,
        pipeline_run_id=stage_input.run_id,
        total_timeline_events=len(pbp_events),
        pbp_event_count=len([e for e in pbp_events if e.get("event_type") == "pbp"]),
        thresholds=list(thresholds),
        sport=stage_input.game_context.get("sport", "NBA"),
        started_at=start_time.isoformat(),
    )
    
    # Reconstruct timeline for partition_game
    timeline = _reconstruct_timeline(pbp_events, lead_states)
    
    # Build summary dict (required by partition_game)
    sport = stage_input.game_context.get("sport", "NBA")
    summary = {"sport": sport}
    
    # Get moment budget for this sport
    budget = MOMENT_BUDGET.get(sport, DEFAULT_MOMENT_BUDGET)
    trace.budget = budget
    
    output.add_log(f"Partitioning game with budget={budget}, thresholds={thresholds}")
    
    # Run partitioning
    try:
        moments = partition_game(
            timeline=timeline,
            summary=summary,
            thresholds=thresholds,
            game_context=stage_input.game_context,
        )
    except Exception as e:
        output.add_log(f"Partitioning failed: {e}", "error")
        raise ValueError(f"Failed to partition game: {e}") from e
    
    output.add_log(f"Generated {len(moments)} moments")
    
    # Build traces for all final moments
    trace.final_moment_count = len(moments)
    for moment in moments:
        # Build signal snapshot for this moment
        signals = _build_signal_snapshot(
            moment, lead_states, tier_crossings, runs, thresholds
        )
        
        # Create trace for this moment
        moment_trace = create_moment_trace_from_moment(moment, signals)
        
        # Validate and update trace
        moment_trace = validate_moment_and_trace(moment, moment_trace)
        
        # Mark as final
        moment_trace.is_final = True
        moment_trace.final_moment_id = moment.id
        
        # Add to generation trace
        trace.add_moment_trace(moment_trace)
    
    # Get notable moments
    notable = get_notable_moments(moments)
    output.add_log(f"Found {len(notable)} notable moments")
    
    # Check budget
    within_budget = len(moments) <= budget
    if not within_budget:
        output.add_log(f"WARNING: Moment count ({len(moments)}) exceeds budget ({budget})", "warning")
    
    # Convert moments to dicts
    moments_dict = [_moment_to_dict(m) for m in moments]
    notable_dict = [_moment_to_dict(m) for m in notable]
    
    # Log moment type breakdown
    type_counts: dict[str, int] = {}
    for m in moments:
        type_counts[m.type.value] = type_counts.get(m.type.value, 0) + 1
    output.add_log(f"Moment type breakdown: {type_counts}")
    
    # Finalize trace
    trace.finished_at = datetime.utcnow().isoformat()
    trace.initial_moment_count = len(moments)  # Note: This is post-merge count
    trace.rejected_count = len(trace.get_rejected_moments())
    trace.merged_count = len(trace.get_merged_moments())
    
    output.add_log(f"Generation trace captured: {len(trace.moment_traces)} moment traces")
    
    # Build output with trace
    moments_output = GeneratedMomentsOutput(
        moments=moments_dict,
        notable_moments=notable_dict,
        moment_count=len(moments),
        budget=budget,
        within_budget=within_budget,
        generation_trace=trace.to_summary(),  # Summary for stage output
    )
    
    output.data = moments_output.to_dict()
    
    # Store full trace in a separate key for detailed inspection
    output.data["_generation_trace_full"] = trace.to_dict()
    
    output.add_log("GENERATE_MOMENTS completed successfully")
    
    return output


def _build_signal_snapshot(
    moment: Moment,
    lead_states: list[dict[str, Any]],
    tier_crossings: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    thresholds: list[int],
) -> SignalSnapshot:
    """Build a signal snapshot for a moment.
    
    Captures the lead states and tier crossings that influenced
    this moment's creation.
    """
    # Find lead states at moment boundaries
    start_state = {}
    end_state = {}
    
    for ls in lead_states:
        idx = ls.get("play_index", -1)
        if idx == moment.start_play:
            start_state = ls
        if idx == moment.end_play:
            end_state = ls
    
    # Find tier crossing that triggered this moment (if any)
    crossing = None
    for tc in tier_crossings:
        idx = tc.get("play_index", -1)
        if moment.start_play <= idx <= moment.end_play:
            crossing = tc
            break
    
    # Find runs within this moment
    moment_runs = []
    for run in runs:
        run_start = run.get("start_idx", 0)
        run_end = run.get("end_idx", 0)
        if (run_start >= moment.start_play and run_end <= moment.end_play) or \
           (run_start <= moment.end_play and run_end >= moment.start_play):
            moment_runs.append(run)
    
    return SignalSnapshot(
        start_lead_state=start_state,
        end_lead_state=end_state,
        tier_crossing=crossing,
        runs=moment_runs,
        thresholds=thresholds,
    )
