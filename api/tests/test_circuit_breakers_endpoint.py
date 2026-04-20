"""Tests for GET /api/admin/circuit-breakers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.admin.circuit_breakers import (
    CircuitBreakersResponse,
    get_circuit_breakers,
)
from app.services.circuit_breaker_registry import BreakerState, CircuitBreakerRegistry


def _make_registry(*breakers: BreakerState) -> CircuitBreakerRegistry:
    reg = CircuitBreakerRegistry()
    for b in breakers:
        reg._breakers[b.name] = b
    return reg


def _make_db_result(events: list[dict]) -> MagicMock:
    rows = []
    for i, ev in enumerate(events):
        row = MagicMock()
        row.id = i + 1
        row.breaker_name = ev["breaker_name"]
        row.reason = ev["reason"]
        row.tripped_at = ev["tripped_at"]
        rows.append(row)
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    return result_mock


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestGetCircuitBreakers:
    def test_returns_empty_when_nothing_registered(self):
        reg = CircuitBreakerRegistry()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result([]))

        with patch("app.routers.admin.circuit_breakers.registry", reg):
            resp = _run(get_circuit_breakers(db=db))

        assert isinstance(resp, CircuitBreakersResponse)
        assert resp.breakers == []
        assert resp.recent_trips == []

    def test_reflects_in_memory_breaker_state(self):
        now = datetime.now(UTC)
        state = BreakerState(
            name="live_odds_redis",
            is_open=True,
            trip_count=3,
            last_trip_reason="redis connection refused",
            last_trip_at=now,
        )
        reg = _make_registry(state)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result([]))

        with patch("app.routers.admin.circuit_breakers.registry", reg):
            resp = _run(get_circuit_breakers(db=db))

        assert len(resp.breakers) == 1
        b = resp.breakers[0]
        assert b.name == "live_odds_redis"
        assert b.is_open is True
        assert b.trip_count == 3
        assert b.last_trip_reason == "redis connection refused"

    def test_includes_persisted_trip_history(self):
        reg = CircuitBreakerRegistry()
        now = datetime.now(UTC)
        events = [
            {"breaker_name": "fairbet_redis", "reason": "timeout", "tripped_at": now}
        ]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result(events))

        with patch("app.routers.admin.circuit_breakers.registry", reg):
            resp = _run(get_circuit_breakers(db=db))

        assert len(resp.recent_trips) == 1
        t = resp.recent_trips[0]
        assert t.breaker_name == "fairbet_redis"
        assert t.reason == "timeout"
        assert t.tripped_at == now

    def test_closed_breaker_shows_correctly(self):
        state = BreakerState(
            name="fairbet_redis",
            is_open=False,
            trip_count=1,
            last_trip_reason="old error",
        )
        reg = _make_registry(state)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result([]))

        with patch("app.routers.admin.circuit_breakers.registry", reg):
            resp = _run(get_circuit_breakers(db=db))

        assert resp.breakers[0].is_open is False
        assert resp.breakers[0].trip_count == 1

    def test_multiple_breakers_returned(self):
        reg = _make_registry(
            BreakerState(name="live_odds_redis", is_open=False, trip_count=0),
            BreakerState(name="fairbet_redis", is_open=True, trip_count=2),
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result([]))

        with patch("app.routers.admin.circuit_breakers.registry", reg):
            resp = _run(get_circuit_breakers(db=db))

        names = {b.name for b in resp.breakers}
        assert names == {"live_odds_redis", "fairbet_redis"}
