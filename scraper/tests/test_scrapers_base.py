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
