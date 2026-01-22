"""Pipeline Executor - Orchestrates game pipeline stages.

The PipelineExecutor is responsible for:
1. Creating and managing pipeline runs
2. Executing individual stages
3. Managing stage transitions and auto-chaining
4. Accumulating outputs between stages
5. Tracking status and logs

Key behaviors:
- Admin/manual triggers always disable auto-chain
- Prod triggers can enable auto-chain
- Each stage's output is persisted before proceeding
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession
from ...utils.datetime_utils import now_utc
from .models import PipelineStage, StageInput, StageOutput, StageResult
from .stages import (
    execute_normalize_pbp,
)

logger = logging.getLogger(__name__)


class PipelineExecutionError(Exception):
    """Raised when pipeline execution fails."""
    
    def __init__(self, message: str, stage: PipelineStage | None = None):
        super().__init__(message)
        self.stage = stage


class PipelineExecutor:
    """Orchestrates game pipeline execution.
    
    The executor manages the lifecycle of pipeline runs and stage executions.
    It handles:
    - Creating new pipeline runs
    - Executing individual stages
    - Managing auto-chain behavior
    - Accumulating outputs between stages
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize executor with a database session.
        
        Args:
            session: Async database session
        """
        self.session = session
    
    async def start_pipeline(
        self,
        game_id: int,
        triggered_by: str,
        auto_chain: bool | None = None,
    ) -> db_models.GamePipelineRun:
        """Start a new pipeline run for a game.
        
        Args:
            game_id: Game to process
            triggered_by: Who triggered the run (prod_auto, admin, manual, backfill)
            auto_chain: Whether to auto-proceed (None = infer from triggered_by)
            
        Returns:
            Created GamePipelineRun record
        """
        # Infer auto_chain from trigger type if not specified
        if auto_chain is None:
            # Only prod_auto gets auto-chain by default
            auto_chain = triggered_by == "prod_auto"
        
        # Admin and manual NEVER auto-chain
        if triggered_by in ("admin", "manual"):
            auto_chain = False
        
        logger.info(
            "pipeline_starting",
            extra={
                "game_id": game_id,
                "triggered_by": triggered_by,
                "auto_chain": auto_chain,
            },
        )
        
        # Verify game exists
        game_result = await self.session.execute(
            select(db_models.SportsGame)
            .options(
                selectinload(db_models.SportsGame.league),
                selectinload(db_models.SportsGame.home_team),
                selectinload(db_models.SportsGame.away_team),
            )
            .where(db_models.SportsGame.id == game_id)
        )
        game = game_result.scalar_one_or_none()
        
        if not game:
            raise PipelineExecutionError(f"Game {game_id} not found")
        
        if not game.is_final:
            raise PipelineExecutionError(f"Game {game_id} is not final (status: {game.status})")
        
        # Create pipeline run
        run = db_models.GamePipelineRun(
            game_id=game_id,
            triggered_by=triggered_by,
            auto_chain=auto_chain,
            status="pending",
        )
        self.session.add(run)
        await self.session.flush()
        
        # Create stage records
        for stage in PipelineStage.ordered_stages():
            stage_record = db_models.GamePipelineStage(
                run_id=run.id,
                stage=stage.value,
                status="pending",
            )
            self.session.add(stage_record)
        
        await self.session.flush()
        
        logger.info(
            "pipeline_created",
            extra={
                "run_id": run.id,
                "run_uuid": str(run.run_uuid),
                "game_id": game_id,
            },
        )
        
        return run
    
    async def _get_run(self, run_id: int) -> db_models.GamePipelineRun:
        """Fetch pipeline run with stages."""
        result = await self.session.execute(
            select(db_models.GamePipelineRun)
            .options(selectinload(db_models.GamePipelineRun.stages))
            .where(db_models.GamePipelineRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        
        if not run:
            raise PipelineExecutionError(f"Pipeline run {run_id} not found")
        
        return run
    
    async def _get_stage_record(
        self,
        run_id: int,
        stage: PipelineStage,
    ) -> db_models.GamePipelineStage:
        """Fetch a specific stage record."""
        result = await self.session.execute(
            select(db_models.GamePipelineStage)
            .where(
                db_models.GamePipelineStage.run_id == run_id,
                db_models.GamePipelineStage.stage == stage.value,
            )
        )
        stage_record = result.scalar_one_or_none()
        
        if not stage_record:
            raise PipelineExecutionError(f"Stage {stage.value} not found for run {run_id}")
        
        return stage_record
    
    async def _get_game_context(self, game_id: int) -> dict[str, str]:
        """Build game context for team name resolution."""
        result = await self.session.execute(
            select(db_models.SportsGame)
            .options(
                selectinload(db_models.SportsGame.league),
                selectinload(db_models.SportsGame.home_team),
                selectinload(db_models.SportsGame.away_team),
            )
            .where(db_models.SportsGame.id == game_id)
        )
        game = result.scalar_one_or_none()
        
        if not game:
            return {}
        
        return {
            "sport": game.league.code if game.league else "NBA",
            "home_team_name": game.home_team.name if game.home_team else "Home",
            "away_team_name": game.away_team.name if game.away_team else "Away",
            "home_team_abbrev": game.home_team.abbreviation if game.home_team else "HOME",
            "away_team_abbrev": game.away_team.abbreviation if game.away_team else "AWAY",
        }
    
    async def _accumulate_outputs(
        self,
        run: db_models.GamePipelineRun,
        up_to_stage: PipelineStage,
    ) -> dict[str, Any]:
        """Accumulate outputs from all completed stages up to the given stage.
        
        Each stage builds on the outputs of previous stages.
        """
        accumulated: dict[str, Any] = {}
        
        for stage in PipelineStage.ordered_stages():
            if stage == up_to_stage:
                break
            
            # Find stage record
            stage_record = next(
                (s for s in run.stages if s.stage == stage.value),
                None,
            )
            
            if stage_record and stage_record.output_json:
                # Merge stage output into accumulated
                accumulated.update(stage_record.output_json)
        
        return accumulated
    
    async def execute_stage(
        self,
        run_id: int,
        stage: PipelineStage,
    ) -> StageResult:
        """Execute a specific stage of the pipeline.
        
        Args:
            run_id: Pipeline run ID
            stage: Stage to execute
            
        Returns:
            StageResult with success/failure and output
        """
        start_time = datetime.utcnow()
        
        logger.info(
            "stage_starting",
            extra={"run_id": run_id, "stage": stage.value},
        )
        
        # Fetch run and stage record
        run = await self._get_run(run_id)
        stage_record = await self._get_stage_record(run_id, stage)
        
        # Validate stage can be executed
        if stage_record.status == "success":
            return StageResult(
                stage=stage,
                success=True,
                output=StageOutput(data=stage_record.output_json or {}),
                duration_seconds=0,
            )
        
        if stage_record.status == "running":
            raise PipelineExecutionError(f"Stage {stage.value} is already running")
        
        # Check prerequisites - previous stage must be complete
        prev_stage = stage.previous_stage()
        if prev_stage:
            prev_record = await self._get_stage_record(run_id, prev_stage)
            if prev_record.status != "success":
                raise PipelineExecutionError(
                    f"Cannot execute {stage.value}: previous stage {prev_stage.value} "
                    f"has status {prev_record.status}"
                )
        
        # Update run and stage status
        run.status = "running"
        run.current_stage = stage.value
        if run.started_at is None:
            run.started_at = now_utc()
        
        stage_record.status = "running"
        stage_record.started_at = now_utc()
        await self.session.flush()
        
        # Build stage input
        game_context = await self._get_game_context(run.game_id)
        accumulated = await self._accumulate_outputs(run, stage)
        
        stage_input = StageInput(
            game_id=run.game_id,
            run_id=run_id,
            previous_output=accumulated if accumulated else None,
            game_context=game_context,
        )
        
        try:
            # Execute the stage
            if stage == PipelineStage.NORMALIZE_PBP:
                output = await execute_normalize_pbp(self.session, stage_input, run_id)
            elif stage == PipelineStage.DERIVE_SIGNALS:
                output = await execute_derive_signals(stage_input)
            elif stage == PipelineStage.GENERATE_MOMENTS:
                output = await execute_generate_moments(stage_input)
            elif stage == PipelineStage.VALIDATE_MOMENTS:
                output = await execute_validate_moments(stage_input)
            elif stage == PipelineStage.FINALIZE_MOMENTS:
                output = await execute_finalize_moments(
                    self.session, stage_input, str(run.run_uuid)
                )
            else:
                raise PipelineExecutionError(f"Unknown stage: {stage.value}")
            
            # Update stage record with success
            stage_record.status = "success"
            stage_record.output_json = output.data
            stage_record.logs_json = output.logs
            stage_record.finished_at = now_utc()
            
            # Calculate duration
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            # Check if pipeline is complete
            if stage == PipelineStage.FINALIZE_MOMENTS:
                run.status = "completed"
                run.finished_at = now_utc()
            elif not run.auto_chain:
                run.status = "paused"
            
            await self.session.flush()
            
            logger.info(
                "stage_completed",
                extra={
                    "run_id": run_id,
                    "stage": stage.value,
                    "duration_seconds": duration,
                },
            )
            
            return StageResult(
                stage=stage,
                success=True,
                output=output,
                duration_seconds=duration,
            )
            
        except Exception as e:
            # Update stage record with failure
            stage_record.status = "failed"
            stage_record.error_details = str(e)
            stage_record.finished_at = now_utc()
            
            run.status = "failed"
            run.finished_at = now_utc()
            
            await self.session.flush()
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            logger.error(
                "stage_failed",
                extra={
                    "run_id": run_id,
                    "stage": stage.value,
                    "error": str(e),
                    "duration_seconds": duration,
                },
                exc_info=True,
            )
            
            return StageResult(
                stage=stage,
                success=False,
                error=str(e),
                duration_seconds=duration,
            )
    
    async def execute_next_stage(self, run_id: int) -> StageResult | None:
        """Execute the next pending stage in the pipeline.
        
        Args:
            run_id: Pipeline run ID
            
        Returns:
            StageResult if a stage was executed, None if pipeline is complete
        """
        run = await self._get_run(run_id)
        
        if not run.can_continue:
            return None
        
        # Find next pending stage
        for stage in PipelineStage.ordered_stages():
            stage_record = next(
                (s for s in run.stages if s.stage == stage.value),
                None,
            )
            
            if stage_record and stage_record.status == "pending":
                return await self.execute_stage(run_id, stage)
        
        return None
    
    async def run_full_pipeline(
        self,
        game_id: int,
        triggered_by: str = "prod_auto",
    ) -> db_models.GamePipelineRun:
        """Run the complete pipeline for a game.
        
        This is a convenience method that creates a run and executes
        all stages in sequence, regardless of auto_chain setting.
        
        Args:
            game_id: Game to process
            triggered_by: Who triggered the run
            
        Returns:
            Completed GamePipelineRun record
        """
        # Start pipeline
        run = await self.start_pipeline(game_id, triggered_by, auto_chain=True)
        
        # Execute all stages
        for stage in PipelineStage.ordered_stages():
            result = await self.execute_stage(run.id, stage)
            
            if not result.success:
                logger.error(
                    "pipeline_failed",
                    extra={
                        "run_id": run.id,
                        "stage": stage.value,
                        "error": result.error,
                    },
                )
                break
        
        # Refresh run to get final status
        run = await self._get_run(run.id)
        
        logger.info(
            "pipeline_finished",
            extra={
                "run_id": run.id,
                "run_uuid": str(run.run_uuid),
                "game_id": game_id,
                "status": run.status,
            },
        )
        
        return run
    
    async def get_run_status(self, run_id: int) -> dict[str, Any]:
        """Get detailed status of a pipeline run.
        
        Args:
            run_id: Pipeline run ID
            
        Returns:
            Dict with run status and stage details
        """
        run = await self._get_run(run_id)
        
        stages = []
        for stage_record in sorted(run.stages, key=lambda s: PipelineStage(s.stage).ordered_stages().index(PipelineStage(s.stage))):
            stages.append({
                "stage": stage_record.stage,
                "status": stage_record.status,
                "started_at": stage_record.started_at.isoformat() if stage_record.started_at else None,
                "finished_at": stage_record.finished_at.isoformat() if stage_record.finished_at else None,
                "error_details": stage_record.error_details,
                "has_output": stage_record.output_json is not None,
                "log_count": len(stage_record.logs_json or []),
            })
        
        return {
            "run_id": run.id,
            "run_uuid": str(run.run_uuid),
            "game_id": run.game_id,
            "triggered_by": run.triggered_by,
            "auto_chain": run.auto_chain,
            "status": run.status,
            "current_stage": run.current_stage,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "stages": stages,
        }
