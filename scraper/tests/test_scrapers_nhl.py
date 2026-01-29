"""Tests for scrapers/nhl_sportsref.py module."""

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


from sports_scraper.scrapers.nhl_sportsref import NHLSportsReferenceScraper


class TestNHLSportsReferenceScraperModuleImports:
    """Tests for NHL scraper module imports."""

    def test_module_imports(self):
        """Module can be imported without errors."""
        from sports_scraper.scrapers import nhl_sportsref
        assert hasattr(nhl_sportsref, 'NHLSportsReferenceScraper')

    def test_scraper_class_exists(self):
        """Scraper class exists and can be referenced."""
        from sports_scraper.scrapers.nhl_sportsref import NHLSportsReferenceScraper
        assert NHLSportsReferenceScraper is not None


class TestNHLSportsReferenceScraper:
    """Tests for NHLSportsReferenceScraper class."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scraper_attributes(self, mock_client, mock_cache):
        """Scraper has NHL-specific attributes."""
        scraper = NHLSportsReferenceScraper()
        assert scraper.sport == "hockey"
        assert scraper.league_code == "NHL"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_base_url(self, mock_client, mock_cache):
        """Scraper has base URL for hockey-reference.com."""
        scraper = NHLSportsReferenceScraper()
        assert "hockey-reference.com" in scraper.base_url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scoreboard_url_format(self, mock_client, mock_cache):
        """Scoreboard URL has correct format."""
        scraper = NHLSportsReferenceScraper()
        url = scraper.scoreboard_url(date(2024, 1, 15))
        assert "month=1" in url or "2024-01" in url
        assert "day=15" in url or "-15" in url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_boxscore_url_format(self, mock_client, mock_cache):
        """Boxscore URL has correct format."""
        scraper = NHLSportsReferenceScraper()
        # Test with a sample game key
        if hasattr(scraper, 'boxscore_url'):
            url = scraper.boxscore_url("202401150BOS")
            assert "202401150BOS" in url
