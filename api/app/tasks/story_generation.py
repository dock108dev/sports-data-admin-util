"""Background tasks for story generation."""

import logging
from datetime import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker

from app.celery_app import celery_app
from app import db_models
from app.services.openai_client import get_openai_client
from app.services.chapters import build_chapters
from app.services.chapters.summary_generator import generate_summaries_sequentially
from app.services.chapters.compact_story_generator import generate_compact_story
import os

logger = logging.getLogger(__name__)


def get_async_session():
    """Create async database session for Celery tasks."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    
    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    engine = create_async_engine(database_url, echo=False)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session_maker()


@celery_app.task(bind=True, name="app.tasks.story_generation.bulk_generate_stories_task")
def bulk_generate_stories_task(
    self,
    start_date: str,
    end_date: str,
    leagues: list[str],
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """
    Background task for bulk story generation.
    
    Args:
        self: Celery task instance (for progress updates)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        leagues: List of league codes
        force_regenerate: Force regeneration even if cached
        
    Returns:
        Dict with results summary
    """
    import asyncio
    
    # Run async code in event loop
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        _bulk_generate_async(self, start_date, end_date, leagues, force_regenerate)
    )
    return result


async def _bulk_generate_async(
    task,
    start_date: str,
    end_date: str,
    leagues: list[str],
    force_regenerate: bool,
) -> dict[str, Any]:
    """Async implementation of bulk generation."""
    
    session = get_async_session()
    
    try:
        # Get OpenAI client
        ai_client = get_openai_client()
        if not ai_client:
            return {
                "success": False,
                "message": "OpenAI API key not configured",
                "total_games": 0,
                "successful": 0,
                "failed": 0,
            }
        
        # Parse dates
        start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
        end_dt = dt.strptime(end_date, "%Y-%m-%d").date()
        
        # Find games
        result = await session.execute(
            select(db_models.SportsGame)
            .join(db_models.SportsLeague)
            .options(
                selectinload(db_models.SportsGame.league),
                selectinload(db_models.SportsGame.plays).selectinload(db_models.SportsGamePlay.team),
            )
            .where(
                db_models.SportsGame.game_date >= start_dt,
                db_models.SportsGame.game_date <= end_dt,
                db_models.SportsLeague.code.in_(leagues),
                db_models.SportsGame.play_count > 0,
            )
            .order_by(db_models.SportsGame.game_date.desc())
        )
        games = result.scalars().all()
        
        total_games = len(games)
        logger.info(f"Found {total_games} games to process")
        
        # Update task state
        task.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": total_games, "status": "Starting..."}
        )
        
        successful = 0
        failed = 0
        cached = 0
        generated = 0
        results = []
        stories_to_save = []
        
        for idx, game in enumerate(games, 1):
            try:
                # Update progress
                task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": idx,
                        "total": total_games,
                        "status": f"Processing game {game.id}...",
                        "successful": successful,
                        "failed": failed,
                        "cached": cached,
                    }
                )
                
                sport = game.league.code
                story_version = "v1"
                
                # Check cache
                cached_story = await session.scalar(
                    select(db_models.SportsGameStory)
                    .where(
                        db_models.SportsGameStory.game_id == game.id,
                        db_models.SportsGameStory.story_version == story_version,
                    )
                )
                
                if cached_story and cached_story.has_summaries and cached_story.has_compact_story and not force_regenerate:
                    logger.info(f"Using cached story for game {game.id}")
                    results.append({
                        "game_id": game.id,
                        "status": "cached",
                        "success": True,
                    })
                    successful += 1
                    cached += 1
                    continue
                
                # Generate new story
                logger.info(f"Generating new story for game {game.id}")
                
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
                
                game_story = build_chapters(timeline=timeline, game_id=game.id, sport=sport)
                
                # Generate summaries
                summary_results = generate_summaries_sequentially(
                    chapters=game_story.chapters,
                    sport=sport,
                    ai_client=ai_client,
                )
                
                # Update chapters with summaries
                for chapter, summary_result in zip(game_story.chapters, summary_results):
                    chapter.summary = summary_result.chapter_summary
                    chapter.title = summary_result.chapter_title
                
                # Generate compact story
                chapter_summaries = [ch.summary for ch in game_story.chapters]
                chapter_titles = [ch.title for ch in game_story.chapters if ch.title]
                
                compact_result = generate_compact_story(
                    chapter_summaries=chapter_summaries,
                    chapter_titles=chapter_titles if len(chapter_titles) == len(chapter_summaries) else None,
                    sport=sport,
                    ai_client=ai_client,
                )
                
                # Save to database
                total_ai_calls = len(summary_results) + 1
                
                story_data = {
                    "game": game,
                    "cached_story": cached_story,
                    "sport": sport,
                    "story_version": story_version,
                    "game_story": game_story,
                    "summary_results": summary_results,
                    "compact_result": compact_result,
                    "total_ai_calls": total_ai_calls,
                }
                stories_to_save.append(story_data)
                
                results.append({
                    "game_id": game.id,
                    "status": "generated",
                    "success": True,
                    "chapter_count": len(game_story.chapters),
                })
                successful += 1
                generated += 1
                
            except Exception as e:
                logger.error(f"Failed to generate story for game {game.id}: {e}")
                results.append({
                    "game_id": game.id,
                    "status": "failed",
                    "success": False,
                    "error": str(e),
                })
                failed += 1
        
        # Save all stories to database
        try:
            for story_data in stories_to_save:
                game = story_data["game"]
                cached_story = story_data["cached_story"]
                game_story = story_data["game_story"]
                summary_results = story_data["summary_results"]
                compact_result = story_data["compact_result"]
                total_ai_calls = story_data["total_ai_calls"]
                
                chapters_json = [
                    {
                        "chapter_id": ch.chapter_id,
                        "play_start_idx": ch.play_start_idx,
                        "play_end_idx": ch.play_end_idx,
                        "period": ch.period,
                        "time_range": {
                            "start": ch.time_range.start if ch.time_range else None,
                            "end": ch.time_range.end if ch.time_range else None,
                        },
                        "reason_codes": ch.reason_codes,
                        "summary": ch.summary,
                        "title": ch.title,
                    }
                    for ch in game_story.chapters
                ]
                
                summaries_json = [r.chapter_summary for r in summary_results]
                titles_json = [r.chapter_title for r in summary_results if r.chapter_title]
                
                if cached_story:
                    cached_story.chapters_json = chapters_json
                    cached_story.chapter_count = len(game_story.chapters)
                    cached_story.summaries_json = summaries_json
                    cached_story.titles_json = titles_json
                    cached_story.compact_story = compact_result.compact_story
                    cached_story.reading_time_minutes = compact_result.reading_time_minutes
                    cached_story.has_summaries = True
                    cached_story.has_titles = len(titles_json) > 0
                    cached_story.has_compact_story = True
                    cached_story.total_ai_calls = total_ai_calls
                    cached_story.generated_at = dt.utcnow()
                else:
                    new_story = db_models.SportsGameStory(
                        game_id=game.id,
                        sport=story_data["sport"],
                        story_version=story_data["story_version"],
                        chapters_json=chapters_json,
                        chapter_count=len(game_story.chapters),
                        summaries_json=summaries_json,
                        titles_json=titles_json,
                        compact_story=compact_result.compact_story,
                        reading_time_minutes=compact_result.reading_time_minutes,
                        has_summaries=True,
                        has_titles=len(titles_json) > 0,
                        has_compact_story=True,
                        generated_at=dt.utcnow(),
                        total_ai_calls=total_ai_calls,
                    )
                    session.add(new_story)
            
            await session.commit()
            logger.info(f"Successfully saved {len(stories_to_save)} stories to database")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to save stories to database: {e}")
            raise
        
        return {
            "success": True,
            "message": f"Generated stories for {successful} of {total_games} games",
            "total_games": total_games,
            "successful": successful,
            "failed": failed,
            "cached": cached,
            "generated": generated,
            "results": results,
        }
        
    finally:
        await session.close()
