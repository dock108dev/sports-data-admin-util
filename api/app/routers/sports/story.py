"""
Story Generation API endpoints.

Provides endpoints for:
- Fetching game stories (chapters + sections + compact story)
- Regenerating stories
- Bulk generation
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
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
    ChapterEntry,
    GameStoryResponse,
    PlayEntry,
    RegenerateRequest,
    RegenerateResponse,
    SectionEntry,
    TimeRange,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# BULK GENERATION JOB STORE (IN-MEMORY)
# ============================================================================

_bulk_jobs: dict[str, dict[str, Any]] = {}


# Current story version - must match story_builder.py
CURRENT_STORY_VERSION = "2.0.0"


# ============================================================================
# STORY CACHE FUNCTIONS
# ============================================================================


async def get_cached_story(
    session: AsyncSession,
    game_id: int,
) -> GameStoryResponse | None:
    """Retrieve a cached story from the database if it exists.

    Args:
        session: Database session
        game_id: Game ID to look up

    Returns:
        GameStoryResponse if cached story exists with current version and compact_story,
        None otherwise.
    """
    query = select(db_models.SportsGameStory).where(
        and_(
            db_models.SportsGameStory.game_id == game_id,
            db_models.SportsGameStory.story_version == CURRENT_STORY_VERSION,
            db_models.SportsGameStory.has_compact_story == True,
        )
    )
    result = await session.execute(query)
    cached = result.scalar_one_or_none()

    if not cached:
        return None

    logger.info(f"Found cached story for game {game_id}")

    try:
        # Reconstruct GameStoryResponse from cached data
        # chapters_json stores serialized chapters
        chapters = []
        for ch_data in cached.chapters_json or []:
            plays = [PlayEntry(**p) for p in ch_data.get("plays", [])]
            time_range = None
            if ch_data.get("time_range"):
                time_range = TimeRange(**ch_data["time_range"])
            chapters.append(ChapterEntry(
                chapter_id=ch_data["chapter_id"],
                index=ch_data["index"],
                play_start_idx=ch_data["play_start_idx"],
                play_end_idx=ch_data["play_end_idx"],
                play_count=ch_data["play_count"],
                reason_codes=ch_data["reason_codes"],
                period=ch_data.get("period"),
                time_range=time_range,
                plays=plays,
            ))

        # summaries_json stores serialized sections (repurposed field)
        sections = []
        for sec_data in cached.summaries_json or []:
            sections.append(SectionEntry(
                section_index=sec_data["section_index"],
                beat_type=sec_data["beat_type"],
                header=sec_data["header"],
                chapters_included=sec_data["chapters_included"],
                start_score=sec_data["start_score"],
                end_score=sec_data["end_score"],
                notes=sec_data.get("notes", []),
            ))

        # titles_json stores additional metadata (repurposed field)
        metadata = cached.titles_json or {}

        return GameStoryResponse(
            game_id=cached.game_id,
            sport=cached.sport,
            story_version=cached.story_version,
            chapters=chapters,
            sections=sections,
            chapter_count=cached.chapter_count,
            section_count=len(sections),
            total_plays=metadata.get("total_plays", sum(ch.play_count for ch in chapters)),
            compact_story=cached.compact_story,
            word_count=metadata.get("word_count"),
            target_word_count=metadata.get("target_word_count"),
            quality=metadata.get("quality"),
            reading_time_estimate_minutes=cached.reading_time_minutes,
            generated_at=cached.generated_at,
            metadata=metadata.get("extra_metadata", {}),
            has_compact_story=cached.has_compact_story,
        )
    except Exception as e:
        logger.warning(f"Failed to deserialize cached story for game {game_id}: {e}")
        return None


async def save_story_to_cache(
    session: AsyncSession,
    game: db_models.SportsGame,
    story: GameStoryResponse,
) -> None:
    """Save a generated story to the database cache.

    Args:
        session: Database session
        game: Game database object
        story: Generated story response to cache
    """
    try:
        # Serialize chapters
        chapters_json = [
            {
                "chapter_id": ch.chapter_id,
                "index": ch.index,
                "play_start_idx": ch.play_start_idx,
                "play_end_idx": ch.play_end_idx,
                "play_count": ch.play_count,
                "reason_codes": ch.reason_codes,
                "period": ch.period,
                "time_range": ch.time_range.model_dump() if ch.time_range else None,
                "plays": [p.model_dump() for p in ch.plays],
            }
            for ch in story.chapters
        ]

        # Serialize sections (stored in summaries_json - repurposed)
        sections_json = [
            {
                "section_index": sec.section_index,
                "beat_type": sec.beat_type,
                "header": sec.header,
                "chapters_included": sec.chapters_included,
                "start_score": sec.start_score,
                "end_score": sec.end_score,
                "notes": sec.notes,
            }
            for sec in story.sections
        ]

        # Store additional metadata in titles_json (repurposed)
        metadata_json = {
            "word_count": story.word_count,
            "target_word_count": story.target_word_count,
            "quality": story.quality,
            "total_plays": story.total_plays,
            "extra_metadata": story.metadata,
        }

        # Check if story already exists (update) or needs to be created
        existing_query = select(db_models.SportsGameStory).where(
            and_(
                db_models.SportsGameStory.game_id == game.id,
                db_models.SportsGameStory.story_version == CURRENT_STORY_VERSION,
            )
        )
        result = await session.execute(existing_query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.chapters_json = chapters_json
            existing.summaries_json = sections_json
            existing.titles_json = metadata_json
            existing.compact_story = story.compact_story
            existing.chapter_count = story.chapter_count
            existing.reading_time_minutes = story.reading_time_estimate_minutes
            existing.has_compact_story = story.has_compact_story
            existing.generated_at = story.generated_at or datetime.now(timezone.utc)
            existing.total_ai_calls = 1  # Single AI call in chapters-first
            logger.info(f"Updated cached story for game {game.id}")
        else:
            # Create new record
            cached_story = db_models.SportsGameStory(
                game_id=game.id,
                sport=story.sport,
                story_version=CURRENT_STORY_VERSION,
                chapters_json=chapters_json,
                chapter_count=story.chapter_count,
                summaries_json=sections_json,
                titles_json=metadata_json,
                compact_story=story.compact_story,
                reading_time_minutes=story.reading_time_estimate_minutes,
                has_summaries=False,
                has_titles=False,
                has_compact_story=story.has_compact_story,
                generated_at=story.generated_at or datetime.now(timezone.utc),
                total_ai_calls=1,
            )
            session.add(cached_story)
            logger.info(f"Created cached story for game {game.id}")

        await session.commit()
    except Exception as e:
        logger.error(f"Failed to save story to cache for game {game.id}: {e}")
        await session.rollback()
        # Don't re-raise - caching failure shouldn't break the response


async def _run_bulk_generation(
    job_id: str,
    start_date: str,
    end_date: str,
    leagues: list[str],
    force: bool,
) -> None:
    """Background task to run bulk story generation.

    Args:
        job_id: Unique job identifier for tracking
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        leagues: List of league codes to process
        force: If True, regenerate even if story already exists.
               If False, skip games that already have stories.
    """
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

            # Get existing stories to check which games already have them
            game_ids = [g.id for g in games_with_pbp]
            existing_stories_query = select(db_models.SportsGameStory.game_id).where(
                and_(
                    db_models.SportsGameStory.game_id.in_(game_ids),
                    db_models.SportsGameStory.story_version == CURRENT_STORY_VERSION,
                    db_models.SportsGameStory.has_compact_story == True,
                )
            )
            existing_result = await session.execute(existing_stories_query)
            existing_story_game_ids = set(existing_result.scalars().all())

            job["total"] = len(games_with_pbp)
            job["current"] = 0
            job["successful"] = 0
            job["failed"] = 0
            job["skipped"] = 0

            for i, game in enumerate(games_with_pbp):
                job["current"] = i + 1
                job["status"] = f"Processing game {game.id}"

                # Check if story already exists
                if game.id in existing_story_game_ids and not force:
                    logger.info(f"Skipping game {game.id} - story already exists")
                    job["skipped"] += 1
                    continue

                try:
                    # Run the chapters-first pipeline
                    story = await build_game_story_response(game, include_debug=False)
                    # Save to cache
                    await save_story_to_cache(session, game, story)
                    job["successful"] += 1
                    logger.info(f"Generated and cached story for game {game.id}")
                except Exception as e:
                    logger.error(f"Failed to generate story for game {game.id}: {e}")
                    job["failed"] += 1

                # Small delay to avoid overwhelming the AI service
                await asyncio.sleep(0.1)

            job["state"] = "SUCCESS"
            job["status"] = "Complete"
            job["result"] = {
                "success": True,
                "message": f"Generated stories for {job['successful']} games ({job['skipped']} skipped, {job['failed']} failed)",
                "total_games": job["total"],
                "successful": job["successful"],
                "failed": job["failed"],
                "skipped": job["skipped"],
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
    force_regenerate: bool = Query(False, description="Force regeneration, bypassing cache"),
    session: AsyncSession = Depends(get_db),
) -> GameStoryResponse:
    """
    Get game story using chapters-first pipeline.

    Returns cached story if available, otherwise generates and caches.

    Pipeline (only runs if not cached):
    chapters → running_stats → beat_classifier → story_sections →
    headers → quality → target_length → render (SINGLE AI CALL) → validate

    Returns:
    - Chapters with reason codes and play ranges
    - Sections with beat types, headers, and notes
    - Compact story (AI-generated)
    - Quality assessment and word count metadata
    """
    # Check cache first (unless force_regenerate is set)
    if not force_regenerate and not include_debug:
        cached_story = await get_cached_story(session, game_id)
        if cached_story:
            logger.info(f"Returning cached story for game {game_id}")
            return cached_story

    # Fetch game with plays for generation
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
        story = await build_game_story_response(game, include_debug=include_debug)

        # Cache the generated story (unless debug mode, which may have extra data)
        if not include_debug:
            await save_story_to_cache(session, game, story)

        return story
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

        # Save to cache (always save on explicit regenerate)
        await save_story_to_cache(session, game, story)

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
        "skipped": 0,
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
        skipped=job.get("skipped"),
        result=job.get("result"),
    )
