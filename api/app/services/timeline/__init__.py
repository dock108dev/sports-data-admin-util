"""
Timeline generation package.

This package provides modular timeline generation for sports games.

Public API:
- generate_timeline_artifact: Main async entry point
- build_nba_timeline: Sync timeline construction
- TimelineArtifactPayload: Result payload dataclass
- TimelineGenerationError: Error type for generation failures

Modules:
- generator.py: Main orchestrator
- pbp_events.py: PBP event building
- phase_utils.py: Phase/time calculations
- artifact.py: Storage/versioning
"""

from .artifact import (
    DEFAULT_TIMELINE_VERSION,
    TimelineArtifactPayload,
    TimelineGenerationError,
    get_stored_artifact,
    store_artifact,
)
from .generator import (
    build_nba_timeline,
    generate_timeline_artifact,
)
from .pbp_events import (
    build_pbp_events,
    nba_game_end,
)
from .phase_utils import (
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
