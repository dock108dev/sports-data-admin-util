"""
Book + Chapters Model

A game is a book. Plays are pages. Chapters are contiguous play ranges
that represent coherent scenes.

This module provides a narrative-first architecture for game storytelling.
"""

from .types import Play, Chapter, GameStory, ChapterBoundary, TimeRange
from .builder import build_chapters
from .chapterizer import Chapterizer, ChapterizerConfig
from .coverage_validator import (
    CoverageValidationResult,
    CoverageValidationError,
    compute_chapters_fingerprint,
    validate_chapter_coverage,
    validate_game_story_coverage,
)
from .debug_logger import (
    ChapterDebugLogger,
    ChapterLogEventType,
    BoundaryAction,
    trace_chapter_reason_codes,
)
from .running_stats import (
    # Data structures
    PlayerSnapshot,
    TeamSnapshot,
    RunningStatsSnapshot,
    PlayerDelta,
    TeamDelta,
    SectionDelta,
    # Builder functions
    normalize_player_key,
    build_initial_snapshot,
    update_snapshot,
    build_running_snapshots,
    compute_section_delta,
    compute_section_deltas_from_snapshots,
)
from .beat_classifier import (
    # Types
    BeatType,
    ChapterContext,
    BeatClassification,
    # Functions
    classify_chapter_beat,
    classify_all_chapters,
    build_chapter_context,
    format_classification_debug,
    get_beat_distribution,
)
from .story_section import (
    # Types
    StorySection,
    TeamStatDelta as SectionTeamStatDelta,
    PlayerStatDelta as SectionPlayerStatDelta,
    ForcedBreakReason,
    # Functions
    build_story_sections,
    enforce_section_count,
    generate_section_notes,
    format_sections_debug,
)
from .header_reset import (
    # Types
    HeaderContext,
    HEADER_TEMPLATES,
    # Functions
    build_header_context,
    generate_header,
    generate_header_for_section,
    generate_all_headers,
    validate_header,
    format_headers_debug,
)
from .game_quality import (
    # Types
    GameQuality,
    QualitySignals,
    QualityScoreResult,
    # Functions
    count_lead_changes,
    compute_quality_score,
    format_quality_debug,
)
from .target_length import (
    # Types
    TargetLengthResult,
    # Functions
    select_target_word_count,
    get_target_words,
    format_target_debug,
)
from .story_renderer import (
    # Types
    ClosingContext,
    SectionRenderInput,
    StoryRenderInput,
    StoryRenderResult,
    StoryRenderError,
    # Functions
    build_section_render_input,
    build_story_render_input,
    build_render_prompt,
    render_story,
    validate_render_input,
    validate_render_result,
    format_render_debug,
)
from .story_validator import (
    # Error types
    StoryValidationError,
    SectionOrderingError,
    StatConsistencyError,
    WordCountError,
    PlayerInventionError,
    StatInventionError,
    OutcomeContradictionError,
    # Result type
    ValidationResult,
    # Validation functions
    validate_section_ordering,
    validate_stat_consistency,
    validate_word_count,
    validate_no_new_players,
    validate_no_stat_invention,
    validate_no_outcome_contradictions,
    validate_pre_render,
    validate_post_render,
    validate_full_pipeline,
    format_validation_debug,
    # Constants
    WORD_COUNT_TOLERANCE_PCT,
)
from .pipeline import (
    # The ONLY supported pipeline orchestrator
    build_game_story,
    PipelineResult,
    PipelineError,
)

__all__ = [
    # Core types
    "Play",
    "Chapter",
    "GameStory",
    "ChapterBoundary",
    "TimeRange",
    # Builder
    "build_chapters",
    # Chapterizer
    "Chapterizer",
    "ChapterizerConfig",
    # Coverage validator
    "CoverageValidationResult",
    "CoverageValidationError",
    "compute_chapters_fingerprint",
    "validate_chapter_coverage",
    "validate_game_story_coverage",
    # Debug logger
    "ChapterDebugLogger",
    "ChapterLogEventType",
    "BoundaryAction",
    "trace_chapter_reason_codes",
    # Running stats builder
    "PlayerSnapshot",
    "TeamSnapshot",
    "RunningStatsSnapshot",
    "PlayerDelta",
    "TeamDelta",
    "SectionDelta",
    "normalize_player_key",
    "build_initial_snapshot",
    "update_snapshot",
    "build_running_snapshots",
    "compute_section_delta",
    "compute_section_deltas_from_snapshots",
    # Beat classifier
    "BeatType",
    "ChapterContext",
    "BeatClassification",
    "classify_chapter_beat",
    "classify_all_chapters",
    "build_chapter_context",
    "format_classification_debug",
    "get_beat_distribution",
    # Story section builder
    "StorySection",
    "SectionTeamStatDelta",
    "SectionPlayerStatDelta",
    "ForcedBreakReason",
    "build_story_sections",
    "enforce_section_count",
    "generate_section_notes",
    "format_sections_debug",
    # Header reset generator
    "HeaderContext",
    "HEADER_TEMPLATES",
    "build_header_context",
    "generate_header",
    "generate_header_for_section",
    "generate_all_headers",
    "validate_header",
    "format_headers_debug",
    # Game quality scoring
    "GameQuality",
    "QualitySignals",
    "QualityScoreResult",
    "count_lead_changes",
    "compute_quality_score",
    "format_quality_debug",
    # Target word count
    "TargetLengthResult",
    "select_target_word_count",
    "get_target_words",
    "format_target_debug",
    # Story renderer (ONLY AI rendering path)
    "ClosingContext",
    "SectionRenderInput",
    "StoryRenderInput",
    "StoryRenderResult",
    "StoryRenderError",
    "build_section_render_input",
    "build_story_render_input",
    "build_render_prompt",
    "render_story",
    "validate_render_input",
    "validate_render_result",
    "format_render_debug",
    # Story validator (FAIL LOUD)
    "StoryValidationError",
    "SectionOrderingError",
    "StatConsistencyError",
    "WordCountError",
    "PlayerInventionError",
    "StatInventionError",
    "OutcomeContradictionError",
    "ValidationResult",
    "validate_section_ordering",
    "validate_stat_consistency",
    "validate_word_count",
    "validate_no_new_players",
    "validate_no_stat_invention",
    "validate_no_outcome_contradictions",
    "validate_pre_render",
    "validate_post_render",
    "validate_full_pipeline",
    "format_validation_debug",
    "WORD_COUNT_TOLERANCE_PCT",
    # Pipeline orchestrator (ONLY supported path)
    "build_game_story",
    "PipelineResult",
    "PipelineError",
]
