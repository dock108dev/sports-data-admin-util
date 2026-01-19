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
    RecapContext,
    RunInfo,
)

# Configuration
from .config import (
    ALWAYS_MERGE_TYPES,
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
from ..moments_boundaries import (
    DensityGateDecision,
    LateFalseDramaDecision,
    DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS,
    DENSITY_GATE_LATE_GAME_PROGRESS,
    LATE_GAME_MIN_QUARTER,
    LATE_GAME_MAX_SECONDS,
    LATE_GAME_SAFE_MARGIN,
    LATE_GAME_SAFE_TIER,
)

# Unified closing taxonomy
from .closing import (
    ClosingCategory,
    ClosingClassification,
    classify_closing_situation,
    classify_closing_from_scores,
    should_expand_in_closing,
    should_suppress_cut_boundary,
    should_suppress_run_boundary,
    should_relax_density_gating,
    should_emit_closing_control,
)

# Sport-agnostic game structure
from .game_structure import (
    PhaseType,
    GameStructure,
    GamePhaseState,
    GamePhaseContext,
    PhaseBoundary,
    get_game_structure,
    compute_game_phase_state,
    compute_game_progress,
    build_game_phase_context,
    is_final_phase,
    is_late_game,
    is_closing_window,
    get_phase_label,
    # Phase thresholds
    DEFAULT_EARLY_GAME_THRESHOLD,
    DEFAULT_MID_GAME_THRESHOLD,
    DEFAULT_LATE_GAME_THRESHOLD,
    DEFAULT_CLOSING_THRESHOLD,
    # Sport configurations
    NBA_STRUCTURE,
    NCAAB_STRUCTURE,
    NHL_STRUCTURE,
    NFL_STRUCTURE,
    DEFAULT_STRUCTURE,
    SPORT_STRUCTURES,
)

# Unified closing configuration
from .config import (
    CLOSING_WINDOW_SECONDS,
    CLOSE_GAME_MAX_TIER,
    CLOSE_GAME_POSSESSION_THRESHOLD,
    DECIDED_GAME_MIN_TIER,
    DECIDED_GAME_SAFE_MARGIN,
)

__all__ = [
    # Types
    "Moment",
    "MomentReason",
    "MomentType",
    "MomentValidationError",
    "PlayerContribution",
    "RecapContext",
    "RunInfo",
    "DensityGateDecision",
    "LateFalseDramaDecision",
    # Unified Closing Taxonomy
    "ClosingCategory",
    "ClosingClassification",
    "classify_closing_situation",
    "classify_closing_from_scores",
    "should_expand_in_closing",
    "should_suppress_cut_boundary",
    "should_suppress_run_boundary",
    "should_relax_density_gating",
    "should_emit_closing_control",
    # Sport-Agnostic Game Structure
    "PhaseType",
    "GameStructure",
    "GamePhaseState",
    "GamePhaseContext",
    "PhaseBoundary",
    "get_game_structure",
    "compute_game_phase_state",
    "compute_game_progress",
    "build_game_phase_context",
    "is_final_phase",
    "is_late_game",
    "is_closing_window",
    "get_phase_label",
    "DEFAULT_EARLY_GAME_THRESHOLD",
    "DEFAULT_MID_GAME_THRESHOLD",
    "DEFAULT_LATE_GAME_THRESHOLD",
    "DEFAULT_CLOSING_THRESHOLD",
    "NBA_STRUCTURE",
    "NCAAB_STRUCTURE",
    "NHL_STRUCTURE",
    "NFL_STRUCTURE",
    "DEFAULT_STRUCTURE",
    "SPORT_STRUCTURES",
    # Configuration
    "ALWAYS_MERGE_TYPES",
    "CLOSING_WINDOW_SECONDS",
    "CLOSE_GAME_MAX_TIER",
    "CLOSE_GAME_POSSESSION_THRESHOLD",
    "DECIDED_GAME_MIN_TIER",
    "DECIDED_GAME_SAFE_MARGIN",
    "DEFAULT_FLIP_HYSTERESIS_PLAYS",
    "DEFAULT_HYSTERESIS_PLAYS",
    "DEFAULT_MOMENT_BUDGET",
    "DEFAULT_TIE_HYSTERESIS_PLAYS",
    "DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS",
    "DENSITY_GATE_LATE_GAME_PROGRESS",
    "LATE_GAME_MIN_QUARTER",
    "LATE_GAME_MAX_SECONDS",
    "LATE_GAME_SAFE_MARGIN",
    "LATE_GAME_SAFE_TIER",
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
