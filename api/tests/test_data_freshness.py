"""Tests for data_freshness staleness computation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.data_freshness import (
    StalenessState,
    compute_staleness_state,
    get_data_updated_at,
    get_source_delay_seconds,
)


class TestComputeStalenessState:
    """Test staleness state computation for different game statuses and ages."""

    def test_final_game_always_fresh(self) -> None:
        old_ts = datetime.now(timezone.utc) - timedelta(hours=24)
        assert compute_staleness_state("final", old_ts) == StalenessState.FRESH

    def test_completed_game_always_fresh(self) -> None:
        old_ts = datetime.now(timezone.utc) - timedelta(hours=24)
        assert compute_staleness_state("completed", old_ts) == StalenessState.FRESH

    def test_official_game_always_fresh(self) -> None:
        old_ts = datetime.now(timezone.utc) - timedelta(days=7)
        assert compute_staleness_state("official", old_ts) == StalenessState.FRESH

    def test_live_game_fresh_under_60s(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(seconds=30)
        assert compute_staleness_state("live", ts) == StalenessState.FRESH

    def test_live_game_stale_at_90s(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(seconds=90)
        assert compute_staleness_state("live", ts) == StalenessState.STALE

    def test_live_game_very_stale_at_6min(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=6)
        assert compute_staleness_state("live", ts) == StalenessState.VERY_STALE

    def test_in_progress_treated_as_live(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(seconds=90)
        assert compute_staleness_state("in_progress", ts) == StalenessState.STALE

    def test_halftime_treated_as_live(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(seconds=90)
        assert compute_staleness_state("halftime", ts) == StalenessState.STALE

    def test_pregame_fresh_under_10min(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert compute_staleness_state("pregame", ts) == StalenessState.FRESH

    def test_pregame_stale_at_15min(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert compute_staleness_state("pregame", ts) == StalenessState.STALE

    def test_pregame_very_stale_at_45min(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=45)
        assert compute_staleness_state("pregame", ts) == StalenessState.VERY_STALE

    def test_scheduled_uses_pregame_thresholds(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert compute_staleness_state("scheduled", ts) == StalenessState.STALE

    def test_none_status_uses_pregame_thresholds(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert compute_staleness_state(None, ts) == StalenessState.STALE

    def test_none_timestamp_is_very_stale(self) -> None:
        assert compute_staleness_state("live", None) == StalenessState.VERY_STALE

    def test_none_timestamp_for_final_is_fresh(self) -> None:
        assert compute_staleness_state("final", None) == StalenessState.FRESH

    def test_explicit_now_parameter(self) -> None:
        updated = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
        assert compute_staleness_state("live", updated, now=now) == StalenessState.FRESH

    def test_naive_timestamps_treated_as_utc(self) -> None:
        updated = datetime(2026, 1, 1, 12, 0, 0)
        now = datetime(2026, 1, 1, 12, 2, 0)
        assert compute_staleness_state("live", updated, now=now) == StalenessState.STALE

    def test_delayed_status_uses_pregame_thresholds(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert compute_staleness_state("delayed", ts) == StalenessState.STALE

    def test_suspended_status_uses_pregame_thresholds(self) -> None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert compute_staleness_state("suspended", ts) == StalenessState.STALE


class TestGetDataUpdatedAt:
    """Test data_updated_at derivation from available timestamps."""

    def test_both_timestamps_returns_latest(self) -> None:
        older = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        newer = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        assert get_data_updated_at(older, newer) == newer
        assert get_data_updated_at(newer, older) == newer

    def test_only_ingested(self) -> None:
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert get_data_updated_at(ts, None) == ts

    def test_only_scraped(self) -> None:
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert get_data_updated_at(None, ts) == ts

    def test_neither_returns_none(self) -> None:
        assert get_data_updated_at(None, None) is None


class TestGetSourceDelaySeconds:
    """Test source delay default."""

    def test_returns_positive_int(self) -> None:
        delay = get_source_delay_seconds()
        assert isinstance(delay, int)
        assert delay >= 0

    def test_default_is_15(self) -> None:
        assert get_source_delay_seconds() == 15


class TestStalenessStateEnum:
    """Test enum values match the API contract."""

    def test_values(self) -> None:
        assert StalenessState.FRESH.value == "fresh"
        assert StalenessState.STALE.value == "stale"
        assert StalenessState.VERY_STALE.value == "very_stale"

    @pytest.mark.parametrize("state", list(StalenessState))
    def test_all_states_are_strings(self, state: StalenessState) -> None:
        assert isinstance(state.value, str)
