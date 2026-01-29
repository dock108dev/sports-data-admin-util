"""Tests for services/pbp_ingestion.py module."""

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


from sports_scraper.services.pbp_ingestion import (
    select_games_for_pbp_nhl_api,
    select_games_for_pbp_ncaab_api,
)


class TestSelectGamesForPbpNhlApi:
    """Tests for select_games_for_pbp_nhl_api function."""

    def test_returns_empty_when_no_league(self):
        """Returns empty list when NHL league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_pbp_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == []


class TestSelectGamesForPbpNcaabApi:
    """Tests for select_games_for_pbp_ncaab_api function."""

    def test_returns_empty_when_no_league(self):
        """Returns empty list when NCAAB league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_pbp_ncaab_api(
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
        from sports_scraper.services import pbp_ingestion
        assert hasattr(pbp_ingestion, 'ingest_pbp_via_nhl_api')

    def test_has_ncaab_ingestion_function(self):
        """Module has NCAAB ingestion function."""
        from sports_scraper.services import pbp_ingestion
        assert hasattr(pbp_ingestion, 'ingest_pbp_via_ncaab_api')

    def test_has_populate_function(self):
        """Module has populate function."""
        from sports_scraper.services import pbp_ingestion
        assert hasattr(pbp_ingestion, '_populate_nhl_game_ids')
