"""Timeline artifact types, constants, and exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# =============================================================================
# CONSTANTS
# =============================================================================

# -----------------------------------------------------------------------------
# NBA Timing Constants
# -----------------------------------------------------------------------------
NBA_REGULATION_REAL_SECONDS = 75 * 60  # ~75 min for 48 min game time
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_OT_GAME_SECONDS = 5 * 60  # 5 min overtime game clock
NBA_OT_REAL_SECONDS = 10 * 60  # ~10 min real time per OT for PBP normalization
NBA_PREGAME_REAL_SECONDS = 10 * 60
NBA_OVERTIME_REAL_SECONDS = 15 * 60  # 5 min game time, ~15 min real time (timeline)
NBA_OVERTIME_PADDING_SECONDS = 30 * 60
DEFAULT_TIMELINE_VERSION = "v1"

# -----------------------------------------------------------------------------
# NCAAB Timing Constants (20-minute halves)
# -----------------------------------------------------------------------------
NCAAB_REGULATION_REAL_SECONDS = 75 * 60
NCAAB_HALFTIME_REAL_SECONDS = 20 * 60
NCAAB_HALF_REAL_SECONDS = NCAAB_REGULATION_REAL_SECONDS // 2
NCAAB_HALF_GAME_SECONDS = 20 * 60
NCAAB_OT_GAME_SECONDS = 5 * 60
NCAAB_OT_REAL_SECONDS = 10 * 60

# -----------------------------------------------------------------------------
# NHL Timing Constants (20-minute periods)
# -----------------------------------------------------------------------------
NHL_REGULATION_REAL_SECONDS = 90 * 60
NHL_INTERMISSION_REAL_SECONDS = 18 * 60
NHL_PERIOD_REAL_SECONDS = NHL_REGULATION_REAL_SECONDS // 3
NHL_PERIOD_GAME_SECONDS = 20 * 60
NHL_OT_GAME_SECONDS = 5 * 60
NHL_OT_REAL_SECONDS = 10 * 60
NHL_PLAYOFF_OT_GAME_SECONDS = 20 * 60

# -----------------------------------------------------------------------------
# Phase 3: League-Aware Timing Constants (Task 3.1)
# These are HEURISTIC estimates for time-based classification only.
# No PBP data is used - imprecision is expected and acceptable.
# -----------------------------------------------------------------------------

# NCAAB: College basketball - two 20-minute halves
NCAAB_REGULATION_REAL_MINUTES = 135  # ~2h15m for 40 min game time
NCAAB_OT_BUFFER_MINUTES = 15  # 5 min OT = ~15 min real time

# NBA: Professional basketball - four 12-minute quarters
NBA_REGULATION_REAL_MINUTES = 165  # ~2h45m for 48 min game time
NBA_OT_BUFFER_MINUTES = 20  # 5 min OT = ~15-20 min real time

# NHL: Hockey - three 20-minute periods
NHL_REGULATION_REAL_MINUTES = 165  # ~2h45m for 60 min game time
NHL_OT_BUFFER_MINUTES = 20  # Sudden death OT = variable

# Postgame window: tweets within 4 hours of game end are postgame
POSTGAME_WINDOW_HOURS = 4

# Social post time windows (configurable)
# These define how far before/after the game we include social posts
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60  # 2 hours before game start
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60  # 2 hours after game end

# -----------------------------------------------------------------------------
# League-specific segment counts for Task 3.2
# -----------------------------------------------------------------------------
LEAGUE_SEGMENTS = {
    "NBA": ["q1", "q2", "halftime", "q3", "q4"],
    "NCAAB": ["first_half", "halftime", "second_half"],
    "NHL": ["p1", "p2", "p3"],
}

# Canonical phase ordering - this is the source of truth for timeline order
# Includes phases for all supported leagues (NBA, NCAAB, NHL)
PHASE_ORDER: dict[str, int] = {
    "pregame": 0,
    # NBA/NCAAB phases
    "q1": 1,
    "first_half": 1,  # NCAAB alias for q1+q2 segment
    "q2": 2,
    "halftime": 3,
    "q3": 4,
    "second_half": 4,  # NCAAB alias for q3+q4 segment
    "q4": 5,
    # NHL phases
    "p1": 1,
    "p2": 3,
    "p3": 5,
    # Overtime phases (all leagues)
    "ot": 6,
    "ot1": 6,
    "ot2": 7,
    "ot3": 8,
    "ot4": 9,
    "shootout": 10,  # NHL shootout
    "postgame": 99,
}


def phase_sort_order(phase: str | None) -> int:
    """Get sort order for a phase. Unknown phases sort after postgame."""
    if phase is None:
        return 100
    return PHASE_ORDER.get(phase, 100)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class TimelineArtifactPayload:
    """Payload for a generated timeline artifact."""

    game_id: int
    sport: str
    timeline_version: str
    generated_at: datetime
    timeline: list[dict[str, Any]]
    summary: dict[str, Any]
    game_analysis: dict[str, Any]


class TimelineGenerationError(Exception):
    """Raised when timeline generation fails."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code
