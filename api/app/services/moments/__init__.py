"""Moments package - partition game timelines into narrative segments.

This package implements Lead Ladder-based moment detection, partitioning
a game timeline into contiguous narrative segments based on control changes.

Usage:
    from app.services.moments import partition_game, Moment, MomentType
"""

# Types and data classes
from .types import (
    Moment,
    MomentReason,
    MomentType,
    PlayerContribution,
    RunInfo,
)

# Configuration
from .config import (
    ALWAYS_MERGE_TYPES,
    DEFAULT_CLOSING_SECONDS,
    DEFAULT_CLOSING_TIER,
    DEFAULT_FLIP_HYSTERESIS_PLAYS,
    DEFAULT_HYSTERESIS_PLAYS,
    DEFAULT_MOMENT_BUDGET,
    DEFAULT_TIE_HYSTERESIS_PLAYS,
    EARLY_GAME_MIN_TIER_FOR_IMMEDIATE,
    EARLY_GAME_PROGRESS_THRESHOLD,
    HIGH_IMPACT_PLAY_TYPES,
    MID_GAME_PROGRESS_THRESHOLD,
    MOMENT_BUDGET,
    PROTECTED_TYPES,
    QUARTER_MOMENT_LIMIT,
)

# Main algorithm and public API
from .partition import (
    get_notable_moments,
    partition_game,
    validate_moments,
)

# Helper functions (some are used by other modules)
from .helpers import (
    get_game_progress,
)

# Re-export from sibling modules
from ..moments_validation import MomentValidationError
from ..moments_normalization import normalize_scores

__all__ = [
    # Types
    "Moment",
    "MomentReason",
    "MomentType",
    "MomentValidationError",
    "PlayerContribution",
    "RunInfo",
    # Configuration
    "ALWAYS_MERGE_TYPES",
    "DEFAULT_CLOSING_SECONDS",
    "DEFAULT_CLOSING_TIER",
    "DEFAULT_FLIP_HYSTERESIS_PLAYS",
    "DEFAULT_HYSTERESIS_PLAYS",
    "DEFAULT_MOMENT_BUDGET",
    "DEFAULT_TIE_HYSTERESIS_PLAYS",
    "EARLY_GAME_MIN_TIER_FOR_IMMEDIATE",
    "EARLY_GAME_PROGRESS_THRESHOLD",
    "HIGH_IMPACT_PLAY_TYPES",
    "MID_GAME_PROGRESS_THRESHOLD",
    "MOMENT_BUDGET",
    "PROTECTED_TYPES",
    "QUARTER_MOMENT_LIMIT",
    # Functions
    "get_notable_moments",
    "partition_game",
    "validate_moments",
    "normalize_scores",
    "get_game_progress",
]
