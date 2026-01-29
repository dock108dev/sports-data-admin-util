"""Tests for services/boxscore_ingestion.py module."""

from __future__ import annotations

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


from sports_scraper.services.boxscore_ingestion import (
    _season_from_date,
    select_games_for_boxscores_nhl_api,
    select_games_for_boxscores_ncaab_api,
)


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

    def test_september_returns_same_year(self):
        """September is before October, so same year."""
        result = _season_from_date(date(2024, 9, 30))
        assert result == 2024


class TestSelectGamesForBoxscoresNhlApi:
    """Tests for select_games_for_boxscores_nhl_api function."""

    def test_returns_empty_when_no_league(self):
        """Returns empty list when NHL league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_boxscores_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == []


class TestSelectGamesForBoxscoresNcaabApi:
    """Tests for select_games_for_boxscores_ncaab_api function."""

    def test_returns_empty_when_no_league(self):
        """Returns empty list when NCAAB league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_boxscores_ncaab_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == []


class TestModuleImports:
    """Tests for module imports."""

    def test_has_nhl_ingestion_function(self):
        """Module has NHL ingestion function."""
        from sports_scraper.services import boxscore_ingestion
        assert hasattr(boxscore_ingestion, 'ingest_boxscores_via_nhl_api')

    def test_has_ncaab_ingestion_function(self):
        """Module has NCAAB ingestion function."""
        from sports_scraper.services import boxscore_ingestion
        assert hasattr(boxscore_ingestion, 'ingest_boxscores_via_ncaab_api')
