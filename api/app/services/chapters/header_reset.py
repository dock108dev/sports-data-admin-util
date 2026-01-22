"""
Header Reset Generator: Deterministic one-sentence orientation anchors.

PURPOSE:
Header resets are one-sentence orientation anchors that tell the reader
WHERE we are in the game without telling WHAT happened. They are:
- Orientation resets for the reader
- Structural guides for AI rendering later
- NOT storytelling
- NOT narrative

WHY INTENTIONALLY MINIMAL:
1. Headers must not compete with AI-generated narrative
2. Headers must be safe to pass directly to AI rendering
3. Headers must not contradict each other across sections
4. Headers must remain deterministic regardless of run

DESIGN PRINCIPLES:
- Exactly one sentence per section
- Deterministic: Same input → same header every run
- No player names
- No inferred performance
- No narrative language, hype, questions, or exclamation points
- Template-based selection keyed by beat_type

ALLOWED INPUTS:
- section.beat_type
- section index / timing context
- high-level stat signals (low scoring, run present)

NOT ALLOWED:
- player stats or names
- future sections
- prior sections
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .beat_classifier import BeatType
from .story_section import StorySection


# ============================================================================
# TEMPLATE MAPPING (AUTHORITATIVE)
# ============================================================================

# Each beat_type maps to one or more templates.
# Multiple templates enable variation based on context (e.g., section index).
# Selection MUST remain deterministic.

HEADER_TEMPLATES: dict[BeatType, list[str]] = {
    BeatType.FAST_START: [
        "Both teams opened at a fast pace.",
        "The game began with early energy from both sides.",
    ],

    BeatType.MISSED_SHOT_FEST: [
        "Scoring was hard to come by as missed shots piled up.",
        "Neither team found a rhythm as shots failed to fall.",
    ],

    BeatType.BACK_AND_FORTH: [
        "Neither side could separate as play moved back and forth.",
        "The teams traded possessions without building significant separation.",
        "Competitive play continued without a clear advantage for either side.",
    ],

    BeatType.EARLY_CONTROL: [
        "One team began to establish a modest edge.",
        "A gap started to form as one side found its footing.",
    ],

    BeatType.RUN: [
        "A stretch of scoring created separation on the scoreboard.",
        "One team strung together consecutive buckets to pull ahead.",
    ],

    BeatType.RESPONSE: [
        "The opposing side answered to keep the game within reach.",
        "A response brought the trailing team back into contention.",
    ],

    BeatType.STALL: [
        "The game slowed with little sustained scoring.",
        "Action stalled as both teams struggled to generate offense.",
    ],

    BeatType.CRUNCH_SETUP: [
        "The game tightened late as every possession began to matter.",
        "With time winding down, the margin remained close.",
    ],

    BeatType.CLOSING_SEQUENCE: [
        "Late possessions took on added importance down the stretch.",
        "The final minutes arrived with the outcome still uncertain.",
    ],

    BeatType.OVERTIME: [
        "Overtime extended the game into a survival phase.",
        "Extra time was needed to determine the outcome.",
    ],
}


# ============================================================================
# HEADER CONTEXT
# ============================================================================

@dataclass
class HeaderContext:
    """Context for header generation.

    Contains only the minimal information needed for template selection.
    Deliberately excludes player stats and names.
    """

    beat_type: BeatType
    section_index: int
    is_first_section: bool
    is_overtime: bool
    is_closing: bool

    # Optional score context (for OT/closing only)
    score_tied: bool = False
    score_margin: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        return {
            "beat_type": self.beat_type.value,
            "section_index": self.section_index,
            "is_first_section": self.is_first_section,
            "is_overtime": self.is_overtime,
            "is_closing": self.is_closing,
            "score_tied": self.score_tied,
            "score_margin": self.score_margin,
        }


# ============================================================================
# HEADER GENERATION
# ============================================================================

def build_header_context(section: StorySection) -> HeaderContext:
    """Build header context from a StorySection.

    Extracts only the minimal information needed for header generation.
    Deliberately ignores player stats and names.

    Args:
        section: The StorySection to build context for

    Returns:
        HeaderContext with minimal orientation data
    """
    is_overtime = section.beat_type == BeatType.OVERTIME
    is_closing = section.beat_type == BeatType.CLOSING_SEQUENCE

    # Calculate score context (for OT/closing)
    home_score = section.end_score.get("home", 0)
    away_score = section.end_score.get("away", 0)
    score_tied = home_score == away_score
    score_margin = abs(home_score - away_score)

    return HeaderContext(
        beat_type=section.beat_type,
        section_index=section.section_index,
        is_first_section=section.section_index == 0,
        is_overtime=is_overtime,
        is_closing=is_closing,
        score_tied=score_tied,
        score_margin=score_margin,
    )


def _select_template(beat_type: BeatType, section_index: int) -> str:
    """Select a template deterministically based on beat_type and index.

    Uses section_index to vary template selection while remaining deterministic.
    Same beat_type + section_index → same template every time.

    Args:
        beat_type: The beat type for this section
        section_index: The 0-based section index

    Returns:
        A single template string
    """
    templates = HEADER_TEMPLATES.get(beat_type, [])

    if not templates:
        # Fallback for unknown beat types (should never happen)
        return "The game continued."

    # Deterministic selection: use section_index to pick template
    template_index = section_index % len(templates)
    return templates[template_index]


def generate_header(context: HeaderContext) -> str:
    """Generate a deterministic one-sentence header.

    CONSTRAINTS (enforced):
    - Exactly one sentence
    - No player names
    - No inferred performance
    - No narrative language
    - No hype, questions, or exclamation points

    Args:
        context: HeaderContext with minimal orientation data

    Returns:
        A single sentence describing where we are in the game
    """
    # Select base template
    header = _select_template(context.beat_type, context.section_index)

    # For overtime, optionally include score context if tied
    if context.is_overtime and context.score_tied:
        header = "With the score tied, overtime extended the game."

    return header


def generate_header_for_section(section: StorySection) -> str:
    """Generate a header directly from a StorySection.

    Convenience function that builds context and generates header.

    Args:
        section: The StorySection to generate a header for

    Returns:
        A single sentence header
    """
    context = build_header_context(section)
    return generate_header(context)


def generate_all_headers(sections: list[StorySection]) -> list[str]:
    """Generate headers for all sections.

    Args:
        sections: List of StorySections in order

    Returns:
        List of header strings, one per section
    """
    return [generate_header_for_section(section) for section in sections]


# ============================================================================
# VALIDATION
# ============================================================================

def validate_header(header: str) -> list[str]:
    """Validate that a header meets all constraints.

    Checks:
    - Exactly one sentence (one period, ends with period)
    - No exclamation points
    - No question marks
    - Not empty

    Args:
        header: The header string to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    if not header:
        errors.append("Header is empty")
        return errors

    if not header.strip():
        errors.append("Header is only whitespace")
        return errors

    # Check for exclamation points
    if "!" in header:
        errors.append("Header contains exclamation point")

    # Check for question marks
    if "?" in header:
        errors.append("Header contains question mark")

    # Check for exactly one sentence
    # A valid header should end with a period and have exactly one period
    stripped = header.strip()
    if not stripped.endswith("."):
        errors.append("Header does not end with a period")

    # Count periods (allowing for abbreviations like "vs." is tricky,
    # but our templates don't use them)
    period_count = stripped.count(".")
    if period_count != 1:
        errors.append(f"Header has {period_count} periods, expected 1")

    return errors


def validate_all_headers(headers: list[str]) -> dict[int, list[str]]:
    """Validate all headers.

    Args:
        headers: List of header strings

    Returns:
        Dict mapping section index to validation errors (only for sections with errors)
    """
    errors = {}

    for i, header in enumerate(headers):
        header_errors = validate_header(header)
        if header_errors:
            errors[i] = header_errors

    return errors


# ============================================================================
# DEBUG OUTPUT
# ============================================================================

def format_headers_debug(sections: list[StorySection], headers: list[str]) -> str:
    """Format headers with their sections for debugging.

    Args:
        sections: List of StorySections
        headers: List of corresponding headers

    Returns:
        Human-readable debug string
    """
    lines = ["Header Resets:", "=" * 60]

    for section, header in zip(sections, headers):
        lines.append(f"Section {section.section_index} ({section.beat_type.value}):")
        lines.append(f"  {header}")
        lines.append("")

    return "\n".join(lines)
