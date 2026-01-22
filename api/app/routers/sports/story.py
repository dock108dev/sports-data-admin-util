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
from .story_schemas import (
    ChapterEntry,
    GameStoryResponse,
    PlayEntry,
    RegenerateRequest,
    RegenerateResponse,
    StoryStateResponse,
    TimeRange,
    PlayerStoryState,
    TeamStoryState,
    BulkGenerateRequest,
    BulkGenerateResponse,
    BulkGenerateResult,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER: BUILD GAME STORY FROM DATABASE
# ============================================================================

async def _build_game_story(
    game: db_models.SportsGame,
    include_debug: bool = False,
) -> GameStoryResponse:
    """
    Build GameStoryResponse from database game object.
    
    This is the authoritative mapping layer between backend and frontend.
    """
    # Get plays
    plays = sorted(game.plays or [], key=lambda p: p.play_index)
    
    if not plays:
        return GameStoryResponse(
            game_id=game.id,
            sport=game.league.code if game.league else "UNKNOWN",
            story_version="1.0.0",
            chapters=[],
            chapter_count=0,
            total_plays=0,
            generated_at=None,
            metadata={},
            has_summaries=False,
            has_titles=False,
            has_compact_story=False,
        )
    
    # Build timeline for chapterization
    # The builder expects events with event_type="pbp"
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
    
    # Generate chapters using ChapterizerV1
    sport = game.league.code if game.league else "NBA"
    game_story = build_chapters(
        timeline=timeline,
        game_id=game.id,
        sport=sport,
        metadata={"generated_at": datetime.utcnow().isoformat()},
    )
    
    # Map to frontend DTO
    chapters = []
    for idx, chapter in enumerate(game_story.chapters):
        # Map plays
        chapter_plays = [
            PlayEntry(
                play_index=p.raw_data.get("play_index", p.index),
                quarter=p.raw_data.get("quarter"),
                game_clock=p.raw_data.get("game_clock"),
                play_type=p.raw_data.get("play_type", p.event_type),
                description=p.raw_data.get("description", ""),
                team=p.raw_data.get("team"),
                score_home=p.raw_data.get("home_score"),
                score_away=p.raw_data.get("away_score"),
            )
            for p in chapter.plays
        ]
        
        # Map time range
        time_range = None
        if chapter.time_range:
            time_range = TimeRange(
                start=chapter.time_range.start,
                end=chapter.time_range.end,
            )
        
        # Build chapter entry
        chapter_entry = ChapterEntry(
            chapter_id=chapter.chapter_id,
            index=idx,
            play_start_idx=chapter.play_start_idx,
            play_end_idx=chapter.play_end_idx,
            play_count=len(chapter.plays),
            reason_codes=chapter.reason_codes,
            period=chapter.period,
            time_range=time_range,
            chapter_summary=None,  # TODO: Load from DB if exists
            chapter_title=None,    # TODO: Load from DB if exists
            plays=chapter_plays,
            chapter_fingerprint=None,  # TODO: Add if include_debug
            boundary_logs=None,        # TODO: Add if include_debug
        )
        
        chapters.append(chapter_entry)
    
    # Determine generation status
    has_summaries = any(ch.chapter_summary for ch in chapters)
    has_titles = any(ch.chapter_title for ch in chapters)
    has_compact_story = game_story.compact_story is not None
    
    return GameStoryResponse(
        game_id=game.id,
        sport=sport,
        story_version="1.0.0",
        chapters=chapters,
        chapter_count=len(chapters),
        total_plays=len(plays),
        compact_story=game_story.compact_story,
        reading_time_estimate_minutes=game_story.reading_time_estimate_minutes,
        generated_at=datetime.utcnow(),
        metadata=game_story.metadata,
        has_summaries=has_summaries,
        has_titles=has_titles,
        has_compact_story=has_compact_story,
    )


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
    
    return await _build_game_story(game, include_debug=include_debug)


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
        story = await _build_game_story(game, include_debug=request.debug)
        
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
        story = await _build_game_story(game, include_debug=request.debug)
        
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
        story = await _build_game_story(game, include_debug=request.debug)
        
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
        story = await _build_game_story(game, include_debug=request.debug)
        
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
        story = await _build_game_story(game, include_debug=request.debug)
        
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


@router.post("/games/bulk-generate", response_model=BulkGenerateResponse)
async def bulk_generate_stories(
    request: BulkGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> BulkGenerateResponse:
    """
    Generate stories for all games in a date range.
    
    This is useful for:
    - Initial story generation for historical games
    - Regenerating stories after rule changes
    - Daily batch processing of new games
    
    Returns summary of successes and failures.
    """
    from datetime import datetime as dt
    
    try:
        # Parse dates
        start_date = dt.strptime(request.start_date, "%Y-%m-%d").date()
        end_date = dt.strptime(request.end_date, "%Y-%m-%d").date()
        
        # Find games in date range with PBP
        result = await session.execute(
            select(db_models.SportsGame)
            .join(db_models.SportsLeague)
            .options(
                selectinload(db_models.SportsGame.league),
                selectinload(db_models.SportsGame.plays).selectinload(db_models.SportsGamePlay.team),
            )
            .where(
                db_models.SportsGame.game_date >= start_date,
                db_models.SportsGame.game_date <= end_date,
                db_models.SportsLeague.code.in_(request.leagues),
            )
            .order_by(db_models.SportsGame.game_date, db_models.SportsGame.id)
        )
        games = result.scalars().all()
        
        # Filter to games with PBP
        games_with_pbp = [g for g in games if g.plays and len(g.plays) > 0]
        
        logger.info(
            "bulk_generate_started",
            extra={
                "start_date": request.start_date,
                "end_date": request.end_date,
                "leagues": request.leagues,
                "total_games": len(games),
                "games_with_pbp": len(games_with_pbp),
            }
        )
        
        # Generate stories
        results = []
        successful = 0
        failed = 0
        
        for game in games_with_pbp:
            try:
                story = await _build_game_story(game, include_debug=False)
                
                results.append(BulkGenerateResult(
                    game_id=game.id,
                    success=True,
                    message=f"Generated {story.chapter_count} chapters",
                    chapter_count=story.chapter_count,
                ))
                successful += 1
                
            except Exception as e:
                logger.error(f"Failed to generate story for game {game.id}: {e}")
                results.append(BulkGenerateResult(
                    game_id=game.id,
                    success=False,
                    message="Failed to generate story",
                    error=str(e),
                ))
                failed += 1
        
        logger.info(
            "bulk_generate_complete",
            extra={
                "total_games": len(games_with_pbp),
                "successful": successful,
                "failed": failed,
            }
        )
        
        return BulkGenerateResponse(
            success=True,
            message=f"Processed {len(games_with_pbp)} games: {successful} successful, {failed} failed",
            total_games=len(games_with_pbp),
            successful=successful,
            failed=failed,
            results=results,
        )
    
    except Exception as e:
        logger.error(f"Bulk generation failed: {e}")
        return BulkGenerateResponse(
            success=False,
            message=f"Bulk generation failed: {str(e)}",
            total_games=0,
            successful=0,
            failed=0,
        )
