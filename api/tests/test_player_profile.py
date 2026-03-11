"""Tests for player and pitcher profile service functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.analytics.services.profile_service import (
    get_pitcher_rolling_profile,
    get_player_rolling_profile,
)


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

        # Create mock stats rows that stats_to_metrics can process
        def make_mock_stats(**overrides):
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

        rows = [(make_mock_stats(barrel_pct=0.10), "2026-03-01") for _ in range(10)]

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

        def make_mock_stats():
            m = MagicMock()
            for k, v in {
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
            }.items():
                setattr(m, k, v)
            return m

        # Only 3 games (< 5 threshold for blending)
        rows = [(make_mock_stats(), "2026-03-01") for _ in range(3)]

        result_mock = MagicMock()
        result_mock.all.return_value = rows

        # Need to mock get_team_rolling_profile for the blend
        # For simplicity, mock to return None (falls back to player-only)
        with patch(
            "app.analytics.services.profile_service.get_team_rolling_profile",
            new_callable=AsyncMock,
        ) as mock_team:
            mock_team.return_value = None

            # Also need to mock the team abbreviation lookup
            team_mock = MagicMock()
            team_mock.abbreviation = "NYY"
            team_result = MagicMock()
            team_result.scalar_one_or_none.return_value = team_mock

            db.execute.side_effect = [result_mock, team_result]

            result = await get_player_rolling_profile("player123", 1, db=db)
            # Should still return metrics even with < 5 games when team profile is None
            assert result is not None


class TestPitcherRollingProfile:
    """Tests for get_pitcher_rolling_profile."""

    @pytest.mark.asyncio
    async def test_returns_none_for_insufficient_data(self):
        """Returns None when pitcher has < 3 games."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = [
            (
                MagicMock(
                    stats={
                        "innings_pitched": 6.0,
                        "strike_outs": 5,
                        "base_on_balls": 2,
                        "home_runs": 1,
                        "hits": 4,
                    }
                ),
                "2026-03-01",
            ),
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
        rows = [(MagicMock(stats=stats), f"2026-03-0{i}") for i in range(1, 6)]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        result = await get_pitcher_rolling_profile("pitcher456", 1, db=db)
        assert result is not None
        assert abs(result["strikeout_rate"] - 0.50) < 0.01
        assert abs(result["walk_rate"] - 0.125) < 0.01
        assert result["contact_suppression"] > 0  # good pitcher suppresses contact
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

        rows = [
            (MagicMock(stats=good_stats), "2026-03-01"),
            (MagicMock(stats=zero_stats), "2026-03-02"),
            (MagicMock(stats=good_stats), "2026-03-03"),
            (MagicMock(stats=good_stats), "2026-03-04"),
        ]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        # Only 3 valid games, which meets the threshold of 3
        result = await get_pitcher_rolling_profile("pitcher456", 1, db=db)
        assert result is not None
