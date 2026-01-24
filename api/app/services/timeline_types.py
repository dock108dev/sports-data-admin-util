"""Timeline artifact types, constants, and exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# =============================================================================
# CONSTANTS
# =============================================================================

NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_PREGAME_REAL_SECONDS = 10 * 60
NBA_OVERTIME_PADDING_SECONDS = 30 * 60
DEFAULT_TIMELINE_VERSION = "v1"

# Social post time windows (configurable)
# These define how far before/after the game we include social posts
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60  # 2 hours before game start
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60  # 2 hours after game end

# Canonical phase ordering - this is the source of truth for timeline order
PHASE_ORDER: dict[str, int] = {
    "pregame": 0,
    "q1": 1,
    "q2": 2,
    "halftime": 3,
    "q3": 4,
    "q4": 5,
    "ot1": 6,
    "ot2": 7,
    "ot3": 8,
    "ot4": 9,
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
