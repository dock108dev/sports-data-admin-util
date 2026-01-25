"""
Story builder: Maps database models to GameStoryResponse using chapters-first pipeline.

This module contains the authoritative mapping layer between backend database
models and frontend DTOs. It uses the chapters-first pipeline exclusively.
"""

from __future__ import annotations

from typing import Any

from ... import db_models
from ...services.chapters import build_game_story, PipelineResult
from ...services.openai_client import get_openai_client
from .story_schemas import (
    ChapterEntry,
    GameStoryResponse,
    PipelineDebugResponse,
    PipelineStageInfo,
    PlayEntry,
    SectionEntry,
    TimeRange,
)


async def build_game_story_response(
    game: db_models.SportsGame,
    include_debug: bool = False,
    use_ai: bool = True,
) -> GameStoryResponse:
    """
    Build GameStoryResponse from database game object using chapters-first pipeline.

    This is the ONLY story generation path. There are no fallbacks.

    Pipeline:
    chapters → running_stats → beat_classifier → story_sections →
    headers → quality → target_length → render → validate

    Args:
        game: Database game object (with plays eagerly loaded)
        include_debug: Whether to include debug information
        use_ai: Whether to use AI for rendering (False for testing)

    Returns:
        GameStoryResponse with compact_story and sections

    Raises:
        PipelineError: If any pipeline stage fails
        StoryValidationError: If validation fails
    """
    # Get plays
    plays = sorted(game.plays or [], key=lambda p: p.play_index)

    if not plays:
        return GameStoryResponse(
            game_id=game.id,
            sport=game.league.code if game.league else "UNKNOWN",
            story_version="2.0.0",
            chapters=[],
            sections=[],
            chapter_count=0,
            section_count=0,
            total_plays=0,
            generated_at=None,
            metadata={},
            has_compact_story=False,
        )

    # Build timeline for pipeline
    timeline = _build_timeline(plays)

    # Get team names from game
    home_team_name = _get_home_team_name(game)
    away_team_name = _get_away_team_name(game)

    sport = game.league.code if game.league else "NBA"

    # Get AI client if enabled
    ai_client = get_openai_client() if use_ai else None

    # Run the chapters-first pipeline (SINGLE AI CALL)
    result = build_game_story(
        timeline=timeline,
        game_id=game.id,
        sport=sport,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        ai_client=ai_client,
        include_debug=include_debug,
    )

    # Map to frontend DTO
    return _map_pipeline_result_to_response(game, result, plays, include_debug)


def _build_timeline(plays: list[db_models.SportsGamePlay]) -> list[dict[str, Any]]:
    """Build timeline dict from database plays."""
    return [
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
            "player_name": getattr(p, "player_name", None),
        }
        for p in plays
    ]


def _get_home_team_name(game: db_models.SportsGame) -> str:
    """Extract home team name from game."""
    if hasattr(game, "home_team") and game.home_team:
        return game.home_team.name or game.home_team.abbreviation or "Home"
    return "Home"


def _get_away_team_name(game: db_models.SportsGame) -> str:
    """Extract away team name from game."""
    if hasattr(game, "away_team") and game.away_team:
        return game.away_team.name or game.away_team.abbreviation or "Away"
    return "Away"


def _map_pipeline_result_to_response(
    game: db_models.SportsGame,
    result: PipelineResult,
    plays: list[db_models.SportsGamePlay],
    include_debug: bool,
) -> GameStoryResponse:
    """Map PipelineResult to GameStoryResponse."""
    sport = game.league.code if game.league else "NBA"

    # Map chapters
    chapters = []
    for idx, chapter in enumerate(result.chapters):
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

        time_range = None
        if chapter.time_range:
            time_range = TimeRange(
                start=chapter.time_range.start,
                end=chapter.time_range.end,
            )

        chapter_entry = ChapterEntry(
            chapter_id=chapter.chapter_id,
            index=idx,
            play_start_idx=chapter.play_start_idx,
            play_end_idx=chapter.play_end_idx,
            play_count=len(chapter.plays),
            reason_codes=chapter.reason_codes,
            period=chapter.period,
            time_range=time_range,
            plays=chapter_plays,
        )

        chapters.append(chapter_entry)

    # Map sections
    sections = []
    for idx, (section, header) in enumerate(zip(result.sections, result.headers)):
        section_entry = SectionEntry(
            section_index=section.section_index,
            beat_type=section.beat_type.value,
            header=header,
            chapters_included=section.chapters_included,
            start_score=section.start_score,
            end_score=section.end_score,
            notes=section.notes,
        )
        sections.append(section_entry)

    return GameStoryResponse(
        game_id=game.id,
        sport=sport,
        story_version="2.0.0",
        chapters=chapters,
        sections=sections,
        chapter_count=len(chapters),
        section_count=len(sections),
        total_plays=len(plays),
        compact_story=result.compact_story,
        word_count=result.word_count,
        target_word_count=result.target_word_count,
        quality=result.quality.quality.value,
        reading_time_estimate_minutes=result.reading_time_minutes,
        generated_at=result.generated_at,
        metadata={
            "quality_score": result.quality.numeric_score,
            "quality_signals": result.quality.signals.to_dict()
            if hasattr(result.quality.signals, "to_dict")
            else {},
        },
        has_compact_story=bool(result.compact_story),
    )


async def build_pipeline_debug_response(
    game: db_models.SportsGame,
    use_ai: bool = True,
) -> PipelineDebugResponse:
    """
    Build a debug view showing the full story generation pipeline.

    Shows data transformation from raw PBP → chapters → sections → prompt → story.

    Args:
        game: Database game object (with plays eagerly loaded)
        use_ai: Whether to use AI for rendering

    Returns:
        PipelineDebugResponse with all transformation stages
    """
    plays = sorted(game.plays or [], key=lambda p: p.play_index)
    sport = game.league.code if game.league else "NBA"

    if not plays:
        return PipelineDebugResponse(
            game_id=game.id,
            sport=sport,
            total_plays=0,
            pipeline_stages=[
                PipelineStageInfo(
                    stage_name="No Data",
                    description="No play-by-play data available",
                )
            ],
        )

    # Build timeline for pipeline
    timeline = _build_timeline(plays)

    # Get team names
    home_team_name = _get_home_team_name(game)
    away_team_name = _get_away_team_name(game)

    # Get AI client if enabled
    ai_client = get_openai_client() if use_ai else None

    # Run pipeline WITH debug enabled to capture prompt
    result = build_game_story(
        timeline=timeline,
        game_id=game.id,
        sport=sport,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        ai_client=ai_client,
        include_debug=True,  # Always include debug for this endpoint
    )

    # Build pipeline stages overview
    pipeline_stages = [
        PipelineStageInfo(
            stage_name="1. Raw PBP",
            description="Play-by-play events from game data",
            input_count=len(plays),
            output_count=len(plays),
        ),
        PipelineStageInfo(
            stage_name="2. Chapters",
            description="Deterministic chapter boundaries (timeouts, period breaks)",
            input_count=len(plays),
            output_count=len(result.chapters),
        ),
        PipelineStageInfo(
            stage_name="3. Sections",
            description="Collapsed chapters with beat types and headers",
            input_count=len(result.chapters),
            output_count=len(result.sections),
        ),
        PipelineStageInfo(
            stage_name="4. OpenAI Prompt",
            description="Structured data sent to AI for rendering",
            input_count=len(result.sections),
            output_count=1,
        ),
        PipelineStageInfo(
            stage_name="5. Story Output",
            description="Final rendered story from AI",
            input_count=1,
            output_count=1 if result.compact_story else 0,
        ),
    ]

    # Build raw PBP sample (first 15 plays)
    raw_pbp_sample = timeline[:15]

    # Build chapters summary
    chapters_summary = []
    for idx, chapter in enumerate(result.chapters):
        chapters_summary.append({
            "index": idx,
            "chapter_id": chapter.chapter_id,
            "period": chapter.period,
            "play_range": f"{chapter.play_start_idx}-{chapter.play_end_idx}",
            "play_count": len(chapter.plays),
            "reason_codes": chapter.reason_codes,
            "time_range": (
                f"{chapter.time_range.start} - {chapter.time_range.end}"
                if chapter.time_range
                else None
            ),
            "sample_plays": [
                {
                    "description": p.raw_data.get("description", "")[:80],
                    "score": f"{p.raw_data.get('home_score', 0)}-{p.raw_data.get('away_score', 0)}",
                }
                for p in chapter.plays[:3]  # First 3 plays per chapter
            ],
        })

    # Build sections summary
    sections_summary = []
    for idx, (section, header) in enumerate(zip(result.sections, result.headers)):
        sections_summary.append({
            "index": idx,
            "beat_type": section.beat_type.value,
            "header": header,
            "chapters_included": section.chapters_included,
            "start_score": section.start_score,
            "end_score": section.end_score,
            "notes": section.notes[:3] if section.notes else [],  # First 3 notes
        })

    # Build render input summary (what's sent to AI)
    render_input_summary = None
    if result.render_input:
        render_input_summary = {
            "sport": result.render_input.sport,
            "home_team": result.render_input.home_team_name,
            "away_team": result.render_input.away_team_name,
            "target_word_count": result.render_input.target_word_count,
            "section_count": len(result.render_input.sections),
            "sections_preview": [
                {
                    "header": s.header,
                    "beat_type": s.beat_type.value,
                    "team_stats_count": len(s.team_stat_deltas),
                    "player_stats_count": len(s.player_stat_deltas),
                    "notes_count": len(s.notes),
                }
                for s in result.render_input.sections
            ],
            "closing": result.render_input.closing.to_dict(),
        }

    return PipelineDebugResponse(
        game_id=game.id,
        sport=sport,
        raw_pbp_sample=raw_pbp_sample,
        total_plays=len(plays),
        chapters_summary=chapters_summary,
        chapter_count=len(result.chapters),
        sections_summary=sections_summary,
        section_count=len(result.sections),
        render_input_summary=render_input_summary,
        openai_prompt=result.prompt_used,
        ai_raw_response=result.raw_ai_response,
        compact_story=result.compact_story,
        word_count=result.word_count,
        target_word_count=result.target_word_count,
        pipeline_stages=pipeline_stages,
    )
