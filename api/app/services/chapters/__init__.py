"""
Book + Chapters Model

A game is a book. Plays are pages. Chapters are contiguous play ranges
that represent coherent scenes.

This module replaces the legacy "Moments" concept with a simpler,
narrative-first architecture.

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
from .prompts import (
    check_for_spoilers,
    validate_title,
    BANNED_PHRASES,
    TITLE_BANNED_WORDS,
)
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
from .narrative_validator import (
    NarrativeValidator,
    ValidationResult,
    validate_narrative_output,
    all_valid,
    get_all_errors,
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
    "check_for_spoilers",
    "BANNED_PHRASES",
    # Title generation
    "ChapterTitleResult",
    "TitleGenerationError",
    "generate_chapter_title",
    "generate_titles_for_chapters",
    "validate_title",
    "TITLE_BANNED_WORDS",
    # Compact story generation
    "CompactStoryResult",
    "CompactStoryGenerationError",
    "generate_compact_story",
    "validate_compact_story_input",
    # Narrative validation
    "NarrativeValidator",
    "ValidationResult",
    "validate_narrative_output",
    "all_valid",
    "get_all_errors",
]
