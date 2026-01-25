"""
Story Renderer: The ONLY place AI generates narrative text.

AI turns a fully-constructed outline into readable prose.
The prompt template lives in story_prompt.py.

ISSUE: AI Story Rendering (Chapters-First Architecture)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from .story_section import StorySection
from .beat_classifier import BeatType
from .story_prompt import SYSTEM_INSTRUCTION, STORY_RENDER_PROMPT


logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

SECTION_MIN_WORDS = 60
SECTION_MAX_WORDS = 120
SECTION_AVG_WORDS = 90


def compute_target_word_count(section_count: int) -> int:
    """Compute target word count from section count."""
    return section_count * SECTION_AVG_WORDS


# ============================================================================
# PROTOCOLS AND DATA CLASSES
# ============================================================================


class AIClient(Protocol):
    """Protocol for AI client implementations."""

    def generate(self, prompt: str) -> str:
        """Generate text from prompt."""
        ...


@dataclass
class ClosingContext:
    """Context for the closing paragraph."""

    final_home_score: int
    final_away_score: int
    home_team_name: str
    away_team_name: str
    decisive_factors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_score": f"{self.home_team_name} {self.final_home_score}, {self.away_team_name} {self.final_away_score}",
            "decisive_factors": self.decisive_factors,
        }


@dataclass
class SectionRenderInput:
    """Input for rendering a single section."""

    header: str
    beat_type: BeatType
    team_stat_deltas: list[dict[str, Any]]
    player_stat_deltas: list[dict[str, Any]]
    notes: list[str]
    start_score: dict[str, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    end_score: dict[str, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    start_period: int | None = None
    end_period: int | None = None
    start_time_remaining: int | None = None
    end_time_remaining: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "header": self.header,
            "beat_type": self.beat_type.value,
            "team_stats": self.team_stat_deltas,
            "player_stats": self.player_stat_deltas,
            "notes": self.notes,
            "start_score": self.start_score,
            "end_score": self.end_score,
        }
        for key in ["start_period", "end_period", "start_time_remaining", "end_time_remaining"]:
            val = getattr(self, key)
            if val is not None:
                result[key] = val
        return result


@dataclass
class StoryRenderInput:
    """Complete input for story rendering."""

    sport: str
    home_team_name: str
    away_team_name: str
    target_word_count: int
    sections: list[SectionRenderInput]
    closing: ClosingContext

    def to_dict(self) -> dict[str, Any]:
        return {
            "sport": self.sport,
            "teams": {"home": self.home_team_name, "away": self.away_team_name},
            "target_word_count": self.target_word_count,
            "sections": [s.to_dict() for s in self.sections],
            "closing": self.closing.to_dict(),
        }


@dataclass
class StoryRenderResult:
    """Result of story rendering."""

    compact_story: str
    word_count: int
    target_word_count: int
    section_count: int
    prompt_used: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "compact_story": self.compact_story,
            "word_count": self.word_count,
            "target_word_count": self.target_word_count,
            "section_count": self.section_count,
        }


class StoryRenderError(Exception):
    """Raised when story rendering fails."""
    pass


# ============================================================================
# PROMPT BUILDING
# ============================================================================


def _format_time_context(period: int | None, time_remaining: int | None) -> str | None:
    """Format time context for reader-facing display."""
    if period is None:
        return None

    if period <= 4:
        period_str = f"Q{period}"
    elif period == 5:
        period_str = "OT"
    else:
        period_str = f"OT{period - 4}"

    if time_remaining is not None:
        minutes = time_remaining // 60
        seconds = time_remaining % 60
        return f"{period_str} {minutes}:{seconds:02d}"
    return period_str


def _format_section_for_prompt(
    section: SectionRenderInput,
    index: int,
    home_team: str,
    away_team: str,
) -> str:
    """Format a single section for the prompt."""
    start_home = section.start_score.get('home', 0)
    start_away = section.start_score.get('away', 0)
    end_home = section.end_score.get('home', 0)
    end_away = section.end_score.get('away', 0)

    current_score_str = f"{away_team} {end_away}, {home_team} {end_home}"
    section_pts_home = end_home - start_home
    section_pts_away = end_away - start_away

    start_time_str = _format_time_context(section.start_period, section.start_time_remaining)
    end_time_str = _format_time_context(section.end_period, section.end_time_remaining)

    lines = [
        f"### Section {index + 1}",
        f"Theme: {section.header}",
        f"Beat: {section.beat_type.value}",
    ]

    if start_time_str and end_time_str:
        lines.append(f"Game time: {start_time_str} → {end_time_str}")
    elif end_time_str:
        lines.append(f"Game time: ends at {end_time_str}")

    lines.extend([
        f"Score at end: {current_score_str}",
        f"Points scored: {away_team} +{section_pts_away}, {home_team} +{section_pts_home}",
    ])

    if section.team_stat_deltas:
        lines.append("Team Stats:")
        for team in section.team_stat_deltas:
            name = team.get("team_name", "Unknown")
            pts = team.get("points_scored", 0)
            fouls = team.get("personal_fouls_committed", 0)
            tech = team.get("technical_fouls_committed", 0)
            to = team.get("timeouts_used", 0)
            line = f"  - {name}: {pts} pts, {fouls} fouls"
            if tech > 0:
                line += f", {tech} tech"
            if to > 0:
                line += f", {to} TO used"
            lines.append(line)

    if section.player_stat_deltas:
        lines.append("Key Players:")
        for player in section.player_stat_deltas:
            name = player.get("player_name", "Unknown")
            team_key = player.get("team_key")
            pts = player.get("points_scored", 0)
            fg = player.get("fg_made", 0)
            three = player.get("three_pt_made", 0)
            ft = player.get("ft_made", 0)
            foul = player.get("personal_foul_count", 0)
            trouble = player.get("foul_trouble_flag", False)

            stat_parts = [f"{pts} pts"]
            if fg > 0:
                stat_parts.append(f"{fg} FG")
            if three > 0:
                stat_parts.append(f"{three} 3PT")
            if ft > 0:
                stat_parts.append(f"{ft} FT")
            if foul > 0:
                stat_parts.append(f"{foul} fouls")
            if trouble:
                stat_parts.append("(foul trouble)")

            if team_key:
                lines.append(f"  - {name} ({team_key.upper()}): {', '.join(stat_parts)}")
            else:
                lines.append(f"  - {name}: {', '.join(stat_parts)}")

    if section.notes:
        lines.append("Notes:")
        for note in section.notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)


def build_render_prompt(input_data: StoryRenderInput) -> str:
    """Build the complete rendering prompt."""
    sections_text = "\n\n".join([
        _format_section_for_prompt(section, i, input_data.home_team_name, input_data.away_team_name)
        for i, section in enumerate(input_data.sections)
    ])

    decisive_factors = (
        "\n".join([f"- {factor}" for factor in input_data.closing.decisive_factors])
        if input_data.closing.decisive_factors
        else "- (none specified)"
    )

    prompt = STORY_RENDER_PROMPT.format(
        sport=input_data.sport,
        home_team=input_data.home_team_name,
        away_team=input_data.away_team_name,
        target_word_count=input_data.target_word_count,
        section_min_words=SECTION_MIN_WORDS,
        section_max_words=SECTION_MAX_WORDS,
        sections_text=sections_text,
        final_score=input_data.closing.to_dict()["final_score"],
        decisive_factors=decisive_factors,
    )

    return f"{SYSTEM_INSTRUCTION}\n\n{prompt}"


# ============================================================================
# INPUT BUILDING
# ============================================================================


def build_section_render_input(section: StorySection, header: str) -> SectionRenderInput:
    """Build rendering input from a StorySection."""
    return SectionRenderInput(
        header=header,
        beat_type=section.beat_type,
        team_stat_deltas=[delta.to_dict() for delta in section.team_stat_deltas.values()],
        player_stat_deltas=[delta.to_dict() for delta in section.player_stat_deltas.values()],
        notes=section.notes,
        start_score=section.start_score,
        end_score=section.end_score,
        start_period=section.start_period,
        end_period=section.end_period,
        start_time_remaining=section.start_time_remaining,
        end_time_remaining=section.end_time_remaining,
    )


def build_story_render_input(
    sections: list[StorySection],
    headers: list[str],
    sport: str,
    home_team_name: str,
    away_team_name: str,
    target_word_count: int,
    decisive_factors: list[str],
) -> StoryRenderInput:
    """Build complete rendering input from sections and headers."""
    if len(sections) != len(headers):
        raise StoryRenderError(f"Section count ({len(sections)}) != header count ({len(headers)})")
    if not sections:
        raise StoryRenderError("No sections provided")

    section_inputs = [
        build_section_render_input(section, header)
        for section, header in zip(sections, headers)
    ]

    final_section = sections[-1]
    closing = ClosingContext(
        final_home_score=final_section.end_score.get("home", 0),
        final_away_score=final_section.end_score.get("away", 0),
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        decisive_factors=decisive_factors,
    )

    return StoryRenderInput(
        sport=sport,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        target_word_count=target_word_count,
        sections=section_inputs,
        closing=closing,
    )


# ============================================================================
# RENDERING
# ============================================================================


def render_story(
    input_data: StoryRenderInput,
    ai_client: AIClient | None = None,
) -> StoryRenderResult:
    """Render story from complete input. This is the ONLY place AI generates narrative text."""
    logger.info(f"Rendering story: {len(input_data.sections)} sections, target {input_data.target_word_count} words")

    prompt = build_render_prompt(input_data)

    if ai_client is None:
        logger.warning("No AI client provided, returning mock story")
        raw_response = json.dumps({"compact_story": _generate_mock_story(input_data)})
    else:
        try:
            raw_response = ai_client.generate(prompt)
        except Exception as e:
            raise StoryRenderError(f"AI generation failed: {e}")

    # Parse response
    try:
        response_text = raw_response.strip()
        if response_text.startswith("```"):
            lines = [line for line in response_text.split("\n") if not line.startswith("```")]
            response_text = "\n".join(lines)
        response_data = json.loads(response_text)
        compact_story = response_data.get("compact_story", "")
    except json.JSONDecodeError as e:
        raise StoryRenderError(f"Failed to parse AI response: {e}")

    if not compact_story:
        raise StoryRenderError("AI returned empty story")

    word_count = len(compact_story.split())
    logger.info(f"Rendered story: {word_count} words (target: {input_data.target_word_count})")

    return StoryRenderResult(
        compact_story=compact_story,
        word_count=word_count,
        target_word_count=input_data.target_word_count,
        section_count=len(input_data.sections),
        prompt_used=prompt,
        raw_response=raw_response,
    )


def _generate_mock_story(input_data: StoryRenderInput) -> str:
    """Generate mock story for testing."""
    paragraphs = []
    for section in input_data.sections:
        para = section.header
        if section.notes:
            para += f" {section.notes[0]}"
        paragraphs.append(para)

    closing = input_data.closing
    paragraphs.append(
        f"Final score: {closing.home_team_name} {closing.final_home_score}, "
        f"{closing.away_team_name} {closing.final_away_score}."
    )
    return "\n\n".join(paragraphs)


# ============================================================================
# VALIDATION
# ============================================================================


def validate_render_input(input_data: StoryRenderInput) -> list[str]:
    """Validate rendering input."""
    errors = []
    if not input_data.sections:
        errors.append("No sections provided")
    if input_data.target_word_count <= 0:
        errors.append("Invalid target word count")
    if not input_data.home_team_name:
        errors.append("Missing home team name")
    if not input_data.away_team_name:
        errors.append("Missing away team name")
    for i, section in enumerate(input_data.sections):
        if not section.header:
            errors.append(f"Section {i} has no header")
        if not section.header.endswith("."):
            errors.append(f"Section {i} header doesn't end with period")
    return errors


def validate_render_result(result: StoryRenderResult, input_data: StoryRenderInput) -> list[str]:
    """Validate rendering result against input."""
    errors = []

    # Check word count deviation
    deviation_pct = abs(result.word_count - result.target_word_count) / result.target_word_count * 100
    if deviation_pct > 50:
        errors.append(
            f"Word count deviation too large: {result.word_count} vs target {result.target_word_count} ({deviation_pct:.0f}%)"
        )

    # Check headers are present
    story_lower = result.compact_story.lower()
    for section in input_data.sections:
        header_words = section.header.lower().split()[:3]
        if not any(word in story_lower for word in header_words if len(word) > 3):
            errors.append(f"Header may be missing: {section.header[:50]}...")

    # Check per-section word counts
    section_word_counts = _parse_section_word_counts(result.compact_story, input_data.sections)
    for i, wc in enumerate(section_word_counts):
        if wc < SECTION_MIN_WORDS:
            errors.append(f"Section {i + 1} too short: {wc} words (minimum: {SECTION_MIN_WORDS})")
        elif wc > SECTION_MAX_WORDS:
            errors.append(f"Section {i + 1} too long: {wc} words (maximum: {SECTION_MAX_WORDS})")

    return errors


def _parse_section_word_counts(story: str, sections: list[SectionRenderInput]) -> list[int]:
    """Parse story to extract word counts per section."""
    if not sections:
        return []

    header_positions: list[tuple[int, int]] = []
    story_lower = story.lower()

    for i, section in enumerate(sections):
        search_phrase = " ".join(section.header.lower().split()[:4])
        pos = story_lower.find(search_phrase)
        if pos >= 0:
            header_positions.append((i, pos))

    if not header_positions:
        paragraphs = [p.strip() for p in story.split("\n\n") if p.strip()]
        return [len(p.split()) for p in paragraphs]

    header_positions.sort(key=lambda x: x[1])

    word_counts = []
    for j, (_, start_pos) in enumerate(header_positions):
        end_pos = header_positions[j + 1][1] if j + 1 < len(header_positions) else len(story)
        section_text = story[start_pos:end_pos].strip()
        word_counts.append(len(section_text.split()))

    return word_counts


# ============================================================================
# DEBUG OUTPUT
# ============================================================================


def format_render_debug(input_data: StoryRenderInput, result: StoryRenderResult | None = None) -> str:
    """Format rendering input/result for debugging."""
    lines = [
        "Story Render Debug:",
        "=" * 60,
        f"Sport: {input_data.sport}",
        f"Teams: {input_data.home_team_name} vs {input_data.away_team_name}",
        f"Target Words: {input_data.target_word_count}",
        f"Sections: {len(input_data.sections)}",
        "",
        "Section Headers:",
    ]

    for i, section in enumerate(input_data.sections):
        lines.append(f"  {i + 1}. [{section.beat_type.value}] {section.header}")

    lines.append("")
    lines.append(f"Closing: {input_data.closing.to_dict()['final_score']}")

    if result:
        lines.extend([
            "",
            "-" * 60,
            "Result:",
            f"  Word Count: {result.word_count}",
            f"  Target: {result.target_word_count}",
            f"  Deviation: {abs(result.word_count - result.target_word_count)} words",
        ])

    lines.append("=" * 60)
    return "\n".join(lines)
