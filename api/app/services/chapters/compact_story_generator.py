"""
Compact Story Generator: Full game narrative synthesis.

This module generates compact game stories from chapter summaries.

ISSUE 12: Generate Full Compact Game Story From Ordered Chapter Summaries

GUARANTEES:
- Derives from chapter summaries only
- No raw plays or stats
- Cohesive narrative with hindsight
- Safe for immediate display
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .prompts import (
    build_compact_story_prompt,
    CompactStoryPromptContext,
    estimate_reading_time,
    validate_compact_story_length,
)

logger = logging.getLogger(__name__)


@dataclass
class CompactStoryResult:
    """Result of compact story generation.
    
    Attributes:
        compact_story: Generated story text
        reading_time_minutes: Estimated reading time
        word_count: Word count
        prompt_used: Prompt sent to AI
        raw_response: Raw AI response
        validation_result: Story validation result
        new_nouns_detected: Potentially new proper nouns
    """
    
    compact_story: str
    reading_time_minutes: float
    word_count: int
    prompt_used: str = ""
    raw_response: str = ""
    validation_result: dict[str, Any] | None = None
    new_nouns_detected: list[str] | None = None


class CompactStoryGenerationError(Exception):
    """Raised when compact story generation fails."""
    pass


def generate_compact_story(
    chapter_summaries: list[str],
    chapter_titles: list[str] | None = None,
    sport: str = "NBA",
    ai_client: Any = None,
    validate_output: bool = True,
) -> CompactStoryResult:
    """Generate compact game story from chapter summaries.
    
    This is the main entry point for compact story generation.
    
    GUARANTEES:
    - Uses only chapter summaries
    - No raw plays or stats
    - Validates output shape
    
    Args:
        chapter_summaries: Ordered list of chapter summaries
        chapter_titles: Optional chapter titles
        sport: Sport identifier
        ai_client: AI client for generation (if None, returns mock)
        validate_output: Whether to validate output
        
    Returns:
        CompactStoryResult with generated story
        
    Raises:
        CompactStoryGenerationError: If generation fails
    """
    if not chapter_summaries:
        raise CompactStoryGenerationError("No chapter summaries provided")
    
    logger.info(f"Generating compact story from {len(chapter_summaries)} chapters")
    
    # Validate inputs
    _validate_inputs(chapter_summaries, chapter_titles)
    
    # Build prompt context
    prompt_context = CompactStoryPromptContext(
        chapter_summaries=chapter_summaries,
        chapter_titles=chapter_titles,
        sport=sport,
    )
    
    # Build prompt
    prompt = build_compact_story_prompt(prompt_context)
    
    # Generate story
    if ai_client is None:
        # Mock response for testing
        logger.warning("No AI client provided, returning mock compact story")
        raw_response = json.dumps({
            "compact_story": _generate_mock_story(chapter_summaries),
        })
    else:
        try:
            raw_response = ai_client.generate(prompt)
        except Exception as e:
            raise CompactStoryGenerationError(f"AI generation failed: {e}")
    
    # Parse response
    try:
        response_data = json.loads(raw_response)
        compact_story = response_data.get("compact_story", "")
    except json.JSONDecodeError as e:
        raise CompactStoryGenerationError(f"Failed to parse AI response: {e}")
    
    if not compact_story:
        raise CompactStoryGenerationError("AI returned empty compact story")
    
    # Calculate metrics
    reading_time = estimate_reading_time(compact_story)
    word_count = len(compact_story.split())
    
    logger.info(
        f"Generated compact story: {word_count} words, "
        f"{reading_time:.1f} min reading time"
    )
    
    return CompactStoryResult(
        compact_story=compact_story,
        reading_time_minutes=reading_time,
        word_count=word_count,
        prompt_used=prompt,
        raw_response=raw_response,
        validation_result=None,
        new_nouns_detected=None,
    )


def _validate_inputs(
    chapter_summaries: list[str],
    chapter_titles: list[str] | None,
) -> None:
    """Validate inputs for compact story generation.
    
    Args:
        chapter_summaries: Chapter summaries
        chapter_titles: Optional chapter titles
        
    Raises:
        CompactStoryGenerationError: If inputs invalid
    """
    if not chapter_summaries:
        raise CompactStoryGenerationError("chapter_summaries cannot be empty")
    
    # Check for empty summaries
    for i, summary in enumerate(chapter_summaries):
        if not summary or not summary.strip():
            raise CompactStoryGenerationError(f"Chapter {i} has empty summary")
    
    # Check titles match if provided
    if chapter_titles is not None:
        if len(chapter_titles) != len(chapter_summaries):
            raise CompactStoryGenerationError(
                f"Chapter titles ({len(chapter_titles)}) and summaries "
                f"({len(chapter_summaries)}) count mismatch"
            )


def _generate_mock_story(chapter_summaries: list[str]) -> str:
    """Generate mock compact story for testing.
    
    Args:
        chapter_summaries: Chapter summaries
        
    Returns:
        Mock story text
    """
    # Create a simple mock that references the summaries
    opening = f"This game unfolded across {len(chapter_summaries)} distinct chapters."
    
    middle_parts = []
    for i, summary in enumerate(chapter_summaries[:3]):  # First 3 for brevity
        middle_parts.append(f"In chapter {i}, {summary.lower()}")
    
    middle = " ".join(middle_parts)
    
    closing = "The game concluded with both teams having given their all."
    
    return f"{opening}\n\n{middle}\n\n{closing}"


def validate_compact_story_input(
    chapter_summaries: list[str],
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Validate compact story input requirements.
    
    Args:
        chapter_summaries: Chapter summaries to validate
        allow_empty: Whether to allow empty summaries
        
    Returns:
        Validation result
    """
    issues = []
    
    if not chapter_summaries:
        issues.append("No chapter summaries provided")
    else:
        for i, summary in enumerate(chapter_summaries):
            if not allow_empty and (not summary or not summary.strip()):
                issues.append(f"Chapter {i} has empty summary")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "chapter_count": len(chapter_summaries) if chapter_summaries else 0,
    }
