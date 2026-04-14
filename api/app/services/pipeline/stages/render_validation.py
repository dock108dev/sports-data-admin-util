"""Validation and cleanup utilities for RENDER_BLOCKS stage.

Contains constants for forbidden words, prohibited patterns, sentence budget
constraints per block role, and functions for validating narratives.
"""

from __future__ import annotations

import re
from typing import Any

from .block_types import MAX_WORDS_PER_BLOCK, MIN_WORDS_PER_BLOCK

# Forbidden words in block narratives
FORBIDDEN_WORDS = [
    "momentum",
    "turning point",
    "dominant",
    "huge",
    "clutch",
    "epic",
    "crucial",
    "massive",
    "incredible",
]

# Sentence style constraints - prohibited stat-feed patterns
PROHIBITED_PATTERNS = [
    # "X had Y points" stat-feed patterns
    r"\bhad\s+\d+\s+points\b",
    r"\bfinished\s+with\s+\d+\b",
    r"\brecorded\s+\d+\b",
    r"\bnotched\s+\d+\b",
    r"\btallied\s+\d+\b",
    r"\bposted\s+\d+\b",
    r"\bracked\s+up\s+\d+\b",
    # Subjective adjectives to avoid
    r"\bincredible\b",
    r"\bamazing\b",
    r"\bunbelievable\b",
    r"\binsane\b",
    r"\belectric\b",
    r"\bexplosive\b",
    r"\bbrilliant\b",
    r"\bstunning\b",
    r"\bspectacular\b",
    r"\bsensational\b",
    # Retrospective foreshadowing / spoiler patterns
    r"\bwould\s+be\s+a\b",
    r"\bwould\s+prove\b",
    r"\bwould\s+become\b",
    r"\bwould\s+later\b",
    r"\bwould\s+eventually\b",
    r"\bwould\s+go\s+on\b",
    r"\bwould\s+not\s+recover\b",
    r"\bforeshadow\b",
]

# Patterns to clean up raw PBP artifacts from narratives
# Use \S+ for name matching to support international names (e.g., Dončić, Schröder)
# Order matters: more specific patterns (like "tip to") must come before general patterns
PBP_ARTIFACT_PATTERNS = [
    # Jump ball tip patterns like "tip to j. smith" - must come before general initial removal
    (r"tip to [a-zA-Z]\.\s*\S+", "won the tip"),
    # "j. smith" style initials - match single letter followed by period and name
    (r"\b[a-zA-Z]\.\s+\S+(?=\s|[.,!?]|$)", ""),
    # Score artifacts like ": 45-42"
    (r"\s*:\s*\d+-\d+", ""),
    # Raw PBP colons followed by lowercase play text
    (r":\s+[a-zA-Z]", lambda m: ". " + m.group(0)[-1].upper()),
]

# Maximum regeneration attempts for play coverage recovery
MAX_REGENERATION_ATTEMPTS = 2

# Sentence budget constraints per semantic role
# (min_sentences, max_sentences)
SENTENCE_BUDGETS: dict[str, tuple[int, int]] = {
    "SETUP": (1, 4),
    "MOMENTUM_SHIFT": (2, 5),
    "RESPONSE": (1, 4),
    "DECISION_POINT": (2, 5),
    "RESOLUTION": (1, 4),
}

# Default for roles not in the budget map
DEFAULT_SENTENCE_BUDGET: tuple[int, int] = (1, 5)


def validate_style_constraints(
    narrative: str,
    block_idx: int,
) -> tuple[list[str], list[str]]:
    """Validate narrative against style constraints.

    Sentence style constraints.
    - No stat-feed prose patterns
    - No subjective adjectives
    - Broadcast tone

    Args:
        narrative: The generated narrative text
        block_idx: Block index for error messages

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not narrative:
        return errors, warnings

    narrative_lower = narrative.lower()

    # Check for prohibited patterns
    for pattern in PROHIBITED_PATTERNS:
        if re.search(pattern, narrative_lower, re.IGNORECASE):
            warnings.append(
                f"Block {block_idx}: Style violation - matches prohibited pattern '{pattern}'"
            )

    # Check for overly long sentences (stat-feed indicator)
    sentences = re.split(r'[.!?]+', narrative)
    for sentence in sentences:
        words = sentence.split()
        if len(words) > 40:
            warnings.append(
                f"Block {block_idx}: Sentence too long ({len(words)} words) - may be stat-feed style"
            )

    # Check for too many numbers (stat-feed indicator)
    numbers_in_narrative = re.findall(r'\b\d+\b', narrative)
    if len(numbers_in_narrative) > 6:
        warnings.append(
            f"Block {block_idx}: Too many numbers ({len(numbers_in_narrative)}) - may be stat-feed style"
        )

    return errors, warnings


def cleanup_pbp_artifacts(narrative: str) -> str:
    """Remove raw PBP artifacts from narrative text.

    Cleans up patterns like:
    - "j. smith" initials → removed (should use full names)
    - "tip to j. smith" → "won the tip"
    - ": 45-42" score artifacts → removed

    Args:
        narrative: The generated narrative text

    Returns:
        Cleaned narrative without raw PBP artifacts
    """
    if not narrative:
        return narrative

    cleaned = narrative
    for pattern, replacement in PBP_ARTIFACT_PATTERNS:
        if callable(replacement):
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        else:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def validate_block_narrative(
    narrative: str,
    block_idx: int,
    role: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate a single block narrative.

    Args:
        narrative: The generated narrative text
        block_idx: Block index for error messages
        role: Semantic role (SETUP, MOMENTUM_SHIFT, etc.) for sentence budget check

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not narrative or not narrative.strip():
        errors.append(f"Block {block_idx}: Empty narrative")
        return errors, warnings

    word_count = len(narrative.split())

    if word_count < MIN_WORDS_PER_BLOCK:
        warnings.append(
            f"Block {block_idx}: Narrative too short ({word_count} words, min: {MIN_WORDS_PER_BLOCK})"
        )

    if word_count > MAX_WORDS_PER_BLOCK:
        warnings.append(
            f"Block {block_idx}: Narrative too long ({word_count} words, max: {MAX_WORDS_PER_BLOCK})"
        )

    # Check forbidden words
    narrative_lower = narrative.lower()
    for word in FORBIDDEN_WORDS:
        if word.lower() in narrative_lower:
            warnings.append(f"Block {block_idx}: Contains forbidden word '{word}'")

    # Check style constraints
    style_errors, style_warnings = validate_style_constraints(narrative, block_idx)
    errors.extend(style_errors)
    warnings.extend(style_warnings)

    # Check sentence budget if role is provided
    if role:
        budget_warnings = validate_sentence_budget(narrative, block_idx, role)
        warnings.extend(budget_warnings)

    return errors, warnings


def _count_sentences(text: str) -> int:
    """Count sentences in narrative text.

    Splits on sentence-ending punctuation (.!?) followed by whitespace
    or end-of-string. Handles abbreviations and decimals reasonably.
    """
    if not text or not text.strip():
        return 0
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]
    return len(sentences)


def validate_sentence_budget(
    narrative: str,
    block_idx: int,
    role: str,
) -> list[str]:
    """Validate that a narrative respects its role's sentence budget.

    Args:
        narrative: The generated narrative text
        block_idx: Block index for error messages
        role: Semantic role (SETUP, MOMENTUM_SHIFT, etc.)

    Returns:
        List of warning messages for budget violations
    """
    warnings: list[str] = []

    if not narrative or not narrative.strip():
        return warnings

    sentence_count = _count_sentences(narrative)
    min_s, max_s = SENTENCE_BUDGETS.get(role, DEFAULT_SENTENCE_BUDGET)

    if sentence_count < min_s:
        warnings.append(
            f"Block {block_idx} ({role}): Too few sentences "
            f"({sentence_count}, min: {min_s})"
        )

    if sentence_count > max_s:
        warnings.append(
            f"Block {block_idx} ({role}): Too many sentences "
            f"({sentence_count}, max: {max_s})"
        )

    return warnings


def validate_all_blocks(
    blocks: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Validate all block narratives including sentence budgets.

    Args:
        blocks: List of block dicts with narrative and role fields

    Returns:
        Tuple of (all_errors, all_warnings) across all blocks
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for block in blocks:
        block_idx = block.get("block_index", 0)
        narrative = block.get("narrative", "")
        role = block.get("role")

        errors, warnings = validate_block_narrative(narrative, block_idx, role)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    return all_errors, all_warnings
