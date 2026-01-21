"""
Chapter Summary Generator: AI-powered sequential narration.

This module generates chapter summaries using prior context only.

ISSUE 10: Generate Per-Chapter Summaries Using Prior Context + Current Chapter Only

GUARANTEES:
- Sequential generation (one chapter at a time)
- No future knowledge
- Context discipline enforced
- Callbacks from prior chapters only
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .types import Chapter
from .story_state import StoryState, derive_story_state_from_chapters
from .prompts import (
    build_chapter_summary_prompt,
    ChapterPromptContext,
    format_player_summary,
    format_team_summary,
    format_plays_for_prompt,
    check_for_spoilers,
)

logger = logging.getLogger(__name__)


@dataclass
class ChapterSummaryResult:
    """Result of chapter summary generation.
    
    Attributes:
        chapter_index: Index of chapter summarized
        chapter_summary: Generated summary text
        chapter_title: Optional generated title
        prompt_used: Prompt sent to AI
        raw_response: Raw AI response
        spoiler_warnings: List of detected spoilers
    """
    
    chapter_index: int
    chapter_summary: str
    chapter_title: str | None = None
    prompt_used: str = ""
    raw_response: str = ""
    spoiler_warnings: list[str] | None = None


class SummaryGenerationError(Exception):
    """Raised when summary generation fails."""
    pass


def generate_chapter_summary(
    current_chapter: Chapter,
    prior_chapters: list[Chapter],
    prior_summaries: list[str] | None = None,
    sport: str = "NBA",
    ai_client: Any = None,
    check_spoilers: bool = True,
) -> ChapterSummaryResult:
    """Generate AI summary for a single chapter.
    
    This is the main entry point for chapter-level summary generation.
    
    GUARANTEES:
    - Only uses prior chapters for context
    - No future knowledge
    - Validates context boundaries
    
    Args:
        current_chapter: Chapter to summarize
        prior_chapters: Chapters 0..N-1 (for context)
        prior_summaries: Optional pre-generated summaries for prior chapters
        sport: Sport identifier (NBA v1)
        ai_client: AI client for generation (if None, returns mock)
        check_spoilers: Whether to check for spoiler phrases
        
    Returns:
        ChapterSummaryResult with generated summary
        
    Raises:
        SummaryGenerationError: If generation fails
    """
    chapter_index = len(prior_chapters)
    
    logger.info(
        f"Generating summary for Chapter {chapter_index} "
        f"(plays {current_chapter.play_start_idx}-{current_chapter.play_end_idx})"
    )
    
    # Derive story state from prior chapters
    story_state = derive_story_state_from_chapters(prior_chapters, sport=sport)
    
    # Validate context boundaries
    _validate_context_boundaries(current_chapter, prior_chapters, story_state)
    
    # Build prompt context
    prompt_context = _build_prompt_context(
        current_chapter=current_chapter,
        chapter_index=chapter_index,
        prior_summaries=prior_summaries or [],
        story_state=story_state,
        is_final_chapter=False,  # TODO: detect from metadata
    )
    
    # Build prompt
    prompt = build_chapter_summary_prompt(prompt_context)
    
    # Generate summary
    if ai_client is None:
        # Mock response for testing
        logger.warning("No AI client provided, returning mock summary")
        raw_response = json.dumps({
            "chapter_summary": f"Mock summary for Chapter {chapter_index}",
            "chapter_title": f"Chapter {chapter_index}",
        })
    else:
        try:
            raw_response = ai_client.generate(prompt)
        except Exception as e:
            raise SummaryGenerationError(f"AI generation failed: {e}")
    
    # Parse response
    try:
        response_data = json.loads(raw_response)
        chapter_summary = response_data.get("chapter_summary", "")
        chapter_title = response_data.get("chapter_title")
    except json.JSONDecodeError as e:
        raise SummaryGenerationError(f"Failed to parse AI response: {e}")
    
    if not chapter_summary:
        raise SummaryGenerationError("AI returned empty summary")
    
    # Check for spoilers
    spoiler_warnings = None
    if check_spoilers:
        spoilers = check_for_spoilers(chapter_summary, is_final_chapter=False)
        if spoilers:
            spoiler_warnings = spoilers
            logger.warning(f"Detected spoilers in Chapter {chapter_index}: {spoilers}")
    
    # Validate output shape
    _validate_output_shape(chapter_summary, chapter_title)
    
    logger.info(f"Generated summary for Chapter {chapter_index}: {len(chapter_summary)} chars")
    
    return ChapterSummaryResult(
        chapter_index=chapter_index,
        chapter_summary=chapter_summary,
        chapter_title=chapter_title,
        prompt_used=prompt,
        raw_response=raw_response,
        spoiler_warnings=spoiler_warnings,
    )


def _validate_context_boundaries(
    current_chapter: Chapter,
    prior_chapters: list[Chapter],
    story_state: StoryState,
) -> None:
    """Validate that context boundaries are correct.
    
    Args:
        current_chapter: Current chapter
        prior_chapters: Prior chapters
        story_state: Story state
        
    Raises:
        SummaryGenerationError: If context boundaries violated
    """
    # Ensure current chapter is not in prior chapters
    for prior in prior_chapters:
        if prior.chapter_id == current_chapter.chapter_id:
            raise SummaryGenerationError(
                f"Current chapter {current_chapter.chapter_id} found in prior chapters"
            )
    
    # Ensure story state only includes prior chapters
    expected_last_processed = len(prior_chapters) - 1 if prior_chapters else -1
    if story_state.chapter_index_last_processed != expected_last_processed:
        raise SummaryGenerationError(
            f"Story state includes wrong chapters. "
            f"Expected last_processed={expected_last_processed}, "
            f"got {story_state.chapter_index_last_processed}"
        )
    
    # Ensure no future plays in context
    if prior_chapters:
        last_prior_play = prior_chapters[-1].play_end_idx
        if current_chapter.play_start_idx <= last_prior_play:
            raise SummaryGenerationError(
                f"Current chapter overlaps with prior chapters. "
                f"Current starts at {current_chapter.play_start_idx}, "
                f"last prior ends at {last_prior_play}"
            )


def _build_prompt_context(
    current_chapter: Chapter,
    chapter_index: int,
    prior_summaries: list[str],
    story_state: StoryState,
    is_final_chapter: bool,
) -> ChapterPromptContext:
    """Build prompt context from chapter and state.
    
    Args:
        current_chapter: Current chapter
        chapter_index: Index of current chapter
        prior_summaries: Prior chapter summaries
        story_state: Story state from prior chapters
        is_final_chapter: Whether this is the final chapter
        
    Returns:
        ChapterPromptContext for prompt building
    """
    state_dict = story_state.to_dict()
    
    # Format components
    player_summary = format_player_summary(state_dict.get("players", {}))
    team_summary = format_team_summary(state_dict.get("teams", {}))
    momentum = state_dict.get("momentum_hint", "unknown")
    themes = ", ".join(state_dict.get("theme_tags", [])) or "none"
    
    period = f"Q{current_chapter.period}" if current_chapter.period else "Unknown"
    time_range = (
        f"{current_chapter.time_range.start} - {current_chapter.time_range.end}"
        if current_chapter.time_range
        else "Unknown"
    )
    reason_codes = ", ".join(current_chapter.reason_codes) or "none"
    plays = format_plays_for_prompt(current_chapter.plays)
    
    return ChapterPromptContext(
        chapter_index=chapter_index,
        prior_summaries=prior_summaries,
        player_summary=player_summary,
        team_summary=team_summary,
        momentum=momentum,
        themes=themes,
        period=period,
        time_range=time_range,
        reason_codes=reason_codes,
        plays=plays,
        is_final_chapter=is_final_chapter,
    )


def _validate_output_shape(summary: str, title: str | None) -> None:
    """Validate output shape constraints.
    
    Args:
        summary: Generated summary
        title: Generated title
        
    Raises:
        SummaryGenerationError: If output shape invalid
    """
    # Check summary length (1-3 sentences)
    sentence_count = summary.count('.') + summary.count('!') + summary.count('?')
    if sentence_count > 3:
        logger.warning(f"Summary has {sentence_count} sentences (max 3 recommended)")
    
    # Check title length (if present)
    if title:
        word_count = len(title.split())
        if word_count > 10:
            logger.warning(f"Title has {word_count} words (max 10 recommended)")


def generate_summaries_sequentially(
    chapters: list[Chapter],
    sport: str = "NBA",
    ai_client: Any = None,
) -> list[ChapterSummaryResult]:
    """Generate summaries for all chapters sequentially.
    
    This demonstrates the sequential generation pattern where each chapter
    uses summaries from all prior chapters.
    
    Args:
        chapters: List of chapters to summarize
        sport: Sport identifier
        ai_client: AI client for generation
        
    Returns:
        List of ChapterSummaryResult objects
    """
    results = []
    prior_summaries = []
    
    for i, chapter in enumerate(chapters):
        prior_chapters = chapters[:i]
        
        result = generate_chapter_summary(
            current_chapter=chapter,
            prior_chapters=prior_chapters,
            prior_summaries=prior_summaries,
            sport=sport,
            ai_client=ai_client,
        )
        
        results.append(result)
        prior_summaries.append(result.chapter_summary)
        
        logger.info(f"Completed {i+1}/{len(chapters)} chapters")
    
    return results
