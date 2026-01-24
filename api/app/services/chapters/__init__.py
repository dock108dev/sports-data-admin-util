"""
Book + Chapters Model

A game is a book. Plays are pages. Chapters are contiguous play ranges
that represent coherent scenes.

This module provides a narrative-first architecture for game storytelling.
"""

from .types import Play, Chapter, GameStory, ChapterBoundary, TimeRange
from .builder import build_chapters
from .boundary_rules import (
    BoundaryType,
    BoundaryMarker,
    VirtualBoundaryReason,
    get_boundary_type_for_reasons,
)
from .virtual_boundaries import detect_virtual_boundaries
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
    BeatDescriptor,  # Phase 2.1
    RunWindow,  # Phase 2.2
    ResponseWindow,  # Phase 2.3
    BackAndForthWindow,  # Phase 2.4
    EarlyWindowStats,  # Phase 2.5
    SectionBeatOverride,  # Phase 2.5
    ChapterContext,
    BeatClassification,
    # Constants (Phase 2.1)
    PRIMARY_BEATS,
    BEAT_PRIORITY,
    MISSED_SHOT_PPP_THRESHOLD,
    # Constants (Phase 2.2)
    RUN_WINDOW_THRESHOLD,
    RUN_MARGIN_EXPANSION_THRESHOLD,
    # Constants (Phase 2.4)
    BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD,
    BACK_AND_FORTH_TIES_THRESHOLD,
    # Constants (Phase 2.5)
    EARLY_WINDOW_DURATION_SECONDS,
    FAST_START_MIN_COMBINED_POINTS,
    FAST_START_MAX_MARGIN,
    EARLY_CONTROL_MIN_LEAD,
    EARLY_CONTROL_MIN_SHARE_PCT,
    # Constants (Phase 2.6)
    CRUNCH_SETUP_TIME_THRESHOLD,
    CRUNCH_SETUP_MARGIN_THRESHOLD,
    CLOSING_SEQUENCE_TIME_THRESHOLD,
    CLOSING_SEQUENCE_MARGIN_THRESHOLD,
    # Functions
    classify_chapter_beat,
    classify_all_chapters,
    build_chapter_context,
    format_classification_debug,
    get_beat_distribution,
    # Run window functions (Phase 2.2)
    detect_run_windows,
    get_qualifying_run_windows,
    # Response window functions (Phase 2.3)
    detect_response_windows,
    get_qualifying_response_windows,
    # Back-and-forth window functions (Phase 2.4)
    detect_back_and_forth_window,
    get_qualifying_back_and_forth_window,
    # Section-level beat functions (Phase 2.5)
    compute_early_window_stats,
    detect_section_fast_start,
    detect_section_early_control,
    detect_opening_section_beat,
)
from .story_section import (
    # Types
    StorySection,
    TeamStatDelta as SectionTeamStatDelta,
    PlayerStatDelta as SectionPlayerStatDelta,
    ForcedBreakReason,
    # Player Prominence types and functions
    PlayerProminence,
    compute_player_prominence,
    select_prominent_players,
    # Constants (Signal thresholds)
    SECTION_MIN_POINTS_THRESHOLD,
    SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD,
    # Constants (Thin section)
    THIN_SECTION_MAX_POINTS,
    THIN_SECTION_MAX_SCORING_PLAYS,
    # Constants (Lumpy section / dominance capping)
    LUMPY_DOMINANCE_THRESHOLD_PCT,
    DOMINANCE_CAP_PCT,
    # Beat compatibility
    INCOMPATIBLE_BEAT_PAIRS,
    CRUNCH_TIER_BEATS,
    NON_CRUNCH_BEATS,
    are_beats_compatible_for_merge,
    # Signal evaluation
    count_meaningful_events,
    get_section_total_points,
    is_section_underpowered,
    handle_underpowered_sections,
    # Thin section functions
    count_section_scoring_plays,
    is_section_thin,
    handle_thin_sections,
    # Lumpy section functions
    get_dominant_player_share,
    is_section_lumpy,
    apply_dominance_cap,
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
    # Phase 1.1: Boundary classification
    "BoundaryType",
    "BoundaryMarker",
    "VirtualBoundaryReason",
    "get_boundary_type_for_reasons",
    "detect_virtual_boundaries",
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
    "BeatDescriptor",  # Phase 2.1
    "RunWindow",  # Phase 2.2
    "ResponseWindow",  # Phase 2.3
    "BackAndForthWindow",  # Phase 2.4
    "EarlyWindowStats",  # Phase 2.5
    "SectionBeatOverride",  # Phase 2.5
    "ChapterContext",
    "BeatClassification",
    "PRIMARY_BEATS",  # Phase 2.1
    "BEAT_PRIORITY",  # Phase 2.1
    "MISSED_SHOT_PPP_THRESHOLD",  # Phase 2.1
    "RUN_WINDOW_THRESHOLD",  # Phase 2.2
    "RUN_MARGIN_EXPANSION_THRESHOLD",  # Phase 2.2
    "BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD",  # Phase 2.4
    "BACK_AND_FORTH_TIES_THRESHOLD",  # Phase 2.4
    "EARLY_WINDOW_DURATION_SECONDS",  # Phase 2.5
    "FAST_START_MIN_COMBINED_POINTS",  # Phase 2.5
    "FAST_START_MAX_MARGIN",  # Phase 2.5
    "EARLY_CONTROL_MIN_LEAD",  # Phase 2.5
    "EARLY_CONTROL_MIN_SHARE_PCT",  # Phase 2.5
    "CRUNCH_SETUP_TIME_THRESHOLD",  # Phase 2.6
    "CRUNCH_SETUP_MARGIN_THRESHOLD",  # Phase 2.6
    "CLOSING_SEQUENCE_TIME_THRESHOLD",  # Phase 2.6
    "CLOSING_SEQUENCE_MARGIN_THRESHOLD",  # Phase 2.6
    "classify_chapter_beat",
    "classify_all_chapters",
    "build_chapter_context",
    "format_classification_debug",
    "get_beat_distribution",
    "detect_run_windows",  # Phase 2.2
    "get_qualifying_run_windows",  # Phase 2.2
    "detect_response_windows",  # Phase 2.3
    "get_qualifying_response_windows",  # Phase 2.3
    "detect_back_and_forth_window",  # Phase 2.4
    "get_qualifying_back_and_forth_window",  # Phase 2.4
    "compute_early_window_stats",  # Phase 2.5
    "detect_section_fast_start",  # Phase 2.5
    "detect_section_early_control",  # Phase 2.5
    "detect_opening_section_beat",  # Phase 2.5
    # Story section builder
    "StorySection",
    "SectionTeamStatDelta",
    "SectionPlayerStatDelta",
    "ForcedBreakReason",
    # Player Prominence
    "PlayerProminence",
    "compute_player_prominence",
    "select_prominent_players",
    # Signal thresholds
    "SECTION_MIN_POINTS_THRESHOLD",
    "SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD",
    # Thin section constants
    "THIN_SECTION_MAX_POINTS",
    "THIN_SECTION_MAX_SCORING_PLAYS",
    # Lumpy section / dominance capping constants
    "LUMPY_DOMINANCE_THRESHOLD_PCT",
    "DOMINANCE_CAP_PCT",
    # Beat compatibility
    "INCOMPATIBLE_BEAT_PAIRS",
    "CRUNCH_TIER_BEATS",
    "NON_CRUNCH_BEATS",
    "are_beats_compatible_for_merge",
    # Signal evaluation
    "count_meaningful_events",
    "get_section_total_points",
    "is_section_underpowered",
    "handle_underpowered_sections",
    # Thin section functions
    "count_section_scoring_plays",
    "is_section_thin",
    "handle_thin_sections",
    # Lumpy section functions
    "get_dominant_player_share",
    "is_section_lumpy",
    "apply_dominance_cap",
    # Section functions
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
