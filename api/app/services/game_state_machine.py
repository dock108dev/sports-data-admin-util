"""Canonical game state machine with transition guards.

Defines the 8 canonical game states, valid transitions between them,
and sport-specific guard hooks that enforce business rules before
allowing a transition.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any


class GameState(str, Enum):
    """Canonical game lifecycle states."""

    SCHEDULED = "scheduled"
    PREGAME = "pregame"
    DELAYED = "delayed"
    LIVE = "live"
    SUSPENDED = "suspended"
    POSTPONED = "postponed"
    FINAL = "final"
    CANCELLED = "cancelled"


VALID_TRANSITIONS: dict[GameState, frozenset[GameState]] = {
    GameState.SCHEDULED: frozenset({
        GameState.PREGAME,
        GameState.DELAYED,
        GameState.POSTPONED,
        GameState.CANCELLED,
    }),
    GameState.PREGAME: frozenset({
        GameState.LIVE,
        GameState.DELAYED,
        GameState.POSTPONED,
        GameState.CANCELLED,
    }),
    GameState.DELAYED: frozenset({
        GameState.PREGAME,
        GameState.LIVE,
        GameState.POSTPONED,
        GameState.CANCELLED,
    }),
    GameState.LIVE: frozenset({
        GameState.SUSPENDED,
        GameState.DELAYED,
        GameState.FINAL,
    }),
    GameState.SUSPENDED: frozenset({
        GameState.LIVE,
        GameState.POSTPONED,
        GameState.FINAL,
        GameState.CANCELLED,
    }),
    GameState.POSTPONED: frozenset({
        GameState.SCHEDULED,
        GameState.CANCELLED,
    }),
    GameState.FINAL: frozenset(),
    GameState.CANCELLED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a state transition violates the allow-list or a guard."""

    def __init__(self, from_state: GameState, to_state: GameState, reason: str | None = None) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        detail = f"Invalid transition: {from_state.value} → {to_state.value}"
        if reason:
            detail += f" ({reason})"
        super().__init__(detail)


class SportGuardContext:
    """Context passed to sport-specific guards for transition validation."""

    def __init__(
        self,
        *,
        league_code: str,
        innings_completed: int | None = None,
        scheduled_start: datetime | None = None,
        game_clock: str | None = None,
        current_period: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.league_code = league_code.upper()
        self.innings_completed = innings_completed
        self.scheduled_start = scheduled_start
        self.game_clock = game_clock
        self.current_period = current_period
        self.extra = extra or {}


def _mlb_final_guard(ctx: SportGuardContext) -> str | None:
    """MLB: game cannot be FINAL before 5 complete innings (regulation minimum)."""
    if ctx.league_code != "MLB":
        return None
    if ctx.innings_completed is None:
        return "MLB game missing innings_completed; cannot verify regulation minimum"
    if ctx.innings_completed < 5:
        return f"MLB game has only {ctx.innings_completed} innings completed; minimum 5 required for official result"
    return None


def _nfl_live_guard(ctx: SportGuardContext) -> str | None:
    """NFL: game cannot go LIVE without a scheduled start time."""
    if ctx.league_code != "NFL":
        return None
    if ctx.scheduled_start is None:
        return "NFL game cannot go LIVE without a scheduled start time"
    return None


_SPORT_GUARDS: dict[GameState, list] = {
    GameState.FINAL: [_mlb_final_guard],
    GameState.LIVE: [_nfl_live_guard],
}


def validate_transition(
    from_state: GameState,
    to_state: GameState,
    context: SportGuardContext | None = None,
) -> None:
    """Validate that a state transition is allowed.

    Raises InvalidTransitionError if the transition is not in the allow-list
    or if any sport-specific guard rejects it.
    """
    if from_state == to_state:
        raise InvalidTransitionError(from_state, to_state, "no-op transition")

    allowed = VALID_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        raise InvalidTransitionError(from_state, to_state, "not in transition allow-list")

    if context is not None:
        for guard in _SPORT_GUARDS.get(to_state, []):
            reason = guard(context)
            if reason is not None:
                raise InvalidTransitionError(from_state, to_state, reason)


def is_terminal(state: GameState) -> bool:
    return len(VALID_TRANSITIONS.get(state, frozenset())) == 0


def is_live(state: GameState) -> bool:
    return state == GameState.LIVE


def is_final(state: GameState) -> bool:
    return state == GameState.FINAL


def is_scheduled(state: GameState) -> bool:
    return state == GameState.SCHEDULED


def is_pregame(state: GameState) -> bool:
    return state == GameState.PREGAME


def is_active(state: GameState) -> bool:
    """True for states where the game is in progress or about to be."""
    return state in (GameState.LIVE, GameState.SUSPENDED, GameState.DELAYED)


def is_pending(state: GameState) -> bool:
    """True for states before the game starts."""
    return state in (GameState.SCHEDULED, GameState.PREGAME)
