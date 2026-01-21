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
                play_index=p.play_index,
                quarter=p.raw_data.get("quarter"),
                game_clock=p.raw_data.get("game_clock"),
                play_type=p.event_type,
                description=p.description,
                team=p.raw_data.get("team"),
                score_home=p.raw_data.get("score_home"),
                score_away=p.raw_data.get("score_away"),
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
            selectinload(db_models.SportsGame.plays),
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
            selectinload(db_models.SportsGame.plays),
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
                selectinload(db_models.SportsGame.plays),
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
    
    Preserves chapters, resets compact story.
    """
    return RegenerateResponse(
        success=False,
        message="Summary generation not yet implemented",
        errors=["AI integration pending"],
    )


@router.post("/games/{game_id}/story/regenerate-compact", response_model=RegenerateResponse)
async def regenerate_compact_story(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate compact story for a game.
    
    Preserves chapters and summaries.
    """
    return RegenerateResponse(
        success=False,
        message="Compact story generation not yet implemented",
        errors=["AI integration pending"],
    )


@router.post("/games/{game_id}/story/regenerate-all", response_model=RegenerateResponse)
async def regenerate_all(
    game_id: int,
    request: RegenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Regenerate everything (chapters → summaries → compact story).
    """
    return RegenerateResponse(
        success=False,
        message="Full regeneration not yet implemented",
        errors=["AI integration pending"],
    )
