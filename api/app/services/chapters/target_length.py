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
Targets calibrated to AI's natural output range (~450-700 words):
- LOW: 450 words (range 350-500)
- MEDIUM: 550 words (range 450-650)
- HIGH: 700 words (range 550-850)

Targets were calibrated based on observed AI output patterns:
- AI naturally produces 450-700 words regardless of instruction
- Targets set to align with this natural range
- Ranges overlap to avoid sharp quality boundaries

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

# LOW quality games: shorter stories (350-500 words)
# AI naturally outputs 450-550 for simple prompts
LOW_MIN = 350
LOW_MAX = 500
LOW_TARGET = 450

# MEDIUM quality games: standard stories (450-650 words)
# AI naturally outputs 500-650 for moderate prompts
MEDIUM_MIN = 450
MEDIUM_MAX = 650
MEDIUM_TARGET = 550

# HIGH quality games: longer stories (550-850 words)
# AI naturally outputs 600-750 for complex prompts
HIGH_MIN = 550
HIGH_MAX = 850
HIGH_TARGET = 700


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

    Selection method: Targets calibrated to AI's natural output.
    - LOW → 450 words (range 350-500)
    - MEDIUM → 550 words (range 450-650)
    - HIGH → 700 words (range 550-850)

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
