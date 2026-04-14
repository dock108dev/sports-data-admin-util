"""Game status flag derivation.

Pure function: maps status string to convenience booleans so clients
don't need to duplicate status-parsing logic.
"""

from __future__ import annotations

from .game_state_machine import GameState

FINAL_STATUSES = frozenset({"final", "completed", "official"})
LIVE_STATUSES = frozenset({"in_progress", "live", "halftime"})
PREGAME_STATUSES = frozenset({"scheduled", "pregame", "pre_game", "created"})
DELAYED_STATUSES = frozenset({"delayed", "suspended"})

TRULY_COMPLETED_STATUSES = frozenset({"final", "completed"})
READ_ELIGIBLE_STATUSES = FINAL_STATUSES

_RAW_TO_CANONICAL: dict[str, GameState] = {
    "scheduled": GameState.SCHEDULED,
    "pregame": GameState.PREGAME,
    "pre_game": GameState.PREGAME,
    "created": GameState.SCHEDULED,
    "delayed": GameState.DELAYED,
    "live": GameState.LIVE,
    "in_progress": GameState.LIVE,
    "halftime": GameState.LIVE,
    "suspended": GameState.SUSPENDED,
    "postponed": GameState.POSTPONED,
    "final": GameState.FINAL,
    "completed": GameState.FINAL,
    "official": GameState.FINAL,
    "cancelled": GameState.CANCELLED,
    "canceled": GameState.CANCELLED,
    "archived": GameState.FINAL,
}


def normalize_to_canonical(raw_status: str | None) -> GameState | None:
    """Map a raw status string from any data source to the canonical GameState."""
    if not raw_status:
        return None
    return _RAW_TO_CANONICAL.get(raw_status.lower().strip())


def compute_status_flags(status: str | None) -> dict[str, bool]:
    """Derive convenience boolean flags from a game status string.

    Args:
        status: Raw status string from the games table (e.g., "final", "live").

    Returns:
        Dict with keys: is_live, is_final, is_pregame, is_truly_completed,
        read_eligible. All False when status is None.
    """
    if not status:
        return {
            "is_live": False,
            "is_final": False,
            "is_pregame": False,
            "is_delayed": False,
            "is_truly_completed": False,
            "read_eligible": False,
        }

    s = status.lower().strip()
    return {
        "is_live": s in LIVE_STATUSES,
        "is_final": s in FINAL_STATUSES,
        "is_pregame": s in PREGAME_STATUSES,
        "is_delayed": s in DELAYED_STATUSES,
        "is_truly_completed": s in TRULY_COMPLETED_STATUSES,
        "read_eligible": s in READ_ELIGIBLE_STATUSES,
    }
