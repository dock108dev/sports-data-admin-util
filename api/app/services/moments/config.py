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

# Game progress thresholds for phase detection (percentage-based)
EARLY_GAME_PROGRESS_THRESHOLD = 0.35  # First ~35% = early game
MID_GAME_PROGRESS_THRESHOLD = 0.75  # 35-75% = mid game (late game starts at 75%+)

# Minimum tier for early-game FLIP/TIE to bypass hysteresis
EARLY_GAME_MIN_TIER_FOR_IMMEDIATE = 1

# =============================================================================
# CLOSING SITUATION CONFIGURATION
# =============================================================================
# UNIFIED CLOSING TAXONOMY:
# There are TWO types of closing situations with different behaviors:
#
# 1. CLOSE_GAME_CLOSING (expansion mode)
#    - Q4/OT with limited time remaining
#    - Game is competitive (tier <= 1 OR margin <= possession threshold)
#    - Behavior: expand, allow micro-moments, relax density gating
#
# 2. DECIDED_GAME_CLOSING (compression mode)
#    - Q4/OT with limited time remaining
#    - Game is decided (tier >= 2 AND margin > safe margin)
#    - Behavior: suppress cuts, absorb runs, no semantic escalation

# Shared window - both closing types use the same time window
CLOSING_WINDOW_SECONDS = 300  # 5 minutes (final window for closing checks)

# CLOSE_GAME_CLOSING thresholds
CLOSE_GAME_MAX_TIER = 1  # Tier <= this = close game
CLOSE_GAME_POSSESSION_THRESHOLD = 6  # Margin <= this = within one possession

# DECIDED_GAME_CLOSING thresholds  
DECIDED_GAME_MIN_TIER = 2  # Tier >= this = game decided
DECIDED_GAME_SAFE_MARGIN = 10  # Margin > this = safe lead

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
