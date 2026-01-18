"""Admin endpoints for game pipeline management.

PIPELINE CONTROL SURFACE
========================

These endpoints provide a complete control surface for the admin UI to:
- Start and manage pipeline runs for specific games
- Execute individual pipeline stages with full control
- Re-run stages without deleting prior outputs (creates new runs)
- View detailed status, logs, and outputs for each stage

SAFETY GUARANTEES
=================

1. IMMUTABILITY: Previous runs are NEVER mutated. Re-running a stage
   creates a NEW pipeline run, preserving the complete history.

2. IDEMPOTENCY: Starting a pipeline or executing a stage is NOT idempotent.
   Each call creates new records. Use GET endpoints to check status before
   triggering new executions.

3. ISOLATION: Each run is independent. Failed runs don't affect other runs.
   You can have multiple runs for the same game in different states.

4. AUDITABILITY: All executions are logged with timestamps, triggerer info,
   and full output preservation for debugging and replay.

STAGE EXECUTION RULES
=====================

- Stages must execute in order within a run (NORMALIZE_PBP -> DERIVE_SIGNALS -> ...)
- A stage can only execute if its predecessor succeeded
- Re-running a stage requires creating a new run (use /rerun endpoint)
- Admin/manual triggers NEVER auto-chain; each stage must be explicitly triggered
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from typing import Any

from ... import db_models
from ...db import AsyncSession, get_db
from ...services.pipeline import PipelineExecutor
from ...services.pipeline.models import PipelineStage
from ...services.pipeline.executor import PipelineExecutionError

router = APIRouter()


# =============================================================================
# ENUMS FOR FRONTEND
# =============================================================================


class PipelineRunStatusEnum(str, Enum):
    """Pipeline run status values."""
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"


class StageStatusEnum(str, Enum):
    """Stage execution status values."""
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"


# =============================================================================
# REQUEST MODELS
# =============================================================================


class StartPipelineRequest(BaseModel):
    """Request to start a new pipeline run for a game.
    
    SAFETY: Each call creates a NEW run. Check existing runs first
    using GET /pipeline/game/{game_id} to avoid duplicate runs.
    """
    triggered_by: str = Field(
        default="admin",
        description="Who triggered the run: admin, manual, backfill, prod_auto",
    )
    auto_chain: bool | None = Field(
        default=None,
        description="Auto-proceed to next stage on success. "
                    "None = infer from triggered_by (admin/manual always False)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "triggered_by": "admin",
                "auto_chain": False,
            }
        }
    }


class RerunPipelineRequest(BaseModel):
    """Request to re-run a pipeline for a game.
    
    SAFETY: Creates a NEW run without modifying previous runs.
    The previous run's outputs remain available for comparison.
    """
    triggered_by: str = Field(
        default="admin",
        description="Who triggered the re-run",
    )
    execute_through_stage: str | None = Field(
        default=None,
        description="Execute all stages up to and including this stage. "
                    "None = only create run, don't execute any stages.",
    )
    reason: str | None = Field(
        default=None,
        description="Optional reason for re-running (for audit trail)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "triggered_by": "admin",
                "execute_through_stage": "GENERATE_MOMENTS",
                "reason": "Testing new threshold values",
            }
        }
    }


class ExecuteStageRequest(BaseModel):
    """Request to execute a specific stage.
    
    IDEMPOTENCY: NOT idempotent. If the stage already succeeded,
    the endpoint returns the existing result without re-executing.
    To re-execute, create a new run using /rerun.
    """
    force: bool = Field(
        default=False,
        description="If True, re-execute even if already succeeded (within same run)",
    )


class RunFullPipelineRequest(BaseModel):
    """Request to run the complete pipeline."""
    triggered_by: str = Field(
        default="admin",
        description="Who triggered the run",
    )


# =============================================================================
# RESPONSE MODELS - Stage Level
# =============================================================================


class StageStatusResponse(BaseModel):
    """Status of a single pipeline stage."""
    stage: str = Field(description="Stage name (e.g., NORMALIZE_PBP)")
    stage_order: int = Field(description="Execution order (1-5)")
    status: str = Field(description="pending, running, success, failed, skipped")
    started_at: str | None = Field(description="ISO timestamp when stage started")
    finished_at: str | None = Field(description="ISO timestamp when stage finished")
    duration_seconds: float | None = Field(description="Execution time in seconds")
    error_details: str | None = Field(description="Error message if failed")
    has_output: bool = Field(description="Whether stage has output data")
    output_summary: dict[str, Any] | None = Field(
        description="Summary of output (counts, key metrics)"
    )
    log_count: int = Field(description="Number of log entries")
    can_execute: bool = Field(
        description="Whether this stage can be executed now "
                    "(previous stage succeeded and this one is pending)"
    )


class StageOutputResponse(BaseModel):
    """Full output from a pipeline stage."""
    run_id: int
    run_uuid: str
    stage: str
    status: str
    output_json: dict[str, Any] | None = Field(
        description="Full stage output data"
    )
    output_summary: dict[str, Any] = Field(
        description="Summary metrics from output"
    )
    generated_at: str | None = Field(
        description="When output was generated"
    )


class StageLogsResponse(BaseModel):
    """Logs from a pipeline stage."""
    run_id: int
    run_uuid: str
    stage: str
    status: str
    logs: list[dict[str, Any]] = Field(
        description="Array of log entries with timestamp, level, message"
    )
    log_count: int


# =============================================================================
# RESPONSE MODELS - Run Level
# =============================================================================


class PipelineRunResponse(BaseModel):
    """Full status of a pipeline run."""
    run_id: int
    run_uuid: str
    game_id: int
    triggered_by: str
    auto_chain: bool
    status: str
    current_stage: str | None
    started_at: str | None
    finished_at: str | None
    duration_seconds: float | None
    created_at: str
    stages: list[StageStatusResponse]
    stages_completed: int
    stages_failed: int
    stages_pending: int
    progress_percent: int = Field(
        description="Overall progress as percentage (0-100)"
    )
    can_continue: bool = Field(
        description="Whether pipeline can be continued"
    )
    next_stage: str | None = Field(
        description="Next stage to execute, if any"
    )


class PipelineRunSummary(BaseModel):
    """Summary of a pipeline run for listing."""
    run_id: int
    run_uuid: str
    game_id: int
    triggered_by: str
    status: str
    current_stage: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    stages_completed: int
    stages_total: int
    progress_percent: int


class StartPipelineResponse(BaseModel):
    """Response after starting a pipeline run."""
    run_id: int
    run_uuid: str
    game_id: int
    status: str
    auto_chain: bool
    stages: list[StageStatusResponse]
    next_stage: str
    message: str


class ExecuteStageResponse(BaseModel):
    """Response after executing a stage."""
    run_id: int
    run_uuid: str
    stage: str
    status: str
    success: bool
    duration_seconds: float
    error: str | None = None
    output_summary: dict[str, Any] | None = None
    next_stage: str | None = None
    pipeline_status: str
    message: str


class ContinuePipelineResponse(BaseModel):
    """Response after continuing a pipeline."""
    run_id: int
    run_uuid: str
    stage_executed: str | None
    success: bool
    duration_seconds: float | None
    pipeline_status: str
    stages_completed: int
    stages_remaining: int
    next_stage: str | None
    message: str


class RerunPipelineResponse(BaseModel):
    """Response after re-running a pipeline."""
    new_run_id: int
    new_run_uuid: str
    game_id: int
    previous_runs_count: int
    status: str
    stages_executed: list[str]
    stages_pending: list[str]
    message: str


class RunFullPipelineResponse(BaseModel):
    """Response after running the full pipeline."""
    run_id: int
    run_uuid: str
    game_id: int
    status: str
    stages_completed: int
    stages_failed: int
    duration_seconds: float | None
    artifact_id: int | None = Field(
        description="Timeline artifact ID if finalization succeeded"
    )
    message: str


# =============================================================================
# RESPONSE MODELS - Game Level
# =============================================================================


class GamePipelineRunsResponse(BaseModel):
    """List of pipeline runs for a game."""
    game_id: int
    game_info: dict[str, Any] = Field(
        description="Basic game info (teams, date, status)"
    )
    runs: list[PipelineRunSummary]
    total_runs: int
    has_successful_run: bool
    latest_artifact_at: str | None = Field(
        description="When the latest timeline artifact was generated"
    )


class GamePipelineSummary(BaseModel):
    """Quick summary of pipeline state for a game."""
    game_id: int
    game_date: str
    home_team: str
    away_team: str
    game_status: str
    has_pbp: bool
    has_timeline_artifact: bool
    latest_artifact_at: str | None
    total_pipeline_runs: int
    latest_run: PipelineRunSummary | None
    can_run_pipeline: bool = Field(
        description="Whether a new pipeline can be started (game is final, has PBP)"
    )


class StageComparisonResponse(BaseModel):
    """Compare a stage's output between two runs."""
    game_id: int
    stage: str
    run_a: dict[str, Any]
    run_b: dict[str, Any]
    differences: dict[str, Any] = Field(
        description="Key differences between outputs"
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _build_stage_status(
    stage_record: db_models.GamePipelineStage,
    stage_order: int,
    can_execute: bool,
) -> StageStatusResponse:
    """Build a StageStatusResponse from a stage record."""
    # Calculate duration
    duration = None
    if stage_record.started_at and stage_record.finished_at:
        duration = (stage_record.finished_at - stage_record.started_at).total_seconds()
    
    # Build output summary
    output_summary = None
    if stage_record.output_json:
        output_summary = _summarize_output(stage_record.stage, stage_record.output_json)
    
    return StageStatusResponse(
        stage=stage_record.stage,
        stage_order=stage_order,
        status=stage_record.status,
        started_at=stage_record.started_at.isoformat() if stage_record.started_at else None,
        finished_at=stage_record.finished_at.isoformat() if stage_record.finished_at else None,
        duration_seconds=duration,
        error_details=stage_record.error_details,
        has_output=stage_record.output_json is not None,
        output_summary=output_summary,
        log_count=len(stage_record.logs_json or []),
        can_execute=can_execute,
    )


def _summarize_output(stage: str, output: dict[str, Any]) -> dict[str, Any]:
    """Create a summary of stage output for quick viewing."""
    if stage == "NORMALIZE_PBP":
        return {
            "total_plays": output.get("total_plays", 0),
            "has_overtime": output.get("has_overtime", False),
            "phases": list(output.get("phase_boundaries", {}).keys()),
        }
    elif stage == "DERIVE_SIGNALS":
        return {
            "lead_state_count": len(output.get("lead_states", [])),
            "tier_crossing_count": len(output.get("tier_crossings", [])),
            "run_count": len(output.get("runs", [])),
            "thresholds": output.get("thresholds", []),
        }
    elif stage == "GENERATE_MOMENTS":
        return {
            "moment_count": output.get("moment_count", 0),
            "notable_count": len(output.get("notable_moments", [])),
            "budget": output.get("budget", 30),
            "within_budget": output.get("within_budget", True),
        }
    elif stage == "VALIDATE_MOMENTS":
        return {
            "passed": output.get("passed", False),
            "critical_passed": output.get("critical_passed", False),
            "error_count": len(output.get("errors", [])),
            "warning_count": output.get("warnings_count", 0),
        }
    elif stage == "FINALIZE_MOMENTS":
        return {
            "artifact_id": output.get("artifact_id"),
            "timeline_events": output.get("timeline_events", 0),
            "moment_count": output.get("moment_count", 0),
        }
    return {}


async def _get_run_with_stages(
    session: AsyncSession,
    run_id: int,
) -> db_models.GamePipelineRun:
    """Fetch a run with its stages loaded."""
    result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(selectinload(db_models.GamePipelineRun.stages))
        .where(db_models.GamePipelineRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run {run_id} not found",
        )
    return run


def _build_run_response(run: db_models.GamePipelineRun) -> PipelineRunResponse:
    """Build a full PipelineRunResponse from a run."""
    ordered_stages = PipelineStage.ordered_stages()
    stage_map = {s.stage: s for s in run.stages}
    
    stages = []
    prev_succeeded = True
    completed = 0
    failed = 0
    pending = 0
    next_stage = None
    
    for i, stage_enum in enumerate(ordered_stages):
        stage_record = stage_map.get(stage_enum.value)
        if not stage_record:
            continue
        
        is_pending = stage_record.status == "pending"
        can_execute = prev_succeeded and is_pending
        
        if can_execute and next_stage is None:
            next_stage = stage_enum.value
        
        stages.append(_build_stage_status(stage_record, i + 1, can_execute))
        
        if stage_record.status == "success":
            completed += 1
            prev_succeeded = True
        elif stage_record.status == "failed":
            failed += 1
            prev_succeeded = False
        elif stage_record.status == "pending":
            pending += 1
            prev_succeeded = prev_succeeded  # Keep previous state
        else:
            prev_succeeded = False
    
    total_stages = len(ordered_stages)
    progress = int((completed / total_stages) * 100) if total_stages > 0 else 0
    
    duration = None
    if run.started_at and run.finished_at:
        duration = (run.finished_at - run.started_at).total_seconds()
    
    return PipelineRunResponse(
        run_id=run.id,
        run_uuid=str(run.run_uuid),
        game_id=run.game_id,
        triggered_by=run.triggered_by,
        auto_chain=run.auto_chain,
        status=run.status,
        current_stage=run.current_stage,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        duration_seconds=duration,
        created_at=run.created_at.isoformat(),
        stages=stages,
        stages_completed=completed,
        stages_failed=failed,
        stages_pending=pending,
        progress_percent=progress,
        can_continue=run.status in ("pending", "paused", "running") and pending > 0,
        next_stage=next_stage,
    )


def _build_run_summary(run: db_models.GamePipelineRun) -> PipelineRunSummary:
    """Build a PipelineRunSummary from a run."""
    completed = sum(1 for s in run.stages if s.status == "success")
    total = len(run.stages)
    progress = int((completed / total) * 100) if total > 0 else 0
    
    return PipelineRunSummary(
        run_id=run.id,
        run_uuid=str(run.run_uuid),
        game_id=run.game_id,
        triggered_by=run.triggered_by,
        status=run.status,
        current_stage=run.current_stage,
        created_at=run.created_at.isoformat(),
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        stages_completed=completed,
        stages_total=total,
        progress_percent=progress,
    )


# =============================================================================
# ENDPOINTS - Pipeline Run Management
# =============================================================================


@router.post(
    "/pipeline/{game_id}/start",
    response_model=StartPipelineResponse,
    summary="Start new pipeline run",
    description="Create a new pipeline run for a game. Does NOT execute any stages. "
                "Use /execute or /continue to start execution.",
)
async def start_pipeline(
    game_id: int,
    request: StartPipelineRequest,
    session: AsyncSession = Depends(get_db),
) -> StartPipelineResponse:
    """Start a new pipeline run for a game.
    
    Creates a pipeline run with all stages in pending status.
    For admin triggers, auto_chain is always False (must manually continue).
    
    SAFETY: Each call creates a NEW run record. Previous runs are preserved.
    """
    executor = PipelineExecutor(session)
    
    try:
        run = await executor.start_pipeline(
            game_id=game_id,
            triggered_by=request.triggered_by,
            auto_chain=request.auto_chain,
        )
        await session.commit()
        
        # Reload to get stages
        run = await _get_run_with_stages(session, run.id)
        response = _build_run_response(run)
        
        return StartPipelineResponse(
            run_id=run.id,
            run_uuid=str(run.run_uuid),
            game_id=run.game_id,
            status=run.status,
            auto_chain=run.auto_chain,
            stages=response.stages,
            next_stage=PipelineStage.NORMALIZE_PBP.value,
            message=f"Pipeline run created. Execute {PipelineStage.NORMALIZE_PBP.value} to begin.",
        )
        
    except PipelineExecutionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start pipeline: {e}",
        )


@router.post(
    "/pipeline/{game_id}/rerun",
    response_model=RerunPipelineResponse,
    summary="Re-run pipeline (creates new run)",
    description="Create a new pipeline run and optionally execute stages. "
                "Previous runs are NEVER modified.",
)
async def rerun_pipeline(
    game_id: int,
    request: RerunPipelineRequest,
    session: AsyncSession = Depends(get_db),
) -> RerunPipelineResponse:
    """Re-run a pipeline for a game by creating a NEW run.
    
    SAFETY: Previous runs are NEVER mutated. This creates a fresh run
    allowing you to compare outputs between runs.
    
    If execute_through_stage is specified, executes all stages up to
    and including that stage before returning.
    """
    executor = PipelineExecutor(session)
    
    # Count previous runs
    count_result = await session.execute(
        select(func.count(db_models.GamePipelineRun.id))
        .where(db_models.GamePipelineRun.game_id == game_id)
    )
    previous_runs = count_result.scalar() or 0
    
    try:
        # Create new run
        run = await executor.start_pipeline(
            game_id=game_id,
            triggered_by=request.triggered_by,
            auto_chain=False,  # Rerun never auto-chains
        )
        await session.flush()
        
        stages_executed = []
        stages_pending = [s.value for s in PipelineStage.ordered_stages()]
        
        # Execute stages if requested
        if request.execute_through_stage:
            try:
                target_stage = PipelineStage(request.execute_through_stage)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid stage: {request.execute_through_stage}",
                )
            
            for stage in PipelineStage.ordered_stages():
                result = await executor.execute_stage(run.id, stage)
                if result.success:
                    stages_executed.append(stage.value)
                    stages_pending.remove(stage.value)
                else:
                    break
                
                if stage == target_stage:
                    break
        
        await session.commit()
        
        # Get final status
        run = await _get_run_with_stages(session, run.id)
        
        return RerunPipelineResponse(
            new_run_id=run.id,
            new_run_uuid=str(run.run_uuid),
            game_id=game_id,
            previous_runs_count=previous_runs,
            status=run.status,
            stages_executed=stages_executed,
            stages_pending=stages_pending,
            message=f"New run created. {len(stages_executed)} stages executed. "
                    f"Previous runs preserved ({previous_runs} total).",
        )
        
    except PipelineExecutionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to re-run pipeline: {e}",
        )


@router.post(
    "/pipeline/run/{run_id}/execute/{stage}",
    response_model=ExecuteStageResponse,
    summary="Execute specific stage",
    description="Execute a specific stage within a pipeline run. "
                "Previous stages must have succeeded.",
)
async def execute_stage(
    run_id: int,
    stage: str,
    request: ExecuteStageRequest = ExecuteStageRequest(),
    session: AsyncSession = Depends(get_db),
) -> ExecuteStageResponse:
    """Execute a specific stage of a pipeline run.
    
    The previous stage must have completed successfully.
    If the stage already succeeded and force=False, returns existing result.
    
    SAFETY: Stage execution updates the run record but never deletes data.
    """
    # Validate stage name
    try:
        pipeline_stage = PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )
    
    run = await _get_run_with_stages(session, run_id)
    executor = PipelineExecutor(session)
    
    try:
        result = await executor.execute_stage(run_id, pipeline_stage)
        await session.commit()
        
        # Reload run for final status
        run = await _get_run_with_stages(session, run_id)
        next_stage = pipeline_stage.next_stage()
        
        # Get output summary
        output_summary = None
        stage_record = next(
            (s for s in run.stages if s.stage == stage),
            None,
        )
        if stage_record and stage_record.output_json:
            output_summary = _summarize_output(stage, stage_record.output_json)
        
        return ExecuteStageResponse(
            run_id=run_id,
            run_uuid=str(run.run_uuid),
            stage=stage,
            status=stage_record.status if stage_record else "unknown",
            success=result.success,
            duration_seconds=result.duration_seconds,
            error=result.error,
            output_summary=output_summary,
            next_stage=next_stage.value if next_stage else None,
            pipeline_status=run.status,
            message="Stage completed successfully" if result.success else f"Stage failed: {result.error}",
        )
        
    except PipelineExecutionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stage execution failed: {e}",
        )


@router.post(
    "/pipeline/run/{run_id}/continue",
    response_model=ContinuePipelineResponse,
    summary="Continue pipeline",
    description="Execute the next pending stage in the pipeline.",
)
async def continue_pipeline(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> ContinuePipelineResponse:
    """Continue a paused pipeline by executing the next pending stage."""
    run = await _get_run_with_stages(session, run_id)
    executor = PipelineExecutor(session)
    
    try:
        result = await executor.execute_next_stage(run_id)
        await session.commit()
        
        # Reload run for final status
        run = await _get_run_with_stages(session, run_id)
        response = _build_run_response(run)
        
        if result is None:
            return ContinuePipelineResponse(
                run_id=run_id,
                run_uuid=str(run.run_uuid),
                stage_executed=None,
                success=True,
                duration_seconds=None,
                pipeline_status=run.status,
                stages_completed=response.stages_completed,
                stages_remaining=response.stages_pending,
                next_stage=response.next_stage,
                message="Pipeline already complete or no pending stages",
            )
        
        return ContinuePipelineResponse(
            run_id=run_id,
            run_uuid=str(run.run_uuid),
            stage_executed=result.stage.value,
            success=result.success,
            duration_seconds=result.duration_seconds,
            pipeline_status=run.status,
            stages_completed=response.stages_completed,
            stages_remaining=response.stages_pending,
            next_stage=response.next_stage,
            message=f"Executed {result.stage.value}: {'success' if result.success else 'failed'}",
        )
        
    except PipelineExecutionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to continue pipeline: {e}",
        )


@router.post(
    "/pipeline/{game_id}/run-full",
    response_model=RunFullPipelineResponse,
    summary="Run complete pipeline",
    description="Create a new run and execute all stages. "
                "Convenience endpoint for automation.",
)
async def run_full_pipeline(
    game_id: int,
    request: RunFullPipelineRequest,
    session: AsyncSession = Depends(get_db),
) -> RunFullPipelineResponse:
    """Run the complete pipeline for a game in one request."""
    executor = PipelineExecutor(session)
    
    try:
        run = await executor.run_full_pipeline(
            game_id=game_id,
            triggered_by=request.triggered_by,
        )
        await session.commit()
        
        # Reload to get stages
        run = await _get_run_with_stages(session, run.id)
        
        completed = sum(1 for s in run.stages if s.status == "success")
        failed = sum(1 for s in run.stages if s.status == "failed")
        
        duration = None
        if run.started_at and run.finished_at:
            duration = (run.finished_at - run.started_at).total_seconds()
        
        # Get artifact ID if finalization succeeded
        artifact_id = None
        finalize_stage = next(
            (s for s in run.stages if s.stage == "FINALIZE_MOMENTS"),
            None,
        )
        if finalize_stage and finalize_stage.output_json:
            artifact_id = finalize_stage.output_json.get("artifact_id")
        
        return RunFullPipelineResponse(
            run_id=run.id,
            run_uuid=str(run.run_uuid),
            game_id=run.game_id,
            status=run.status,
            stages_completed=completed,
            stages_failed=failed,
            duration_seconds=duration,
            artifact_id=artifact_id,
            message=f"Pipeline {run.status} with {completed}/{len(run.stages)} stages completed",
        )
        
    except PipelineExecutionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution failed: {e}",
        )


# =============================================================================
# ENDPOINTS - Status and Info
# =============================================================================


@router.get(
    "/pipeline/run/{run_id}",
    response_model=PipelineRunResponse,
    summary="Get run status",
    description="Get detailed status of a pipeline run including all stages.",
)
async def get_run_status(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> PipelineRunResponse:
    """Get detailed status of a pipeline run."""
    run = await _get_run_with_stages(session, run_id)
    return _build_run_response(run)


@router.get(
    "/pipeline/game/{game_id}",
    response_model=GamePipelineRunsResponse,
    summary="List runs for game",
    description="List all pipeline runs for a game, most recent first.",
)
async def get_game_pipeline_runs(
    game_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    include_game_info: bool = Query(default=True),
    session: AsyncSession = Depends(get_db),
) -> GamePipelineRunsResponse:
    """List all pipeline runs for a game."""
    # Fetch runs with stages
    result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(selectinload(db_models.GamePipelineRun.stages))
        .where(db_models.GamePipelineRun.game_id == game_id)
        .order_by(db_models.GamePipelineRun.created_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()
    
    # Get game info
    game_info: dict[str, Any] = {}
    latest_artifact_at = None
    
    if include_game_info:
        game_result = await session.execute(
            select(db_models.SportsGame)
            .options(
                selectinload(db_models.SportsGame.home_team),
                selectinload(db_models.SportsGame.away_team),
            )
            .where(db_models.SportsGame.id == game_id)
        )
        game = game_result.scalar_one_or_none()
        
        if game:
            game_info = {
                "game_id": game.id,
                "game_date": game.game_date.isoformat() if game.game_date else None,
                "home_team": game.home_team.name if game.home_team else "Unknown",
                "away_team": game.away_team.name if game.away_team else "Unknown",
                "status": game.status,
            }
            
            # Check for timeline artifact
            artifact_result = await session.execute(
                select(db_models.SportsGameTimelineArtifact)
                .where(db_models.SportsGameTimelineArtifact.game_id == game_id)
                .order_by(db_models.SportsGameTimelineArtifact.generated_at.desc())
                .limit(1)
            )
            artifact = artifact_result.scalar_one_or_none()
            if artifact:
                latest_artifact_at = artifact.generated_at.isoformat()
    
    # Check for successful runs
    has_successful = any(r.status == "completed" for r in runs)
    
    return GamePipelineRunsResponse(
        game_id=game_id,
        game_info=game_info,
        runs=[_build_run_summary(r) for r in runs],
        total_runs=len(runs),
        has_successful_run=has_successful,
        latest_artifact_at=latest_artifact_at,
    )


@router.get(
    "/pipeline/game/{game_id}/summary",
    response_model=GamePipelineSummary,
    summary="Get game pipeline summary",
    description="Quick overview of pipeline state for a game.",
)
async def get_game_pipeline_summary(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GamePipelineSummary:
    """Get a quick summary of pipeline state for a game."""
    # Fetch game with teams
    game_result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()
    
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found",
        )
    
    # Check for PBP data
    pbp_result = await session.execute(
        select(func.count(db_models.SportsGamePlay.id))
        .where(db_models.SportsGamePlay.game_id == game_id)
    )
    has_pbp = (pbp_result.scalar() or 0) > 0
    
    # Check for timeline artifact
    artifact_result = await session.execute(
        select(db_models.SportsGameTimelineArtifact)
        .where(db_models.SportsGameTimelineArtifact.game_id == game_id)
        .order_by(db_models.SportsGameTimelineArtifact.generated_at.desc())
        .limit(1)
    )
    artifact = artifact_result.scalar_one_or_none()
    
    # Get pipeline runs
    runs_result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(selectinload(db_models.GamePipelineRun.stages))
        .where(db_models.GamePipelineRun.game_id == game_id)
        .order_by(db_models.GamePipelineRun.created_at.desc())
    )
    runs = runs_result.scalars().all()
    
    latest_run = _build_run_summary(runs[0]) if runs else None
    
    return GamePipelineSummary(
        game_id=game_id,
        game_date=game.game_date.isoformat() if game.game_date else "",
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        game_status=game.status,
        has_pbp=has_pbp,
        has_timeline_artifact=artifact is not None,
        latest_artifact_at=artifact.generated_at.isoformat() if artifact else None,
        total_pipeline_runs=len(runs),
        latest_run=latest_run,
        can_run_pipeline=game.status == "final" and has_pbp,
    )


# =============================================================================
# ENDPOINTS - Stage Details
# =============================================================================


@router.get(
    "/pipeline/run/{run_id}/stage/{stage}/logs",
    response_model=StageLogsResponse,
    summary="Get stage logs",
    description="Get all log entries from a specific stage execution.",
)
async def get_stage_logs(
    run_id: int,
    stage: str,
    session: AsyncSession = Depends(get_db),
) -> StageLogsResponse:
    """Get logs from a specific stage."""
    # Validate stage name
    try:
        PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )
    
    run = await _get_run_with_stages(session, run_id)
    stage_record = next((s for s in run.stages if s.stage == stage), None)
    
    if not stage_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage {stage} not found for run {run_id}",
        )
    
    logs = stage_record.logs_json or []
    
    return StageLogsResponse(
        run_id=run_id,
        run_uuid=str(run.run_uuid),
        stage=stage,
        status=stage_record.status,
        logs=logs,
        log_count=len(logs),
    )


@router.get(
    "/pipeline/run/{run_id}/stage/{stage}/output",
    response_model=StageOutputResponse,
    summary="Get stage output",
    description="Get the full output data from a specific stage execution.",
)
async def get_stage_output(
    run_id: int,
    stage: str,
    session: AsyncSession = Depends(get_db),
) -> StageOutputResponse:
    """Get full output from a specific stage."""
    # Validate stage name
    try:
        PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )
    
    run = await _get_run_with_stages(session, run_id)
    stage_record = next((s for s in run.stages if s.stage == stage), None)
    
    if not stage_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage {stage} not found for run {run_id}",
        )
    
    output = stage_record.output_json
    summary = _summarize_output(stage, output) if output else {}
    
    return StageOutputResponse(
        run_id=run_id,
        run_uuid=str(run.run_uuid),
        stage=stage,
        status=stage_record.status,
        output_json=output,
        output_summary=summary,
        generated_at=stage_record.finished_at.isoformat() if stage_record.finished_at else None,
    )


@router.get(
    "/pipeline/game/{game_id}/compare/{stage}",
    response_model=StageComparisonResponse,
    summary="Compare stage outputs",
    description="Compare a stage's output between two runs.",
)
async def compare_stage_outputs(
    game_id: int,
    stage: str,
    run_a_id: int = Query(..., description="First run ID"),
    run_b_id: int = Query(..., description="Second run ID"),
    session: AsyncSession = Depends(get_db),
) -> StageComparisonResponse:
    """Compare a stage's output between two runs.
    
    Useful for understanding how changes affect moment generation.
    """
    # Validate stage name
    try:
        PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )
    
    # Fetch both runs
    run_a = await _get_run_with_stages(session, run_a_id)
    run_b = await _get_run_with_stages(session, run_b_id)
    
    # Verify both runs are for the same game
    if run_a.game_id != game_id or run_b.game_id != game_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both runs must be for the specified game",
        )
    
    # Get stage records
    stage_a = next((s for s in run_a.stages if s.stage == stage), None)
    stage_b = next((s for s in run_b.stages if s.stage == stage), None)
    
    if not stage_a or not stage_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage {stage} not found in one or both runs",
        )
    
    # Build comparison
    output_a = stage_a.output_json or {}
    output_b = stage_b.output_json or {}
    
    # Calculate differences based on stage type
    differences: dict[str, Any] = {}
    
    if stage == "GENERATE_MOMENTS":
        moments_a = output_a.get("moment_count", 0)
        moments_b = output_b.get("moment_count", 0)
        differences["moment_count_delta"] = moments_b - moments_a
        differences["notable_count_a"] = len(output_a.get("notable_moments", []))
        differences["notable_count_b"] = len(output_b.get("notable_moments", []))
    elif stage == "DERIVE_SIGNALS":
        crossings_a = len(output_a.get("tier_crossings", []))
        crossings_b = len(output_b.get("tier_crossings", []))
        differences["tier_crossings_delta"] = crossings_b - crossings_a
        differences["runs_count_a"] = len(output_a.get("runs", []))
        differences["runs_count_b"] = len(output_b.get("runs", []))
    elif stage == "VALIDATE_MOMENTS":
        differences["passed_a"] = output_a.get("passed", False)
        differences["passed_b"] = output_b.get("passed", False)
        differences["errors_a"] = len(output_a.get("errors", []))
        differences["errors_b"] = len(output_b.get("errors", []))
    
    return StageComparisonResponse(
        game_id=game_id,
        stage=stage,
        run_a={
            "run_id": run_a.id,
            "run_uuid": str(run_a.run_uuid),
            "created_at": run_a.created_at.isoformat(),
            "status": stage_a.status,
            "output_summary": _summarize_output(stage, output_a),
        },
        run_b={
            "run_id": run_b.id,
            "run_uuid": str(run_b.run_uuid),
            "created_at": run_b.created_at.isoformat(),
            "status": stage_b.status,
            "output_summary": _summarize_output(stage, output_b),
        },
        differences=differences,
    )


# =============================================================================
# ENDPOINTS - Metadata
# =============================================================================


@router.get(
    "/pipeline/stages",
    summary="List pipeline stages",
    description="Get the ordered list of pipeline stages with descriptions.",
)
async def list_pipeline_stages() -> dict[str, Any]:
    """List all pipeline stages with metadata.
    
    Useful for building dynamic UIs.
    """
    stages = []
    for i, stage in enumerate(PipelineStage.ordered_stages()):
        stages.append({
            "name": stage.value,
            "order": i + 1,
            "description": _get_stage_description(stage),
            "next_stage": stage.next_stage().value if stage.next_stage() else None,
            "previous_stage": stage.previous_stage().value if stage.previous_stage() else None,
        })
    
    return {
        "stages": stages,
        "total_stages": len(stages),
    }


def _get_stage_description(stage: PipelineStage) -> str:
    """Get human-readable description for a stage."""
    descriptions = {
        PipelineStage.NORMALIZE_PBP: "Read PBP data from database and normalize with phase assignments",
        PipelineStage.DERIVE_SIGNALS: "Compute lead states, tier crossings, and scoring runs",
        PipelineStage.GENERATE_MOMENTS: "Partition game into narrative moments using Lead Ladder",
        PipelineStage.VALIDATE_MOMENTS: "Validate moment structure, ordering, and coverage",
        PipelineStage.FINALIZE_MOMENTS: "Merge with social posts and persist timeline artifact",
    }
    return descriptions.get(stage, "Unknown stage")
