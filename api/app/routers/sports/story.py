"""
Story Generation API endpoints.

ISSUE 14: Wire GameStory Output to Admin UI

Provides endpoints for:
- Fetching game stories (chapters + summaries + compact story)
- Fetching story state for debugging
- Regenerating story components
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession, get_db
from ...services.chapters import (
    ChapterizerV1,
    build_chapters,
    derive_story_state_from_chapters,
    generate_summaries_sequentially,
    generate_titles_for_chapters,
    generate_compact_story,
)
from ...services.openai_client import get_openai_client
from .story_builder import build_game_story_response
from .story_schemas import (
    GameStoryResponse,
    RegenerateRequest,
    RegenerateResponse,
    StoryStateResponse,
    PlayerStoryState,
    TeamStoryState,
    BulkGenerateRequest,
    BulkGenerateResponse,
    BulkGenerateResult,
    BulkGenerateJobResponse,
    JobStatusResponse,
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
    Get game story (chapters + summaries + compact story).
    
    This is the single source of truth for the Admin UI Story Generator.
    
    Returns:
    - Chapters with reason codes and play ranges
    - Chapter summaries and titles (if generated)
    - Compact game story (if generated)
    - Generation status flags
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
    
    return await build_game_story_response(game, include_debug=include_debug)


@router.get("/games/{game_id}/story-state", response_model=StoryStateResponse)
async def get_story_state(
    game_id: int,
    chapter: int = Query(..., description="Chapter index (0-based)"),
    session: AsyncSession = Depends(get_db),
) -> StoryStateResponse:
    """
    Get story state before a specific chapter.
    
    Used for debugging AI context and verifying no future knowledge leakage.
    
    Returns:
    - Player signals (top 6 by points)
    - Team signals (score, momentum)
    - Theme tags
    - Constraints validation
    """
    # Get game story
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
    
    # Build chapters
    plays = sorted(game.plays or [], key=lambda p: p.play_index)
    if not plays:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Game has no plays"
        )
    
    timeline = [
        {
            "play_index": p.play_index,
            "quarter": p.quarter,
            "game_clock": p.game_clock,
            "play_type": p.play_type,
            "description": p.description,
            "team": p.team,
            "score_home": p.score_home,
            "score_away": p.score_away,
        }
        for p in plays
    ]
    
    sport = game.league.code if game.league else "NBA"
    game_story = build_chapters(timeline=timeline, game_id=game.id, sport=sport)
    
    if chapter >= len(game_story.chapters):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chapter {chapter} out of range (0-{len(game_story.chapters)-1})"
        )
    
    # Derive story state from prior chapters
    prior_chapters = game_story.chapters[:chapter]
    story_state = derive_story_state_from_chapters(prior_chapters, sport=sport)
    
    # Map to response
    players = {
        name: PlayerStoryState(
            player_name=name,
            points_so_far=player.points_so_far,
            made_fg_so_far=player.made_fg_so_far,
            made_3pt_so_far=player.made_3pt_so_far,
            made_ft_so_far=player.made_ft_so_far,
            notable_actions_so_far=player.notable_actions_so_far,
        )
        for name, player in story_state.players.items()
    }
    
    teams = {
        name: TeamStoryState(
            team_name=name,
            score_so_far=team.score_so_far,
        )
        for name, team in story_state.teams.items()
    }
    
    return StoryStateResponse(
        chapter_index_last_processed=story_state.chapter_index_last_processed,
        players=players,
        teams=teams,
        momentum_hint=story_state.momentum_hint.value,
        theme_tags=story_state.theme_tags,
        constraints=story_state.constraints,
    )


@router.post("/games/{game_id}/story/regenerate-chapters", response_model=RegenerateResponse)
async def regenerate_chapters(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate chapters for a game.
    
    This resets summaries and compact story.
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
        
        # Regenerate story
        story = await build_game_story_response(game, include_debug=request.debug)
        
        return RegenerateResponse(
            success=True,
            message=f"Regenerated {story.chapter_count} chapters",
            story=story,
        )
    
    except Exception as e:
        logger.error(f"Failed to regenerate chapters for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message="Failed to regenerate chapters",
            errors=[str(e)],
        )


@router.post("/games/{game_id}/story/regenerate-summaries", response_model=RegenerateResponse)
async def regenerate_summaries(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate chapter summaries for a game.
    
    ISSUE 3.0: Sequential per-chapter summary generation using prior context only.
    
    This generates summaries for each chapter sequentially, ensuring:
    - No future knowledge
    - Prior context only
    - Callbacks from earlier chapters
    """
    try:
        # Get OpenAI client
        ai_client = get_openai_client()
        if not ai_client:
            return RegenerateResponse(
                success=False,
                message="OpenAI API key not configured",
                errors=["Add OPENAI_API_KEY to .env to enable AI summary generation"],
            )
        
        # Get game
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
        
        # Build chapters (deterministic structure)
        plays = sorted(game.plays or [], key=lambda p: p.play_index)
        timeline = [
            {
                "event_type": "pbp",
                "play_index": p.play_index,
                "quarter": p.quarter,
                "game_clock": p.game_clock,
                "play_type": p.play_type,
                "description": p.description,
                "team": p.team.abbreviation if p.team else None,
                "home_score": p.home_score,
                "away_score": p.away_score,
            }
            for p in plays
        ]
        
        sport = game.league.code if game.league else "NBA"
        game_story = build_chapters(timeline=timeline, game_id=game.id, sport=sport)
        
        # Generate summaries sequentially (ISSUE 3.0)
        logger.info(f"Generating summaries for {len(game_story.chapters)} chapters")
        summary_results = generate_summaries_sequentially(
            chapters=game_story.chapters,
            sport=sport,
            ai_client=ai_client,
        )
        
        # Update chapters with summaries
        for idx, (chapter, summary_result) in enumerate(zip(game_story.chapters, summary_results)):
            chapter.summary = summary_result.chapter_summary
            chapter.title = summary_result.chapter_title
        
        # Rebuild response with summaries
        story = await build_game_story_response(game, include_debug=request.debug)
        
        # Inject generated summaries into response
        for idx, summary_result in enumerate(summary_results):
            if idx < len(story.chapters):
                story.chapters[idx].chapter_summary = summary_result.chapter_summary
                story.chapters[idx].chapter_title = summary_result.chapter_title
        
        story.has_summaries = True
        story.has_titles = any(r.chapter_title for r in summary_results)
        
        return RegenerateResponse(
            success=True,
            message=f"Generated summaries for {len(summary_results)} chapters",
            story=story,
        )
    
    except Exception as e:
        logger.error(f"Failed to regenerate summaries for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message="Failed to regenerate summaries",
            errors=[str(e)],
        )


@router.post("/games/{game_id}/story/regenerate-titles", response_model=RegenerateResponse)
async def regenerate_titles(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate chapter titles for a game.
    
    ISSUE 3.1: Generate titles from summaries only.
    
    Requirements:
    - Summaries must already exist
    - Titles derive from summary text only
    - No new information added
    - Safe for UI display
    """
    try:
        # Get OpenAI client
        ai_client = get_openai_client()
        if not ai_client:
            return RegenerateResponse(
                success=False,
                message="OpenAI API key not configured",
                errors=["Add OPENAI_API_KEY to .env to enable AI title generation"],
            )
        
        # Get game
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
        
        # Build chapters
        plays = sorted(game.plays or [], key=lambda p: p.play_index)
        timeline = [
            {
                "event_type": "pbp",
                "play_index": p.play_index,
                "quarter": p.quarter,
                "game_clock": p.game_clock,
                "play_type": p.play_type,
                "description": p.description,
                "team": p.team.abbreviation if p.team else None,
                "home_score": p.home_score,
                "away_score": p.away_score,
            }
            for p in plays
        ]
        
        sport = game.league.code if game.league else "NBA"
        game_story = build_chapters(timeline=timeline, game_id=game.id, sport=sport)
        
        # Check if summaries exist
        if not all(ch.summary for ch in game_story.chapters):
            return RegenerateResponse(
                success=False,
                message="Cannot generate titles: summaries must be generated first",
                errors=["Run 'Regenerate Summaries' first, then regenerate titles"],
            )
        
        # Generate titles from summaries (ISSUE 3.1)
        logger.info(f"Generating titles for {len(game_story.chapters)} chapters")
        title_results = generate_titles_for_chapters(
            chapters=game_story.chapters,
            ai_client=ai_client,
        )
        
        # Update chapters with titles
        for chapter, title_result in zip(game_story.chapters, title_results):
            chapter.title = title_result.chapter_title
        
        # Rebuild response with titles
        story = await build_game_story_response(game, include_debug=request.debug)
        
        # Inject generated titles into response
        for idx, title_result in enumerate(title_results):
            if idx < len(story.chapters):
                story.chapters[idx].chapter_title = title_result.chapter_title
        
        story.has_titles = True
        
        return RegenerateResponse(
            success=True,
            message=f"Generated titles for {len(title_results)} chapters",
            story=story,
        )
    
    except Exception as e:
        logger.error(f"Failed to regenerate titles for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message="Failed to regenerate titles",
            errors=[str(e)],
        )


@router.post("/games/{game_id}/story/regenerate-compact", response_model=RegenerateResponse)
async def regenerate_compact_story(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate compact story for a game.
    
    ISSUE 3.2: Generate full compact game story from ordered chapter summaries.
    
    Requirements:
    - All chapter summaries must exist
    - Uses summaries only (no plays, stats, or story state)
    - Cohesive narrative with hindsight
    - Safe for immediate display
    """
    try:
        # Get OpenAI client
        ai_client = get_openai_client()
        if not ai_client:
            return RegenerateResponse(
                success=False,
                message="OpenAI API key not configured",
                errors=["Add OPENAI_API_KEY to .env to enable AI compact story generation"],
            )
        
        # Get game
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
        
        # Build chapters
        plays = sorted(game.plays or [], key=lambda p: p.play_index)
        timeline = [
            {
                "event_type": "pbp",
                "play_index": p.play_index,
                "quarter": p.quarter,
                "game_clock": p.game_clock,
                "play_type": p.play_type,
                "description": p.description,
                "team": p.team.abbreviation if p.team else None,
                "home_score": p.home_score,
                "away_score": p.away_score,
            }
            for p in plays
        ]
        
        sport = game.league.code if game.league else "NBA"
        game_story = build_chapters(timeline=timeline, game_id=game.id, sport=sport)
        
        # Check if summaries exist
        if not all(ch.summary for ch in game_story.chapters):
            return RegenerateResponse(
                success=False,
                message="Cannot generate compact story: chapter summaries must be generated first",
                errors=["Run 'Regenerate Summaries' first, then regenerate compact story"],
            )
        
        # Extract summaries and titles (ISSUE 3.2: summaries only)
        chapter_summaries = [ch.summary for ch in game_story.chapters]
        chapter_titles = [ch.title for ch in game_story.chapters if ch.title]
        
        # Generate compact story from summaries only
        logger.info(f"Generating compact story from {len(chapter_summaries)} chapter summaries")
        compact_result = generate_compact_story(
            chapter_summaries=chapter_summaries,
            chapter_titles=chapter_titles if len(chapter_titles) == len(chapter_summaries) else None,
            sport=sport,
            ai_client=ai_client,
        )
        
        # Rebuild response with compact story
        story = await build_game_story_response(game, include_debug=request.debug)
        
        # Inject compact story into response
        story.compact_story = compact_result.compact_story
        story.reading_time_estimate_minutes = compact_result.reading_time_minutes
        story.has_compact_story = True
        
        return RegenerateResponse(
            success=True,
            message=f"Generated compact story ({compact_result.word_count} words, {compact_result.reading_time_minutes:.1f} min read)",
            story=story,
        )
    
    except Exception as e:
        logger.error(f"Failed to regenerate compact story for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message="Failed to regenerate compact story",
            errors=[str(e)],
        )


@router.post("/games/{game_id}/story/regenerate-all", response_model=RegenerateResponse)
async def regenerate_all(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate everything (chapters → summaries → compact story).
    
    ISSUE 3.0: Full pipeline execution:
    1. Generate chapters (deterministic)
    2. Generate summaries sequentially (prior context only)
    3. Generate compact story (full arc)
    """
    try:
        # Get OpenAI client
        ai_client = get_openai_client()
        if not ai_client:
            return RegenerateResponse(
                success=False,
                message="OpenAI API key not configured",
                errors=["Add OPENAI_API_KEY to .env to enable AI generation"],
            )
        
        # Get game
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
        
        # Step 1: Build chapters (deterministic structure)
        plays = sorted(game.plays or [], key=lambda p: p.play_index)
        timeline = [
            {
                "event_type": "pbp",
                "play_index": p.play_index,
                "quarter": p.quarter,
                "game_clock": p.game_clock,
                "play_type": p.play_type,
                "description": p.description,
                "team": p.team.abbreviation if p.team else None,
                "home_score": p.home_score,
                "away_score": p.away_score,
            }
            for p in plays
        ]
        
        sport = game.league.code if game.league else "NBA"
        game_story = build_chapters(timeline=timeline, game_id=game.id, sport=sport)
        
        logger.info(f"Step 1/3: Generated {len(game_story.chapters)} chapters")
        
        # Step 2: Generate summaries sequentially
        logger.info(f"Step 2/3: Generating summaries for {len(game_story.chapters)} chapters")
        summary_results = generate_summaries_sequentially(
            chapters=game_story.chapters,
            sport=sport,
            ai_client=ai_client,
        )
        
        # Update chapters with summaries
        for chapter, summary_result in zip(game_story.chapters, summary_results):
            chapter.summary = summary_result.chapter_summary
            chapter.title = summary_result.chapter_title
        
        # Step 3: Generate compact story from summaries (ISSUE 3.2)
        logger.info("Step 3/3: Generating compact story from chapter summaries")
        chapter_summaries = [ch.summary for ch in game_story.chapters]
        chapter_titles = [ch.title for ch in game_story.chapters if ch.title]
        
        compact_result = generate_compact_story(
            chapter_summaries=chapter_summaries,
            chapter_titles=chapter_titles if len(chapter_titles) == len(chapter_summaries) else None,
            sport=sport,
            ai_client=ai_client,
        )
        
        game_story.compact_story = compact_result.compact_story
        game_story.reading_time_estimate_minutes = compact_result.reading_time_minutes
        
        # Rebuild response with all AI content
        story = await build_game_story_response(game, include_debug=request.debug)
        
        # Inject generated content into response
        for idx, summary_result in enumerate(summary_results):
            if idx < len(story.chapters):
                story.chapters[idx].chapter_summary = summary_result.chapter_summary
                story.chapters[idx].chapter_title = summary_result.chapter_title
        
        story.compact_story = compact_result.compact_story
        story.reading_time_estimate_minutes = compact_result.reading_time_estimate_minutes
        story.has_summaries = True
        story.has_titles = any(r.chapter_title for r in summary_results)
        story.has_compact_story = True
        
        return RegenerateResponse(
            success=True,
            message=f"Generated complete story: {len(summary_results)} chapters + compact story",
            story=story,
        )
    
    except Exception as e:
        logger.error(f"Failed to regenerate all for game {game_id}: {e}")
        return RegenerateResponse(
            success=False,
            message="Failed to regenerate story",
            errors=[str(e)],
        )


@router.post("/games/bulk-generate-async", response_model=BulkGenerateJobResponse)
async def bulk_generate_stories_async(
    request: BulkGenerateRequest,
) -> BulkGenerateJobResponse:
    """
    Start a background job to generate stories for all games in a date range.
    
    Returns immediately with a job ID that can be used to check status.
    This allows the UI to remain responsive during long-running generation tasks.
    """
    from app.tasks.story_generation import bulk_generate_stories_task
    
    # Queue the task
    task = bulk_generate_stories_task.delay(
        start_date=request.start_date,
        end_date=request.end_date,
        leagues=request.leagues,
        force_regenerate=request.force,
    )
    
    return BulkGenerateJobResponse(
        job_id=task.id,
        message="Story generation job started",
        status_url=f"/api/admin/sports/games/bulk-generate-status/{task.id}",
    )


@router.get("/games/bulk-generate-status/{job_id}", response_model=JobStatusResponse)
async def get_bulk_generate_status(
    job_id: str,
) -> JobStatusResponse:
    """
    Check the status of a background story generation job.
    
    States:
    - PENDING: Job is queued but not started
    - PROGRESS: Job is running
    - SUCCESS: Job completed successfully
    - FAILURE: Job failed with an error
    """
    from celery.result import AsyncResult
    
    task = AsyncResult(job_id)
    
    response = JobStatusResponse(
        job_id=job_id,
        state=task.state,
    )
    
    if task.state == "PENDING":
        response.status = "Waiting to start..."
    elif task.state == "PROGRESS":
        info = task.info or {}
        response.current = info.get("current")
        response.total = info.get("total")
        response.status = info.get("status", "Processing...")
        response.successful = info.get("successful")
        response.failed = info.get("failed")
        response.cached = info.get("cached")
    elif task.state == "SUCCESS":
        response.result = task.result
        response.status = "Completed"
    elif task.state == "FAILURE":
        response.status = f"Failed: {str(task.info)}"
    
    return response


# Synchronous bulk generation removed - use /games/bulk-generate-async instead
