"""
Story Generation API endpoints (Chapters-First Architecture).

Provides endpoints for:
- Fetching game stories (chapters + sections + compact story)
- Regenerating stories

This uses the chapters-first pipeline EXCLUSIVELY.
There are no legacy paths, no fallbacks, no dual modes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession, get_db
from ...services.chapters import PipelineError, StoryValidationError
from .story_builder import build_game_story_response
from .story_schemas import (
    GameStoryResponse,
    RegenerateRequest,
    RegenerateResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


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
