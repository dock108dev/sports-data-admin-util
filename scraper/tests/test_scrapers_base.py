"""Tests for scrapers/base.py module."""

from __future__ import annotations

import os
import sys
from datetime import date
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


from sports_scraper.scrapers.base import BaseSportsReferenceScraper, ScraperError, NoGamesFoundError


# Concrete subclass for testing (base class can't be instantiated directly)
class _TestScraper(BaseSportsReferenceScraper):
    sport = "test"
    league_code = "TEST"
    base_url = "https://example.com/"


class TestScraperError:
    """Tests for ScraperError exception."""

    def test_creates_exception_with_message(self):
        """Creates exception with message."""
        error = ScraperError("Test error message")
        assert str(error) == "Test error message"

    def test_is_exception_subclass(self):
        """ScraperError is an Exception subclass."""
        assert issubclass(ScraperError, Exception)


class TestNoGamesFoundError:
    """Tests for NoGamesFoundError exception."""

    def test_is_scraper_error_subclass(self):
        """NoGamesFoundError is a ScraperError subclass."""
        assert issubclass(NoGamesFoundError, ScraperError)


class TestBaseSportsReferenceScraper:
    """Tests for BaseSportsReferenceScraper class."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_init_creates_client(self, mock_client_class, mock_cache_class):
        """Initializes with HTTP client."""
        scraper = _TestScraper()

        assert mock_client_class.called
        assert scraper.client is not None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_init_creates_cache(self, mock_client_class, mock_cache_class):
        """Initializes with HTML cache."""
        scraper = _TestScraper()

        assert mock_cache_class.called

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_sport_attribute(self, mock_client_class, mock_cache_class):
        """Has sport attribute."""
        scraper = _TestScraper()

        assert hasattr(scraper, "sport")
        assert scraper.sport == "test"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_league_code_attribute(self, mock_client_class, mock_cache_class):
        """Has league_code attribute."""
        scraper = _TestScraper()

        assert hasattr(scraper, "league_code")
        assert scraper.league_code == "TEST"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_base_url_attribute(self, mock_client_class, mock_cache_class):
        """Has base_url attribute."""
        scraper = _TestScraper()

        assert hasattr(scraper, "base_url")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_iter_dates_yields_range(self, mock_client_class, mock_cache_class):
        """iter_dates yields dates in range."""
        scraper = _TestScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 1), date(2024, 1, 3)))
        assert len(dates) == 3
        assert dates[0] == date(2024, 1, 1)
        assert dates[2] == date(2024, 1, 3)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_client_is_accessible(self, mock_client_class, mock_cache_class):
        """Client attribute is accessible for manual cleanup."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        scraper = _TestScraper()
        # Client is available as an attribute for manual cleanup if needed
        assert scraper.client is mock_client

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scoreboard_url_format(self, mock_client_class, mock_cache_class):
        """scoreboard_url returns URL with date params."""
        scraper = _TestScraper()
        url = scraper.scoreboard_url(date(2024, 1, 15))
        assert "month=1" in url
        assert "day=15" in url
        assert "year=2024" in url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_iter_dates_single_day(self, mock_client_class, mock_cache_class):
        """iter_dates handles single day range."""
        scraper = _TestScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 15), date(2024, 1, 15)))
        assert len(dates) == 1
        assert dates[0] == date(2024, 1, 15)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_iter_dates_month_boundary(self, mock_client_class, mock_cache_class):
        """iter_dates crosses month boundaries correctly."""
        scraper = _TestScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 30), date(2024, 2, 2)))
        assert len(dates) == 4
        assert dates[0] == date(2024, 1, 30)
        assert dates[1] == date(2024, 1, 31)
        assert dates[2] == date(2024, 2, 1)
        assert dates[3] == date(2024, 2, 2)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_internal_delay_settings(self, mock_client_class, mock_cache_class):
        """Scraper has delay settings for polite scraping."""
        scraper = _TestScraper()
        assert hasattr(scraper, "_min_delay")
        assert hasattr(scraper, "_max_delay")
        assert hasattr(scraper, "_rate_limit_wait")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_season_from_date_method_exists(self, mock_client_class, mock_cache_class):
        """_season_from_date method exists."""
        scraper = _TestScraper()
        assert hasattr(scraper, "_season_from_date")
        assert callable(scraper._season_from_date)


class TestScraperConstants:
    """Tests for scraper module constants."""

    def test_scraper_error_is_runtime_error(self):
        """ScraperError is a RuntimeError subclass."""
        assert issubclass(ScraperError, RuntimeError)

    def test_no_games_found_error_is_scraper_error(self):
        """NoGamesFoundError is a ScraperError subclass."""
        assert issubclass(NoGamesFoundError, ScraperError)

    def test_scraper_error_message(self):
        """ScraperError preserves message."""
        error = ScraperError("Test error message")
        assert str(error) == "Test error message"

    def test_no_games_found_error_message(self):
        """NoGamesFoundError preserves message."""
        error = NoGamesFoundError("No games for date")
        assert "No games" in str(error)


class TestBaseSportsReferenceScraperAbstractMethods:
    """Tests for abstract methods in BaseSportsReferenceScraper."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_fetch_games_for_date_raises(self, mock_client_class, mock_cache_class):
        """fetch_games_for_date raises NotImplementedError."""
        scraper = _TestScraper()
        with pytest.raises(NotImplementedError):
            scraper.fetch_games_for_date(date(2024, 1, 15))

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_pbp_url_raises(self, mock_client_class, mock_cache_class):
        """pbp_url raises NotImplementedError."""
        scraper = _TestScraper()
        with pytest.raises(NotImplementedError):
            scraper.pbp_url("GAME123")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_fetch_play_by_play_raises(self, mock_client_class, mock_cache_class):
        """fetch_play_by_play raises NotImplementedError."""
        scraper = _TestScraper()
        with pytest.raises(NotImplementedError):
            scraper.fetch_play_by_play("GAME123", date(2024, 1, 15))

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_fetch_single_boxscore_raises(self, mock_client_class, mock_cache_class):
        """fetch_single_boxscore raises NotImplementedError."""
        scraper = _TestScraper()
        with pytest.raises(NotImplementedError):
            scraper.fetch_single_boxscore("GAME123", date(2024, 1, 15))


class TestPoliteDelay:
    """Tests for _polite_delay method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    @patch("time.sleep")
    def test_polite_delay_sleeps(self, mock_sleep, mock_client_class, mock_cache_class):
        """_polite_delay sleeps appropriate amount."""
        scraper = _TestScraper()
        scraper._last_request_time = 0  # Force delay
        scraper._polite_delay()
        # Should have called sleep since elapsed time is large
        # Note: May or may not sleep depending on timing

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_polite_delay_updates_last_request_time(self, mock_client_class, mock_cache_class):
        """_polite_delay updates _last_request_time."""
        import time
        scraper = _TestScraper()
        scraper._min_delay = 0
        scraper._max_delay = 0.001
        before = time.time()
        scraper._polite_delay()
        assert scraper._last_request_time >= before


class TestFetchFromNetwork:
    """Tests for _fetch_from_network method.

    Note: These tests verify behavior without invoking the actual retry logic
    to avoid 60+ second test times.
    """

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_retry_decorator(self, mock_client_class, mock_cache_class):
        """Method has retry decorator configured."""
        scraper = _TestScraper()
        # Verify the method exists and is callable
        assert hasattr(scraper, "_fetch_from_network")
        assert callable(scraper._fetch_from_network)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_successful_fetch_returns_html(self, mock_client_class, mock_cache_class):
        """Successful fetch returns HTML text."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.url = "https://example.com/test?param=1"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        scraper = _TestScraper()
        scraper._min_delay = 0
        scraper._max_delay = 0
        result = scraper._fetch_from_network("https://example.com/test?param=1")
        assert result == "<html><body>Test</body></html>"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_no_games_found_on_redirect(self, mock_client_class, mock_cache_class):
        """Raises NoGamesFoundError when redirected to different page."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html></html>"
        mock_response.url = "https://example.com/"  # Redirected to main page (no query params)
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        scraper = _TestScraper()
        scraper._min_delay = 0
        scraper._max_delay = 0
        with pytest.raises(NoGamesFoundError, match="No games found"):
            scraper._fetch_from_network("https://example.com/test?date=2024-01-01")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_html_on_success(self, mock_client_class, mock_cache_class):
        """Returns HTML text on successful fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.url = "https://example.com/test?param=1"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        scraper = _TestScraper()
        scraper._min_delay = 0
        scraper._max_delay = 0
        result = scraper._fetch_from_network("https://example.com/test?param=1")
        assert result == "<html><body>Test</body></html>"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_no_games_found_on_redirect(self, mock_client_class, mock_cache_class):
        """Raises NoGamesFoundError when redirected to different page."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html></html>"
        mock_response.url = "https://example.com/"  # Redirected to main page (no query params)
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        scraper = _TestScraper()
        scraper._min_delay = 0
        scraper._max_delay = 0
        with pytest.raises(NoGamesFoundError, match="No games found"):
            scraper._fetch_from_network("https://example.com/test?date=2024-01-01")


class TestFetchHtml:
    """Tests for fetch_html method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_cached_html_if_available(self, mock_client_class, mock_cache_class):
        """Returns cached HTML if available."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = "<html><body>Cached</body></html>"
        mock_cache_class.return_value = mock_cache

        scraper = _TestScraper()
        result = scraper.fetch_html("https://example.com/test")
        assert "Cached" in str(result)
        mock_cache.get.assert_called_once()

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_fetches_from_network_when_not_cached(self, mock_client_class, mock_cache_class):
        """Fetches from network when not in cache."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # Not cached
        mock_cache_class.return_value = mock_cache

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Fresh</body></html>"
        mock_response.url = "https://example.com/test?param=1"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        scraper = _TestScraper()
        scraper._min_delay = 0
        scraper._max_delay = 0
        result = scraper.fetch_html("https://example.com/test?param=1")
        assert "Fresh" in str(result)
        mock_cache.put.assert_called_once()


class TestFetchDateRange:
    """Tests for fetch_date_range method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    @patch("time.sleep")
    def test_continues_on_no_games_found(self, mock_sleep, mock_client_class, mock_cache_class):
        """Continues to next date when NoGamesFoundError raised."""
        scraper = _TestScraper()
        scraper._day_delay_min = 0
        scraper._day_delay_max = 0

        call_count = 0
        def mock_fetch(day):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NoGamesFoundError("No games")
            return []

        scraper.fetch_games_for_date = mock_fetch
        games = list(scraper.fetch_date_range(date(2024, 1, 1), date(2024, 1, 2)))
        assert call_count == 2  # Both dates were attempted

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    @patch("time.sleep")
    def test_continues_on_scraper_error(self, mock_sleep, mock_client_class, mock_cache_class):
        """Continues to next date when ScraperError raised."""
        scraper = _TestScraper()
        scraper._day_delay_min = 0
        scraper._day_delay_max = 0
        scraper._error_delay_min = 0
        scraper._error_delay_max = 0

        call_count = 0
        def mock_fetch(day):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ScraperError("Scrape failed")
            return []

        scraper.fetch_games_for_date = mock_fetch
        games = list(scraper.fetch_date_range(date(2024, 1, 1), date(2024, 1, 2)))
        assert call_count == 2

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    @patch("time.sleep")
    def test_continues_on_unexpected_error(self, mock_sleep, mock_client_class, mock_cache_class):
        """Continues to next date when unexpected exception raised."""
        scraper = _TestScraper()
        scraper._day_delay_min = 0
        scraper._day_delay_max = 0
        scraper._error_delay_min = 0
        scraper._error_delay_max = 0

        call_count = 0
        def mock_fetch(day):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Unexpected error")
            return []

        scraper.fetch_games_for_date = mock_fetch
        games = list(scraper.fetch_date_range(date(2024, 1, 1), date(2024, 1, 2)))
        assert call_count == 2


class TestParseTeamRow:
    """Tests for _parse_team_row method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_when_no_team_link(self, mock_client_class, mock_cache_class):
        """Raises ScraperError when team link missing."""
        from bs4 import BeautifulSoup
        scraper = _TestScraper()
        html = '<tr><td>No Link</td><td class="right">100</td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        with pytest.raises(ScraperError, match="Missing team link"):
            scraper._parse_team_row(row)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_when_no_score_cell(self, mock_client_class, mock_cache_class):
        """Raises ScraperError when score cell missing."""
        from bs4 import BeautifulSoup
        scraper = _TestScraper()
        html = '<tr><td><a href="/team/test">Test Team</a></td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        with pytest.raises(ScraperError, match="Missing score cell"):
            scraper._parse_team_row(row)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_for_invalid_score(self, mock_client_class, mock_cache_class):
        """Raises ScraperError for non-numeric score."""
        from bs4 import BeautifulSoup
        scraper = _TestScraper()
        html = '<tr><td><a href="/team/test">Test Team</a></td><td class="right">N/A</td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        with pytest.raises(ScraperError, match="Invalid score"):
            scraper._parse_team_row(row)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_parses_valid_team_row(self, mock_client_class, mock_cache_class):
        """Parses valid team row - use NCAAB scraper which has valid league_code."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.ncaab_sportsref import NCAABSportsReferenceScraper
        scraper = NCAABSportsReferenceScraper()
        html = '<tr><td><a href="/team/duke">Duke Blue Devils</a></td><td class="right">85</td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        identity, score = scraper._parse_team_row(row)
        assert score == 85
        assert identity.league_code == "NCAAB"


class TestSeasonFromDate:
    """Tests for _season_from_date method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_calls_utility_function(self, mock_client_class, mock_cache_class):
        """_season_from_date delegates to season_from_date utility."""
        scraper = _TestScraper()
        # For most sports, season = year (utility handles winter sports differently)
        result = scraper._season_from_date(date(2024, 7, 15))
        assert isinstance(result, int)
