"""
Target Word Count Selection: Deterministic word count from game quality.

PURPOSE:
Converts a GameQuality score (LOW/MEDIUM/HIGH) into a numeric target word count.
This value is passed directly to the AI rendering layer as an instruction.

WHY RANGES ARE COARSE:
1. AI generation is approximate - precise targets create false precision
2. Coarse buckets (300-500, 600-800, 900-1200) are easy to reason about
3. Three tiers match the three quality levels (no interpolation needed)
4. Easy to explain: "short story", "standard story", "long story"

WHY DETERMINISM MATTERS:
1. Same game quality → same target every run
2. No surprises to the AI layer
3. Reproducible behavior for debugging
4. No external state or randomness to manage

SELECTION METHOD:
Fixed midpoint of each range:
- LOW: (300 + 500) / 2 = 400 words
- MEDIUM: (600 + 800) / 2 = 700 words
- HIGH: (900 + 1200) / 2 = 1050 words

Midpoint was chosen because:
- Simple and predictable
- Gives headroom in both directions
- Easy to change later if needed

CODEBASE REVIEW:
- No existing target word count selection found
- word_count in compact_story_generator.py is for OUTPUT measurement, not targeting
- This module is the ONLY target selection path

ISSUE: Target Word Count (Chapters-First Architecture)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .game_quality import GameQuality


# ============================================================================
# WORD COUNT RANGES (LOCKED - NO TUNING)
# ============================================================================

# LOW quality games: shorter stories (300-500 words)
LOW_MIN = 300
LOW_MAX = 500
LOW_TARGET = (LOW_MIN + LOW_MAX) // 2  # 400

# MEDIUM quality games: standard stories (600-800 words)
MEDIUM_MIN = 600
MEDIUM_MAX = 800
MEDIUM_TARGET = (MEDIUM_MIN + MEDIUM_MAX) // 2  # 700

# HIGH quality games: longer stories (900-1200 words)
HIGH_MIN = 900
HIGH_MAX = 1200
HIGH_TARGET = (HIGH_MIN + HIGH_MAX) // 2  # 1050


# ============================================================================
# TARGET SELECTION RESULT
# ============================================================================

@dataclass
class TargetLengthResult:
    """Result of target word count selection.

    Contains:
    - The target word count for AI instruction
    - The input quality that determined it
    - The valid range for reference
    """
    target_words: int
    quality: GameQuality
    range_min: int
    range_max: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging and logging."""
        return {
            "target_words": self.target_words,
            "quality": self.quality.value,
            "range_min": self.range_min,
            "range_max": self.range_max,
        }


# ============================================================================
# TARGET SELECTION FUNCTION
# ============================================================================

def select_target_word_count(quality: GameQuality) -> TargetLengthResult:
    """Select deterministic target word count from game quality.

    This is the ONLY target word count selection path.
    The AI rendering layer receives this value as an instruction.

    Selection method: Fixed midpoint of each range.
    - LOW → 400 words (midpoint of 300-500)
    - MEDIUM → 700 words (midpoint of 600-800)
    - HIGH → 1050 words (midpoint of 900-1200)

    Args:
        quality: GameQuality enum (LOW, MEDIUM, or HIGH)

    Returns:
        TargetLengthResult with target_words and range metadata
    """
    if quality == GameQuality.LOW:
        return TargetLengthResult(
            target_words=LOW_TARGET,
            quality=quality,
            range_min=LOW_MIN,
            range_max=LOW_MAX,
        )
    elif quality == GameQuality.MEDIUM:
        return TargetLengthResult(
            target_words=MEDIUM_TARGET,
            quality=quality,
            range_min=MEDIUM_MIN,
            range_max=MEDIUM_MAX,
        )
    elif quality == GameQuality.HIGH:
        return TargetLengthResult(
            target_words=HIGH_TARGET,
            quality=quality,
            range_min=HIGH_MIN,
            range_max=HIGH_MAX,
        )
    else:
        # Defensive: if somehow invalid, default to MEDIUM
        # This should never happen with proper typing
        return TargetLengthResult(
            target_words=MEDIUM_TARGET,
            quality=GameQuality.MEDIUM,
            range_min=MEDIUM_MIN,
            range_max=MEDIUM_MAX,
        )


def get_target_words(quality: GameQuality) -> int:
    """Convenience function to get just the target word count.

    Args:
        quality: GameQuality enum

    Returns:
        Target word count as integer
    """
    return select_target_word_count(quality).target_words


# ============================================================================
# DEBUG OUTPUT
# ============================================================================

def format_target_debug(result: TargetLengthResult) -> str:
    """Format target selection for debugging.

    Args:
        result: TargetLengthResult to format

    Returns:
        Human-readable debug string
    """
    lines = [
        "Target Word Count Selection:",
        "=" * 40,
        f"  Input Quality:  {result.quality.value}",
        f"  Valid Range:    {result.range_min}-{result.range_max} words",
        f"  Target:         {result.target_words} words",
        "=" * 40,
    ]

    return "\n".join(lines)
