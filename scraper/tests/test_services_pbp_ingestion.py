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
    ingest_pbp_via_nhl_api,
    ingest_pbp_via_ncaab_api,
    _populate_nhl_game_ids,
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
        )

        assert result == []

    def test_queries_nhl_games(self):
        """Queries games with NHL league filter."""
        mock_session = MagicMock()
        mock_league = MagicMock(id=1)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Setup query chain
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query

        result = select_games_for_pbp_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
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
        )

        assert result == []


class TestPopulateNhlGameIds:
    """Tests for _populate_nhl_game_ids function."""

    @patch("sports_scraper.services.pbp_ingestion.NHLLiveFeedClient")
    def test_populates_game_ids_from_schedule(self, mock_client_class):
        """Populates NHL game IDs from schedule API."""
        mock_session = MagicMock()

        # Mock league
        mock_league = MagicMock(id=1)

        # Mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock schedule response
        mock_client.fetch_schedule.return_value = [
            MagicMock(
                game_id=2024020001,
                home_team=MagicMock(abbreviation="BOS"),
                away_team=MagicMock(abbreviation="NYR"),
                game_date=datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc),
            ),
        ]

        # Mock team query
        mock_team = MagicMock(id=10)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_team

        # Mock game query - game not found, then return None
        mock_session.query.return_value.filter.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = None

        _populate_nhl_game_ids(
            mock_session,
            mock_league,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        mock_client.fetch_schedule.assert_called_once()


class TestIngestPbpViaNhlApi:
    """Tests for ingest_pbp_via_nhl_api function."""

    @patch("sports_scraper.services.pbp_ingestion.NHLLiveFeedClient")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_nhl_api")
    def test_returns_zero_when_no_games(self, mock_select, mock_client_class):
        """Returns 0 when no games need PBP."""
        mock_session = MagicMock()
        mock_select.return_value = []

        result = ingest_pbp_via_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
        )

        assert result == 0

    @patch("sports_scraper.services.pbp_ingestion.NHLLiveFeedClient")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_nhl_api")
    @patch("sports_scraper.services.pbp_ingestion.persist_plays")
    def test_ingests_plays_for_games(self, mock_persist, mock_select, mock_client_class):
        """Ingests PBP data for selected games."""
        mock_session = MagicMock()
        mock_select.return_value = [
            (1, 2024020001, date(2024, 1, 15)),
        ]

        # Mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock PBP response
        mock_pbp = MagicMock()
        mock_pbp.plays = [MagicMock(), MagicMock()]
        mock_client.fetch_pbp.return_value = mock_pbp

        result = ingest_pbp_via_nhl_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
        )

        assert result == 1
        mock_client.fetch_pbp.assert_called_once_with(2024020001)


class TestIngestPbpViaNcaabApi:
    """Tests for ingest_pbp_via_ncaab_api function."""

    @patch("sports_scraper.services.pbp_ingestion.NCAABLiveFeedClient")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_ncaab_api")
    def test_returns_zero_when_no_games(self, mock_select, mock_client_class):
        """Returns 0 when no games need PBP."""
        mock_session = MagicMock()
        mock_select.return_value = []

        result = ingest_pbp_via_ncaab_api(
            mock_session,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
        )

        assert result == 0
