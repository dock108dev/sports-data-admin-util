"""Tests for the NBA timeline builder."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from app.services.timeline_generator import build_nba_timeline


class TestTimelineGenerator(unittest.TestCase):
    def _build_game(self) -> SimpleNamespace:
        start_time = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=123,
            start_time=start_time,
            home_team_id=1,
            away_team_id=2,
            home_team=SimpleNamespace(name="Home"),
            away_team=SimpleNamespace(name="Away"),
            home_score=100,
            away_score=98,
        )

    def test_build_nba_timeline_uses_game_clock_for_synthetic_time(self) -> None:
        game = self._build_game()
        plays = [
            SimpleNamespace(
                play_index=1,
                quarter=1,
                game_clock="12:00",
                play_type="tip",
                team_id=None,
                player_id=None,
                player_name=None,
                description="Tipoff",
                home_score=0,
                away_score=0,
            ),
            SimpleNamespace(
                play_index=2,
                quarter=1,
                game_clock="6:00",
                play_type="shot",
                team_id=1,
                player_id="99",
                player_name="Player",
                description="Mid-range jumper",
                home_score=2,
                away_score=0,
            ),
            SimpleNamespace(
                play_index=3,
                quarter=1,
                game_clock="0:00",
                play_type="end",
                team_id=None,
                player_id=None,
                player_name=None,
                description="End of quarter",
                home_score=25,
                away_score=22,
            ),
        ]

        timeline, summary, game_end = build_nba_timeline(game, plays, [])

        self.assertEqual(summary["flow"], "close")
        self.assertEqual(len(timeline), 3)

        timestamps = [datetime.fromisoformat(event["synthetic_timestamp"]) for event in timeline]
        self.assertEqual(timestamps[0], game.start_time)
        self.assertEqual(timestamps[1], game.start_time + timedelta(minutes=7, seconds=30))
        self.assertEqual(timestamps[2], game.start_time + timedelta(minutes=15))
        self.assertEqual(game_end, game.start_time + timedelta(minutes=75))

    def test_build_nba_timeline_extends_for_overtime(self) -> None:
        game = self._build_game()
        plays = [
            SimpleNamespace(
                play_index=1,
                quarter=5,
                game_clock="5:00",
                play_type="tip",
                team_id=None,
                player_id=None,
                player_name=None,
                description="Overtime tip",
                home_score=100,
                away_score=100,
            )
        ]

        _, _, game_end = build_nba_timeline(game, plays, [])
        self.assertEqual(game_end, game.start_time + timedelta(minutes=105))


if __name__ == "__main__":
    unittest.main()
