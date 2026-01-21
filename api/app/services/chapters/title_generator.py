"""
Chapter Title Generator: Lightweight AI-powered title creation.

This module generates chapter titles from summaries.

ISSUE 11: Generate Chapter Titles (NBA v1)

GUARANTEES:
- Titles derive from summaries only
- No new information added
- No spoilers or finality (unless final chapter)
- Safe for UI display
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .types import Chapter
from .prompts import (
    build_chapter_title_prompt,
    TitlePromptContext,
    validate_title,
)

logger = logging.getLogger(__name__)


@dataclass
class ChapterTitleResult:
    """Result of chapter title generation.
    
    Attributes:
        chapter_index: Index of chapter
        chapter_title: Generated title
        prompt_used: Prompt sent to AI
        raw_response: Raw AI response
        validation_result: Title validation result
    """
    
    chapter_index: int
    chapter_title: str
    prompt_used: str = ""
    raw_response: str = ""
    validation_result: dict[str, Any] | None = None


class TitleGenerationError(Exception):
    """Raised when title generation fails."""
    pass


def generate_chapter_title(
    chapter: Chapter,
    chapter_summary: str,
    chapter_index: int,
    ai_client: Any = None,
    is_final_chapter: bool = False,
    validate_output: bool = True,
) -> ChapterTitleResult:
    """Generate AI title for a chapter.
    
    This is the main entry point for chapter title generation.
    
    GUARANTEES:
    - Title derives from summary only
    - No future knowledge
    - Validates output shape and safety
    
    Args:
        chapter: Chapter to title
        chapter_summary: Pre-generated summary for this chapter
        chapter_index: Index of chapter
        ai_client: AI client for generation (if None, returns mock)
        is_final_chapter: Whether this is the final chapter
        validate_output: Whether to validate title
        
    Returns:
        ChapterTitleResult with generated title
        
    Raises:
        TitleGenerationError: If generation fails
    """
    logger.info(f"Generating title for Chapter {chapter_index}")
    
    # Build prompt context
    prompt_context = _build_title_prompt_context(
        chapter=chapter,
        chapter_summary=chapter_summary,
        chapter_index=chapter_index,
        is_final_chapter=is_final_chapter,
    )
    
    # Build prompt
    prompt = build_chapter_title_prompt(prompt_context)
    
    # Generate title
    if ai_client is None:
        # Mock response for testing
        logger.warning("No AI client provided, returning mock title")
        raw_response = json.dumps({
            "chapter_title": f"Chapter {chapter_index} Title",
        })
    else:
        try:
            raw_response = ai_client.generate(prompt)
        except Exception as e:
            raise TitleGenerationError(f"AI generation failed: {e}")
    
    # Parse response
    try:
        response_data = json.loads(raw_response)
        chapter_title = response_data.get("chapter_title", "")
    except json.JSONDecodeError as e:
        raise TitleGenerationError(f"Failed to parse AI response: {e}")
    
    if not chapter_title:
        raise TitleGenerationError("AI returned empty title")
    
    # Validate title
    validation_result = None
    if validate_output:
        validation_result = validate_title(
            chapter_title,
            is_final_chapter=is_final_chapter,
        )
        
        if not validation_result["valid"]:
            logger.warning(
                f"Title validation issues for Chapter {chapter_index}: "
                f"{validation_result['issues']}"
            )
    
    logger.info(f"Generated title for Chapter {chapter_index}: '{chapter_title}'")
    
    return ChapterTitleResult(
        chapter_index=chapter_index,
        chapter_title=chapter_title,
        prompt_used=prompt,
        raw_response=raw_response,
        validation_result=validation_result,
    )


def _build_title_prompt_context(
    chapter: Chapter,
    chapter_summary: str,
    chapter_index: int,
    is_final_chapter: bool,
) -> TitlePromptContext:
    """Build title prompt context.
    
    Args:
        chapter: Chapter object
        chapter_summary: Pre-generated summary
        chapter_index: Index of chapter
        is_final_chapter: Whether this is the final chapter
        
    Returns:
        TitlePromptContext for prompt building
    """
    period = f"Q{chapter.period}" if chapter.period else "Unknown"
    time_range = (
        f"{chapter.time_range.start} - {chapter.time_range.end}"
        if chapter.time_range
        else "Unknown"
    )
    reason_codes = ", ".join(chapter.reason_codes) or "none"
    
    return TitlePromptContext(
        chapter_index=chapter_index,
        chapter_summary=chapter_summary,
        period=period,
        time_range=time_range,
        reason_codes=reason_codes,
        is_final_chapter=is_final_chapter,
    )


def generate_titles_for_chapters(
    chapters: list[Chapter],
    summaries: list[str],
    ai_client: Any = None,
) -> list[ChapterTitleResult]:
    """Generate titles for all chapters.
    
    Args:
        chapters: List of chapters
        summaries: List of pre-generated summaries (must match chapters)
        ai_client: AI client for generation
        
    Returns:
        List of ChapterTitleResult objects
        
    Raises:
        TitleGenerationError: If chapters/summaries mismatch
    """
    if len(chapters) != len(summaries):
        raise TitleGenerationError(
            f"Chapters ({len(chapters)}) and summaries ({len(summaries)}) count mismatch"
        )
    
    results = []
    
    for i, (chapter, summary) in enumerate(zip(chapters, summaries)):
        is_final = (i == len(chapters) - 1)
        
        result = generate_chapter_title(
            chapter=chapter,
            chapter_summary=summary,
            chapter_index=i,
            ai_client=ai_client,
            is_final_chapter=is_final,
        )
        
        results.append(result)
        logger.info(f"Completed {i+1}/{len(chapters)} titles")
    
    return results
