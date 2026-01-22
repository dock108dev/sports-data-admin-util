"""
Book + Chapters Model

A game is a book. Plays are pages. Chapters are contiguous play ranges
that represent coherent scenes.

This module provides a narrative-first architecture for game storytelling.

Issue 0.2: Canonical data model and output contract.
"""

from .types import Play, Chapter, GameStory, ChapterBoundary, TimeRange
from .builder import build_chapters
from .chapterizer import ChapterizerV1, ChapterizerConfig
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
from .story_state import (
    StoryState,
    PlayerStoryState,
    TeamStoryState,
    MomentumHint,
    derive_story_state_from_chapters,
    build_initial_state,
    update_state,
    build_state_incrementally,
)
from .ai_context import (
    ChapterSummary,
    ChapterAIInput,
    BookAIInput,
    build_chapter_ai_input,
    build_book_ai_input,
    validate_no_future_context,
)
from .ai_signals import (
    SignalValidationError,
    validate_ai_signals,
    check_for_disallowed_signals,
    format_ai_signals_summary,
    ALLOWED_PLAYER_SIGNALS,
    ALLOWED_TEAM_SIGNALS,
    ALLOWED_THEME_TAGS,
    ALLOWED_NOTABLE_ACTIONS,
    DISALLOWED_SIGNALS,
)
from .summary_generator import (
    ChapterSummaryResult,
    SummaryGenerationError,
    generate_chapter_summary,
    generate_summaries_sequentially,
)
# Validation removed - trust the architecture
from .title_generator import (
    ChapterTitleResult,
    TitleGenerationError,
    generate_chapter_title,
    generate_titles_for_chapters,
)
from .compact_story_generator import (
    CompactStoryResult,
    CompactStoryGenerationError,
    generate_compact_story,
    validate_compact_story_input,
)
# Narrative validator removed - trust the architecture
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
    "ChapterizerV1",
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
    # Story state
    "StoryState",
    "PlayerStoryState",
    "TeamStoryState",
    "MomentumHint",
    "derive_story_state_from_chapters",
    "build_initial_state",
    "update_state",
    "build_state_incrementally",
    # AI context
    "ChapterSummary",
    "ChapterAIInput",
    "BookAIInput",
    "build_chapter_ai_input",
    "build_book_ai_input",
    "validate_no_future_context",
    # AI signals
    "SignalValidationError",
    "validate_ai_signals",
    "check_for_disallowed_signals",
    "format_ai_signals_summary",
    "ALLOWED_PLAYER_SIGNALS",
    "ALLOWED_TEAM_SIGNALS",
    "ALLOWED_THEME_TAGS",
    "ALLOWED_NOTABLE_ACTIONS",
    "DISALLOWED_SIGNALS",
    # Summary generation
    "ChapterSummaryResult",
    "SummaryGenerationError",
    "generate_chapter_summary",
    "generate_summaries_sequentially",
    # Title generation
    "ChapterTitleResult",
    "TitleGenerationError",
    "generate_chapter_title",
    "generate_titles_for_chapters",
    # Compact story generation
    "CompactStoryResult",
    "CompactStoryGenerationError",
    "generate_compact_story",
    "validate_compact_story_input",
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
]
