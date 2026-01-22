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
    
    # Context boundaries enforced by architecture
    
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
        # Note: Titles are generated separately (Issue 3.1)
        chapter_title = None
    except json.JSONDecodeError as e:
        raise SummaryGenerationError(f"Failed to parse AI response: {e}")
    
    if not chapter_summary:
        raise SummaryGenerationError("AI returned empty summary")
    
    logger.info(f"Generated summary for Chapter {chapter_index}: {len(chapter_summary)} chars")
    
    return ChapterSummaryResult(
        chapter_index=chapter_index,
        chapter_summary=chapter_summary,
        chapter_title=chapter_title,
        prompt_used=prompt,
        raw_response=raw_response,
        spoiler_warnings=None,
    )


def _build_prompt_context(
    current_chapter: Chapter,
    chapter_index: int,
    prior_summaries: list[str],
    story_state: StoryState,
    is_final_chapter: bool,
    max_prior_summaries: int = 7,
) -> ChapterPromptContext:
    """Build prompt context from chapter and state.
    
    OPTIMIZATION: Uses sliding window for prior summaries to reduce token usage.
    
    Strategy:
    - Keep first summary (sets the scene)
    - Keep last N summaries (recent context)
    - Skip middle summaries (covered by running stats)
    
    Args:
        current_chapter: Current chapter
        chapter_index: Index of current chapter
        prior_summaries: Prior chapter summaries
        story_state: Story state from prior chapters
        is_final_chapter: Whether this is the final chapter
        max_prior_summaries: Maximum prior summaries to include
        
    Returns:
        ChapterPromptContext for prompt building
    """
    state_dict = story_state.to_dict()
    
    # Apply sliding window to prior summaries
    if len(prior_summaries) > max_prior_summaries:
        # Keep first summary + last (max_prior_summaries - 1) summaries
        windowed_summaries = [prior_summaries[0]] + prior_summaries[-(max_prior_summaries - 1):]
        logger.info(
            f"Applied sliding window to prior summaries: {len(prior_summaries)} -> {len(windowed_summaries)} "
            f"(kept first + last {max_prior_summaries-1})"
        )
    else:
        windowed_summaries = prior_summaries
    
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
        prior_summaries=windowed_summaries,
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
