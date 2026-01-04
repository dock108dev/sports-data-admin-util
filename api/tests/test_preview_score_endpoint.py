"""Integration tests for the preview score endpoint."""

from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from typing import AsyncGenerator

from fastapi.testclient import TestClient

from app.db import get_db
from api.main import app


class _FakeResult:
    def __init__(self, game: SimpleNamespace | None = None) -> None:
        self._game = game

    def scalar_one_or_none(self) -> SimpleNamespace | None:
        return self._game


class _FakeSession:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result

    async def execute(self, statement: object) -> _FakeResult:
        return self._result


class TestPreviewScoreEndpoint(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_preview_score_returns_tags_and_scores(self) -> None:
        game = SimpleNamespace(
            id=123,
            game_date=datetime(2024, 1, 1),
            league=SimpleNamespace(code="NCAAB"),
            home_team=SimpleNamespace(
                id=1,
                name="Alpha",
                external_ref="team-001",
                external_codes={},
            ),
            away_team=SimpleNamespace(
                id=2,
                name="Beta",
                external_ref="team-002",
                external_codes={},
            ),
        )
        session = _FakeSession(_FakeResult(game=game))

        async def override_get_db() -> AsyncGenerator[_FakeSession, None]:
            yield session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/admin/sports/games/123/preview-score")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["game_id"], "123")
        self.assertIn("conference_lead", payload["tags"])
        self.assertIn("top25_matchup", payload["tags"])
        self.assertIsInstance(payload["excitement_score"], int)
        self.assertIsInstance(payload["quality_score"], int)
        self.assertGreaterEqual(payload["excitement_score"], 0)
        self.assertLessEqual(payload["excitement_score"], 100)
        self.assertGreaterEqual(payload["quality_score"], 0)
        self.assertLessEqual(payload["quality_score"], 100)
        self.assertTrue(payload["nugget"])


if __name__ == "__main__":
    unittest.main()
