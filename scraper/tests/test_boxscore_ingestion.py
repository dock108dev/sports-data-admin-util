"""Tests for services/boxscore_ingestion.py module."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


from sports_scraper.utils.date_utils import season_ending_year as _season_from_date


class TestSeasonFromDate:
    """Tests for _season_from_date function."""

    def test_october_returns_next_year(self):
        """October game belongs to next calendar year's season."""
        result = _season_from_date(date(2024, 10, 15))
        assert result == 2025

    def test_november_returns_next_year(self):
        """November game belongs to next calendar year's season."""
        result = _season_from_date(date(2024, 11, 20))
        assert result == 2025

    def test_december_returns_next_year(self):
        """December game belongs to next calendar year's season."""
        result = _season_from_date(date(2024, 12, 25))
        assert result == 2025

    def test_january_returns_same_year(self):
        """January game belongs to current calendar year's season."""
        result = _season_from_date(date(2025, 1, 15))
        assert result == 2025

    def test_april_returns_same_year(self):
        """April game belongs to current calendar year's season."""
        result = _season_from_date(date(2025, 4, 10))
        assert result == 2025

    def test_june_returns_same_year(self):
        """June game belongs to current calendar year's season."""
        result = _season_from_date(date(2025, 6, 15))
        assert result == 2025

    def test_september_returns_same_year(self):
        """September game (preseason) belongs to next calendar year's season."""
        result = _season_from_date(date(2024, 9, 30))
        assert result == 2024  # September < October, so same year

    def test_first_day_of_october(self):
        """October 1st game belongs to next calendar year's season."""
        result = _season_from_date(date(2024, 10, 1))
        assert result == 2025

    def test_last_day_of_september(self):
        """September 30th game belongs to current year's season."""
        result = _season_from_date(date(2024, 9, 30))
        assert result == 2024
