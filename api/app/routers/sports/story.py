"""
Story Generation API endpoints (Chapters-First Architecture).

Provides endpoints for:
- Fetching game stories (chapters + sections + compact story)
- Regenerating stories
- Bulk generation

This uses the chapters-first pipeline EXCLUSIVELY.
There are no legacy paths, no fallbacks, no dual modes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession, get_db, AsyncSessionLocal
from ...services.chapters import PipelineError, StoryValidationError
from .story_builder import build_game_story_response
from .story_schemas import (
    BulkGenerateAsyncResponse,
    BulkGenerateRequest,
    BulkGenerateStatusResponse,
    GameStoryResponse,
    RegenerateRequest,
    RegenerateResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# BULK GENERATION JOB STORE (IN-MEMORY)
# ============================================================================

_bulk_jobs: dict[str, dict[str, Any]] = {}


async def _run_bulk_generation(
    job_id: str,
    start_date: str,
    end_date: str,
    leagues: list[str],
    force: bool,
) -> None:
    """Background task to run bulk story generation."""
    job = _bulk_jobs[job_id]
    job["state"] = "PROGRESS"
    job["status"] = "Starting..."

    try:
        async with AsyncSessionLocal() as session:
            # Parse dates
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

            # Query games in date range with PBP data
            query = (
                select(db_models.SportsGame)
                .join(db_models.SportsGame.league)
                .options(
                    selectinload(db_models.SportsGame.league),
                    selectinload(db_models.SportsGame.plays).selectinload(
                        db_models.SportsGamePlay.team
                    ),
                )
                .where(
                    and_(
                        db_models.SportsGame.game_date >= start_dt,
                        db_models.SportsGame.game_date <= end_dt,
                        db_models.SportsLeague.code.in_(leagues),
                    )
                )
            )
            result = await session.execute(query)
            games = result.scalars().all()

            # Filter to games with plays
            games_with_pbp = [g for g in games if g.plays and len(g.plays) > 0]

            job["total"] = len(games_with_pbp)
            job["current"] = 0
            job["successful"] = 0
            job["failed"] = 0
            job["cached"] = 0

            for i, game in enumerate(games_with_pbp):
                job["current"] = i + 1
                job["status"] = f"Processing game {game.id}"

                try:
                    # Run the chapters-first pipeline
                    await build_game_story_response(game, include_debug=False)
                    job["successful"] += 1
                except Exception as e:
                    logger.error(f"Failed to generate story for game {game.id}: {e}")
                    job["failed"] += 1

                # Small delay to avoid overwhelming the AI service
                await asyncio.sleep(0.1)

            job["state"] = "SUCCESS"
            job["status"] = "Complete"
            job["result"] = {
                "success": True,
                "message": f"Generated stories for {job['successful']} of {job['total']} games",
                "total_games": job["total"],
                "successful": job["successful"],
                "failed": job["failed"],
                "cached": job["cached"],
                "generated": job["successful"],
            }

    except Exception as e:
        logger.error(f"Bulk generation job {job_id} failed: {e}")
        job["state"] = "FAILURE"
        job["status"] = str(e)


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/games/{game_id}/story", response_model=GameStoryResponse)
async def get_game_story(
    game_id: int,
    include_debug: bool = Query(False, description="Include debug info"),
    session: AsyncSession = Depends(get_db),
) -> GameStoryResponse:
    """
    Get game story using chapters-first pipeline.

    This is the ONLY story generation path. There are no fallbacks.

    Pipeline:
    chapters → running_stats → beat_classifier → story_sections →
    headers → quality → target_length → render (SINGLE AI CALL) → validate

    Returns:
    - Chapters with reason codes and play ranges
    - Sections with beat types, headers, and notes
    - Compact story (AI-generated)
    - Quality assessment and word count metadata
    """
    result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.league),
            selectinload(db_models.SportsGame.plays).selectinload(db_models.SportsGamePlay.team),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = result.scalar_one_or_none()

    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game not found"
        )

    try:
        return await build_game_story_response(game, include_debug=include_debug)
    except PipelineError as e:
        logger.error(f"Pipeline error for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline failed at stage '{e.stage}': {str(e)}"
        )
    except StoryValidationError as e:
        logger.error(f"Validation error for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Story validation failed: {str(e)}"
        )


@router.post("/games/{game_id}/story/regenerate", response_model=RegenerateResponse)
async def regenerate_story(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate story for a game using chapters-first pipeline.

    This runs the full pipeline from scratch:
    chapters → running_stats → beat_classifier → story_sections →
    headers → quality → target_length → render (SINGLE AI CALL) → validate
    """
    try:
        result = await session.execute(
            select(db_models.SportsGame)
            .options(
                selectinload(db_models.SportsGame.league),
                selectinload(db_models.SportsGame.plays).selectinload(db_models.SportsGamePlay.team),
            )
            .where(db_models.SportsGame.id == game_id)
        )
        game = result.scalar_one_or_none()

        if not game:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found"
            )

        # Regenerate story using chapters-first pipeline
        story = await build_game_story_response(game, include_debug=request.debug)

        return RegenerateResponse(
            success=True,
            message=f"Generated story: {story.section_count} sections, {story.word_count or 0} words",
            story=story,
        )

    except PipelineError as e:
        logger.error(f"Pipeline error for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message=f"Pipeline failed at stage '{e.stage}'",
            errors=[str(e)],
        )
    except StoryValidationError as e:
        logger.error(f"Validation error for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message="Story validation failed",
            errors=[str(e)],
        )
    except Exception as e:
        logger.error(f"Failed to regenerate story for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message="Failed to regenerate story",
            errors=[str(e)],
        )


# ============================================================================
# BULK GENERATION ENDPOINTS
# ============================================================================

@router.post("/games/bulk-generate-async", response_model=BulkGenerateAsyncResponse)
async def bulk_generate_stories_async(
    request: BulkGenerateRequest,
    background_tasks: BackgroundTasks,
) -> BulkGenerateAsyncResponse:
    """
    Start bulk story generation for games in a date range.

    Returns a job ID that can be polled for status.
    Uses the chapters-first pipeline for all games.
    """
    job_id = str(uuid.uuid4())

    # Initialize job state
    _bulk_jobs[job_id] = {
        "state": "PENDING",
        "current": None,
        "total": None,
        "status": "Queued",
        "successful": 0,
        "failed": 0,
        "cached": 0,
        "result": None,
    }

    # Schedule background task
    background_tasks.add_task(
        _run_bulk_generation,
        job_id,
        request.start_date,
        request.end_date,
        request.leagues,
        request.force,
    )

    return BulkGenerateAsyncResponse(
        job_id=job_id,
        message="Bulk generation started",
        status_url=f"/api/admin/sports/games/bulk-generate-status/{job_id}",
    )


@router.get("/games/bulk-generate-status/{job_id}", response_model=BulkGenerateStatusResponse)
async def get_bulk_generate_status(job_id: str) -> BulkGenerateStatusResponse:
    """
    Get status of a bulk generation job.
    """
    if job_id not in _bulk_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    job = _bulk_jobs[job_id]

    return BulkGenerateStatusResponse(
        job_id=job_id,
        state=job["state"],
        current=job.get("current"),
        total=job.get("total"),
        status=job.get("status"),
        successful=job.get("successful"),
        failed=job.get("failed"),
        cached=job.get("cached"),
        result=job.get("result"),
    )
