"""Tests for the canonical game state machine.

Covers transition validation, sport-specific guards, and property-based
tests for all 64 state-pair combinations.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.game_state_machine import (
    VALID_TRANSITIONS,
    GameState,
    InvalidTransitionError,
    SportGuardContext,
    is_active,
    is_final,
    is_live,
    is_pending,
    is_pregame,
    is_scheduled,
    is_terminal,
    validate_transition,
)


class TestGameStateEnum:
    def test_all_eight_states_exist(self) -> None:
        assert len(GameState) == 8

    def test_state_values(self) -> None:
        expected = {
            "scheduled", "pregame", "delayed", "live",
            "suspended", "postponed", "final", "cancelled",
        }
        assert {s.value for s in GameState} == expected

    def test_string_enum(self) -> None:
        assert GameState.LIVE == "live"
        assert isinstance(GameState.LIVE, str)


class TestTransitionAllowList:
    def test_final_is_terminal(self) -> None:
        assert len(VALID_TRANSITIONS[GameState.FINAL]) == 0

    def test_cancelled_is_terminal(self) -> None:
        assert len(VALID_TRANSITIONS[GameState.CANCELLED]) == 0

    def test_every_state_has_entry(self) -> None:
        for state in GameState:
            assert state in VALID_TRANSITIONS

    def test_happy_path(self) -> None:
        path = [
            GameState.SCHEDULED,
            GameState.PREGAME,
            GameState.LIVE,
            GameState.FINAL,
        ]
        for from_s, to_s in zip(path, path[1:]):
            validate_transition(from_s, to_s)

    def test_delayed_recovery(self) -> None:
        validate_transition(GameState.LIVE, GameState.DELAYED)
        validate_transition(GameState.DELAYED, GameState.LIVE)

    def test_suspended_recovery(self) -> None:
        validate_transition(GameState.LIVE, GameState.SUSPENDED)
        validate_transition(GameState.SUSPENDED, GameState.LIVE)

    def test_postponed_reschedule(self) -> None:
        validate_transition(GameState.POSTPONED, GameState.SCHEDULED)


class TestValidateTransition:
    def test_noop_rejected(self) -> None:
        with pytest.raises(InvalidTransitionError, match="no-op"):
            validate_transition(GameState.LIVE, GameState.LIVE)

    def test_final_to_live_rejected(self) -> None:
        with pytest.raises(InvalidTransitionError, match="not in transition allow-list"):
            validate_transition(GameState.FINAL, GameState.LIVE)

    def test_cancelled_to_live_rejected(self) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_transition(GameState.CANCELLED, GameState.LIVE)

    def test_error_attributes(self) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(GameState.FINAL, GameState.LIVE)
        err = exc_info.value
        assert err.from_state == GameState.FINAL
        assert err.to_state == GameState.LIVE

    def test_valid_transition_no_context_succeeds(self) -> None:
        validate_transition(GameState.SCHEDULED, GameState.PREGAME)


class TestAllStatePairCombinations:
    """Property-based: test all 64 state-pair combinations (8×8)."""

    @pytest.mark.parametrize(
        "from_state",
        list(GameState),
        ids=lambda s: s.value,
    )
    @pytest.mark.parametrize(
        "to_state",
        list(GameState),
        ids=lambda s: s.value,
    )
    def test_all_pairs_consistent(self, from_state: GameState, to_state: GameState) -> None:
        allowed = VALID_TRANSITIONS[from_state]
        if from_state == to_state:
            with pytest.raises(InvalidTransitionError):
                validate_transition(from_state, to_state)
        elif to_state in allowed:
            validate_transition(from_state, to_state)
        else:
            with pytest.raises(InvalidTransitionError):
                validate_transition(from_state, to_state)


class TestMLBGuard:
    def _mlb_ctx(self, innings: int | None = None) -> SportGuardContext:
        return SportGuardContext(league_code="MLB", innings_completed=innings)

    def test_mlb_final_requires_5_innings(self) -> None:
        with pytest.raises(InvalidTransitionError, match="minimum 5 required"):
            validate_transition(
                GameState.LIVE, GameState.FINAL,
                context=self._mlb_ctx(innings=4),
            )

    def test_mlb_final_allowed_at_5_innings(self) -> None:
        validate_transition(
            GameState.LIVE, GameState.FINAL,
            context=self._mlb_ctx(innings=5),
        )

    def test_mlb_final_allowed_at_9_innings(self) -> None:
        validate_transition(
            GameState.LIVE, GameState.FINAL,
            context=self._mlb_ctx(innings=9),
        )

    def test_mlb_final_missing_innings_rejected(self) -> None:
        with pytest.raises(InvalidTransitionError, match="missing innings_completed"):
            validate_transition(
                GameState.LIVE, GameState.FINAL,
                context=self._mlb_ctx(innings=None),
            )

    def test_non_mlb_ignores_innings_guard(self) -> None:
        ctx = SportGuardContext(league_code="NBA", innings_completed=0)
        validate_transition(GameState.LIVE, GameState.FINAL, context=ctx)


class TestNFLGuard:
    def test_nfl_live_requires_start_time(self) -> None:
        ctx = SportGuardContext(league_code="NFL", scheduled_start=None)
        with pytest.raises(InvalidTransitionError, match="scheduled start time"):
            validate_transition(GameState.PREGAME, GameState.LIVE, context=ctx)

    def test_nfl_live_with_start_time(self) -> None:
        ctx = SportGuardContext(
            league_code="NFL",
            scheduled_start=datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc),
        )
        validate_transition(GameState.PREGAME, GameState.LIVE, context=ctx)

    def test_non_nfl_ignores_start_time_guard(self) -> None:
        ctx = SportGuardContext(league_code="NBA", scheduled_start=None)
        validate_transition(GameState.PREGAME, GameState.LIVE, context=ctx)


class TestHelperFunctions:
    def test_is_terminal(self) -> None:
        assert is_terminal(GameState.FINAL) is True
        assert is_terminal(GameState.CANCELLED) is True
        assert is_terminal(GameState.LIVE) is False
        assert is_terminal(GameState.POSTPONED) is False

    def test_is_live(self) -> None:
        assert is_live(GameState.LIVE) is True
        assert is_live(GameState.FINAL) is False

    def test_is_final(self) -> None:
        assert is_final(GameState.FINAL) is True
        assert is_final(GameState.LIVE) is False

    def test_is_scheduled(self) -> None:
        assert is_scheduled(GameState.SCHEDULED) is True
        assert is_scheduled(GameState.PREGAME) is False

    def test_is_pregame(self) -> None:
        assert is_pregame(GameState.PREGAME) is True
        assert is_pregame(GameState.SCHEDULED) is False

    def test_is_active(self) -> None:
        assert is_active(GameState.LIVE) is True
        assert is_active(GameState.SUSPENDED) is True
        assert is_active(GameState.DELAYED) is True
        assert is_active(GameState.FINAL) is False
        assert is_active(GameState.SCHEDULED) is False

    def test_is_pending(self) -> None:
        assert is_pending(GameState.SCHEDULED) is True
        assert is_pending(GameState.PREGAME) is True
        assert is_pending(GameState.LIVE) is False
