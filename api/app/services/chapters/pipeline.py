"""
LEGACY FLOW-BASED RECAP SYSTEM (V1)

Chapters-First GameStory Pipeline: The ONLY supported pipeline.

This module is the single orchestrator for game story generation.
It wires all chapters-first components in the correct order:

    chapters
        → running_stats.build_running_snapshots()
        → beat_classifier.classify_all_chapters()
        → story_section.build_story_sections()
        → header_reset.generate_all_headers()
        → game_quality.compute_quality_score()
        → target_length.select_target_word_count()
        → story_renderer.render_story()  [SINGLE AI CALL]
        → story_validator.validate_post_render()

DESIGN PRINCIPLES:
- Exactly ONE place where pipeline ordering is defined
- No fallbacks. If any stage fails, raise.
- Pre-render validation before AI, post-render validation after AI
- Fail loud. No recovery. No retry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .types import Chapter
from .builder import build_chapters
from .running_stats import (
    build_running_snapshots,
    compute_section_deltas_from_snapshots,
    RunningStatsSnapshot,
)
from .beat_classifier import (
    classify_all_chapters,
    BeatClassification,
)
from .story_section import (
    build_story_sections,
    StorySection,
)
from .header_reset import generate_all_headers as generate_all_themes
from .game_quality import compute_quality_score, QualityScoreResult
from .target_length import select_target_word_count, TargetLengthResult
from .story_renderer import (
    build_story_render_input,
    render_story,
    StoryRenderInput,
    StoryRenderError,
)
from .story_validator import (
    validate_pre_render,
    validate_post_render,
    StoryValidationError,
)


logger = logging.getLogger(__name__)


# ============================================================================
# AI CLIENT PROTOCOL
# ============================================================================


class AIClient(Protocol):
    """Protocol for AI client implementations."""

    def generate(self, prompt: str) -> str:
        """Generate text from prompt."""
        ...


# ============================================================================
# PIPELINE RESULT
# ============================================================================


@dataclass
class PipelineResult:
    """Result of the chapters-first pipeline.

    Contains everything needed for the Admin UI response.
    """

    # Core output
    game_id: int
    sport: str
    compact_story: str
    word_count: int
    target_word_count: int

    # Structural data
    chapters: list[Chapter]
    sections: list[StorySection]
    themes: list[str]

    # Quality assessment
    quality: QualityScoreResult
    target_length: TargetLengthResult

    # Metadata
    generated_at: datetime
    reading_time_minutes: float

    # Debug data (optional)
    classifications: list[BeatClassification] | None = None
    snapshots: list[RunningStatsSnapshot] | None = None
    render_input: StoryRenderInput | None = None
    prompt_used: str | None = None
    raw_ai_response: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "game_id": self.game_id,
            "sport": self.sport,
            "compact_story": self.compact_story,
            "word_count": self.word_count,
            "target_word_count": self.target_word_count,
            "chapter_count": len(self.chapters),
            "section_count": len(self.sections),
            "quality": self.quality.quality.value,
            "generated_at": self.generated_at.isoformat(),
            "reading_time_minutes": self.reading_time_minutes,
        }


class PipelineError(Exception):
    """Raised when any pipeline stage fails."""

    def __init__(self, stage: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage
        self.details = details or {}


# ============================================================================
# PIPELINE ORCHESTRATOR
# ============================================================================


def build_game_story(
    timeline: list[dict[str, Any]],
    game_id: int,
    sport: str = "NBA",
    home_team_name: str = "Home",
    away_team_name: str = "Away",
    ai_client: AIClient | None = None,
    include_debug: bool = False,
) -> PipelineResult:
    """
    Build a game story using the chapters-first pipeline.

    This is the ONLY supported pipeline. There are no fallbacks.

    Pipeline stages (in order):
    1. build_chapters - Deterministic chapter boundaries
    2. build_running_snapshots - Cumulative stats at chapter boundaries
    3. classify_all_chapters - Beat type assignment
    4. build_story_sections - Collapse chapters into 3-10 sections
    5. generate_all_headers - Deterministic one-sentence headers
    6. compute_quality_score - LOW/MEDIUM/HIGH assessment
    7. select_target_word_count - Deterministic word count target
    8. validate_pre_render - Section ordering + stat consistency
    9. render_story - SINGLE AI CALL
    10. validate_post_render - Word count + no inventions + no contradictions

    Args:
        timeline: List of play-by-play events
        game_id: Game identifier
        sport: Sport code (e.g., "NBA")
        home_team_name: Home team name for AI prompt
        away_team_name: Away team name for AI prompt
        ai_client: AI client for rendering (if None, uses mock)
        include_debug: Include debug data in result

    Returns:
        PipelineResult with compact_story and all structural data

    Raises:
        PipelineError: If any stage fails
        StoryValidationError: If validation fails (fail loud)
    """
    logger.info(f"Starting chapters-first pipeline for game {game_id}")

    # =========================================================================
    # STAGE 1: BUILD CHAPTERS
    # =========================================================================
    try:
        game_story = build_chapters(
            timeline=timeline,
            game_id=game_id,
            sport=sport,
        )
        chapters = game_story.chapters
        logger.info(f"Stage 1: Built {len(chapters)} chapters")
    except Exception as e:
        raise PipelineError("build_chapters", str(e))

    if not chapters:
        raise PipelineError("build_chapters", "No chapters produced")

    # =========================================================================
    # STAGE 2: BUILD RUNNING STATS SNAPSHOTS
    # =========================================================================
    try:
        snapshots = build_running_snapshots(chapters)
        logger.info(f"Stage 2: Built {len(snapshots)} running stat snapshots")
    except Exception as e:
        raise PipelineError("build_running_snapshots", str(e))

    # =========================================================================
    # STAGE 3: CLASSIFY ALL CHAPTERS (Beat Types)
    # =========================================================================
    try:
        classifications = classify_all_chapters(chapters)
        logger.info(f"Stage 3: Classified {len(classifications)} chapters")
    except Exception as e:
        raise PipelineError("classify_all_chapters", str(e))

    # =========================================================================
    # STAGE 4: BUILD STORY SECTIONS (Collapse)
    # =========================================================================
    try:
        # Compute section deltas from snapshots
        section_deltas = compute_section_deltas_from_snapshots(snapshots)

        sections = build_story_sections(
            chapters=chapters,
            classifications=classifications,
            section_deltas=section_deltas,
        )
        logger.info(f"Stage 4: Built {len(sections)} story sections")
    except Exception as e:
        raise PipelineError("build_story_sections", str(e))

    if not sections:
        raise PipelineError("build_story_sections", "No sections produced")

    # =========================================================================
    # STAGE 5: GENERATE THEMES (Deterministic)
    # =========================================================================
    try:
        themes = generate_all_themes(sections)
        logger.info(f"Stage 5: Generated {len(themes)} themes")
    except Exception as e:
        raise PipelineError("generate_all_themes", str(e))

    # =========================================================================
    # STAGE 6: COMPUTE QUALITY SCORE
    # =========================================================================
    try:
        # Get final scores from last section
        final_section = sections[-1]
        final_home_score = final_section.end_score.get("home", 0)
        final_away_score = final_section.end_score.get("away", 0)

        # Build score history from sections
        score_history = []
        for section in sections:
            score_history.append(
                {
                    "home": section.end_score.get("home", 0),
                    "away": section.end_score.get("away", 0),
                }
            )

        quality = compute_quality_score(
            sections=sections,
            final_home_score=final_home_score,
            final_away_score=final_away_score,
            score_history=score_history,
        )
        logger.info(
            f"Stage 6: Quality score = {quality.quality.value} ({quality.numeric_score:.1f})"
        )
    except Exception as e:
        raise PipelineError("compute_quality_score", str(e))

    # =========================================================================
    # STAGE 7: SELECT TARGET WORD COUNT
    # =========================================================================
    try:
        target_length = select_target_word_count(quality.quality)
        logger.info(f"Stage 7: Target word count = {target_length.target_words}")
    except Exception as e:
        raise PipelineError("select_target_word_count", str(e))

    # =========================================================================
    # STAGE 8: PRE-RENDER VALIDATION
    # =========================================================================
    try:
        all_chapter_ids = [ch.chapter_id for ch in chapters]
        validate_pre_render(sections, all_chapter_ids)
        logger.info("Stage 8: Pre-render validation PASSED")
    except StoryValidationError:
        # Re-raise validation errors directly (fail loud)
        raise
    except Exception as e:
        raise PipelineError("validate_pre_render", str(e))

    # =========================================================================
    # STAGE 9: RENDER STORY (SINGLE AI CALL)
    # =========================================================================
    try:
        # Build render input
        decisive_factors = _compute_decisive_factors(sections, quality)

        render_input = build_story_render_input(
            sections=sections,
            themes=themes,
            sport=sport,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
            target_word_count=target_length.target_words,
            decisive_factors=decisive_factors,
        )

        # Render story (SINGLE AI CALL)
        render_result = render_story(render_input, ai_client=ai_client)
        logger.info(f"Stage 9: Rendered story ({render_result.word_count} words)")
    except StoryRenderError as e:
        raise PipelineError("render_story", str(e))
    except Exception as e:
        raise PipelineError("render_story", str(e))

    # =========================================================================
    # STAGE 10: POST-RENDER VALIDATION
    # =========================================================================
    try:
        validate_post_render(
            compact_story=render_result.compact_story,
            input_data=render_input,
            result=render_result,
        )
        logger.info("Stage 10: Post-render validation PASSED")
    except StoryValidationError:
        # Re-raise validation errors directly (fail loud)
        raise
    except Exception as e:
        raise PipelineError("validate_post_render", str(e))

    # =========================================================================
    # BUILD RESULT
    # =========================================================================
    reading_time_minutes = render_result.word_count / 200.0  # ~200 wpm average

    result = PipelineResult(
        game_id=game_id,
        sport=sport,
        compact_story=render_result.compact_story,
        word_count=render_result.word_count,
        target_word_count=target_length.target_words,
        chapters=chapters,
        sections=sections,
        themes=themes,
        quality=quality,
        target_length=target_length,
        generated_at=datetime.utcnow(),
        reading_time_minutes=reading_time_minutes,
    )

    if include_debug:
        result.classifications = classifications
        result.snapshots = snapshots
        result.render_input = render_input
        result.prompt_used = render_result.prompt_used
        result.raw_ai_response = render_result.raw_response

    logger.info(
        f"Pipeline complete for game {game_id}: {render_result.word_count} words"
    )
    return result


def _compute_decisive_factors(
    sections: list[StorySection],
    quality: QualityScoreResult,
) -> list[str]:
    """Compute deterministic decisive factors for closing paragraph.

    Args:
        sections: Story sections
        quality: Quality score result

    Returns:
        List of decisive factor bullets
    """
    factors = []

    # Add quality-based factors
    signals = quality.signals
    if signals.has_overtime:
        factors.append("Game required overtime to decide")

    if signals.has_crunch:
        factors.append("Late-game intensity shaped the outcome")

    if signals.lead_changes >= 10:
        factors.append(f"Lead changed hands {signals.lead_changes} times")
    elif signals.lead_changes >= 5:
        factors.append("Multiple lead changes kept the game close")

    if signals.final_margin is not None:
        if signals.final_margin <= 3:
            factors.append("Final margin was razor-thin")
        elif signals.final_margin <= 6:
            factors.append("Final margin was within one possession")

    if signals.run_response_count >= 3:
        factors.append("Both teams answered scoring runs throughout")

    # Fallback if no factors
    if not factors:
        factors.append("Competitive play throughout the game")

    return factors
