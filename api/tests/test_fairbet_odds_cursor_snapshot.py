"""Focused tests for cursor/snapshot guardrails in FairBet odds endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers.fairbet import odds as odds_router


class _Result:
    def __init__(self, scalar_value=None):
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value


def _base_kwargs(session: AsyncMock) -> dict:
    return {
        "request": None,
        "session": session,
        "league": None,
        "market_category": None,
        "exclude_categories": None,
        "game_id": None,
        "book": None,
        "player_name": None,
        "min_ev": None,
        "has_fair": None,
        "sort_by": "game_time",
        "limit": 100,
        "offset": 0,
        "cursor": None,
        "snapshot_id": None,
        "include_meta": False,
    }


@pytest.mark.asyncio
async def test_ev_snapshot_missing_returns_410(monkeypatch):
    session = AsyncMock()
    session.execute.return_value = _Result(None)  # max(updated_at)
    monkeypatch.setattr(odds_router, "get_snapshot", lambda _: None)

    with pytest.raises(HTTPException) as exc:
        kwargs = _base_kwargs(session)
        kwargs["sort_by"] = "ev"
        kwargs["snapshot_id"] = "dead-snapshot"
        await odds_router.get_fairbet_odds(**kwargs)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_cursor_sort_mismatch_returns_400():
    session = AsyncMock()
    session.execute.return_value = _Result(None)  # max(updated_at)
    bad_cursor = odds_router.encode_cursor({"sort": "market", "v": ["spreads", "team:a", "2026-01-01T00:00:00+00:00", 1, -3.5]})

    with pytest.raises(HTTPException) as exc:
        kwargs = _base_kwargs(session)
        kwargs["sort_by"] = "game_time"
        kwargs["cursor"] = bad_cursor
        await odds_router.get_fairbet_odds(**kwargs)
    assert exc.value.status_code == 400
