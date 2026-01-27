"""Pipeline router endpoints.

This module contains all the FastAPI endpoint handlers for pipeline management.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import selectinload
from typing import Any

from .... import db_models
from ....db import AsyncSession, get_db, AsyncSessionLocal
from ....services.pipeline import PipelineExecutor
from ....services.pipeline.models import PipelineStage
from ....services.pipeline.executor import PipelineExecutionError

from .models import (
    BulkGenerateAsyncResponse,
    BulkGenerateRequest,
    BulkGenerateStatusResponse,
    ContinuePipelineResponse,
    ExecuteStageRequest,
    ExecuteStageResponse,
    GamePipelineRunsResponse,
    GamePipelineSummary,
    PipelineRunResponse,
    RerunPipelineRequest,
    RerunPipelineResponse,
    RunFullPipelineRequest,
    RunFullPipelineResponse,
    StageComparisonResponse,
    StageLogsResponse,
    StageOutputResponse,
    StartPipelineRequest,
    StartPipelineResponse,
)
from .helpers import (
    build_run_response,
    build_run_summary,
    get_run_with_stages,
    get_stage_description,
    summarize_output,
)

router = APIRouter()


# =============================================================================
# BULK GENERATION BACKGROUND TASK
# =============================================================================


async def _run_bulk_pipeline_generation(job_id: int) -> None:
    """Background task to run bulk pipeline generation.

    Job state is persisted in the database for consistency across workers.
    """
    async with AsyncSessionLocal() as session:
        # Load the job record
        job_result = await session.execute(
            select(db_models.BulkStoryGenerationJob).where(
                db_models.BulkStoryGenerationJob.id == job_id
            )
        )
        job = job_result.scalar_one_or_none()
        if not job:
            return

        # Mark job as running
        job.status = "running"
        job.started_at = datetime.utcnow()
        await session.commit()

        try:
            # Query games in the date range for specified leagues
            query = (
                select(db_models.SportsGame)
                .join(db_models.SportsLeague)
                .options(
                    selectinload(db_models.SportsGame.home_team),
                    selectinload(db_models.SportsGame.away_team),
                )
                .where(
                    and_(
                        db_models.SportsGame.game_date >= job.start_date,
                        db_models.SportsGame.game_date <= job.end_date,
                        db_models.SportsGame.status == "final",
                    )
                )
                .order_by(db_models.SportsGame.game_date)
            )

            # Filter by leagues if specified
            if job.leagues:
                query = query.where(db_models.SportsLeague.code.in_(job.leagues))

            result = await session.execute(query)
            games = result.scalars().all()

            # Filter to games that have PBP data
            games_with_pbp = []
            for game in games:
                pbp_count = await session.execute(
                    select(func.count(db_models.SportsGamePlay.id)).where(
                        db_models.SportsGamePlay.game_id == game.id
                    )
                )
                if (pbp_count.scalar() or 0) > 0:
                    games_with_pbp.append(game)

            job.total_games = len(games_with_pbp)
            await session.commit()

            errors_list: list[dict[str, Any]] = []

            for i, game in enumerate(games_with_pbp):
                job.current_game = i + 1
                await session.commit()

                # Check if game already has a v2-moments story
                if not job.force_regenerate:
                    story_result = await session.execute(
                        select(db_models.SportsGameStory).where(
                            db_models.SportsGameStory.game_id == game.id,
                            db_models.SportsGameStory.moments_json.isnot(None),
                        )
                    )
                    existing_story = story_result.scalar_one_or_none()
                    if existing_story:
                        job.skipped += 1
                        await session.commit()
                        continue

                # Run the full pipeline
                try:
                    executor = PipelineExecutor(session)
                    await executor.run_full_pipeline(
                        game_id=game.id,
                        triggered_by="bulk_admin",
                    )
                    await session.commit()
                    job.successful += 1
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    # Re-fetch job after rollback
                    job_result = await session.execute(
                        select(db_models.BulkStoryGenerationJob).where(
                            db_models.BulkStoryGenerationJob.id == job_id
                        )
                    )
                    job = job_result.scalar_one()
                    job.failed += 1
                    errors_list.append({"game_id": game.id, "error": str(e)})
                    await session.commit()

                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.2)

            # Mark job as completed
            job.status = "completed"
            job.finished_at = datetime.utcnow()
            job.errors_json = errors_list
            await session.commit()

        except Exception as e:
            # Mark job as failed on unexpected error
            await session.rollback()
            job_result = await session.execute(
                select(db_models.BulkStoryGenerationJob).where(
                    db_models.BulkStoryGenerationJob.id == job_id
                )
            )
            job = job_result.scalar_one_or_none()
            if job:
                job.status = "failed"
                job.finished_at = datetime.utcnow()
                job.errors_json = [{"error": str(e)}]
                await session.commit()


# =============================================================================
# ENDPOINTS - Pipeline Run Management
# =============================================================================


@router.post(
    "/pipeline/{game_id}/start",
    response_model=StartPipelineResponse,
    summary="Start new pipeline run",
    description="Create a new pipeline run for a game.",
)
async def start_pipeline(
    game_id: int,
    request: StartPipelineRequest,
    session: AsyncSession = Depends(get_db),
) -> StartPipelineResponse:
    """Start a new pipeline run for a game."""
    executor = PipelineExecutor(session)

    try:
        run = await executor.start_pipeline(
            game_id=game_id,
            triggered_by=request.triggered_by,
            auto_chain=request.auto_chain,
        )
        await session.commit()

        run = await get_run_with_stages(session, run.id)
        response = build_run_response(run)

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
    description="Create a new pipeline run and optionally execute stages.",
)
async def rerun_pipeline(
    game_id: int,
    request: RerunPipelineRequest,
    session: AsyncSession = Depends(get_db),
) -> RerunPipelineResponse:
    """Re-run a pipeline for a game by creating a NEW run."""
    executor = PipelineExecutor(session)

    count_result = await session.execute(
        select(func.count(db_models.GamePipelineRun.id)).where(
            db_models.GamePipelineRun.game_id == game_id
        )
    )
    previous_runs = count_result.scalar() or 0

    try:
        run = await executor.start_pipeline(
            game_id=game_id,
            triggered_by=request.triggered_by,
            auto_chain=False,
        )
        await session.flush()

        stages_executed: list[str] = []
        stages_pending = [s.value for s in PipelineStage.ordered_stages()]

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

        run = await get_run_with_stages(session, run.id)

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
    description="Execute a specific stage within a pipeline run.",
)
async def execute_stage(
    run_id: int,
    stage: str,
    request: ExecuteStageRequest = ExecuteStageRequest(),
    session: AsyncSession = Depends(get_db),
) -> ExecuteStageResponse:
    """Execute a specific stage of a pipeline run."""
    try:
        pipeline_stage = PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )

    executor = PipelineExecutor(session)

    try:
        result = await executor.execute_stage(run_id, pipeline_stage)
        await session.commit()

        run = await get_run_with_stages(session, run_id)
        next_stage = pipeline_stage.next_stage()

        output_summary = None
        stage_record = next(
            (s for s in run.stages if s.stage == stage),
            None,
        )
        if stage_record and stage_record.output_json:
            output_summary = summarize_output(stage, stage_record.output_json)

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
            message=(
                "Stage completed successfully"
                if result.success
                else f"Stage failed: {result.error}"
            ),
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
    executor = PipelineExecutor(session)

    try:
        result = await executor.execute_next_stage(run_id)
        await session.commit()

        run = await get_run_with_stages(session, run_id)
        response = build_run_response(run)

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
    description="Create a new run and execute all stages.",
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

        run = await get_run_with_stages(session, run.id)

        completed = sum(1 for s in run.stages if s.status == "success")
        failed = sum(1 for s in run.stages if s.status == "failed")

        duration = None
        if run.started_at and run.finished_at:
            duration = (run.finished_at - run.started_at).total_seconds()

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
    run = await get_run_with_stages(session, run_id)
    return build_run_response(run)


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
    result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(selectinload(db_models.GamePipelineRun.stages))
        .where(db_models.GamePipelineRun.game_id == game_id)
        .order_by(db_models.GamePipelineRun.created_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()

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

            artifact_result = await session.execute(
                select(db_models.SportsGameTimelineArtifact)
                .where(db_models.SportsGameTimelineArtifact.game_id == game_id)
                .order_by(db_models.SportsGameTimelineArtifact.generated_at.desc())
                .limit(1)
            )
            artifact = artifact_result.scalar_one_or_none()
            if artifact:
                latest_artifact_at = artifact.generated_at.isoformat()

    has_successful = any(r.status == "completed" for r in runs)

    return GamePipelineRunsResponse(
        game_id=game_id,
        game_info=game_info,
        runs=[build_run_summary(r) for r in runs],
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

    pbp_result = await session.execute(
        select(func.count(db_models.SportsGamePlay.id)).where(
            db_models.SportsGamePlay.game_id == game_id
        )
    )
    has_pbp = (pbp_result.scalar() or 0) > 0

    artifact_result = await session.execute(
        select(db_models.SportsGameTimelineArtifact)
        .where(db_models.SportsGameTimelineArtifact.game_id == game_id)
        .order_by(db_models.SportsGameTimelineArtifact.generated_at.desc())
        .limit(1)
    )
    artifact = artifact_result.scalar_one_or_none()

    runs_result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(selectinload(db_models.GamePipelineRun.stages))
        .where(db_models.GamePipelineRun.game_id == game_id)
        .order_by(db_models.GamePipelineRun.created_at.desc())
    )
    runs = runs_result.scalars().all()

    latest_run = build_run_summary(runs[0]) if runs else None

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
    try:
        PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )

    run = await get_run_with_stages(session, run_id)
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
    try:
        PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )

    run = await get_run_with_stages(session, run_id)
    stage_record = next((s for s in run.stages if s.stage == stage), None)

    if not stage_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage {stage} not found for run {run_id}",
        )

    output = stage_record.output_json
    summary = summarize_output(stage, output) if output else {}

    return StageOutputResponse(
        run_id=run_id,
        run_uuid=str(run.run_uuid),
        stage=stage,
        status=stage_record.status,
        output_json=output,
        output_summary=summary,
        generated_at=(
            stage_record.finished_at.isoformat() if stage_record.finished_at else None
        ),
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
    """Compare a stage's output between two runs."""
    try:
        PipelineStage(stage)
    except ValueError:
        valid_stages = [s.value for s in PipelineStage]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {stage}. Valid stages: {valid_stages}",
        )

    run_a = await get_run_with_stages(session, run_a_id)
    run_b = await get_run_with_stages(session, run_b_id)

    if run_a.game_id != game_id or run_b.game_id != game_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both runs must be for the specified game",
        )

    stage_a = next((s for s in run_a.stages if s.stage == stage), None)
    stage_b = next((s for s in run_b.stages if s.stage == stage), None)

    if not stage_a or not stage_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage {stage} not found in one or both runs",
        )

    output_a = stage_a.output_json or {}
    output_b = stage_b.output_json or {}

    differences: dict[str, Any] = {}

    if stage == "GENERATE_MOMENTS":
        chapters_a = output_a.get("chapter_count", 0)
        chapters_b = output_b.get("chapter_count", 0)
        differences["chapter_count_delta"] = chapters_b - chapters_a
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
            "output_summary": summarize_output(stage, output_a),
        },
        run_b={
            "run_id": run_b.id,
            "run_uuid": str(run_b.run_uuid),
            "created_at": run_b.created_at.isoformat(),
            "status": stage_b.status,
            "output_summary": summarize_output(stage, output_b),
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
    """List all pipeline stages with metadata."""
    stages = []
    for i, stage in enumerate(PipelineStage.ordered_stages()):
        stages.append(
            {
                "name": stage.value,
                "order": i + 1,
                "description": get_stage_description(stage),
                "next_stage": stage.next_stage().value if stage.next_stage() else None,
                "previous_stage": (
                    stage.previous_stage().value if stage.previous_stage() else None
                ),
            }
        )

    return {
        "stages": stages,
        "total_stages": len(stages),
    }


# =============================================================================
# ENDPOINTS - Bulk Generation
# =============================================================================


@router.post(
    "/pipeline/bulk-generate-async",
    response_model=BulkGenerateAsyncResponse,
    summary="Start bulk story generation",
    description="Start an async job to generate stories for multiple games.",
)
async def bulk_generate_async(
    request: BulkGenerateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> BulkGenerateAsyncResponse:
    """Start bulk story generation as a background job.

    Job state is persisted in the database for consistency across workers.
    """
    # Parse date strings to datetime
    start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(request.end_date, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59
    )

    # Create job record in database
    job = db_models.BulkStoryGenerationJob(
        status="pending",
        start_date=start_dt,
        end_date=end_dt,
        leagues=request.leagues,
        force_regenerate=request.force,
        triggered_by="admin",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    job_uuid = str(job.job_uuid)

    # Start background task
    background_tasks.add_task(_run_bulk_pipeline_generation, job_id=job.id)

    return BulkGenerateAsyncResponse(
        job_id=job_uuid,
        message="Bulk generation job started",
        status_url=f"/api/admin/sports/pipeline/bulk-generate-status/{job_uuid}",
    )


@router.get(
    "/pipeline/bulk-generate-status/{job_id}",
    response_model=BulkGenerateStatusResponse,
    summary="Get bulk generation status",
    description="Get the status of a bulk generation job.",
)
async def get_bulk_generate_status(
    job_id: str,
    session: AsyncSession = Depends(get_db),
) -> BulkGenerateStatusResponse:
    """Get the status of a bulk generation job from the database."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job ID format: {job_id}",
        )

    result = await session.execute(
        select(db_models.BulkStoryGenerationJob).where(
            db_models.BulkStoryGenerationJob.job_uuid == job_uuid
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Map DB status to state for API response
    state_map = {
        "pending": "PENDING",
        "running": "PROGRESS",
        "completed": "SUCCESS",
        "failed": "FAILURE",
    }

    # Build result dict if job is complete
    result_dict = None
    if job.status in ("completed", "failed"):
        result_dict = {
            "total": job.total_games,
            "successful": job.successful,
            "failed": job.failed,
            "skipped": job.skipped,
            "errors": job.errors_json or [],
        }

    return BulkGenerateStatusResponse(
        job_id=str(job.job_uuid),
        state=state_map.get(job.status, "PENDING"),
        current=job.current_game,
        total=job.total_games,
        successful=job.successful,
        failed=job.failed,
        skipped=job.skipped,
        result=result_dict,
    )
