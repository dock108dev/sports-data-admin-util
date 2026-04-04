"""Tests for player and pitcher profile service functions."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analytics.services.profile_service import (
    get_pitcher_rolling_profile,
    get_player_rolling_profile,
)


def _make_mock_stats(**overrides):
    """Create a mock stats row compatible with stats_to_metrics()."""
    defaults = {
        "total_pitches": 100,
        "zone_pitches": 50,
        "zone_swings": 30,
        "zone_contact": 25,
        "outside_pitches": 50,
        "outside_swings": 15,
        "outside_contact": 8,
        "z_swing_pct": 0.60,
        "o_swing_pct": 0.30,
        "z_contact_pct": 0.83,
        "o_contact_pct": 0.53,
        "balls_in_play": 20,
        "hard_hit_count": 7,
        "barrel_count": 2,
        "avg_exit_velo": 90.0,
        "hard_hit_pct": 0.35,
        "barrel_pct": 0.10,
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


class TestPlayerRollingProfile:
    """Tests for get_player_rolling_profile."""

    @pytest.mark.asyncio
    async def test_returns_none_for_no_data(self):
        """Returns None when player has no games."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute.return_value = result_mock

        result = await get_player_rolling_profile("player123", 1, db=db)
        assert result is None

    @pytest.mark.asyncio
    async def test_averages_metrics_across_games(self):
        """Averages stats_to_metrics output across multiple games."""
        db = AsyncMock()

        game_date = datetime(2026, 3, 1, tzinfo=UTC)
        rows = [(_make_mock_stats(barrel_pct=0.10), game_date) for _ in range(10)]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        result = await get_player_rolling_profile("player123", 1, db=db)
        assert result is not None
        assert "barrel_rate" in result
        assert "contact_rate" in result
        assert "whiff_rate" in result

    @pytest.mark.asyncio
    async def test_sparse_data_blends_with_team(self):
        """When < 5 games, blends with team average."""
        db = AsyncMock()

        # Only 3 games (< 5 threshold for blending)
        game_date = datetime(2026, 3, 1, tzinfo=UTC)
        rows = [(_make_mock_stats(), game_date) for _ in range(3)]

        player_result_mock = MagicMock()
        player_result_mock.all.return_value = rows

        # Team lookup mock
        team_mock = MagicMock()
        team_mock.abbreviation = "NYY"
        team_result_mock = MagicMock()
        team_result_mock.scalar_one_or_none.return_value = team_mock

        with patch(
            "app.analytics.services.profile_service.get_team_rolling_profile",
            new_callable=AsyncMock,
        ) as mock_team:
            mock_team.return_value = None

            db.execute.side_effect = [player_result_mock, team_result_mock]

            result = await get_player_rolling_profile("player123", 1, db=db)
            # Should still return metrics even with < 5 games when team profile is None
            assert result is not None


class TestPitcherRollingProfile:
    """Tests for get_pitcher_rolling_profile."""

    @pytest.mark.asyncio
    async def test_cross_team_pitcher_includes_all_teams(self):
        """Pitcher traded mid-season should include stats from both teams.

        The query should NOT filter by team_id, so a pitcher who played
        for team 1 and team 2 gets all their games in the profile.
        """
        db = AsyncMock()

        # 3 games with team_id=1, 3 games with team_id=2
        # All should be included since we no longer filter by team_id
        game_date = datetime(2026, 3, 1, tzinfo=UTC)
        stats_team1 = {
            "innings_pitched": 6.0,
            "strike_outs": 6,
            "base_on_balls": 2,
            "home_runs": 1,
            "hits": 5,
        }
        stats_team2 = {
            "innings_pitched": 7.0,
            "strike_outs": 8,
            "base_on_balls": 1,
            "home_runs": 0,
            "hits": 3,
        }
        # Simulate 6 rows coming back (3 from each team, but query doesn't
        # filter by team so they all come through)
        rows = [
            (MagicMock(stats=stats_team1), game_date),
            (MagicMock(stats=stats_team1), game_date),
            (MagicMock(stats=stats_team1), game_date),
            (MagicMock(stats=stats_team2), game_date),
            (MagicMock(stats=stats_team2), game_date),
            (MagicMock(stats=stats_team2), game_date),
        ]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        # Pass team_id=2 (current team) — should still get all 6 games
        result = await get_pitcher_rolling_profile("pitcher789", 2, db=db)
        assert result is not None
        # The K rate should be a blend of both teams' stats, not just team 2
        # team1 approx: 6/(5+2+6+1)=0.4286, team2 approx: 8/(3+1+8+0)=0.6667
        # blended ≈ 0.5476
        assert result["strikeout_rate"] > 0.43  # higher than team1-only
        assert result["strikeout_rate"] < 0.67  # lower than team2-only

    @pytest.mark.asyncio
    async def test_returns_none_for_insufficient_data(self):
        """Returns None when pitcher has < 3 games."""
        db = AsyncMock()
        stats = {
            "innings_pitched": 6.0,
            "strike_outs": 5,
            "base_on_balls": 2,
            "home_runs": 1,
            "hits": 4,
        }
        game_date = datetime(2026, 3, 1, tzinfo=UTC)
        result_mock = MagicMock()
        result_mock.all.return_value = [
            (MagicMock(stats=stats), game_date),
        ]
        db.execute.return_value = result_mock

        result = await get_pitcher_rolling_profile("pitcher456", 1, db=db)
        assert result is None

    @pytest.mark.asyncio
    async def test_derives_rates_from_boxscore(self):
        """Correctly derives K rate, BB rate, contact/power suppression."""
        db = AsyncMock()

        # Pitcher with 6 IP, 8 K, 2 BB, 1 HR, 5 H per game
        # approx_BF = 5 + 2 + 8 + 1 = 16
        # K_rate = 8/16 = 0.50
        # BB_rate = 2/16 = 0.125
        stats = {
            "innings_pitched": 6.0,
            "strike_outs": 8,
            "base_on_balls": 2,
            "home_runs": 1,
            "hits": 5,
        }
        game_date = datetime(2026, 3, 1, tzinfo=UTC)
        rows = [(MagicMock(stats=stats), game_date) for _ in range(5)]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        result = await get_pitcher_rolling_profile("pitcher456", 1, db=db)
        assert result is not None
        assert abs(result["strikeout_rate"] - 0.50) < 0.01
        assert abs(result["walk_rate"] - 0.125) < 0.01
        assert result["contact_suppression"] > 0
        assert "power_suppression" in result

    @pytest.mark.asyncio
    async def test_skips_games_with_zero_bf(self):
        """Games with 0 approx batters faced are skipped."""
        db = AsyncMock()

        good_stats = {
            "innings_pitched": 6.0,
            "strike_outs": 5,
            "base_on_balls": 2,
            "home_runs": 1,
            "hits": 4,
        }
        zero_stats = {
            "innings_pitched": 0,
            "strike_outs": 0,
            "base_on_balls": 0,
            "home_runs": 0,
            "hits": 0,
        }

        game_date = datetime(2026, 3, 1, tzinfo=UTC)
        rows = [
            (MagicMock(stats=good_stats), game_date),
            (MagicMock(stats=zero_stats), game_date),
            (MagicMock(stats=good_stats), game_date),
            (MagicMock(stats=good_stats), game_date),
        ]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        # Only 3 valid games, which meets the threshold of 3
        result = await get_pitcher_rolling_profile("pitcher456", 1, db=db)
        assert result is not None
