"""Admin endpoints for Moment explainability and inspection.

MOMENT EXPLAINABILITY API
=========================

These endpoints provide full visibility into how moments are generated,
including:

1. CONSTRUCTION TRACES - Why each moment exists
2. REJECTED MOMENTS - Moments that failed validation
3. MERGED MOMENTS - Moments combined during budget enforcement
4. SIGNAL INSPECTION - Lead states and tier crossings used

TRACE DATA SOURCES
==================

Moment traces are stored in the GENERATE_MOMENTS stage output:
- `generation_trace` (summary) - High-level statistics
- `_generation_trace_full` - Complete traces for all moments

Each moment trace includes:
- trigger_type: What signal caused the moment
- input_start_idx, input_end_idx: Play range
- signals: Lead states, tier crossings, runs
- validation: Pass/fail with issues
- actions: History of operations (created, merged, rejected)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Any

from ... import db_models
from ...db import AsyncSession, get_db
from ...services.pipeline.models import PipelineStage

router = APIRouter()


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class MomentTraceSummary(BaseModel):
    """Summary of a moment's construction trace."""
    moment_id: str
    moment_type: str
    trigger_type: str
    trigger_description: str
    play_range: str
    play_count: int
    is_final: bool
    was_rejected: bool
    was_merged: bool
    validation_passed: bool
    issues: list[str]


class MomentTraceDetail(BaseModel):
    """Full detail of a moment's construction trace."""
    moment_id: str
    moment_type: str
    input_start_idx: int
    input_end_idx: int
    play_count: int
    trigger_type: str
    trigger_description: str
    signals: dict[str, Any] = Field(description="Lead states, tier crossings, runs")
    validation: dict[str, Any] = Field(description="Validation results")
    actions: list[dict[str, Any]] = Field(description="Action history")
    is_final: bool
    final_moment_id: str | None
    rejection_reason: str | None
    merged_into_id: str | None
    absorbed_moment_ids: list[str]
    created_at: str


class GenerationTraceSummary(BaseModel):
    """Summary of a moment generation run."""
    game_id: int
    pipeline_run_id: int | None
    pbp_event_count: int
    thresholds: list[int]
    budget: int
    sport: str
    initial_moment_count: int
    rejected_count: int
    merged_count: int
    final_moment_count: int
    rejected_moment_ids: list[str]
    merged_moment_ids: list[str]
    final_moment_ids: list[str | None]


class GenerationTraceResponse(BaseModel):
    """Full generation trace response."""
    run_id: int
    run_uuid: str
    game_id: int
    summary: GenerationTraceSummary
    moment_traces: list[MomentTraceDetail] | None = None


class MomentExplainerResponse(BaseModel):
    """Human-readable explanation of why a moment exists."""
    moment_id: str
    moment_type: str
    explanation: str = Field(description="Human-readable explanation")
    trigger: dict[str, Any]
    signals_summary: str
    validation_summary: str
    play_range_summary: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def _get_generation_trace(
    run_id: int,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """Get the generation trace from a pipeline run's GENERATE_MOMENTS stage."""
    result = await session.execute(
        select(db_models.GamePipelineStage)
        .where(
            db_models.GamePipelineStage.run_id == run_id,
            db_models.GamePipelineStage.stage == PipelineStage.GENERATE_MOMENTS.value,
        )
    )
    stage = result.scalar_one_or_none()
    
    if not stage or not stage.output_json:
        return None
    
    return stage.output_json.get("_generation_trace_full")


def _trace_to_summary(trace: dict[str, Any]) -> MomentTraceSummary:
    """Convert a moment trace dict to summary model."""
    validation = trace.get("validation", {})
    return MomentTraceSummary(
        moment_id=trace.get("moment_id", ""),
        moment_type=trace.get("moment_type", ""),
        trigger_type=trace.get("trigger_type", "unknown"),
        trigger_description=trace.get("trigger_description", ""),
        play_range=f"{trace.get('input_start_idx', 0)}-{trace.get('input_end_idx', 0)}",
        play_count=trace.get("play_count", 0),
        is_final=trace.get("is_final", False),
        was_rejected=trace.get("rejection_reason") is not None,
        was_merged=trace.get("merged_into_id") is not None,
        validation_passed=validation.get("passed", True),
        issues=validation.get("issues", []),
    )


def _trace_to_detail(trace: dict[str, Any]) -> MomentTraceDetail:
    """Convert a moment trace dict to detail model."""
    return MomentTraceDetail(
        moment_id=trace.get("moment_id", ""),
        moment_type=trace.get("moment_type", ""),
        input_start_idx=trace.get("input_start_idx", 0),
        input_end_idx=trace.get("input_end_idx", 0),
        play_count=trace.get("play_count", 0),
        trigger_type=trace.get("trigger_type", "unknown"),
        trigger_description=trace.get("trigger_description", ""),
        signals=trace.get("signals", {}),
        validation=trace.get("validation", {}),
        actions=trace.get("actions", []),
        is_final=trace.get("is_final", False),
        final_moment_id=trace.get("final_moment_id"),
        rejection_reason=trace.get("rejection_reason"),
        merged_into_id=trace.get("merged_into_id"),
        absorbed_moment_ids=trace.get("absorbed_moment_ids", []),
        created_at=trace.get("created_at", ""),
    )


def _generate_explanation(trace: dict[str, Any]) -> str:
    """Generate a human-readable explanation for a moment."""
    moment_type = trace.get("moment_type", "unknown")
    trigger = trace.get("trigger_type", "unknown")
    play_count = trace.get("play_count", 0)
    trigger_desc = trace.get("trigger_description", "")
    
    explanations = {
        "FLIP": f"This moment represents a lead change. The {trigger_desc}.",
        "TIE": f"This moment represents the game being tied. {trigger_desc}.",
        "LEAD_BUILD": f"This moment shows one team extending their lead. {trigger_desc}.",
        "CUT": f"This moment shows one team cutting into the opponent's lead. {trigger_desc}.",
        "CLOSING_CONTROL": f"This is a 'dagger' moment - late game control lock. {trigger_desc}.",
        "HIGH_IMPACT": f"This moment contains a high-impact event. {trigger_desc}.",
        "NEUTRAL": "This moment represents normal game flow without major control changes.",
    }
    
    base = explanations.get(moment_type, f"This is a {moment_type} moment.")
    
    # Add trigger info
    trigger_info = {
        "tier_cross": "Triggered by a Lead Ladder tier crossing.",
        "flip": "Triggered by a lead change.",
        "tie": "Triggered by the game being tied.",
        "closing_lock": "Triggered by late-game control lock.",
        "high_impact": "Triggered by a high-impact event.",
        "stable": "No specific trigger - stable game flow.",
    }
    
    trigger_text = trigger_info.get(trigger, "")
    
    return f"{base} {trigger_text} Contains {play_count} plays."


# =============================================================================
# ENDPOINTS - Generation Trace
# =============================================================================


@router.get(
    "/moments/pipeline-run/{run_id}/trace",
    response_model=GenerationTraceResponse,
    summary="Get moment generation trace",
    description="Get the full generation trace from a pipeline run.",
)
async def get_generation_trace(
    run_id: int,
    include_full_traces: bool = Query(
        default=False,
        description="Include full moment traces (can be large)",
    ),
    session: AsyncSession = Depends(get_db),
) -> GenerationTraceResponse:
    """Get the complete generation trace for a pipeline run.
    
    The trace includes:
    - Summary statistics (initial/rejected/merged/final counts)
    - List of rejected and merged moment IDs
    - Optionally, full traces for all moments
    """
    # Fetch run
    run_result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(selectinload(db_models.GamePipelineRun.stages))
        .where(db_models.GamePipelineRun.id == run_id)
    )
    run = run_result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run {run_id} not found",
        )
    
    # Get generation trace
    trace = await _get_generation_trace(run_id, session)
    
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generation trace found for run {run_id}. "
                   "Make sure GENERATE_MOMENTS stage has completed.",
        )
    
    # Build summary
    summary_data = trace.get("summary", {})
    summary = GenerationTraceSummary(
        game_id=trace.get("game_id", run.game_id),
        pipeline_run_id=trace.get("pipeline_run_id", run_id),
        pbp_event_count=trace.get("pbp_event_count", 0),
        thresholds=trace.get("thresholds", []),
        budget=trace.get("budget", 0),
        sport=trace.get("sport", "NBA"),
        initial_moment_count=summary_data.get("initial_moment_count", 0),
        rejected_count=summary_data.get("rejected_count", 0),
        merged_count=summary_data.get("merged_count", 0),
        final_moment_count=summary_data.get("final_moment_count", 0),
        rejected_moment_ids=[
            t.get("moment_id", "")
            for t in trace.get("moment_traces", {}).values()
            if t.get("rejection_reason")
        ],
        merged_moment_ids=[
            t.get("moment_id", "")
            for t in trace.get("moment_traces", {}).values()
            if t.get("merged_into_id")
        ],
        final_moment_ids=[
            t.get("final_moment_id")
            for t in trace.get("moment_traces", {}).values()
            if t.get("is_final")
        ],
    )
    
    # Optionally include full traces
    moment_traces = None
    if include_full_traces:
        moment_traces = [
            _trace_to_detail(t)
            for t in trace.get("moment_traces", {}).values()
        ]
    
    return GenerationTraceResponse(
        run_id=run.id,
        run_uuid=str(run.run_uuid),
        game_id=run.game_id,
        summary=summary,
        moment_traces=moment_traces,
    )


@router.get(
    "/moments/pipeline-run/{run_id}/trace/{moment_id}",
    response_model=MomentTraceDetail,
    summary="Get single moment trace",
    description="Get the construction trace for a specific moment.",
)
async def get_moment_trace(
    run_id: int,
    moment_id: str,
    session: AsyncSession = Depends(get_db),
) -> MomentTraceDetail:
    """Get the full construction trace for a single moment.
    
    This includes:
    - Input play range
    - Trigger reasons
    - Signals used (lead states, tier crossings, runs)
    - Validation results
    - Action history (created, merged, rejected)
    """
    trace = await _get_generation_trace(run_id, session)
    
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generation trace found for run {run_id}",
        )
    
    moment_traces = trace.get("moment_traces", {})
    
    if moment_id not in moment_traces:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moment {moment_id} not found in trace. "
                   f"Available: {list(moment_traces.keys())[:10]}...",
        )
    
    return _trace_to_detail(moment_traces[moment_id])


@router.get(
    "/moments/pipeline-run/{run_id}/trace/{moment_id}/explain",
    response_model=MomentExplainerResponse,
    summary="Explain a moment",
    description="Get a human-readable explanation of why a moment exists.",
)
async def explain_moment(
    run_id: int,
    moment_id: str,
    session: AsyncSession = Depends(get_db),
) -> MomentExplainerResponse:
    """Get a human-readable explanation of why a moment exists.
    
    This provides a narrative explanation suitable for display
    in admin UIs or debugging.
    """
    trace = await _get_generation_trace(run_id, session)
    
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generation trace found for run {run_id}",
        )
    
    moment_traces = trace.get("moment_traces", {})
    
    if moment_id not in moment_traces:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moment {moment_id} not found in trace",
        )
    
    moment_trace = moment_traces[moment_id]
    
    # Generate explanation
    explanation = _generate_explanation(moment_trace)
    
    # Summarize signals
    signals = moment_trace.get("signals", {})
    signals_summary = "No signals captured."
    if signals:
        parts = []
        if signals.get("tier_crossing"):
            tc = signals["tier_crossing"]
            parts.append(f"Tier crossing: {tc.get('crossing_type', 'unknown')}")
        if signals.get("runs"):
            parts.append(f"{len(signals['runs'])} scoring run(s)")
        if signals.get("start_lead_state"):
            start = signals["start_lead_state"]
            parts.append(f"Start tier: {start.get('tier', 0)}")
        if parts:
            signals_summary = "; ".join(parts)
    
    # Summarize validation
    validation = moment_trace.get("validation", {})
    if validation.get("passed"):
        validation_summary = "Validation passed"
    else:
        issues = validation.get("issues", [])
        validation_summary = f"Validation failed: {', '.join(issues)}" if issues else "Validation failed"
    
    return MomentExplainerResponse(
        moment_id=moment_id,
        moment_type=moment_trace.get("moment_type", "unknown"),
        explanation=explanation,
        trigger={
            "type": moment_trace.get("trigger_type", "unknown"),
            "description": moment_trace.get("trigger_description", ""),
        },
        signals_summary=signals_summary,
        validation_summary=validation_summary,
        play_range_summary=f"Plays {moment_trace.get('input_start_idx', 0)} to {moment_trace.get('input_end_idx', 0)} ({moment_trace.get('play_count', 0)} plays)",
    )


# =============================================================================
# ENDPOINTS - Rejected/Merged Moments
# =============================================================================


@router.get(
    "/moments/pipeline-run/{run_id}/rejected",
    summary="List rejected moments",
    description="Get all moments that were rejected during generation.",
)
async def list_rejected_moments(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all moments that were rejected during generation.
    
    Rejected moments failed validation and were either:
    - Merged into adjacent moments
    - Dropped entirely (rare)
    """
    trace = await _get_generation_trace(run_id, session)
    
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generation trace found for run {run_id}",
        )
    
    rejected = [
        _trace_to_summary(t)
        for t in trace.get("moment_traces", {}).values()
        if t.get("rejection_reason")
    ]
    
    # Group by rejection reason
    by_reason: dict[str, list[MomentTraceSummary]] = {}
    for r in rejected:
        # Get rejection reason from the full trace
        full_trace = trace.get("moment_traces", {}).get(r.moment_id, {})
        reason = full_trace.get("rejection_reason", "unknown")
        if reason not in by_reason:
            by_reason[reason] = []
        by_reason[reason].append(r)
    
    return {
        "run_id": run_id,
        "total_rejected": len(rejected),
        "by_reason": {
            reason: [m.model_dump() for m in moments]
            for reason, moments in by_reason.items()
        },
        "rejected_moments": [m.model_dump() for m in rejected],
    }


@router.get(
    "/moments/pipeline-run/{run_id}/merged",
    summary="List merged moments",
    description="Get all moments that were merged during generation.",
)
async def list_merged_moments(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all moments that were merged during generation.
    
    Merged moments were combined with adjacent moments during:
    - Consecutive same-type merging
    - Quarter limit enforcement
    - Budget enforcement
    """
    trace = await _get_generation_trace(run_id, session)
    
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generation trace found for run {run_id}",
        )
    
    merged = [
        _trace_to_summary(t)
        for t in trace.get("moment_traces", {}).values()
        if t.get("merged_into_id")
    ]
    
    # Build merge tree
    merge_tree: dict[str, list[str]] = {}  # absorber -> list of absorbed
    for t in trace.get("moment_traces", {}).values():
        if t.get("absorbed_moment_ids"):
            merge_tree[t.get("moment_id", "")] = t.get("absorbed_moment_ids", [])
    
    return {
        "run_id": run_id,
        "total_merged": len(merged),
        "merge_tree": merge_tree,
        "merged_moments": [m.model_dump() for m in merged],
    }


# =============================================================================
# ENDPOINTS - Game-level Moment Inspection
# =============================================================================


@router.get(
    "/moments/game/{game_id}/latest-trace",
    summary="Get latest moment trace for game",
    description="Get the generation trace from the most recent pipeline run.",
)
async def get_latest_game_trace(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GenerationTraceResponse:
    """Get the generation trace from the most recent completed pipeline run.
    
    Convenience endpoint for quickly inspecting a game's moments.
    """
    # Find latest completed run
    run_result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(selectinload(db_models.GamePipelineRun.stages))
        .where(
            db_models.GamePipelineRun.game_id == game_id,
            db_models.GamePipelineRun.status == "completed",
        )
        .order_by(db_models.GamePipelineRun.created_at.desc())
        .limit(1)
    )
    run = run_result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No completed pipeline runs found for game {game_id}",
        )
    
    # Delegate to the run-specific endpoint (include full traces for UI)
    return await get_generation_trace(run.id, include_full_traces=True, session=session)
