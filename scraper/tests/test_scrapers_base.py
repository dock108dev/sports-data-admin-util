"""Tests for scrapers/base.py module."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
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


from sports_scraper.scrapers.base import (
    ScraperError,
    NoGamesFoundError,
    BaseSportsReferenceScraper,
)


class TestScraperError:
    """Tests for ScraperError exception."""

    def test_is_runtime_error(self):
        """ScraperError inherits from RuntimeError."""
        error = ScraperError("Test error")
        assert isinstance(error, RuntimeError)
        assert str(error) == "Test error"


class TestNoGamesFoundError:
    """Tests for NoGamesFoundError exception."""

    def test_is_scraper_error(self):
        """NoGamesFoundError inherits from ScraperError."""
        error = NoGamesFoundError("No games today")
        assert isinstance(error, ScraperError)
        assert str(error) == "No games today"


class ConcreteTestScraper(BaseSportsReferenceScraper):
    """Concrete implementation for testing."""

    sport = "test"
    league_code = "TEST"
    base_url = "https://www.test-reference.com/test/boxscores/"


class TestBaseSportsReferenceScraperInit:
    """Tests for BaseSportsReferenceScraper initialization."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_init_creates_client(self, mock_client, mock_cache):
        """Initializes with httpx client."""
        scraper = ConcreteTestScraper()
        mock_client.assert_called_once()
        assert scraper._last_request_time == 0.0

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_init_with_custom_timeout(self, mock_client, mock_cache):
        """Accepts custom timeout."""
        scraper = ConcreteTestScraper(timeout_seconds=60)
        call_kwargs = mock_client.call_args
        assert call_kwargs.kwargs["timeout"] == 60


class TestBaseSportsReferenceScraperIterDates:
    """Tests for iter_dates method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_iter_single_date(self, mock_client, mock_cache):
        """Iterates single date range."""
        scraper = ConcreteTestScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 15), date(2024, 1, 15)))
        assert len(dates) == 1
        assert dates[0] == date(2024, 1, 15)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_iter_multiple_dates(self, mock_client, mock_cache):
        """Iterates multiple dates."""
        scraper = ConcreteTestScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 15), date(2024, 1, 17)))
        assert len(dates) == 3
        assert dates[0] == date(2024, 1, 15)
        assert dates[1] == date(2024, 1, 16)
        assert dates[2] == date(2024, 1, 17)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_iter_empty_range(self, mock_client, mock_cache):
        """Empty iteration when end before start."""
        scraper = ConcreteTestScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 17), date(2024, 1, 15)))
        assert len(dates) == 0


class TestBaseSportsReferenceScraperScoreboardUrl:
    """Tests for scoreboard_url method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_builds_url_with_date(self, mock_client, mock_cache):
        """Builds scoreboard URL with date params."""
        scraper = ConcreteTestScraper()
        url = scraper.scoreboard_url(date(2024, 1, 15))
        assert "month=1" in url
        assert "day=15" in url
        assert "year=2024" in url


class TestBaseSportsReferenceScraperPbpUrl:
    """Tests for pbp_url method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_not_implemented(self, mock_client, mock_cache):
        """Base class raises NotImplementedError."""
        scraper = ConcreteTestScraper()
        with pytest.raises(NotImplementedError):
            scraper.pbp_url("game123")


class TestBaseSportsReferenceScraperPoliteDelay:
    """Tests for _polite_delay method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    @patch("sports_scraper.scrapers.base.time.sleep")
    @patch("sports_scraper.scrapers.base.time.time")
    def test_delays_after_request(self, mock_time, mock_sleep, mock_client, mock_cache):
        """Delays when time since last request is less than min delay."""
        mock_time.return_value = 100.0

        scraper = ConcreteTestScraper()
        scraper._last_request_time = 99.0  # Only 1 second elapsed
        scraper._min_delay = 5.0
        scraper._max_delay = 9.0

        scraper._polite_delay()

        # Should have slept for roughly the remaining delay time
        mock_sleep.assert_called_once()

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    @patch("sports_scraper.scrapers.base.time.sleep")
    @patch("sports_scraper.scrapers.base.time.time")
    def test_no_delay_if_enough_time_passed(self, mock_time, mock_sleep, mock_client, mock_cache):
        """No delay when enough time has passed."""
        mock_time.return_value = 100.0

        scraper = ConcreteTestScraper()
        scraper._last_request_time = 90.0  # 10 seconds elapsed
        scraper._min_delay = 5.0
        scraper._max_delay = 9.0

        scraper._polite_delay()

        # Should not have slept since enough time passed
        mock_sleep.assert_not_called()


class TestBaseSportsReferenceScraperFetchHtml:
    """Tests for fetch_html method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_cached_html(self, mock_client, mock_cache):
        """Returns cached HTML when available."""
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = "<html><body>Cached</body></html>"
        mock_cache.return_value = mock_cache_instance

        scraper = ConcreteTestScraper()
        result = scraper.fetch_html("https://example.com", date(2024, 1, 15))

        assert result is not None
        mock_cache_instance.get.assert_called_once()


class TestBaseSportsReferenceScraperFetchGamesForDate:
    """Tests for fetch_games_for_date method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_not_implemented(self, mock_client, mock_cache):
        """Base class raises NotImplementedError."""
        scraper = ConcreteTestScraper()
        with pytest.raises(NotImplementedError):
            scraper.fetch_games_for_date(date(2024, 1, 15))


class TestBaseSportsReferenceScraperFetchPlayByPlay:
    """Tests for fetch_play_by_play method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_not_implemented(self, mock_client, mock_cache):
        """Base class raises NotImplementedError."""
        scraper = ConcreteTestScraper()
        with pytest.raises(NotImplementedError):
            scraper.fetch_play_by_play("game123", date(2024, 1, 15))


class TestBaseSportsReferenceScraperFetchSingleBoxscore:
    """Tests for fetch_single_boxscore method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_not_implemented(self, mock_client, mock_cache):
        """Base class raises NotImplementedError."""
        scraper = ConcreteTestScraper()
        with pytest.raises(NotImplementedError):
            scraper.fetch_single_boxscore("game123", date(2024, 1, 15))


class TestBaseSportsReferenceScraperSeasonFromDate:
    """Tests for _season_from_date method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_delegates_to_util(self, mock_client, mock_cache):
        """Delegates to season_from_date utility."""
        scraper = ConcreteTestScraper()
        # Should return a valid season year
        result = scraper._season_from_date(date(2024, 1, 15))
        assert isinstance(result, int)
        assert result > 2000
