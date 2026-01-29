"""Tests for scrapers/nba_sportsref.py module."""

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


class TestNBASportsReferenceScraperModuleImports:
    """Tests for NBA scraper module imports."""

    def test_module_imports(self):
        """Module can be imported without errors."""
        from sports_scraper.scrapers import nba_sportsref
        assert hasattr(nba_sportsref, 'NBASportsReferenceScraper')

    def test_scraper_class_exists(self):
        """Scraper class exists and can be referenced."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        assert NBASportsReferenceScraper is not None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scraper_attributes(self, mock_client, mock_cache):
        """Scraper has NBA-specific attributes."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        assert scraper.sport == "nba"
        assert scraper.league_code == "NBA"


class TestNBASportsReferenceScraperUrls:
    """Tests for URL generation methods."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scoreboard_url_format(self, mock_client, mock_cache):
        """Scoreboard URL has correct format."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        url = scraper.scoreboard_url(date(2024, 1, 15))
        assert "month=1" in url
        assert "day=15" in url
        assert "year=2024" in url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scoreboard_url_different_dates(self, mock_client, mock_cache):
        """Scoreboard URL works for different dates."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()

        url1 = scraper.scoreboard_url(date(2024, 12, 25))
        assert "month=12" in url1
        assert "day=25" in url1

        url2 = scraper.scoreboard_url(date(2023, 6, 1))
        assert "month=6" in url2
        assert "year=2023" in url2
