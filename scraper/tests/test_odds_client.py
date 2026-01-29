"""Comprehensive tests for odds/client.py module."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

from sports_scraper.odds.client import (
    OddsAPIClient,
    SPORT_KEY_MAP,
    MARKET_TYPES,
    CLOSING_LINE_HOURS,
)


# ============================================================================
# Constants Tests
# ============================================================================

class TestSportKeyMap:
    """Tests for SPORT_KEY_MAP constant."""

    def test_nba_mapping(self):
        assert SPORT_KEY_MAP["NBA"] == "basketball_nba"

    def test_nhl_mapping(self):
        assert SPORT_KEY_MAP["NHL"] == "icehockey_nhl"

    def test_nfl_mapping(self):
        assert SPORT_KEY_MAP["NFL"] == "americanfootball_nfl"

    def test_mlb_mapping(self):
        assert SPORT_KEY_MAP["MLB"] == "baseball_mlb"

    def test_ncaab_mapping(self):
        assert SPORT_KEY_MAP["NCAAB"] == "basketball_ncaab"

    def test_ncaaf_mapping(self):
        assert SPORT_KEY_MAP["NCAAF"] == "americanfootball_ncaaf"


class TestMarketTypes:
    """Tests for MARKET_TYPES constant."""

    def test_spreads_market(self):
        assert MARKET_TYPES["spreads"] == "spread"

    def test_totals_market(self):
        assert MARKET_TYPES["totals"] == "total"

    def test_h2h_market(self):
        assert MARKET_TYPES["h2h"] == "moneyline"


class TestClosingLineHours:
    """Tests for CLOSING_LINE_HOURS constant."""

    def test_nba_closing_hour(self):
        assert CLOSING_LINE_HOURS["NBA"] == 23

    def test_nhl_closing_hour(self):
        assert CLOSING_LINE_HOURS["NHL"] == 23

    def test_nfl_closing_hour(self):
        assert CLOSING_LINE_HOURS["NFL"] == 17  # Sunday afternoon games


# ============================================================================
# Client Tests
# ============================================================================

class TestOddsAPIClientInit:
    """Tests for OddsAPIClient initialization."""

    @patch("sports_scraper.odds.client.settings")
    def test_init_with_api_key(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        assert client._cache_dir == Path("/tmp/cache/odds")

    @patch("sports_scraper.odds.client.settings")
    def test_init_without_api_key(self, mock_settings):
        mock_settings.odds_api_key = None
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        # Should not raise, just log warning
        client = OddsAPIClient()
        assert client._cache_dir == Path("/tmp/cache/odds")


class TestOddsAPIClientHelpers:
    """Tests for OddsAPIClient helper methods."""

    @patch("sports_scraper.odds.client.settings")
    def test_sport_key_valid_league(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        assert client._sport_key("NBA") == "basketball_nba"
        assert client._sport_key("nba") == "basketball_nba"  # Case insensitive

    @patch("sports_scraper.odds.client.settings")
    def test_sport_key_invalid_league(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        assert client._sport_key("INVALID") is None

    @patch("sports_scraper.odds.client.settings")
    def test_truncate_body_short(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        result = client._truncate_body("short text", limit=500)
        assert result == "short text"

    @patch("sports_scraper.odds.client.settings")
    def test_truncate_body_long(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        long_text = "x" * 600
        result = client._truncate_body(long_text, limit=500)
        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")

    @patch("sports_scraper.odds.client.settings")
    def test_truncate_body_none(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        assert client._truncate_body(None) is None


class TestOddsAPIClientCache:
    """Tests for OddsAPIClient cache methods."""

    @patch("sports_scraper.odds.client.settings")
    def test_get_cache_path_live(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        path = client._get_cache_path("NBA", date(2024, 1, 15), is_historical=False)
        assert "live" in path.name
        assert "2024-01-15" in path.name

    @patch("sports_scraper.odds.client.settings")
    def test_get_cache_path_historical(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        path = client._get_cache_path("NBA", date(2024, 1, 15), is_historical=True)
        assert "historical" in path.name

    @patch("sports_scraper.odds.client.settings")
    def test_read_cache_miss(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        path = tmp_path / "nonexistent.json"
        result = client._read_cache(path)
        assert result is None

    @patch("sports_scraper.odds.client.settings")
    def test_read_cache_hit(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        cache_file = tmp_path / "test.json"
        cache_file.write_text('{"key": "value"}')

        result = client._read_cache(cache_file)
        assert result == {"key": "value"}

    @patch("sports_scraper.odds.client.settings")
    def test_read_cache_invalid_json(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        cache_file = tmp_path / "invalid.json"
        cache_file.write_text("not valid json {")

        result = client._read_cache(cache_file)
        assert result is None

    @patch("sports_scraper.odds.client.settings")
    def test_write_cache(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        cache_file = tmp_path / "new_dir" / "test.json"

        client._write_cache(cache_file, {"key": "value"})

        assert cache_file.exists()
        assert json.loads(cache_file.read_text()) == {"key": "value"}


class TestOddsAPIClientFetchMainlines:
    """Tests for fetch_mainlines method."""

    @patch("sports_scraper.odds.client.settings")
    def test_fetch_mainlines_no_api_key(self, mock_settings):
        mock_settings.odds_api_key = None
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        result = client.fetch_mainlines("NBA", date(2024, 1, 15), date(2024, 1, 15))
        assert result == []

    @patch("sports_scraper.odds.client.settings")
    def test_fetch_mainlines_invalid_league(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        result = client.fetch_mainlines("INVALID", date(2024, 1, 15), date(2024, 1, 15))
        assert result == []


class TestOddsAPIClientFetchHistorical:
    """Tests for fetch_historical_odds method."""

    @patch("sports_scraper.odds.client.settings")
    def test_fetch_historical_no_api_key(self, mock_settings):
        mock_settings.odds_api_key = None
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        result = client.fetch_historical_odds("NBA", date(2024, 1, 15))
        assert result == []

    @patch("sports_scraper.odds.client.settings")
    def test_fetch_historical_invalid_league(self, mock_settings):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/cache"

        client = OddsAPIClient()
        result = client.fetch_historical_odds("INVALID", date(2024, 1, 15))
        assert result == []


class TestOddsAPIClientParseEvents:
    """Tests for _parse_odds_events method."""

    @patch("sports_scraper.odds.client.settings")
    def test_parse_empty_events(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        result = client._parse_odds_events("NBA", [], None)
        assert result == []

    @patch("sports_scraper.odds.client.settings")
    def test_parse_event_with_bookmakers(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        events = [
            {
                "id": "abc123",
                "commence_time": "2024-01-15T00:00:00Z",
                "home_team": "Boston Celtics",
                "away_team": "Los Angeles Lakers",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "title": "Pinnacle",
                        "last_update": "2024-01-14T23:00:00Z",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": -110, "point": -5.5},
                                    {"name": "Los Angeles Lakers", "price": -110, "point": 5.5},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        result = client._parse_odds_events("NBA", events, None)
        assert len(result) == 2  # 2 outcomes (home and away spread)

    @patch("sports_scraper.odds.client.settings")
    def test_parse_event_filters_books(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        events = [
            {
                "id": "abc123",
                "commence_time": "2024-01-15T00:00:00Z",
                "home_team": "Boston Celtics",
                "away_team": "Los Angeles Lakers",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "title": "Pinnacle",
                        "last_update": "2024-01-14T23:00:00Z",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": -110, "point": -5.5},
                                ]
                            }
                        ]
                    },
                    {
                        "key": "draftkings",
                        "title": "DraftKings",
                        "last_update": "2024-01-14T23:00:00Z",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": -115, "point": -5.5},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        # Filter to only pinnacle
        result = client._parse_odds_events("NBA", events, books=["pinnacle"])
        assert len(result) == 1
        assert result[0].book == "Pinnacle"

    @patch("sports_scraper.odds.client.settings")
    def test_parse_event_skips_missing_data(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        events = [
            {
                "id": "abc123",
                "commence_time": "2024-01-15T00:00:00Z",
                "home_team": "Boston Celtics",
                "away_team": "Los Angeles Lakers",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "title": "Pinnacle",
                        "last_update": "2024-01-14T23:00:00Z",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": None, "price": -110, "point": -5.5},  # Missing side
                                    {"name": "Lakers", "price": None, "point": 5.5},  # Missing price
                                    {"name": "Celtics", "price": -110, "point": None},  # Missing point for spread
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        result = client._parse_odds_events("NBA", events, None)
        assert len(result) == 0  # All outcomes should be skipped

    @patch("sports_scraper.odds.client.settings")
    def test_parse_event_moneyline_no_point_required(self, mock_settings, tmp_path):
        mock_settings.odds_api_key = "test_key"
        mock_settings.odds_config.base_url = "https://api.test.com"
        mock_settings.odds_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = str(tmp_path)

        client = OddsAPIClient()
        events = [
            {
                "id": "abc123",
                "commence_time": "2024-01-15T00:00:00Z",
                "home_team": "Boston Celtics",
                "away_team": "Los Angeles Lakers",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "title": "Pinnacle",
                        "last_update": "2024-01-14T23:00:00Z",
                        "markets": [
                            {
                                "key": "h2h",  # Moneyline
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": -180},  # No point needed
                                    {"name": "Los Angeles Lakers", "price": 150},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        result = client._parse_odds_events("NBA", events, None)
        assert len(result) == 2  # Both moneylines should be parsed
