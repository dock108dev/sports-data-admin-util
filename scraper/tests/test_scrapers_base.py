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
