"""Moment system configuration constants.

This module contains all configurable thresholds and budgets for the moment system.
All values are sport-agnostic with per-sport overrides where needed.
"""

from .types import MomentType

# =============================================================================
# HYSTERESIS CONFIGURATION
# =============================================================================

# Default hysteresis: number of plays a tier must persist to register
DEFAULT_HYSTERESIS_PLAYS = 2

# FLIP/TIE hysteresis: number of plays to confirm leader changes
DEFAULT_FLIP_HYSTERESIS_PLAYS = 2
DEFAULT_TIE_HYSTERESIS_PLAYS = 1

# =============================================================================
# TIME-AWARE GATING CONFIGURATION
# =============================================================================

# Game progress thresholds for phase detection
EARLY_GAME_PROGRESS_THRESHOLD = 0.35  # First ~35% (Q1 + early Q2)
MID_GAME_PROGRESS_THRESHOLD = 0.75  # Mid-game ends at ~75% (late Q3)

# Minimum tier for early-game FLIP/TIE to bypass hysteresis
EARLY_GAME_MIN_TIER_FOR_IMMEDIATE = 1

# =============================================================================
# CLOSING SITUATION CONFIGURATION
# =============================================================================

# Default thresholds for closing detection
DEFAULT_CLOSING_SECONDS = 300  # 5 minutes
DEFAULT_CLOSING_TIER = 1  # Max tier for "close" game

# =============================================================================
# HIGH-IMPACT PLAY TYPES
# =============================================================================

HIGH_IMPACT_PLAY_TYPES = frozenset({
    "ejection",
    "flagrant",
    "technical",
    "injury",
})

# =============================================================================
# MOMENT BUDGET (HARD CONSTRAINT)
# =============================================================================

MOMENT_BUDGET: dict[str, int] = {
    "NBA": 30,
    "NCAAB": 32,
    "NFL": 22,
    "NHL": 28,
    "MLB": 26,
}
DEFAULT_MOMENT_BUDGET = 30

# Per-quarter/period limits prevent "chaotic quarter" bloat
QUARTER_MOMENT_LIMIT = 7

# =============================================================================
# MOMENT TYPE CATEGORIES
# =============================================================================

# Moment types that can NEVER be merged (dramatic moments)
PROTECTED_TYPES = frozenset({
    MomentType.FLIP,
    MomentType.CLOSING_CONTROL,
    MomentType.HIGH_IMPACT,
    MomentType.MOMENTUM_SHIFT,
})

# Moment types that should always be merged when consecutive
ALWAYS_MERGE_TYPES = frozenset({
    MomentType.NEUTRAL,
    MomentType.LEAD_BUILD,
    MomentType.CUT,
})
