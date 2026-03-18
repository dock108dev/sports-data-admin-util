"""Tests for ProfileMixin, MLBPitchDatasetBuilder, and MLBBattedBallDatasetBuilder.

Covers the profile-loading mixin (static methods) and dataset builder
extraction logic without requiring a real database.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analytics.datasets._profile_mixin import ProfileMixin


# ---------------------------------------------------------------------------
# Helper: create mock stats objects that stats_to_metrics() can handle
# ---------------------------------------------------------------------------

def _make_advanced_stats(**overrides):
    """Create a mock MLBPlayerAdvancedStats-like object.

    Must match the attributes accessed by stats_to_metrics().
    """
    defaults = {
        "total_pitches": 20,
        "balls_in_play": 8,
        "hard_hit_count": 3,
        "barrel_count": 1,
        "zone_pitches": 10,
        "zone_swings": 6,
        "zone_contact": 5,
        "outside_pitches": 10,
        "outside_swings": 4,
        "outside_contact": 2,
        # Percentage columns
        "z_swing_pct": 0.60,
        "o_swing_pct": 0.30,
        "z_contact_pct": 0.85,
        "o_contact_pct": 0.60,
        "avg_exit_velo": 88.0,
        "hard_hit_pct": 0.35,
        "barrel_pct": 0.06,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_pitcher_stats(**overrides):
    """Create a mock MLBPitcherGameStats-like object."""
    defaults = {
        "batters_faced": 25,
        "innings_pitched": 6.0,
        "strikeouts": 6,
        "walks": 2,
        "home_runs_allowed": 1,
        "hits": 5,
        "earned_runs": 3,
        "pitches_thrown": 90,
        "zone_swings": 30,
        "zone_contact": 25,
        "outside_swings": 15,
        "outside_contact": 8,
        "outside_pitches": 40,
        "balls_in_play": 12,
        "total_exit_velo_against": 1050.0,
        "hard_hit_against": 4,
        "barrel_against": 1,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# ProfileMixin._build_player_profile tests
# ---------------------------------------------------------------------------


class TestBuildPlayerProfile:
    """Test the static _build_player_profile method."""

    def test_returns_none_when_insufficient_games(self):
        history = {
            "player1": [
                ("2025-06-01", _make_advanced_stats()),
                ("2025-06-02", _make_advanced_stats()),
            ]
        }
        result = ProfileMixin._build_player_profile(
            "player1", history, "2025-07-01", window=30, min_games=5,
        )
        assert result is None

    def test_returns_none_for_unknown_player(self):
        result = ProfileMixin._build_player_profile(
            "unknown", {}, "2025-07-01", window=30, min_games=1,
        )
        assert result is None

    def test_filters_by_date(self):
        history = {
            "p1": [
                ("2025-06-01", _make_advanced_stats(total_pitches=10)),
                ("2025-06-02", _make_advanced_stats(total_pitches=20)),
                ("2025-07-15", _make_advanced_stats(total_pitches=100)),
            ]
        }
        result = ProfileMixin._build_player_profile(
            "p1", history, "2025-07-01", window=30, min_games=1,
        )
        assert result is not None
        # Should only use games before 2025-07-01, not the July 15th game

    def test_applies_rolling_window(self):
        history = {
            "p1": [
                (f"2025-06-{i:02d}", _make_advanced_stats(total_pitches=i * 10))
                for i in range(1, 20)
            ]
        }
        result = ProfileMixin._build_player_profile(
            "p1", history, "2025-07-01", window=5, min_games=1,
        )
        assert result is not None

    def test_aggregates_metrics(self):
        s1 = _make_advanced_stats(total_pitches=10, balls_in_play=5)
        s2 = _make_advanced_stats(total_pitches=20, balls_in_play=10)
        history = {
            "p1": [
                ("2025-06-01", s1),
                ("2025-06-02", s2),
            ]
        }
        result = ProfileMixin._build_player_profile(
            "p1", history, "2025-07-01", window=30, min_games=1,
        )
        assert result is not None
        assert isinstance(result, dict)
        # Values should be averages
        for key in result:
            assert isinstance(result[key], float)


# ---------------------------------------------------------------------------
# ProfileMixin._build_pitcher_profile tests
# ---------------------------------------------------------------------------


class TestBuildPitcherProfile:
    """Test the static _build_pitcher_profile method."""

    def test_returns_none_when_insufficient_games(self):
        history = {
            "pitcher1": [("2025-06-01", _make_pitcher_stats())]
        }
        result = ProfileMixin._build_pitcher_profile(
            "pitcher1", history, "2025-07-01", window=30, min_games=3,
        )
        assert result is None

    def test_returns_none_for_unknown_pitcher(self):
        result = ProfileMixin._build_pitcher_profile(
            "unknown", {}, "2025-07-01", window=30, min_games=1,
        )
        assert result is None

    def test_builds_profile_with_sufficient_data(self):
        history = {
            "p1": [
                ("2025-06-01", _make_pitcher_stats()),
                ("2025-06-05", _make_pitcher_stats()),
                ("2025-06-10", _make_pitcher_stats()),
            ]
        }
        result = ProfileMixin._build_pitcher_profile(
            "p1", history, "2025-07-01", window=30, min_games=3,
        )
        assert result is not None
        # Should have pitcher-specific keys
        assert "k_rate" in result
        assert "bb_rate" in result
        assert "era" in result

    def test_filters_by_date(self):
        history = {
            "p1": [
                ("2025-06-01", _make_pitcher_stats()),
                ("2025-06-05", _make_pitcher_stats()),
                ("2025-07-15", _make_pitcher_stats()),  # after cutoff
            ]
        }
        result = ProfileMixin._build_pitcher_profile(
            "p1", history, "2025-07-01", window=30, min_games=2,
        )
        assert result is not None

    def test_applies_rolling_window(self):
        history = {
            "p1": [
                (f"2025-06-{i:02d}", _make_pitcher_stats(strikeouts=i))
                for i in range(1, 15)
            ]
        }
        result = ProfileMixin._build_pitcher_profile(
            "p1", history, "2025-07-01", window=3, min_games=1,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# ProfileMixin._load_profile_histories tests (async, mocked DB)
# ---------------------------------------------------------------------------


class TestLoadProfileHistories:
    """Test _load_profile_histories with mocked async DB."""

    @pytest.fixture
    def mixin_with_mock_db(self):
        """Create a concrete class using ProfileMixin with a mocked DB."""
        class TestBuilder(ProfileMixin):
            def __init__(self):
                self._db = AsyncMock()

        builder = TestBuilder()
        # Mock execute to return empty results
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        builder._db.execute = AsyncMock(return_value=mock_result)
        return builder

    @pytest.mark.asyncio
    async def test_returns_three_dicts(self, mixin_with_mock_db):
        builder = mixin_with_mock_db
        batter_h, pitcher_h, team_h = await builder._load_profile_histories(
            dt_start=None, dt_end=None, rolling_window=30,
        )
        assert isinstance(batter_h, dict)
        assert isinstance(pitcher_h, dict)
        assert isinstance(team_h, dict)

    @pytest.mark.asyncio
    async def test_calls_execute_three_times(self, mixin_with_mock_db):
        builder = mixin_with_mock_db
        await builder._load_profile_histories(
            dt_start=None, dt_end=None, rolling_window=30,
        )
        assert builder._db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_with_dt_end(self, mixin_with_mock_db):
        from datetime import UTC, datetime

        builder = mixin_with_mock_db
        dt = datetime(2025, 7, 1, tzinfo=UTC)
        batter_h, pitcher_h, team_h = await builder._load_profile_histories(
            dt_start=None, dt_end=dt, rolling_window=30,
        )
        assert builder._db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_populates_histories_from_results(self):
        """Test that results are correctly grouped by player/team."""

        class TestBuilder(ProfileMixin):
            def __init__(self):
                self._db = AsyncMock()

        builder = TestBuilder()

        batter_row = SimpleNamespace(player_external_ref="b1")
        pitcher_row = SimpleNamespace(player_external_ref="p1")
        team_row = SimpleNamespace(team_id=10)

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.__iter__ = MagicMock(return_value=iter([
                    (batter_row, "2025-06-01"),
                ]))
            elif call_count == 2:
                result.__iter__ = MagicMock(return_value=iter([
                    (pitcher_row, "2025-06-02"),
                ]))
            elif call_count == 3:
                result.__iter__ = MagicMock(return_value=iter([
                    (team_row, "2025-06-03"),
                ]))
            else:
                result.__iter__ = MagicMock(return_value=iter([]))
            return result

        builder._db.execute = mock_execute

        batter_h, pitcher_h, team_h = await builder._load_profile_histories(
            dt_start=None, dt_end=None, rolling_window=30,
        )

        assert "b1" in batter_h
        assert len(batter_h["b1"]) == 1
        assert "p1" in pitcher_h
        assert len(pitcher_h["p1"]) == 1
        assert 10 in team_h
        assert len(team_h[10]) == 1


# ---------------------------------------------------------------------------
# MLBPitchDatasetBuilder tests (mocked DB)
# ---------------------------------------------------------------------------


class TestMLBPitchDatasetBuilderAsync:
    """Test MLBPitchDatasetBuilder.build() with mocked DB."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_games(self):
        from app.analytics.datasets.mlb_pitch_dataset import MLBPitchDatasetBuilder

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        builder = MLBPitchDatasetBuilder(db)
        rows = await builder.build(
            date_start="2025-07-01", date_end="2025-07-31",
            include_profiles=False,
        )
        assert rows == []

    @pytest.mark.asyncio
    async def test_extracts_pitches_from_play_events(self):
        from app.analytics.datasets.mlb_pitch_dataset import MLBPitchDatasetBuilder

        db = AsyncMock()

        # Mock game
        game = SimpleNamespace(
            id=1, game_date="2025-07-15", season=2025,
            home_team_id=10, away_team_id=20, status="final",
        )

        # Mock play with playEvents
        play = SimpleNamespace(
            game_id=1,
            play_index=0,
            player_id="100",
            raw_data={
                "matchup": {
                    "batter": {"id": 100},
                    "pitcher": {"id": 200},
                },
                "playEvents": [
                    {
                        "isPitch": True,
                        "details": {"code": "B"},
                        "count": {"balls": 0, "strikes": 0},
                        "pitchData": {"zone": 14, "startSpeed": 92.0},
                    },
                    {
                        "isPitch": True,
                        "details": {"code": "S"},
                        "count": {"balls": 1, "strikes": 0},
                        "pitchData": {"zone": 5, "startSpeed": 85.0},
                    },
                    {
                        "isPitch": False,
                        "details": {"code": "V"},
                    },
                    {
                        "isPitch": True,
                        "details": {"code": "X"},
                        "count": {"balls": 1, "strikes": 1},
                        "pitchData": {"zone": 8, "startSpeed": 93.0},
                    },
                ],
            },
        )

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Games query
                result.scalars.return_value.all.return_value = [game]
            elif call_count == 2:
                # Plays query
                result.scalars.return_value.all.return_value = [play]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        builder = MLBPitchDatasetBuilder(db)
        rows = await builder.build(
            date_start="2025-07-01", date_end="2025-07-31",
            include_profiles=False,
        )

        assert len(rows) == 3  # 3 isPitch events, all have valid codes
        assert rows[0]["outcome"] == "ball"
        assert rows[0]["count_balls"] == 0
        assert rows[0]["count_strikes"] == 0
        assert rows[0]["pitch_zone"] == 14
        assert rows[0]["pitch_speed"] == 92.0
        assert rows[1]["outcome"] == "swinging_strike"
        assert rows[2]["outcome"] == "in_play"


# ---------------------------------------------------------------------------
# MLBBattedBallDatasetBuilder tests (mocked DB)
# ---------------------------------------------------------------------------


class TestMLBBattedBallDatasetBuilderAsync:
    """Test MLBBattedBallDatasetBuilder.build() with mocked DB."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_games(self):
        from app.analytics.datasets.mlb_batted_ball_dataset import (
            MLBBattedBallDatasetBuilder,
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        builder = MLBBattedBallDatasetBuilder(db)
        rows = await builder.build(
            date_start="2025-07-01", date_end="2025-07-31",
            include_profiles=False,
        )
        assert rows == []

    @pytest.mark.asyncio
    async def test_extracts_batted_ball_data(self):
        from app.analytics.datasets.mlb_batted_ball_dataset import (
            MLBBattedBallDatasetBuilder,
        )

        db = AsyncMock()

        game = SimpleNamespace(
            id=1, game_date="2025-07-15", season=2025,
            home_team_id=10, away_team_id=20, status="final",
        )

        play = SimpleNamespace(
            game_id=1,
            play_index=0,
            player_id="100",
            raw_data={
                "event": "Single",
                "matchup": {
                    "batter": {"id": 100},
                    "pitcher": {"id": 200},
                },
                "hitData": {
                    "launchSpeed": 95.2,
                    "launchAngle": 18.5,
                    "coordinates": {"coordX": 140.0, "coordY": 150.0},
                },
            },
        )

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [game]
            elif call_count == 2:
                result.scalars.return_value.all.return_value = [play]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        builder = MLBBattedBallDatasetBuilder(db)
        rows = await builder.build(
            date_start="2025-07-01", date_end="2025-07-31",
            include_profiles=False,
        )

        assert len(rows) == 1
        assert rows[0]["outcome"] == "single"
        assert rows[0]["exit_velocity"] == 95.2
        assert rows[0]["launch_angle"] == 18.5
        assert rows[0]["spray_angle"] != 0.0  # off-center hit

    @pytest.mark.asyncio
    async def test_skips_null_launch_speed(self):
        from app.analytics.datasets.mlb_batted_ball_dataset import (
            MLBBattedBallDatasetBuilder,
        )

        db = AsyncMock()

        game = SimpleNamespace(
            id=1, game_date="2025-07-15", season=2025,
            home_team_id=10, away_team_id=20, status="final",
        )

        play = SimpleNamespace(
            game_id=1, play_index=0, player_id="100",
            raw_data={
                "event": "Groundout",
                "matchup": {
                    "batter": {"id": 100},
                    "pitcher": {"id": 200},
                },
                "hitData": {
                    "launchSpeed": None,
                    "launchAngle": 5.0,
                },
            },
        )

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [game]
            elif call_count == 2:
                result.scalars.return_value.all.return_value = [play]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        builder = MLBBattedBallDatasetBuilder(db)
        rows = await builder.build(
            date_start="2025-07-01", date_end="2025-07-31",
            include_profiles=False,
        )
        assert len(rows) == 0  # skipped due to null launchSpeed

    @pytest.mark.asyncio
    async def test_skips_non_bip_events(self):
        from app.analytics.datasets.mlb_batted_ball_dataset import (
            MLBBattedBallDatasetBuilder,
        )

        db = AsyncMock()

        game = SimpleNamespace(
            id=1, game_date="2025-07-15", season=2025,
            home_team_id=10, away_team_id=20, status="final",
        )

        # Strikeout is not a BIP
        play = SimpleNamespace(
            game_id=1, play_index=0, player_id="100",
            raw_data={
                "event": "Strikeout",
                "matchup": {
                    "batter": {"id": 100},
                    "pitcher": {"id": 200},
                },
            },
        )

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [game]
            elif call_count == 2:
                result.scalars.return_value.all.return_value = [play]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        builder = MLBBattedBallDatasetBuilder(db)
        rows = await builder.build(
            date_start="2025-07-01", date_end="2025-07-31",
            include_profiles=False,
        )
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_handles_missing_coordinates(self):
        from app.analytics.datasets.mlb_batted_ball_dataset import (
            MLBBattedBallDatasetBuilder,
        )

        db = AsyncMock()

        game = SimpleNamespace(
            id=1, game_date="2025-07-15", season=2025,
            home_team_id=10, away_team_id=20, status="final",
        )

        play = SimpleNamespace(
            game_id=1, play_index=0, player_id="100",
            raw_data={
                "event": "Home Run",
                "matchup": {
                    "batter": {"id": 100},
                    "pitcher": {"id": 200},
                },
                "hitData": {
                    "launchSpeed": 108.0,
                    "launchAngle": 28.0,
                    "coordinates": {},  # no coordX/coordY
                },
            },
        )

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [game]
            elif call_count == 2:
                result.scalars.return_value.all.return_value = [play]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        builder = MLBBattedBallDatasetBuilder(db)
        rows = await builder.build(
            date_start="2025-07-01", date_end="2025-07-31",
            include_profiles=False,
        )
        assert len(rows) == 1
        assert rows[0]["spray_angle"] == 0.0  # default when no coords
        assert rows[0]["outcome"] == "home_run"
