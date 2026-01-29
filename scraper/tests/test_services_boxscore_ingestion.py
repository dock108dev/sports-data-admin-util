"""Tests for services/boxscore_ingestion.py module."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

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
    ingest_boxscores_via_nhl_api,
    ingest_boxscores_via_ncaab_api,
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

    def test_queries_nhl_games(self):
        """Queries games with NHL league filter."""
        mock_session = MagicMock()
        mock_league = MagicMock(id=1)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Setup query chain to return empty results
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query

        result = select_games_for_boxscores_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=False,
            updated_before=None,
        )

        assert result == []
        assert mock_session.query.called


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


class TestIngestBoxscoresViaNhlApi:
    """Tests for ingest_boxscores_via_nhl_api function."""

    @patch("sports_scraper.services.boxscore_ingestion.NHLLiveFeedClient")
    @patch("sports_scraper.services.boxscore_ingestion.select_games_for_boxscores_nhl_api")
    def test_returns_zero_when_no_games(self, mock_select, mock_client_class):
        """Returns 0 when no games need boxscores."""
        mock_session = MagicMock()
        mock_select.return_value = []

        result = ingest_boxscores_via_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == 0

    @patch("sports_scraper.services.boxscore_ingestion.NHLLiveFeedClient")
    @patch("sports_scraper.services.boxscore_ingestion.select_games_for_boxscores_nhl_api")
    @patch("sports_scraper.services.boxscore_ingestion.persist_game_payload")
    def test_ingests_games_with_boxscores(self, mock_persist, mock_select, mock_client_class):
        """Ingests boxscores for selected games."""
        mock_session = MagicMock()
        mock_select.return_value = [
            (1, 2024020001, date(2024, 1, 15)),
        ]

        # Mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock boxscore response
        mock_boxscore = MagicMock()
        mock_boxscore.team_boxscores = [MagicMock(), MagicMock()]
        mock_boxscore.player_boxscores = []
        mock_client.fetch_boxscore.return_value = mock_boxscore

        result = ingest_boxscores_via_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == 1
        mock_client.fetch_boxscore.assert_called_once_with(2024020001)


class TestIngestBoxscoresViaNcaabApi:
    """Tests for ingest_boxscores_via_ncaab_api function."""

    @patch("sports_scraper.services.boxscore_ingestion.NCAABLiveFeedClient")
    @patch("sports_scraper.services.boxscore_ingestion.select_games_for_boxscores_ncaab_api")
    def test_returns_zero_when_no_games(self, mock_select, mock_client_class):
        """Returns 0 when no games need boxscores."""
        mock_session = MagicMock()
        mock_select.return_value = []

        result = ingest_boxscores_via_ncaab_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == 0
