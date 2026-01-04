"""Integration tests for the compact posts endpoint."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

from fastapi.testclient import TestClient

from api.app.db import get_db
from api.app.routers import sports as sports_router
from api.main import app


class _FakeResult:
    def __init__(
        self,
        posts: list[SimpleNamespace] | None = None,
        scalar_value: int | None = None,
        row: tuple[datetime, datetime] | None = None,
    ) -> None:
        self._posts = posts or []
        self._scalar_value = scalar_value
        self._row = row

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list[SimpleNamespace]:
        return self._posts

    def scalar_one_or_none(self) -> int | None:
        return self._scalar_value

    def one_or_none(self) -> tuple[datetime, datetime] | None:
        return self._row


class _FakeSession:
    def __init__(self, execute_results: list[_FakeResult]) -> None:
        self._execute_results = execute_results

    async def execute(self, statement: object) -> _FakeResult:
        return self._execute_results.pop(0)


class TestCompactPostsEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.moments_response = sports_router.CompactMomentsResponse(
            moments=[
                sports_router.CompactMoment(playIndex=5, quarter=1, gameClock="12:00", momentType="tip"),
                sports_router.CompactMoment(playIndex=10, quarter=1, gameClock="11:30", momentType="shot"),
            ],
            momentTypes=["tip", "shot"],
        )
        sports_router._compact_cache.clear()
        sports_router._store_compact_cache(123, self.moments_response)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        sports_router._compact_cache.clear()

    def test_compact_posts_dedupes_and_scores(self) -> None:
        start_time = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(minutes=2)

        team = SimpleNamespace(abbreviation="CAT")
        posts = [
            SimpleNamespace(
                id=1,
                post_url="https://example.com/1",
                posted_at=start_time + timedelta(seconds=10),
                has_video=False,
                team_id=10,
                tweet_text="Final: Cats 102-99 Dogs",
                video_url=None,
                image_url=None,
                source_handle="@cats",
                media_type=None,
                team=team,
            ),
            SimpleNamespace(
                id=2,
                post_url="https://example.com/2",
                posted_at=start_time + timedelta(seconds=20),
                has_video=False,
                team_id=10,
                tweet_text="Final: Cats 102-99 Dogs",
                video_url=None,
                image_url=None,
                source_handle="@cats",
                media_type=None,
                team=team,
            ),
            SimpleNamespace(
                id=3,
                post_url="https://example.com/3",
                posted_at=start_time + timedelta(seconds=30),
                has_video=True,
                team_id=10,
                tweet_text="What a dunk!",
                video_url="https://example.com/video.mp4",
                image_url=None,
                source_handle="@cats",
                media_type="video",
                team=team,
            ),
        ]
        session = _FakeSession([
            _FakeResult(row=(start_time, end_time)),
            _FakeResult(posts=posts),
        ])

        async def override_get_db() -> AsyncGenerator[_FakeSession, None]:
            yield session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/admin/sports/games/123/compact/5/posts")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["posts"]), 2)
        self.assertEqual(payload["posts"][0]["id"], 1)
        self.assertTrue(payload["posts"][0]["containsScore"])
        self.assertEqual(payload["posts"][1]["id"], 3)
        self.assertFalse(payload["posts"][1]["containsScore"])


if __name__ == "__main__":
    unittest.main()
