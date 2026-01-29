"""Tests for services/run_manager.py module."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
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


from sports_scraper.services.run_manager import ScrapeRunManager


class TestScrapeRunManagerImports:
    """Tests for ScrapeRunManager module imports."""

    def test_class_exists(self):
        """ScrapeRunManager class exists."""
        assert ScrapeRunManager is not None

    def test_class_is_callable(self):
        """ScrapeRunManager can be instantiated."""
        # Note: Full instantiation requires scrapers to be available
        # Just verify it's a class
        assert callable(ScrapeRunManager)


class TestScrapeRunManagerAttributes:
    """Tests for ScrapeRunManager class attributes."""

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_init_creates_scrapers(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Initializes with scrapers."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert mock_scrapers.called

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_init_creates_odds_sync(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Initializes with odds synchronizer."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert mock_odds.called

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_has_supported_leagues(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Has supported league lists."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert hasattr(manager, "_supported_social_leagues")
        assert hasattr(manager, "_supported_live_pbp_leagues")
