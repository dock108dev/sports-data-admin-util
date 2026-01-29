"""Tests for services/pbp_ingestion.py module."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from sports_scraper.services.pbp_ingestion import (
    select_games_for_pbp_nhl_api,
    select_games_for_pbp_ncaab_api,
    ingest_pbp_via_sportsref,
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


class TestIngestPbpViaSportsref:
    """Tests for ingest_pbp_via_sportsref."""

    def test_returns_zero_when_no_scraper(self):
        """Returns (0, 0) when no scraper available."""
        mock_session = MagicMock()

        result = ingest_pbp_via_sportsref(
            mock_session,
            run_id=1,
            league_code="NBA",
            scraper=None,  # No scraper
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)

    @patch("sports_scraper.services.pbp_ingestion.upsert_plays")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_sportsref")
    def test_returns_zero_when_no_games(self, mock_select, mock_upsert):
        """Returns (0, 0) when no games selected."""
        mock_session = MagicMock()
        mock_scraper = MagicMock()
        mock_select.return_value = []

        result = ingest_pbp_via_sportsref(
            mock_session,
            run_id=1,
            league_code="NBA",
            scraper=mock_scraper,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)

    @patch("sports_scraper.services.pbp_ingestion.upsert_plays")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_sportsref")
    def test_handles_not_implemented(self, mock_select, mock_upsert):
        """Returns (0, 0) when scraper raises NotImplementedError."""
        mock_session = MagicMock()
        mock_scraper = MagicMock()
        mock_scraper.fetch_play_by_play.side_effect = NotImplementedError()
        mock_select.return_value = [(1, "BOS202401150", date(2024, 1, 15))]

        result = ingest_pbp_via_sportsref(
            mock_session,
            run_id=1,
            league_code="NBA",
            scraper=mock_scraper,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)

    @patch("sports_scraper.services.pbp_ingestion.upsert_plays")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_sportsref")
    def test_handles_fetch_exception(self, mock_select, mock_upsert):
        """Continues when fetch raises exception."""
        mock_session = MagicMock()
        mock_scraper = MagicMock()
        mock_scraper.fetch_play_by_play.side_effect = Exception("Fetch error")
        mock_select.return_value = [(1, "BOS202401150", date(2024, 1, 15))]

        result = ingest_pbp_via_sportsref(
            mock_session,
            run_id=1,
            league_code="NBA",
            scraper=mock_scraper,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)

    @patch("sports_scraper.services.pbp_ingestion.upsert_plays")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_sportsref")
    def test_successful_ingestion(self, mock_select, mock_upsert):
        """Successfully ingests PBP."""
        from sports_scraper.models import NormalizedPlay

        mock_session = MagicMock()
        mock_scraper = MagicMock()

        mock_payload = MagicMock()
        mock_payload.plays = [
            NormalizedPlay(play_index=1, quarter=1, game_clock="12:00", play_type="shot", description="test"),
        ]
        mock_scraper.fetch_play_by_play.return_value = mock_payload

        mock_select.return_value = [(1, "BOS202401150", date(2024, 1, 15))]
        mock_upsert.return_value = 1

        result = ingest_pbp_via_sportsref(
            mock_session,
            run_id=1,
            league_code="NBA",
            scraper=mock_scraper,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (1, 1)


class TestIngestPbpViaNhlApi:
    """Tests for ingest_pbp_via_nhl_api."""

    @patch("sports_scraper.services.pbp_ingestion._populate_nhl_game_ids")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_nhl_api")
    def test_returns_zero_when_no_games(self, mock_select, mock_populate):
        """Returns (0, 0) when no games selected."""
        mock_session = MagicMock()
        mock_select.return_value = []

        result = ingest_pbp_via_nhl_api(
            mock_session,
            run_id=1,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 10, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)

    @patch("sports_scraper.services.pbp_ingestion.upsert_plays")
    @patch("sports_scraper.live.nhl.NHLLiveFeedClient")
    @patch("sports_scraper.services.pbp_ingestion._populate_nhl_game_ids")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_nhl_api")
    def test_successful_ingestion(self, mock_select, mock_populate, mock_client_class, mock_upsert):
        """Successfully ingests PBP."""
        from sports_scraper.models import NormalizedPlay

        mock_session = MagicMock()
        mock_select.return_value = [(1, 2025020001)]

        mock_client = MagicMock()
        mock_payload = MagicMock()
        mock_payload.plays = [
            NormalizedPlay(play_index=1, quarter=1, game_clock="12:00", play_type="shot", description="test"),
        ]
        mock_client.fetch_play_by_play.return_value = mock_payload
        mock_client_class.return_value = mock_client

        mock_session.query.return_value.get.return_value = None  # No game found
        mock_upsert.return_value = 1

        result = ingest_pbp_via_nhl_api(
            mock_session,
            run_id=1,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 10, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (1, 1)

    @patch("sports_scraper.live.nhl.NHLLiveFeedClient")
    @patch("sports_scraper.services.pbp_ingestion._populate_nhl_game_ids")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_nhl_api")
    def test_handles_empty_pbp_response(self, mock_select, mock_populate, mock_client_class):
        """Handles empty PBP response."""
        mock_session = MagicMock()
        mock_select.return_value = [(1, 2025020001)]

        mock_client = MagicMock()
        mock_payload = MagicMock()
        mock_payload.plays = []
        mock_client.fetch_play_by_play.return_value = mock_payload
        mock_client_class.return_value = mock_client

        result = ingest_pbp_via_nhl_api(
            mock_session,
            run_id=1,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 10, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)

    @patch("sports_scraper.live.nhl.NHLLiveFeedClient")
    @patch("sports_scraper.services.pbp_ingestion._populate_nhl_game_ids")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_nhl_api")
    def test_handles_fetch_exception(self, mock_select, mock_populate, mock_client_class):
        """Handles fetch exception."""
        mock_session = MagicMock()
        mock_select.return_value = [(1, 2025020001)]

        mock_client = MagicMock()
        mock_client.fetch_play_by_play.side_effect = Exception("Fetch error")
        mock_client_class.return_value = mock_client

        result = ingest_pbp_via_nhl_api(
            mock_session,
            run_id=1,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 10, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)


class TestIngestPbpViaNcaabApi:
    """Tests for ingest_pbp_via_ncaab_api."""

    @patch("sports_scraper.services.boxscore_ingestion._populate_ncaab_game_ids")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_ncaab_api")
    def test_returns_zero_when_no_games(self, mock_select, mock_populate):
        """Returns (0, 0) when no games selected."""
        mock_session = MagicMock()
        mock_select.return_value = []

        result = ingest_pbp_via_ncaab_api(
            mock_session,
            run_id=1,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)

    @patch("sports_scraper.services.pbp_ingestion.upsert_plays")
    @patch("sports_scraper.live.ncaab.NCAABLiveFeedClient")
    @patch("sports_scraper.services.boxscore_ingestion._populate_ncaab_game_ids")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_ncaab_api")
    def test_successful_ingestion(self, mock_select, mock_populate, mock_client_class, mock_upsert):
        """Successfully ingests PBP."""
        from sports_scraper.models import NormalizedPlay

        mock_session = MagicMock()
        mock_select.return_value = [(1, 123456)]

        mock_client = MagicMock()
        mock_payload = MagicMock()
        mock_payload.plays = [
            NormalizedPlay(play_index=1, quarter=1, game_clock="20:00", play_type="shot", description="test"),
        ]
        mock_client.fetch_play_by_play.return_value = mock_payload
        mock_client_class.return_value = mock_client

        mock_session.query.return_value.get.return_value = None
        mock_upsert.return_value = 1

        result = ingest_pbp_via_ncaab_api(
            mock_session,
            run_id=1,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (1, 1)

    @patch("sports_scraper.live.ncaab.NCAABLiveFeedClient")
    @patch("sports_scraper.services.boxscore_ingestion._populate_ncaab_game_ids")
    @patch("sports_scraper.services.pbp_ingestion.select_games_for_pbp_ncaab_api")
    def test_handles_empty_pbp_response(self, mock_select, mock_populate, mock_client_class):
        """Handles empty PBP response."""
        mock_session = MagicMock()
        mock_select.return_value = [(1, 123456)]

        mock_client = MagicMock()
        mock_payload = MagicMock()
        mock_payload.plays = []
        mock_client.fetch_play_by_play.return_value = mock_payload
        mock_client_class.return_value = mock_client

        result = ingest_pbp_via_ncaab_api(
            mock_session,
            run_id=1,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            only_missing=True,
            updated_before=None,
        )

        assert result == (0, 0)


class TestPopulateNhlGameIds:
    """Tests for _populate_nhl_game_ids."""

    def test_returns_zero_when_no_league(self):
        """Returns 0 when NHL league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = _populate_nhl_game_ids(
            mock_session,
            run_id=1,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 10, 31),
        )

        assert result == 0


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

    def test_has_sportsref_function(self):
        """Module has sportsref function."""
        from sports_scraper.services import pbp_ingestion
        assert hasattr(pbp_ingestion, 'ingest_pbp_via_sportsref')
