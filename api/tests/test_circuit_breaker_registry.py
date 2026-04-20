"""Tests for services/circuit_breaker_registry.py."""

from __future__ import annotations

import queue
from datetime import UTC, datetime

import pytest

from app.services.circuit_breaker_registry import (
    BreakerState,
    CircuitBreakerRegistry,
)


@pytest.fixture()
def reg() -> CircuitBreakerRegistry:
    return CircuitBreakerRegistry()


class TestRegister:
    def test_creates_entry(self, reg: CircuitBreakerRegistry) -> None:
        reg.register("test_breaker")
        state = reg.get("test_breaker")
        assert state is not None
        assert state.name == "test_breaker"
        assert state.is_open is False
        assert state.trip_count == 0

    def test_idempotent(self, reg: CircuitBreakerRegistry) -> None:
        reg.register("b")
        reg.register("b")
        assert len(reg.get_all()) == 1


class TestRecordTrip:
    def test_increments_count(self, reg: CircuitBreakerRegistry) -> None:
        reg.register("b")
        reg.record_trip("b", "redis connection refused")
        state = reg.get("b")
        assert state is not None
        assert state.trip_count == 1
        assert state.is_open is True
        assert state.last_trip_reason == "redis connection refused"
        assert state.last_trip_at is not None

    def test_multiple_trips(self, reg: CircuitBreakerRegistry) -> None:
        reg.register("b")
        reg.record_trip("b", "err1")
        reg.record_trip("b", "err2")
        state = reg.get("b")
        assert state is not None
        assert state.trip_count == 2
        assert state.last_trip_reason == "err2"

    def test_auto_registers_unknown_breaker(self, reg: CircuitBreakerRegistry) -> None:
        reg.record_trip("unknown", "oops")
        state = reg.get("unknown")
        assert state is not None
        assert state.trip_count == 1

    def test_enqueues_pending_event(self, reg: CircuitBreakerRegistry) -> None:
        reg.record_trip("b", "reason")
        events = reg.drain_pending()
        assert len(events) == 1
        assert events[0].breaker_name == "b"
        assert events[0].reason == "reason"

    def test_drain_clears_queue(self, reg: CircuitBreakerRegistry) -> None:
        reg.record_trip("b", "r1")
        reg.record_trip("b", "r2")
        first = reg.drain_pending()
        assert len(first) == 2
        second = reg.drain_pending()
        assert len(second) == 0


class TestRecordReset:
    def test_marks_closed(self, reg: CircuitBreakerRegistry) -> None:
        reg.register("b")
        reg.record_trip("b", "err")
        reg.record_reset("b")
        state = reg.get("b")
        assert state is not None
        assert state.is_open is False
        assert state.last_reset_at is not None

    def test_does_not_change_trip_count(self, reg: CircuitBreakerRegistry) -> None:
        reg.register("b")
        reg.record_trip("b", "err")
        reg.record_reset("b")
        state = reg.get("b")
        assert state is not None
        assert state.trip_count == 1

    def test_auto_registers_unknown_breaker(self, reg: CircuitBreakerRegistry) -> None:
        reg.record_reset("never_tripped")
        state = reg.get("never_tripped")
        assert state is not None
        assert state.is_open is False


class TestGetAll:
    def test_returns_all(self, reg: CircuitBreakerRegistry) -> None:
        reg.register("a")
        reg.register("b")
        names = {s.name for s in reg.get_all()}
        assert names == {"a", "b"}
