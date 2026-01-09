"""Tests for game snapshot endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator
import unittest

from fastapi.testclient import TestClient

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from app.db import get_db
from api.main import app


class _FakeScalarResult:
    def __init__(self, items: list[SimpleNamespace]) -> None:
        self._items = items

    def all(self) -> list[SimpleNamespace]:
        return self._items


class _FakeResult:
    def __init__(
        self,
        rows: list[tuple] | None = None,
        scalars: list[SimpleNamespace] | None = None,
    ) -> None:
        self._rows = rows or []
        self._scalars = scalars or []

    def all(self) -> list[tuple]:
        return self._rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._scalars)


class _FakeSession:
    def __init__(
        self,
        execute_results: list[_FakeResult],
        get_result: SimpleNamespace | None,
    ) -> None:
        self._execute_results = execute_results
        self._get_result = get_result

    async def execute(self, statement: object) -> _FakeResult:
        return self._execute_results.pop(0)

    async def get(self, model: object, game_id: int) -> SimpleNamespace | None:
        return self._get_result


class TestGameSnapshotEndpoints(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def _override_db(self, session: _FakeSession) -> None:
        async def override_get_db() -> AsyncGenerator[_FakeSession, None]:
            yield session

        app.dependency_overrides[get_db] = override_get_db

    def _build_game(self, status: str = "scheduled") -> SimpleNamespace:
        league = SimpleNamespace(code="NBA")
        home_team = SimpleNamespace(id=1, name="Home", abbreviation="HME")
        away_team = SimpleNamespace(id=2, name="Away", abbreviation="AWY")
        now = datetime(2026, 1, 15, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=123,
            league=league,
            status=status,
            game_date=now,
            home_team=home_team,
            away_team=away_team,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            updated_at=now,
            last_scraped_at=None,
            last_ingested_at=None,
            last_pbp_at=None,
            last_social_at=None,
            home_score=100,
            away_score=98,
        )

    def test_list_games_last2_returns_games(self) -> None:
        game = self._build_game()
        session = _FakeSession(
            execute_results=[_FakeResult(rows=[(game, True, False, False)])],
            get_result=None,
        )
        self._override_db(session)
        client = TestClient(app)

        response = client.get("/games?range=last2")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["range"], "last2")
        self.assertEqual(payload["games"][0]["id"], 123)
        self.assertTrue(payload["games"][0]["has_pbp"])

    def test_list_games_current_live_game(self) -> None:
        game = self._build_game(status="live")
        session = _FakeSession(
            execute_results=[_FakeResult(rows=[(game, False, True, False)])],
            get_result=None,
        )
        self._override_db(session)
        client = TestClient(app)

        response = client.get("/games?range=current")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["games"][0]["status"], "live")
        self.assertTrue(payload["games"][0]["has_social"])

    def test_invalid_range_returns_400(self) -> None:
        session = _FakeSession(execute_results=[], get_result=None)
        self._override_db(session)
        client = TestClient(app)

        response = client.get("/games?range=bad")
        self.assertEqual(response.status_code, 400)

    def test_pbp_empty_returns_empty_periods(self) -> None:
        game = self._build_game()
        session = _FakeSession(
            execute_results=[_FakeResult(scalars=[])],
            get_result=game,
        )
        self._override_db(session)
        client = TestClient(app)

        response = client.get("/games/123/pbp")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["periods"], [])

    def test_social_only_game_returns_posts(self) -> None:
        game = self._build_game()
        post = SimpleNamespace(
            id=9,
            team=game.home_team,
            team_id=game.home_team.id,
            tweet_text="Starting lineup announced",
            posted_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            reveal_risk=False,
        )
        session = _FakeSession(
            execute_results=[_FakeResult(scalars=[post])],
            get_result=game,
        )
        self._override_db(session)
        client = TestClient(app)

        response = client.get("/games/123/social")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["posts"][0]["reveal_level"], "pre")

    def test_invalid_reveal_returns_400(self) -> None:
        game = self._build_game()
        session = _FakeSession(
            execute_results=[_FakeResult(scalars=[]), _FakeResult(scalars=[])],
            get_result=game,
        )
        self._override_db(session)
        client = TestClient(app)

        response = client.get("/games/123/recap?reveal=bad")
        self.assertEqual(response.status_code, 400)

    def test_unknown_game_returns_404(self) -> None:
        session = _FakeSession(
            execute_results=[],
            get_result=None,
        )
        self._override_db(session)
        client = TestClient(app)

        response = client.get("/games/404/pbp")
        self.assertEqual(response.status_code, 404)
