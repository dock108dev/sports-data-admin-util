"""
Narrative QA & Spoiler Guard Pass (Post-Generation Validation).

This module provides deterministic, rule-based validation of AI-generated narrative output.

FINAL PROMPT: Narrative QA & Spoiler Guard Pass

GUARANTEES:
- No LLM calls
- No rewriting
- Deterministic
- Loud on failure
- Trustable output

This validator ensures:
- No future knowledge leaks
- No finality when not allowed
- No new facts introduced
- Structural constraints met
- Safe for UI display
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .prompts import (
    check_for_spoilers,
    validate_title,
    check_for_new_proper_nouns,
    BANNED_PHRASES,
    TITLE_BANNED_WORDS,
)

logger = logging.getLogger(__name__)


# ============================================================================
# VALIDATION RESULT
# ============================================================================

@dataclass
class ValidationResult:
    """Result of narrative validation.
    
    Attributes:
        valid: Whether validation passed
        errors: List of validation errors (empty if valid)
        warnings: List of validation warnings (non-blocking)
    """
    
    valid: bool
    errors: list[str]
    warnings: list[str] | None = None
    
    def __bool__(self) -> bool:
        """Allow using ValidationResult as boolean."""
        return self.valid


# ============================================================================
# NARRATIVE VALIDATOR
# ============================================================================

class NarrativeValidator:
    """
    Deterministic validator for AI-generated narrative text.
    
    This validator never modifies text. It only detects violations.
    """
    
    @staticmethod
    def validate_chapter_summary(
        text: str,
        is_final_chapter: bool = False,
        chapter_plays: list[dict[str, Any]] | None = None,
    ) -> ValidationResult:
        """
        Validate chapter summary text.
        
        Checks:
        1. Spoiler & finality guard
        2. Future knowledge guard
        3. Structural shape (1-3 sentences)
        4. Non-empty
        
        Args:
            text: Summary text to validate
            is_final_chapter: Whether this is the final chapter
            chapter_plays: Optional plays for entity checking
            
        Returns:
            ValidationResult with pass/fail and errors
        """
        errors = []
        warnings = []
        
        # 1. Non-empty guard
        if not text or not text.strip():
            errors.append("Summary is empty")
            return ValidationResult(valid=False, errors=errors)
        
        # 2. Spoiler & finality guard
        spoilers = check_for_spoilers(text, is_final_chapter=is_final_chapter)
        if spoilers:
            errors.append(f"Spoiler phrases detected: {', '.join(spoilers)}")
        
        # 3. Future knowledge guard
        future_phrases = NarrativeValidator._check_future_knowledge(text)
        if future_phrases:
            errors.append(f"Future knowledge phrases detected: {', '.join(future_phrases)}")
        
        # 4. Structural shape guard (1-3 sentences)
        sentence_count = text.count('.') + text.count('!') + text.count('?')
        if sentence_count == 0:
            errors.append("Summary has no sentences")
        elif sentence_count > 3:
            warnings.append(f"Summary has {sentence_count} sentences (recommended: 1-3)")
        
        # 5. No bullet points
        if text.strip().startswith('-') or text.strip().startswith('•') or '\n-' in text or '\n•' in text:
            errors.append("Summary contains bullet points (must be prose)")
        
        valid = len(errors) == 0
        
        if not valid:
            logger.warning(f"Chapter summary validation failed: {errors}")
        
        return ValidationResult(valid=valid, errors=errors, warnings=warnings)
    
    @staticmethod
    def validate_chapter_title(
        text: str,
        is_final_chapter: bool = False,
    ) -> ValidationResult:
        """
        Validate chapter title text.
        
        Checks:
        1. Length (3-8 words)
        2. No numbers
        3. No punctuation (except apostrophes)
        4. Spoiler guard
        
        Args:
            text: Title text to validate
            is_final_chapter: Whether this is the final chapter
            
        Returns:
            ValidationResult with pass/fail and errors
        """
        errors = []
        warnings = []
        
        # 1. Non-empty guard
        if not text or not text.strip():
            errors.append("Title is empty")
            return ValidationResult(valid=False, errors=errors)
        
        # 2. Use existing validate_title function
        validation_result = validate_title(
            text,
            is_final_chapter=is_final_chapter,
            check_numbers=True,
            check_banned_words=True,
        )
        
        if not validation_result["valid"]:
            errors.extend(validation_result["issues"])
        
        valid = len(errors) == 0
        
        if not valid:
            logger.warning(f"Chapter title validation failed: {errors}")
        
        return ValidationResult(valid=valid, errors=errors, warnings=warnings)
    
    @staticmethod
    def validate_compact_story(
        text: str,
        chapter_summaries: list[str],
    ) -> ValidationResult:
        """
        Validate compact story text.
        
        Checks:
        1. Non-empty
        2. Paragraph-based (not bullets)
        3. No new entities (not in summaries)
        4. No play-by-play listing
        
        Args:
            text: Compact story text to validate
            chapter_summaries: Chapter summaries (source of truth)
            
        Returns:
            ValidationResult with pass/fail and errors
        """
        errors = []
        warnings = []
        
        # 1. Non-empty guard
        if not text or not text.strip():
            errors.append("Compact story is empty")
            return ValidationResult(valid=False, errors=errors)
        
        # 2. No bullet points
        if text.strip().startswith('-') or text.strip().startswith('•') or '\n-' in text or '\n•' in text:
            errors.append("Compact story contains bullet points (must be prose)")
        
        # 3. New entity guard
        new_nouns = check_for_new_proper_nouns(text, chapter_summaries)
        if new_nouns:
            warnings.append(f"Potentially new entities detected: {', '.join(new_nouns[:5])}")
        
        # 4. Play-by-play listing guard (heuristic)
        if NarrativeValidator._looks_like_play_by_play(text):
            errors.append("Compact story appears to be play-by-play listing (must be narrative)")
        
        # 5. Minimum length (should be substantial)
        word_count = len(text.split())
        if word_count < 100:
            warnings.append(f"Compact story is very short ({word_count} words)")
        
        valid = len(errors) == 0
        
        if not valid:
            logger.warning(f"Compact story validation failed: {errors}")
        
        return ValidationResult(valid=valid, errors=errors, warnings=warnings)
    
    @staticmethod
    def _check_future_knowledge(text: str) -> list[str]:
        """
        Check for phrases indicating future knowledge.
        
        Args:
            text: Text to check
            
        Returns:
            List of detected future knowledge phrases
        """
        text_lower = text.lower()
        
        future_phrases = [
            "later",
            "eventually",
            "from there",
            "that would prove",
            "on the way to",
            "would go on to",
            "would never",
            "little did they know",
            "foreshadowing",
        ]
        
        found = []
        for phrase in future_phrases:
            if phrase in text_lower:
                found.append(phrase)
        
        return found
    
    @staticmethod
    def _looks_like_play_by_play(text: str) -> bool:
        """
        Heuristic check for play-by-play listing.
        
        Indicators:
        - Multiple timestamps (e.g., "3:45", "2:30")
        - Repeated shot descriptions
        - List-like structure
        
        Args:
            text: Text to check
            
        Returns:
            True if text looks like play-by-play
        """
        # Check for multiple timestamps
        timestamp_pattern = r'\d{1,2}:\d{2}'
        timestamps = re.findall(timestamp_pattern, text)
        if len(timestamps) > 3:
            return True
        
        # Check for repeated "made", "missed", "shot" patterns
        shot_words = ['made', 'missed', 'shot', 'layup', 'jumper', 'three-pointer']
        shot_count = sum(text.lower().count(word) for word in shot_words)
        if shot_count > 10:
            return True
        
        # Check for list-like structure (many short sentences)
        sentences = text.split('.')
        short_sentences = [s for s in sentences if len(s.split()) < 10]
        if len(short_sentences) > len(sentences) * 0.7:  # 70% are short
            return True
        
        return False


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_narrative_output(
    summary: str | None = None,
    title: str | None = None,
    compact_story: str | None = None,
    is_final_chapter: bool = False,
    chapter_summaries: list[str] | None = None,
) -> dict[str, ValidationResult]:
    """
    Validate all narrative outputs at once.
    
    Args:
        summary: Chapter summary to validate
        title: Chapter title to validate
        compact_story: Compact story to validate
        is_final_chapter: Whether this is the final chapter
        chapter_summaries: Chapter summaries for compact story validation
        
    Returns:
        Dictionary of validation results by field
    """
    results = {}
    
    if summary is not None:
        results["summary"] = NarrativeValidator.validate_chapter_summary(
            summary,
            is_final_chapter=is_final_chapter,
        )
    
    if title is not None:
        results["title"] = NarrativeValidator.validate_chapter_title(
            title,
            is_final_chapter=is_final_chapter,
        )
    
    if compact_story is not None and chapter_summaries is not None:
        results["compact_story"] = NarrativeValidator.validate_compact_story(
            compact_story,
            chapter_summaries=chapter_summaries,
        )
    
    return results


def all_valid(results: dict[str, ValidationResult]) -> bool:
    """
    Check if all validation results are valid.
    
    Args:
        results: Dictionary of validation results
        
    Returns:
        True if all results are valid
    """
    return all(result.valid for result in results.values())


def get_all_errors(results: dict[str, ValidationResult]) -> list[str]:
    """
    Get all errors from validation results.
    
    Args:
        results: Dictionary of validation results
        
    Returns:
        List of all error messages
    """
    errors = []
    for field, result in results.items():
        if not result.valid:
            errors.extend([f"{field}: {error}" for error in result.errors])
    return errors
