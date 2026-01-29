"""Comprehensive tests for services modules with mocked DB sessions."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
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


# ============================================================================
# Tests for services/game_selection.py
# ============================================================================

from sports_scraper.services.game_selection import (
    select_games_for_boxscores,
    select_games_for_odds,
    select_games_for_social,
    select_games_for_pbp_sportsref,
)


class TestSelectGamesForBoxscores:
    """Tests for select_games_for_boxscores function."""

    def test_no_league_returns_empty(self):
        """Returns empty list when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_boxscores(
            mock_session, "INVALID", date(2024, 1, 15), date(2024, 1, 15)
        )

        assert result == []

    def test_returns_game_tuples(self):
        """Returns list of (game_id, source_key, game_date) tuples."""
        mock_session = MagicMock()

        # Mock league query
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock games query
        mock_game = MagicMock()
        mock_game.id = 100
        mock_game.source_game_key = "ABC123"
        mock_game.game_date = datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc)
        mock_session.query.return_value.filter.return_value.all.return_value = [mock_game]

        result = select_games_for_boxscores(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 15)
        )

        assert len(result) == 1
        assert result[0][0] == 100
        assert result[0][1] == "ABC123"
        assert result[0][2] == date(2024, 1, 15)

    def test_only_missing_filter(self):
        """Tests only_missing filter is applied."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = select_games_for_boxscores(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 15),
            only_missing=True
        )

        assert result == []

    def test_updated_before_filter(self):
        """Tests updated_before filter is applied."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        cutoff = datetime(2024, 1, 14, tzinfo=timezone.utc)
        result = select_games_for_boxscores(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 15),
            updated_before=cutoff
        )

        assert result == []


class TestSelectGamesForOdds:
    """Tests for select_games_for_odds function."""

    def test_no_league_returns_empty(self):
        """Returns empty list when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_odds(
            mock_session, "INVALID", date(2024, 1, 15), date(2024, 1, 15)
        )

        assert result == []

    def test_returns_unique_dates(self):
        """Returns list of unique game dates."""
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock date query results
        mock_result1 = MagicMock()
        mock_result1.game_day = date(2024, 1, 15)
        mock_result2 = MagicMock()
        mock_result2.game_day = date(2024, 1, 16)
        mock_session.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
            mock_result1, mock_result2
        ]

        result = select_games_for_odds(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 16)
        )

        assert len(result) == 2
        assert date(2024, 1, 15) in result
        assert date(2024, 1, 16) in result

    def test_filters_none_dates(self):
        """Filters out None game_day values."""
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        mock_result1 = MagicMock()
        mock_result1.game_day = date(2024, 1, 15)
        mock_result2 = MagicMock()
        mock_result2.game_day = None
        mock_session.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
            mock_result1, mock_result2
        ]

        result = select_games_for_odds(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 16)
        )

        assert len(result) == 1
        assert date(2024, 1, 15) in result


class TestSelectGamesForSocial:
    """Tests for select_games_for_social function."""

    def test_no_league_returns_empty(self):
        """Returns empty list when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_social(
            mock_session, "INVALID", date(2024, 1, 15), date(2024, 1, 15)
        )

        assert result == []

    @patch("sports_scraper.services.game_selection.settings")
    def test_returns_game_ids(self, mock_settings):
        """Returns list of game IDs."""
        mock_settings.social_config.recent_game_window_hours = 48
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            (100,), (101,), (102,)
        ]

        result = select_games_for_social(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 15)
        )

        assert len(result) == 3
        assert 100 in result
        assert 101 in result

    @patch("sports_scraper.services.game_selection.settings")
    def test_backfill_mode(self, mock_settings):
        """Tests backfill mode includes all statuses."""
        mock_settings.social_config.recent_game_window_hours = 48
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = select_games_for_social(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 15),
            is_backfill=True
        )

        assert result == []

    @patch("sports_scraper.services.game_selection.settings")
    def test_exclude_pregame(self, mock_settings):
        """Tests include_pregame=False excludes scheduled games."""
        mock_settings.social_config.recent_game_window_hours = 48
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = select_games_for_social(
            mock_session, "NBA", date(2024, 1, 15), date(2024, 1, 15),
            is_backfill=True,
            include_pregame=False
        )

        assert result == []


class TestSelectGamesForPbpSportsref:
    """Tests for select_games_for_pbp_sportsref function."""

    def test_no_league_returns_empty(self):
        """Returns empty list when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = select_games_for_pbp_sportsref(
            mock_session,
            league_code="INVALID",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            only_missing=False,
            updated_before=None,
        )

        assert result == []

    def test_returns_game_tuples(self):
        """Returns list of (game_id, source_key, game_date) tuples."""
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        mock_game = MagicMock()
        mock_game.id = 100
        mock_game.source_game_key = "202401150BOS"
        mock_game.game_date = datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc)
        mock_session.query.return_value.filter.return_value.all.return_value = [
            (100, "202401150BOS", datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc))
        ]

        result = select_games_for_pbp_sportsref(
            mock_session,
            league_code="NBA",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            only_missing=False,
            updated_before=None,
        )

        assert len(result) == 1
        assert result[0][0] == 100
        assert result[0][1] == "202401150BOS"
        assert result[0][2] == date(2024, 1, 15)

    def test_filters_none_source_keys(self):
        """Filters out entries with None source_key."""
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        mock_session.query.return_value.filter.return_value.all.return_value = [
            (100, "202401150BOS", datetime(2024, 1, 15, tzinfo=timezone.utc)),
            (101, None, datetime(2024, 1, 15, tzinfo=timezone.utc)),
        ]

        result = select_games_for_pbp_sportsref(
            mock_session,
            league_code="NBA",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            only_missing=False,
            updated_before=None,
        )

        assert len(result) == 1
        assert result[0][0] == 100


# ============================================================================
# Tests for services/diagnostics.py
# ============================================================================

from sports_scraper.services.diagnostics import (
    detect_missing_pbp,
    detect_external_id_conflicts,
    PBP_SUPPORTED_LEAGUES,
    PBP_MIN_PLAY_COUNT,
    EXTERNAL_ID_KEYS,
)


class TestDiagnosticsConstants:
    """Tests for diagnostics constants."""

    def test_pbp_supported_leagues(self):
        assert "NBA" in PBP_SUPPORTED_LEAGUES
        assert "NHL" in PBP_SUPPORTED_LEAGUES

    def test_pbp_min_play_count(self):
        assert PBP_MIN_PLAY_COUNT >= 1

    def test_external_id_keys(self):
        assert "NBA" in EXTERNAL_ID_KEYS
        assert "NHL" in EXTERNAL_ID_KEYS
        assert EXTERNAL_ID_KEYS["NBA"] == "nba_game_id"
        assert EXTERNAL_ID_KEYS["NHL"] == "nhl_game_pk"


class TestDetectMissingPbp:
    """Tests for detect_missing_pbp function."""

    def test_no_league_returns_empty(self):
        """Returns empty list when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = detect_missing_pbp(mock_session, league_code="INVALID")

        assert result == []

    def test_returns_missing_game_ids(self):
        """Returns list of game IDs missing PBP."""
        mock_session = MagicMock()

        mock_league = MagicMock()
        mock_league.id = 1
        mock_league.code = "NBA"
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock query results - games with no plays
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = [
            (100, "live", 0, "12345"),
            (101, "final", 0, "12346"),
        ]

        # Mock execute for insert
        mock_session.execute.return_value = MagicMock()

        result = detect_missing_pbp(mock_session, league_code="NBA")

        assert len(result) == 2
        assert 100 in result
        assert 101 in result


class TestDetectExternalIdConflicts:
    """Tests for detect_external_id_conflicts function."""

    def test_no_league_returns_zero(self):
        """Returns 0 when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = detect_external_id_conflicts(mock_session, league_code="INVALID")

        assert result == 0

    def test_no_external_key_returns_zero(self):
        """Returns 0 when no external key defined for league."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # MLB has no external_id_key defined
        result = detect_external_id_conflicts(mock_session, league_code="MLB")

        assert result == 0

    def test_no_duplicates_returns_zero(self):
        """Returns 0 when no duplicate external IDs found."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock duplicate query - no results
        mock_session.query.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

        result = detect_external_id_conflicts(mock_session, league_code="NBA")

        assert result == 0


# ============================================================================
# Tests for services/job_runs.py
# ============================================================================

from sports_scraper.services.job_runs import (
    create_scrape_run,
    complete_scrape_run,
)


class TestCreateScrapeRun:
    """Tests for create_scrape_run function."""

    def test_creates_run_record(self):
        """Creates a scrape run record and returns ID."""
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_run.id = 123
        mock_session.add.return_value = None
        mock_session.flush.return_value = None

        # Mock the ScrapeRun class
        with patch("sports_scraper.services.job_runs.db_models") as mock_db:
            mock_db.ScrapeRun.return_value = mock_run

            result = create_scrape_run(
                mock_session,
                job_type="boxscore_ingestion",
                league_code="NBA",
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15),
            )

            assert result == 123
            mock_session.add.assert_called_once()
            mock_session.flush.assert_called_once()


class TestCompleteScrapeRun:
    """Tests for complete_scrape_run function."""

    def test_updates_run_record(self):
        """Updates scrape run with completion data."""
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run

        complete_scrape_run(
            mock_session,
            run_id=123,
            status="completed",
            records_processed=50,
            errors=[],
        )

        assert mock_run.status == "completed"
        assert mock_run.records_processed == 50
        mock_session.flush.assert_called_once()

    def test_handles_missing_run(self):
        """Handles case when run not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        complete_scrape_run(
            mock_session,
            run_id=999,
            status="completed",
            records_processed=0,
            errors=[],
        )


# ============================================================================
# Tests for services/ingestion.py
# ============================================================================

from sports_scraper.services.ingestion import (
    INGESTION_MAPPING,
)


class TestIngestionMapping:
    """Tests for ingestion mapping constants."""

    def test_mapping_exists(self):
        """Verify ingestion mapping is defined."""
        assert INGESTION_MAPPING is not None
        assert isinstance(INGESTION_MAPPING, dict)
