"""
Timeline artifact generation - backwards compatibility shim.

This module now re-exports from the modular timeline package.
For new code, import directly from app.services.timeline.

See:
- timeline/generator.py: Main orchestrator
- timeline/pbp_events.py: PBP event building
- timeline/phase_utils.py: Phase/time calculations
- timeline/artifact.py: Storage/versioning
"""

# Re-export everything from the new package for backwards compatibility
from .timeline import (
    # Main API
    generate_timeline_artifact,
    build_nba_timeline,
    TimelineArtifactPayload,
    TimelineGenerationError,
    DEFAULT_TIMELINE_VERSION,
    # Storage
    get_stored_artifact,
    store_artifact,
    # PBP
    build_pbp_events,
    nba_game_end,
    # Phase utilities
    PHASE_ORDER,
    SOCIAL_PREGAME_WINDOW_SECONDS,
    SOCIAL_POSTGAME_WINDOW_SECONDS,
    compute_phase_boundaries,
    nba_block_for_quarter,
    nba_phase_for_quarter,
    nba_quarter_start,
    parse_clock_to_seconds,
    phase_sort_order,
    progress_from_index,
)

# Backwards compatibility aliases (private functions now public in package)
_phase_sort_order = phase_sort_order
_nba_phase_for_quarter = nba_phase_for_quarter
_nba_block_for_quarter = nba_block_for_quarter
_nba_quarter_start = nba_quarter_start
_nba_regulation_end = None  # Deprecated - use nba_game_end instead
_nba_game_end = nba_game_end
_compute_phase_boundaries = compute_phase_boundaries
_build_pbp_events = build_pbp_events
_parse_clock_to_seconds = parse_clock_to_seconds
_progress_from_index = progress_from_index

__all__ = [
    # Main API
    "generate_timeline_artifact",
    "build_nba_timeline",
    "TimelineArtifactPayload",
    "TimelineGenerationError",
    "DEFAULT_TIMELINE_VERSION",
    # Storage
    "get_stored_artifact",
    "store_artifact",
    # PBP
    "build_pbp_events",
    "nba_game_end",
    # Phase utilities
    "PHASE_ORDER",
    "SOCIAL_PREGAME_WINDOW_SECONDS",
    "SOCIAL_POSTGAME_WINDOW_SECONDS",
    "compute_phase_boundaries",
    "nba_block_for_quarter",
    "nba_phase_for_quarter",
    "nba_quarter_start",
    "parse_clock_to_seconds",
    "phase_sort_order",
    "progress_from_index",
]
