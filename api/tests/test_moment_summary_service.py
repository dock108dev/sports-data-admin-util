"""Tests for moment summary service."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from api.app.services import moment_summaries


class _FakeResult:
    def __init__(self, scalar_value=None, scalars_value=None) -> None:
        self._scalar_value = scalar_value
        self._scalars_value = scalars_value or []

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalars(self):
        return self

    def all(self):
        return self._scalars_value


class _FakeSession:
    def __init__(self, results) -> None:
        self._results = list(results)

    async def execute(self, statement):
        return self._results.pop(0)


class _ErrorSession:
    async def execute(self, statement):
        raise RuntimeError("db error")


class TestMomentSummaryService(unittest.TestCase):
    def tearDown(self) -> None:
        moment_summaries._clear_summary_cache()

    def test_summary_cached_and_reused(self) -> None:
        play = SimpleNamespace(
            id=10,
            game_id=1,
            play_index=5,
            play_type="shot",
            description="Drive to the rim for a strong finish.",
            raw_data={"team_abbreviation": "BOS"},
        )
        session = _FakeSession(
            [
                _FakeResult(scalar_value=play),
                _FakeResult(scalar_value=6),
                _FakeResult(scalars_value=[play]),
            ]
        )

        summary = asyncio.run(moment_summaries.summarize_moment(1, 5, session))
        self.assertTrue(summary)

        cached_summary = asyncio.run(moment_summaries.summarize_moment(1, 5, _FakeSession([])))
        self.assertEqual(summary, cached_summary)

    def test_fallback_when_no_plays(self) -> None:
        play = SimpleNamespace(
            id=20,
            game_id=2,
            play_index=9,
            play_type="timeout",
            description=None,
            raw_data={},
        )
        session = _FakeSession(
            [
                _FakeResult(scalar_value=play),
                _FakeResult(scalar_value=None),
                _FakeResult(scalars_value=[]),
            ]
        )

        summary = asyncio.run(moment_summaries.summarize_moment(2, 9, session))
        self.assertEqual(
            summary,
            "Moment recap unavailable.",
        )

    def test_fallback_when_session_errors(self) -> None:
        summary = asyncio.run(moment_summaries.summarize_moment(3, 12, _ErrorSession()))
        self.assertEqual(summary, "Moment recap unavailable.")


if __name__ == "__main__":
    unittest.main()
