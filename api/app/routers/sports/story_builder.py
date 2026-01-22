"""
Story builder helper: Maps database models to GameStoryResponse.

This module contains the authoritative mapping layer between
backend database models and frontend DTOs.
"""

from __future__ import annotations

from datetime import datetime

from ... import db_models
from ...services.chapters import build_chapters
from .story_schemas import (
    ChapterEntry,
    GameStoryResponse,
    PlayEntry,
    TimeRange,
)


async def build_game_story_response(
    game: db_models.SportsGame,
    include_debug: bool = False,
) -> GameStoryResponse:
    """
    Build GameStoryResponse from database game object.
    
    This is the authoritative mapping layer between backend and frontend.
    
    Args:
        game: Database game object (with plays eagerly loaded)
        include_debug: Whether to include debug information
        
    Returns:
        GameStoryResponse with chapters and metadata
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
            chapter_summary=None,  # Populated by AI generation
            chapter_title=None,    # Populated by AI generation
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
