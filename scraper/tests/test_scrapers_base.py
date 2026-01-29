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


from sports_scraper.scrapers.base import BaseSportsReferenceScraper, ScraperError


class TestScraperError:
    """Tests for ScraperError exception."""

    def test_creates_exception_with_message(self):
        """Creates exception with message."""
        error = ScraperError("Test error message")
        assert str(error) == "Test error message"

    def test_is_exception_subclass(self):
        """ScraperError is an Exception subclass."""
        assert issubclass(ScraperError, Exception)


class TestBaseSportsReferenceScraper:
    """Tests for BaseSportsReferenceScraper class."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_init_creates_client(self, mock_client_class, mock_cache_class):
        """Initializes with HTTP client."""
        scraper = BaseSportsReferenceScraper()

        assert mock_client_class.called
        assert scraper.client is not None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_init_creates_cache(self, mock_client_class, mock_cache_class):
        """Initializes with HTML cache."""
        scraper = BaseSportsReferenceScraper()

        assert mock_cache_class.called
        assert scraper.cache is not None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_sport_attribute(self, mock_client_class, mock_cache_class):
        """Has sport attribute (empty string by default)."""
        scraper = BaseSportsReferenceScraper()

        assert hasattr(scraper, "sport")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_league_code_attribute(self, mock_client_class, mock_cache_class):
        """Has league_code attribute."""
        scraper = BaseSportsReferenceScraper()

        assert hasattr(scraper, "league_code")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_base_url_attribute(self, mock_client_class, mock_cache_class):
        """Has base_url attribute."""
        scraper = BaseSportsReferenceScraper()

        assert hasattr(scraper, "base_url")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_fetch_html_gets_from_cache_first(self, mock_client_class, mock_cache_class):
        """Fetches HTML from cache if available."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = "<html>cached</html>"
        mock_cache_class.return_value = mock_cache

        scraper = BaseSportsReferenceScraper()
        result = scraper._fetch_html("http://example.com/test")

        mock_cache.get.assert_called_once()
        assert result == "<html>cached</html>"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_fetch_html_fetches_from_client_on_cache_miss(self, mock_client_class, mock_cache_class):
        """Fetches HTML from client when cache misses."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache_class.return_value = mock_cache

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>fresh</html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        scraper = BaseSportsReferenceScraper()
        result = scraper._fetch_html("http://example.com/test")

        mock_client.get.assert_called_once()
        mock_cache.set.assert_called_once()
        assert result == "<html>fresh</html>"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_close_closes_client(self, mock_client_class, mock_cache_class):
        """Close method closes HTTP client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        scraper = BaseSportsReferenceScraper()
        scraper.close()

        mock_client.close.assert_called_once()
