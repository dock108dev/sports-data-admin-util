"""
Story Renderer: The ONLY place AI generates narrative text.

PURPOSE:
This module is the single AI rendering call for the chapters-first game story system.
AI turns a fully-constructed outline into readable prose.

AI'S ROLE (STRICTLY LIMITED):
- Turn outline into prose
- Use provided headers verbatim
- Match target word count approximately
- Add language polish WITHOUT adding logic

AI IS NOT ALLOWED TO:
- Plan or restructure
- Infer importance
- Invent context
- Decide what matters
- Add drama not supported by input

WHAT THE SYSTEM HAS ALREADY DETERMINED:
- Structure (sections)
- Pacing (beat types)
- Stats (deltas)
- Section boundaries
- Headers (deterministic)
- Target length

CODEBASE REVIEW:
- compact_story_generator.py uses chapter summaries (old approach)
- This module uses StorySections with headers (new approach)
- This is the ONLY rendering path for chapters-first architecture

ISSUE: AI Story Rendering (Chapters-First Architecture)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from .story_section import StorySection
from .beat_classifier import BeatType


logger = logging.getLogger(__name__)


# ============================================================================
# SECTION LENGTH CONSTANTS
# ============================================================================

SECTION_MIN_WORDS = 60
SECTION_MAX_WORDS = 120
SECTION_AVG_WORDS = 90  # Used to compute total target: section_count × 90


def compute_target_word_count(section_count: int) -> int:
    """Compute target word count from section count.

    Args:
        section_count: Number of sections in story

    Returns:
        Target word count (section_count × SECTION_AVG_WORDS)
    """
    return section_count * SECTION_AVG_WORDS


# ============================================================================
# AI CLIENT PROTOCOL
# ============================================================================


class AIClient(Protocol):
    """Protocol for AI client implementations."""

    def generate(self, prompt: str) -> str:
        """Generate text from prompt.

        Args:
            prompt: The prompt to send to AI

        Returns:
            Raw AI response string
        """
        ...


# ============================================================================
# RENDERING INPUT (AUTHORITATIVE)
# ============================================================================


@dataclass
class ClosingContext:
    """Context for the closing paragraph.

    Contains ONLY what AI needs for the final paragraph.
    """

    final_home_score: int
    final_away_score: int
    home_team_name: str
    away_team_name: str
    decisive_factors: list[str]  # Deterministic bullets

    def to_dict(self) -> dict[str, Any]:
        """Serialize for prompt building."""
        return {
            "final_score": f"{self.home_team_name} {self.final_home_score}, {self.away_team_name} {self.final_away_score}",
            "decisive_factors": self.decisive_factors,
        }


@dataclass
class SectionRenderInput:
    """Input for rendering a single section.

    Contains ONLY what AI needs to render this section.
    No raw plays, no chapters, no cumulative stats.
    """

    header: str  # Deterministic one-sentence header (use verbatim)
    beat_type: BeatType
    team_stat_deltas: list[dict[str, Any]]
    player_stat_deltas: list[dict[str, Any]]  # Bounded: top 1-3 per team
    notes: list[str]  # Machine-generated bullets
    start_score: dict[str, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    end_score: dict[str, int] = field(default_factory=lambda: {"home": 0, "away": 0})

    def to_dict(self) -> dict[str, Any]:
        """Serialize for prompt building."""
        return {
            "header": self.header,
            "beat_type": self.beat_type.value,
            "team_stats": self.team_stat_deltas,
            "player_stats": self.player_stat_deltas,
            "notes": self.notes,
            "start_score": self.start_score,
            "end_score": self.end_score,
        }


@dataclass
class StoryRenderInput:
    """Complete input for story rendering.

    This is the AUTHORITATIVE payload sent to AI.
    Contains everything AI needs and nothing more.
    """

    sport: str
    home_team_name: str
    away_team_name: str
    target_word_count: int
    sections: list[SectionRenderInput]
    closing: ClosingContext

    def to_dict(self) -> dict[str, Any]:
        """Serialize for prompt building."""
        return {
            "sport": self.sport,
            "teams": {
                "home": self.home_team_name,
                "away": self.away_team_name,
            },
            "target_word_count": self.target_word_count,
            "sections": [s.to_dict() for s in self.sections],
            "closing": self.closing.to_dict(),
        }


# ============================================================================
# RENDERING RESULT
# ============================================================================


@dataclass
class StoryRenderResult:
    """Result of story rendering.

    Contains the rendered story and metadata.
    """

    compact_story: str
    word_count: int
    target_word_count: int
    section_count: int
    prompt_used: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
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
# SYSTEM INSTRUCTION (STRICT)
# ============================================================================

SYSTEM_INSTRUCTION = """You are a neutral sports anchor summarizing a completed game after watching highlight packages.

You are NOT discovering what happened.
You are NOT deciding what mattered.
You are describing an already-defined story.

Follow the outline EXACTLY."""


# ============================================================================
# RENDERING PROMPT (AUTHORITATIVE)
# ============================================================================

STORY_RENDER_PROMPT = """## GAME OUTLINE

Sport: {sport}
Teams: {home_team} vs {away_team}
Target Length: approximately {target_word_count} words

## SECTIONS (IN ORDER)

{sections_text}

## CLOSING CONTEXT

Final Score: {final_score}
Decisive Factors:
{decisive_factors}

## RENDERING RULES (NON-NEGOTIABLE)

1. Write ONE cohesive article
2. Use the provided headers VERBATIM and IN ORDER
3. Write paragraphs UNDER each header
4. Do NOT add or remove headers
5. Do NOT reference sections, chapters, or beats explicitly
6. Do NOT invent players, stats, or moments not in the input
7. Do NOT repeat the same idea across sections
8. Avoid play-by-play phrasing
9. Tone: calm, professional, SportsCenter-style
10. Perspective: neutral, post-game
11. SCORE MENTIONS: Each section paragraph COULD mention the score at that point. Use end_score in the last paragraph only, and it must be used naturally in context.

## LENGTH CONTROL (NON-NEGOTIABLE)

- Total target: approximately {target_word_count} words
- Per-section bounds: {section_min_words}-{section_max_words} words per section
- Each section MUST contain at least {section_min_words} words
- Each section MUST NOT exceed {section_max_words} words
- Count your words carefully for each section

## STAT USAGE RULES (NON-NEGOTIABLE)

- Use ONLY the stats provided in each section
- Do NOT compute percentages or efficiency
- Do NOT introduce cumulative totals mid-story
- Player mentions must be grounded in provided stats
- If a stat or player is not in the input, it does not exist

## SCORE PRESENTATION RULES (NON-NEGOTIABLE)

- You MAY include the running score where it fits naturally in context
- The end_score should appear in the LAST paragraph of each section (e.g., "...leaving the score at 102-98")
- The notes may say "Team A outscored Team B 14-6" - this is the SECTION scoring (Team A scored 14 points, Team B scored 6 points IN THIS SECTION). This is NOT a run. Do NOT call this a run.
- A "run" is specifically 8+ UNANSWERED points (e.g., "a 10-0 run" or "an 8-0 run"). Only use "run" for actual unanswered scoring sequences.

## FACT-ONLY CONSTRAINT (NON-NEGOTIABLE)

You may ONLY restate factual information explicitly present in the input.
You may NOT infer quality, efficiency, trends, or dominance.

PROHIBITED LANGUAGE (never use these or similar terms):
- "efficient", "inefficient"
- "struggled", "struggling"
- "hot start", "cold shooting", "cold streak"
- "dominant", "dominated", "dominance"
- "controlled", "took control"
- "strong performance", "weak performance"
- "impressive", "disappointing"
- "clutch", "choked"
- "momentum", "momentum shift"
- "outplayed", "outmatched"
- "chemistry", "rhythm"

ALLOWED: Direct stat restatement, factual descriptions of what happened.
Example: "scored 12 points on 4-for-6 shooting" (factual)
NOT ALLOWED: "had an efficient night" (inference)

## CLOSING PARAGRAPH (REQUIRED)

The FINAL paragraph MUST:
- State the final score clearly (e.g., "Team A defeated Team B 110-102" or "The final score: Team A 110, Team B 102")
- Briefly summarize decisive factors (as provided)
- Do NOT editorialize or speculate beyond the game
- The final score is NON-NEGOTIABLE - it MUST appear in the last paragraph

## OUTPUT

Return ONLY a JSON object:
{{"compact_story": "Your article here. Use \\n\\n for paragraph breaks."}}

No markdown fences. No explanation. No metadata."""


def _format_section_for_prompt(
    section: SectionRenderInput,
    index: int,
    home_team: str,
    away_team: str,
) -> str:
    """Format a single section for the prompt.

    Args:
        section: The section to format
        index: Section index (0-based)
        home_team: Home team name
        away_team: Away team name

    Returns:
        Formatted section text
    """
    # Format score as "Away X, Home Y" for clarity
    start_home = section.start_score.get('home', 0)
    start_away = section.start_score.get('away', 0)
    end_home = section.end_score.get('home', 0)
    end_away = section.end_score.get('away', 0)

    # Current running total (the main score to include in narrative)
    current_score_str = f"{away_team} {end_away}, {home_team} {end_home}"

    # Section scoring (how many points each team scored IN THIS SECTION - not a run)
    section_pts_home = end_home - start_home
    section_pts_away = end_away - start_away

    lines = [
        f"### Section {index + 1}",
        f"Header: {section.header}",
        f"Beat: {section.beat_type.value}",
        f"Current score at end of section: {current_score_str}",
        f"Section scoring: {away_team} scored {section_pts_away}, {home_team} scored {section_pts_home} (NOT a run, just section totals)",
    ]

    # Team stats
    if section.team_stat_deltas:
        lines.append("Team Stats:")
        for team in section.team_stat_deltas:
            name = team.get("team_name", "Unknown")
            pts = team.get("points_scored", 0)
            fouls = team.get("personal_fouls_committed", 0)
            tech = team.get("technical_fouls_committed", 0)
            to = team.get("timeouts_used", 0)
            lines.append(
                f"  - {name}: {pts} pts, {fouls} fouls"
                + (f", {tech} tech" if tech > 0 else "")
                + (f", {to} TO used" if to > 0 else "")
            )

    # Player stats (bounded)
    if section.player_stat_deltas:
        lines.append("Key Players:")
        for player in section.player_stat_deltas:
            name = player.get("player_name", "Unknown")
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

            lines.append(f"  - {name}: {', '.join(stat_parts)}")

    # Notes
    if section.notes:
        lines.append("Notes:")
        for note in section.notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)


def build_render_prompt(input_data: StoryRenderInput) -> str:
    """Build the complete rendering prompt.

    Args:
        input_data: Complete rendering input

    Returns:
        Formatted prompt string
    """
    # Format all sections
    sections_text = "\n\n".join(
        [
            _format_section_for_prompt(
                section, i, input_data.home_team_name, input_data.away_team_name
            )
            for i, section in enumerate(input_data.sections)
        ]
    )

    # Format decisive factors
    decisive_factors = (
        "\n".join([f"- {factor}" for factor in input_data.closing.decisive_factors])
        if input_data.closing.decisive_factors
        else "- (none specified)"
    )

    # Build final prompt
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
# INPUT BUILDING HELPERS
# ============================================================================


def build_section_render_input(
    section: StorySection,
    header: str,
) -> SectionRenderInput:
    """Build rendering input from a StorySection.

    Args:
        section: The StorySection with stats and notes
        header: The deterministic header for this section

    Returns:
        SectionRenderInput ready for prompt
    """
    # Convert team deltas to dicts
    team_deltas = [delta.to_dict() for delta in section.team_stat_deltas.values()]

    # Convert player deltas to dicts (already bounded to top 1-3)
    player_deltas = [delta.to_dict() for delta in section.player_stat_deltas.values()]

    return SectionRenderInput(
        header=header,
        beat_type=section.beat_type,
        team_stat_deltas=team_deltas,
        player_stat_deltas=player_deltas,
        notes=section.notes,
        start_score=section.start_score,
        end_score=section.end_score,
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
    """Build complete rendering input from sections and headers.

    Args:
        sections: List of StorySections in order
        headers: List of headers (one per section, in order)
        sport: Sport identifier (e.g., "NBA")
        home_team_name: Home team name
        away_team_name: Away team name
        target_word_count: Target word count for story
        decisive_factors: Deterministic bullets for closing

    Returns:
        StoryRenderInput ready for rendering

    Raises:
        StoryRenderError: If sections and headers count mismatch
    """
    if len(sections) != len(headers):
        raise StoryRenderError(
            f"Section count ({len(sections)}) != header count ({len(headers)})"
        )

    if not sections:
        raise StoryRenderError("No sections provided")

    # Build section inputs
    section_inputs = [
        build_section_render_input(section, header)
        for section, header in zip(sections, headers)
    ]

    # Get final score from last section
    final_section = sections[-1]
    final_home = final_section.end_score.get("home", 0)
    final_away = final_section.end_score.get("away", 0)

    # Build closing context
    closing = ClosingContext(
        final_home_score=final_home,
        final_away_score=final_away,
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
# RENDERING FUNCTION
# ============================================================================


def render_story(
    input_data: StoryRenderInput,
    ai_client: AIClient | None = None,
) -> StoryRenderResult:
    """Render story from complete input.

    This is the ONLY place AI generates narrative text.

    Args:
        input_data: Complete rendering input
        ai_client: AI client for generation (if None, returns mock)

    Returns:
        StoryRenderResult with rendered story

    Raises:
        StoryRenderError: If rendering fails
    """
    logger.info(
        f"Rendering story: {len(input_data.sections)} sections, "
        f"target {input_data.target_word_count} words"
    )

    # Build prompt
    prompt = build_render_prompt(input_data)

    # Generate story
    if ai_client is None:
        logger.warning("No AI client provided, returning mock story")
        raw_response = json.dumps(
            {
                "compact_story": _generate_mock_story(input_data),
            }
        )
    else:
        try:
            raw_response = ai_client.generate(prompt)
        except Exception as e:
            raise StoryRenderError(f"AI generation failed: {e}")

    # Parse response
    try:
        # Handle potential markdown fences
        response_text = raw_response.strip()
        if response_text.startswith("```"):
            # Remove markdown fences
            lines = response_text.split("\n")
            lines = [line for line in lines if not line.startswith("```")]
            response_text = "\n".join(lines)

        response_data = json.loads(response_text)
        compact_story = response_data.get("compact_story", "")
    except json.JSONDecodeError as e:
        raise StoryRenderError(f"Failed to parse AI response: {e}")

    if not compact_story:
        raise StoryRenderError("AI returned empty story")

    # Calculate word count
    word_count = len(compact_story.split())

    logger.info(
        f"Rendered story: {word_count} words (target: {input_data.target_word_count})"
    )

    return StoryRenderResult(
        compact_story=compact_story,
        word_count=word_count,
        target_word_count=input_data.target_word_count,
        section_count=len(input_data.sections),
        prompt_used=prompt,
        raw_response=raw_response,
    )


def _generate_mock_story(input_data: StoryRenderInput) -> str:
    """Generate mock story for testing.

    Args:
        input_data: Rendering input

    Returns:
        Mock story text using headers
    """
    paragraphs = []

    for section in input_data.sections:
        # Use header as section start
        para = f"{section.header}"

        # Add minimal content from notes
        if section.notes:
            para += f" {section.notes[0]}"

        paragraphs.append(para)

    # Add closing
    closing = input_data.closing
    final_para = (
        f"Final score: {closing.home_team_name} {closing.final_home_score}, "
        f"{closing.away_team_name} {closing.final_away_score}."
    )
    paragraphs.append(final_para)

    return "\n\n".join(paragraphs)


# ============================================================================
# VALIDATION
# ============================================================================


def validate_render_input(input_data: StoryRenderInput) -> list[str]:
    """Validate rendering input.

    Args:
        input_data: Input to validate

    Returns:
        List of validation errors (empty if valid)
    """
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


def validate_render_result(
    result: StoryRenderResult,
    input_data: StoryRenderInput,
) -> list[str]:
    """Validate rendering result against input.

    Checks for failure conditions:
    - Missing headers
    - Wrong header order
    - Extreme length deviation
    - Per-section word count bounds

    Args:
        result: The rendering result
        input_data: The original input

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check word count deviation
    deviation = abs(result.word_count - result.target_word_count)
    deviation_pct = deviation / result.target_word_count * 100

    if deviation_pct > 50:
        errors.append(
            f"Word count deviation too large: {result.word_count} vs "
            f"target {result.target_word_count} ({deviation_pct:.0f}%)"
        )

    # Check headers are present (simple check)
    story_lower = result.compact_story.lower()
    for section in input_data.sections:
        # Check for key words from header
        header_words = section.header.lower().split()[:3]
        if not any(word in story_lower for word in header_words if len(word) > 3):
            errors.append(f"Header may be missing: {section.header[:50]}...")

    # Check per-section word counts
    section_word_counts = _parse_section_word_counts(
        result.compact_story, input_data.sections
    )
    for i, word_count in enumerate(section_word_counts):
        if word_count < SECTION_MIN_WORDS:
            errors.append(
                f"Section {i + 1} too short: {word_count} words "
                f"(minimum: {SECTION_MIN_WORDS})"
            )
        elif word_count > SECTION_MAX_WORDS:
            errors.append(
                f"Section {i + 1} too long: {word_count} words "
                f"(maximum: {SECTION_MAX_WORDS})"
            )

    return errors


def _parse_section_word_counts(
    story: str,
    sections: list[SectionRenderInput],
) -> list[int]:
    """Parse story to extract word counts per section.

    Uses headers as delimiters to split story into sections.

    Args:
        story: The rendered story text
        sections: List of sections with headers

    Returns:
        List of word counts per section (may be shorter than sections if parsing fails)
    """
    if not sections:
        return []

    # Build a list of (header, start_position) tuples
    header_positions: list[tuple[int, int]] = []  # (section_index, position)

    story_lower = story.lower()
    for i, section in enumerate(sections):
        # Find header in story (case-insensitive, look for key phrase)
        header_lower = section.header.lower()
        # Try to find the first few words as a marker
        header_words = header_lower.split()[:4]
        search_phrase = " ".join(header_words)

        pos = story_lower.find(search_phrase)
        if pos >= 0:
            header_positions.append((i, pos))

    if not header_positions:
        # Fallback: split by double newlines
        paragraphs = [p.strip() for p in story.split("\n\n") if p.strip()]
        return [len(p.split()) for p in paragraphs]

    # Sort by position
    header_positions.sort(key=lambda x: x[1])

    # Extract word counts between positions
    word_counts: list[int] = []
    for j, (section_idx, start_pos) in enumerate(header_positions):
        if j + 1 < len(header_positions):
            end_pos = header_positions[j + 1][1]
        else:
            end_pos = len(story)

        section_text = story[start_pos:end_pos].strip()
        word_count = len(section_text.split())
        word_counts.append(word_count)

    return word_counts


# ============================================================================
# DEBUG OUTPUT
# ============================================================================


def format_render_debug(
    input_data: StoryRenderInput,
    result: StoryRenderResult | None = None,
) -> str:
    """Format rendering input/result for debugging.

    Args:
        input_data: Rendering input
        result: Optional rendering result

    Returns:
        Human-readable debug string
    """
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
        lines.extend(
            [
                "",
                "-" * 60,
                "Result:",
                f"  Word Count: {result.word_count}",
                f"  Target: {result.target_word_count}",
                f"  Deviation: {abs(result.word_count - result.target_word_count)} words",
            ]
        )

    lines.append("=" * 60)

    return "\n".join(lines)
