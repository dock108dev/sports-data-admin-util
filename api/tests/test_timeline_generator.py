"""Tests for the NBA timeline builder."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from app.services.game_analysis import build_game_analysis
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
        self.assertEqual(timestamps[1], game.start_time + timedelta(minutes=9, seconds=22, milliseconds=500))
        self.assertEqual(timestamps[2], game.start_time + timedelta(minutes=18, seconds=45))
        # NBA_REGULATION_REAL_SECONDS = 75 * 60 = 75 minutes
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
        # 75 min regulation + 15 min OT1 = 90 min
        self.assertEqual(game_end, game.start_time + timedelta(minutes=90))

    def test_build_nba_timeline_orders_social_within_phase(self) -> None:
        """Social events within the same phase are ordered by intra-phase order.
        
        IMPORTANT: This tests intra-phase ordering, NOT global timestamp ordering.
        Backend order is the single source of truth. Clients must NOT re-sort.
        """
        game = self._build_game()
        posts = [
            SimpleNamespace(
                posted_at=game.start_time + timedelta(minutes=4),
                source_handle="@home",
                tweet_text="Late post",
            ),
            SimpleNamespace(
                posted_at=game.start_time + timedelta(minutes=1),
                source_handle="@away",
                tweet_text="Early post",
            ),
        ]

        timeline, _, _ = build_nba_timeline(game, [], posts)

        self.assertEqual(len(timeline), 2)
        # Both posts are in Q1 phase; ordered by posted_at within phase
        self.assertEqual(timeline[0]["text"], "Early post")
        self.assertEqual(timeline[1]["text"], "Late post")
        # Verify phase is assigned
        self.assertEqual(timeline[0]["phase"], "q1")
        self.assertEqual(timeline[1]["phase"], "q1")
        # Role is assigned based on phase (q1 = in-game → reaction)
        self.assertEqual(timeline[0]["role"], "reaction")
        self.assertEqual(
            set(timeline[0].keys()),
            {"event_type", "author", "handle", "text", "role", "phase", "synthetic_timestamp", "intra_phase_order"},
        )

    def test_build_nba_game_analysis_moments(self) -> None:
        """Test that game analysis produces moments.
        
        The Lead Ladder-based moments system partitions the timeline into:
        - LEAD_BUILD: Lead tier increased
        - CUT: Lead tier decreased (opponent cutting in)
        - TIE: Game returned to even
        - FLIP: Leader changed
        - CLOSING_CONTROL: Late-game lock-in
        - HIGH_IMPACT: High-impact events (ejections, etc.)
        - NEUTRAL: Normal flow
        
        Note: OPENER was removed in 2026-01 refactor, replaced by is_period_start flag.
        """
        timeline = [
            {
                "event_type": "pbp",
                "home_score": 2,
                "away_score": 0,
                "quarter": 1,
                "game_clock": "12:00",
                "synthetic_timestamp": "2026-01-15T02:00:00Z",
                "description": "Home scores layup",
            },
            {
                "event_type": "pbp",
                "home_score": 4,
                "away_score": 0,
                "quarter": 1,
                "game_clock": "10:30",
                "synthetic_timestamp": "2026-01-15T02:01:00Z",
                "description": "Home scores layup",
            },
            {
                "event_type": "pbp",
                "home_score": 6,
                "away_score": 0,
                "quarter": 1,
                "game_clock": "9:00",
                "synthetic_timestamp": "2026-01-15T02:02:00Z",
                "description": "Home scores three pointer",
            },
            {
                "event_type": "pbp",
                "home_score": 8,
                "away_score": 0,
                "quarter": 1,
                "game_clock": "8:00",
                "synthetic_timestamp": "2026-01-15T02:03:00Z",
                "description": "Home scores layup",
            },
            {
                "event_type": "pbp",
                "home_score": 10,
                "away_score": 0,
                "quarter": 1,
                "game_clock": "6:00",
                "synthetic_timestamp": "2026-01-15T02:05:00Z",
                "description": "Home scores layup",
            },
            {
                "event_type": "pbp",
                "home_score": 10,
                "away_score": 3,
                "quarter": 1,
                "game_clock": "5:00",
                "synthetic_timestamp": "2026-01-15T02:06:00Z",
                "description": "Away scores three pointer",
            },
            {
                "event_type": "pbp",
                "home_score": 100,
                "away_score": 95,
                "quarter": 4,
                "game_clock": "0:30",
                "synthetic_timestamp": "2026-01-15T03:10:00Z",
                "description": "Home makes free throw",
            },
        ]
        summary = {
            "teams": {"home": {"id": 1, "name": "Home"}, "away": {"id": 2, "name": "Away"}},
            "final_score": {"home": 100, "away": 95},
            "flow": "close",
        }

        analysis = build_game_analysis(timeline, summary)

        moments = analysis["moments"]

        # Should have at least one moment
        self.assertGreaterEqual(len(moments), 1)

        # Check moment structure
        for moment in moments:
            self.assertIn("id", moment)
            self.assertIn("type", moment)
            self.assertIn("start_play", moment)
            self.assertIn("end_play", moment)
            self.assertIn("is_notable", moment)

        # Check that we detected tier crossings - should have LEAD_BUILD or OPENER
        moment_types = {m["type"] for m in moments}
        # New system uses LEAD_BUILD for extending leads, OPENER for period starts
        valid_new_types = {"LEAD_BUILD", "CUT", "TIE", "FLIP", "CLOSING_CONTROL", 
                          "HIGH_IMPACT", "NEUTRAL", "OPENER"}
        self.assertTrue(moment_types.issubset(valid_new_types))


if __name__ == "__main__":
    unittest.main()
