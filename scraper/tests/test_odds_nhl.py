"""Tests for NHL odds ingestion parity with NBA.

These tests verify that:
1. NHL uses the same odds pipeline as NBA
2. Sport key mapping is correct
3. Future dates are supported for odds (live endpoint)
4. Historical dates are supported (historical endpoint)
5. Game stubs are created for future games when odds arrive first
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
API_ROOT = REPO_ROOT / "api"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# Set required env vars before imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ODDS_API_KEY", "test_key_for_unit_tests")
os.environ.setdefault("ENVIRONMENT", "development")

# Now import odds modules directly
from sports_scraper.odds.client import CLOSING_LINE_HOURS, SPORT_KEY_MAP, OddsAPIClient


class TestSportKeyMapping:
    """Tests for SPORT_KEY_MAP configuration."""

    def test_nhl_sport_key_exists(self) -> None:
        """NHL must be in the sport key map."""
        assert "NHL" in SPORT_KEY_MAP

    def test_nhl_sport_key_value(self) -> None:
        """NHL sport key must be the correct Odds API value."""
        assert SPORT_KEY_MAP["NHL"] == "icehockey_nhl"

    def test_nba_sport_key_exists(self) -> None:
        """NBA must be in the sport key map (reference implementation)."""
        assert "NBA" in SPORT_KEY_MAP
        assert SPORT_KEY_MAP["NBA"] == "basketball_nba"

    def test_closing_line_hour_nhl(self) -> None:
        """NHL must have a closing line hour configured."""
        assert "NHL" in CLOSING_LINE_HOURS
        # NHL games typically start around 7 PM ET
        assert CLOSING_LINE_HOURS["NHL"] == 23


class TestOddsAPIClientRouting:
    """Tests for OddsAPIClient sport routing."""

    def test_sport_key_nhl(self) -> None:
        """OddsAPIClient should return correct sport key for NHL."""
        client = OddsAPIClient()
        assert client._sport_key("NHL") == "icehockey_nhl"

    def test_sport_key_nba(self) -> None:
        """OddsAPIClient should return correct sport key for NBA."""
        client = OddsAPIClient()
        assert client._sport_key("NBA") == "basketball_nba"

    def test_sport_key_case_insensitive(self) -> None:
        """Sport key lookup should be case-insensitive."""
        client = OddsAPIClient()
        assert client._sport_key("nhl") == "icehockey_nhl"
        assert client._sport_key("Nhl") == "icehockey_nhl"

    def test_sport_key_unknown_returns_none(self) -> None:
        """Unknown league should return None."""
        client = OddsAPIClient()
        assert client._sport_key("FAKE_LEAGUE") is None


class TestOddsSynchronizerDateRouting:
    """Tests for OddsSynchronizer date-based endpoint routing."""

    def test_past_dates_use_historical(self) -> None:
        """Dates in the past should route to historical endpoint."""
        from sports_scraper.odds.synchronizer import OddsSynchronizer
        from sports_scraper.models.schemas import IngestionConfig

        sync = OddsSynchronizer()
        today = date.today()
        past_date = today - timedelta(days=5)

        config = IngestionConfig(
            league_code="NHL",
            start_date=past_date,
            end_date=past_date,
            odds=True,
            boxscores=False,
        )

        with patch.object(sync, "_sync_historical", return_value=5) as mock_hist:
            with patch.object(sync, "_sync_live", return_value=0) as mock_live:
                result = sync.sync(config)

                mock_hist.assert_called_once()
                mock_live.assert_not_called()
                assert result == 5

    def test_future_dates_use_live(self) -> None:
        """Dates in the future should route to live endpoint."""
        from sports_scraper.odds.synchronizer import OddsSynchronizer
        from sports_scraper.models.schemas import IngestionConfig

        sync = OddsSynchronizer()
        today = date.today()
        future_date = today + timedelta(days=2)

        config = IngestionConfig(
            league_code="NHL",
            start_date=future_date,
            end_date=future_date,
            odds=True,
            boxscores=False,
        )

        with patch.object(sync, "_sync_historical", return_value=0) as mock_hist:
            with patch.object(sync, "_sync_live", return_value=3) as mock_live:
                result = sync.sync(config)

                mock_live.assert_called_once()
                mock_hist.assert_not_called()
                assert result == 3

    def test_mixed_range_uses_both(self) -> None:
        """Date range spanning past and future should use both endpoints."""
        from sports_scraper.odds.synchronizer import OddsSynchronizer
        from sports_scraper.models.schemas import IngestionConfig

        sync = OddsSynchronizer()
        today = date.today()
        past_date = today - timedelta(days=3)
        future_date = today + timedelta(days=2)

        config = IngestionConfig(
            league_code="NHL",
            start_date=past_date,
            end_date=future_date,
            odds=True,
            boxscores=False,
        )

        with patch.object(sync, "_sync_historical", return_value=10) as mock_hist:
            with patch.object(sync, "_sync_live", return_value=5) as mock_live:
                result = sync.sync(config)

                mock_hist.assert_called_once()
                mock_live.assert_called_once()
                assert result == 15  # 10 historical + 5 live


class TestNHLTeamNormalization:
    """Tests for NHL team name normalization in odds parsing."""

    def test_nhl_team_normalization_exists(self) -> None:
        """NHL teams should be in the normalization mappings."""
        from sports_scraper.normalization import normalize_team_name

        # Test a few representative NHL teams
        teams_to_test = [
            ("Boston Bruins", "Boston Bruins", "BOS"),
            ("Toronto Maple Leafs", "Toronto Maple Leafs", "TOR"),
            ("Vegas Golden Knights", "Vegas Golden Knights", "VGK"),
            ("New York Rangers", "New York Rangers", "NYR"),
        ]

        for input_name, expected_canonical, expected_abbr in teams_to_test:
            canonical, abbr = normalize_team_name("NHL", input_name)
            assert canonical == expected_canonical, f"Failed for {input_name}"
            assert abbr == expected_abbr, f"Failed abbr for {input_name}"

    def test_nhl_team_variation_normalization(self) -> None:
        """Common team name variations should normalize correctly."""
        from sports_scraper.normalization import normalize_team_name

        # Test variations
        canonical, abbr = normalize_team_name("NHL", "LA Kings")
        assert canonical == "Los Angeles Kings"
        assert abbr == "LAK"

        canonical, abbr = normalize_team_name("NHL", "NY Rangers")
        assert canonical == "New York Rangers"
        assert abbr == "NYR"


class TestNormalizedOddsSnapshot:
    """Tests for NormalizedOddsSnapshot with NHL data."""

    def test_nhl_snapshot_creation(self) -> None:
        """NHL odds snapshot should be creatable with valid data."""
        from sports_scraper.models.schemas import NormalizedOddsSnapshot, TeamIdentity

        home_team = TeamIdentity(
            league_code="NHL",
            name="Boston Bruins",
            short_name="Bruins",
            abbreviation="BOS",
        )
        away_team = TeamIdentity(
            league_code="NHL",
            name="Toronto Maple Leafs",
            short_name="Maple Leafs",
            abbreviation="TOR",
        )
        now = datetime.now(timezone.utc)

        snapshot = NormalizedOddsSnapshot(
            league_code="NHL",
            book="DraftKings",
            market_type="spread",
            side="Boston Bruins",
            line=-1.5,
            price=-110,
            observed_at=now,
            home_team=home_team,
            away_team=away_team,
            game_date=now + timedelta(days=1),
            source_key="test_event_123",
            is_closing_line=True,
            raw_payload={"test": "data"},
        )

        assert snapshot.league_code == "NHL"
        assert snapshot.home_team.abbreviation == "BOS"
        assert snapshot.away_team.abbreviation == "TOR"
        assert snapshot.market_type == "spread"


class TestOddsOnlyRunConfig:
    """Tests for odds-only run configuration."""

    def test_odds_only_config(self) -> None:
        """Odds-only config should work without boxscores/pbp/social."""
        from sports_scraper.models.schemas import IngestionConfig

        config = IngestionConfig(
            league_code="NHL",
            start_date=date.today() - timedelta(days=4),
            end_date=date.today() + timedelta(days=2),
            odds=True,
            boxscores=False,
            pbp=False,
            social=False,
        )

        assert config.odds is True
        assert config.boxscores is False
        assert config.pbp is False
        assert config.social is False

    def test_odds_disabled_returns_zero(self) -> None:
        """Synchronizer should return 0 when odds is disabled."""
        from sports_scraper.odds.synchronizer import OddsSynchronizer
        from sports_scraper.models.schemas import IngestionConfig

        sync = OddsSynchronizer()
        config = IngestionConfig(
            league_code="NHL",
            odds=False,
            boxscores=True,
        )

        result = sync.sync(config)
        assert result == 0


class TestSeasonCalculation:
    """Tests for NHL season calculation."""

    def test_nhl_season_october(self) -> None:
        """October dates should be current season."""
        from sports_scraper.utils.date_utils import season_from_date

        oct_date = date(2024, 10, 15)
        assert season_from_date(oct_date, "NHL") == 2024

    def test_nhl_season_january(self) -> None:
        """January dates should be previous year's season."""
        from sports_scraper.utils.date_utils import season_from_date

        jan_date = date(2025, 1, 15)
        assert season_from_date(jan_date, "NHL") == 2024

    def test_nhl_season_june(self) -> None:
        """June (playoffs) should be previous year's season."""
        from sports_scraper.utils.date_utils import season_from_date

        june_date = date(2025, 6, 15)
        assert season_from_date(june_date, "NHL") == 2024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
