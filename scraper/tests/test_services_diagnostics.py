"""Tests for services/diagnostics.py module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sports_scraper.services.diagnostics import (
    CONFLICT_OVERLAP_WINDOW_HOURS,
    EXTERNAL_ID_KEYS,
    PBP_MIN_PLAY_COUNT,
    PBP_SUPPORTED_LEAGUES,
    detect_external_id_conflicts,
    detect_missing_pbp,
)


class TestConstants:
    """Tests for module constants."""

    def test_pbp_supported_leagues(self):
        """PBP supported leagues are NBA and NHL."""
        assert "NBA" in PBP_SUPPORTED_LEAGUES
        assert "NHL" in PBP_SUPPORTED_LEAGUES

    def test_pbp_min_play_count(self):
        """Minimum play count is 1."""
        assert PBP_MIN_PLAY_COUNT == 1

    def test_conflict_overlap_window(self):
        """Conflict overlap window is 6 hours."""
        assert CONFLICT_OVERLAP_WINDOW_HOURS == 6

    def test_external_id_keys(self):
        """External ID keys are defined for NBA and NHL."""
        assert EXTERNAL_ID_KEYS["NBA"] == "nba_game_id"
        assert EXTERNAL_ID_KEYS["NHL"] == "nhl_game_pk"


class TestDetectMissingPbp:
    """Tests for detect_missing_pbp function."""

    def test_returns_empty_when_no_league(self):
        """Returns empty list when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = detect_missing_pbp(mock_session, league_code="UNKNOWN")

        assert result == []

    @patch("sports_scraper.services.diagnostics.now_utc")
    def test_returns_empty_when_no_missing_games(self, mock_now):
        """Returns empty list when no games are missing PBP."""
        mock_now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Query chain returns empty list
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

        result = detect_missing_pbp(mock_session, league_code="NBA")

        # Should have deleted all missing PBP records since none found
        assert result == []

    @patch("sports_scraper.services.diagnostics.now_utc")
    @patch("sports_scraper.services.diagnostics.insert")
    def test_detects_missing_pbp_for_nba(self, mock_insert, mock_now):
        """Detects missing PBP for NBA (supported league)."""
        mock_now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock query to return games with missing PBP
        mock_row = (100, "live", 0, "2024010100")  # game_id, status, play_count, external_id
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = [
            mock_row
        ]

        # Mock insert statement
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_update.return_value = mock_stmt
        mock_insert.return_value = MagicMock()
        mock_insert.return_value.values.return_value = mock_stmt

        result = detect_missing_pbp(mock_session, league_code="NBA")

        assert 100 in result

    @patch("sports_scraper.services.diagnostics.now_utc")
    @patch("sports_scraper.services.diagnostics.insert")
    def test_detects_missing_pbp_for_unsupported_league(self, mock_insert, mock_now):
        """Detects missing PBP for unsupported league with 'not_supported' reason."""
        mock_now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock query to return games with missing PBP (without external_id since unsupported)
        mock_row = (100, "final", 0)  # game_id, status, play_count
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = [
            mock_row
        ]

        # Mock insert statement
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_update.return_value = mock_stmt
        mock_insert.return_value = MagicMock()
        mock_insert.return_value.values.return_value = mock_stmt

        result = detect_missing_pbp(mock_session, league_code="NCAAF")

        assert 100 in result

    @patch("sports_scraper.services.diagnostics.now_utc")
    def test_uses_custom_min_play_count(self, mock_now):
        """Uses custom minimum play count."""
        mock_now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

        result = detect_missing_pbp(
            mock_session,
            league_code="NBA",
            min_play_count=10,
        )

        # Function should complete without error
        assert result == []


class TestDetectExternalIdConflicts:
    """Tests for detect_external_id_conflicts function."""

    def test_returns_zero_when_no_league(self):
        """Returns 0 when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = detect_external_id_conflicts(mock_session, league_code="UNKNOWN")

        assert result == 0

    def test_returns_zero_when_no_external_key(self):
        """Returns 0 when league has no external ID key defined."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # NCAAF doesn't have an external ID key in the mapping
        result = detect_external_id_conflicts(mock_session, league_code="NCAAF")

        assert result == 0

    def test_returns_zero_when_no_duplicates(self):
        """Returns 0 when no duplicate external IDs found."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # No duplicates found
        mock_session.query.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

        result = detect_external_id_conflicts(mock_session, league_code="NBA")

        assert result == 0

    @patch("sports_scraper.services.diagnostics.insert")
    def test_detects_overlapping_conflicts(self, mock_insert):
        """Detects conflicts when games have overlapping start times."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock duplicate external ID found
        mock_session.query.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = [
            ("2024010100",)
        ]

        # Two games with same external ID and overlapping times
        mock_game1 = MagicMock()
        mock_game1.id = 100
        mock_game1.game_date = datetime(2024, 1, 1, 19, 0, 0, tzinfo=UTC)
        mock_game1.home_team_id = 1
        mock_game1.away_team_id = 2

        mock_game2 = MagicMock()
        mock_game2.id = 101
        mock_game2.game_date = datetime(2024, 1, 1, 20, 0, 0, tzinfo=UTC)  # 1 hour later
        mock_game2.home_team_id = 1
        mock_game2.away_team_id = 2

        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            mock_game1,
            mock_game2,
        ]

        # Mock insert statement with rowcount
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
        mock_insert.return_value = MagicMock()
        mock_insert.return_value.values.return_value = mock_stmt
        mock_session.execute.return_value.rowcount = 1

        result = detect_external_id_conflicts(mock_session, league_code="NBA")

        assert result == 1

    @patch("sports_scraper.services.diagnostics.insert")
    def test_detects_team_mismatch_conflicts(self, mock_insert):
        """Detects conflicts when games have team mismatches."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock duplicate external ID found
        mock_session.query.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = [
            ("2024010100",)
        ]

        # Two games with same external ID but different teams
        mock_game1 = MagicMock()
        mock_game1.id = 100
        mock_game1.game_date = datetime(2024, 1, 1, 19, 0, 0, tzinfo=UTC)
        mock_game1.home_team_id = 1
        mock_game1.away_team_id = 2

        mock_game2 = MagicMock()
        mock_game2.id = 101
        mock_game2.game_date = datetime(2024, 1, 15, 19, 0, 0, tzinfo=UTC)  # Different day
        mock_game2.home_team_id = 3  # Different home team
        mock_game2.away_team_id = 4  # Different away team

        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            mock_game1,
            mock_game2,
        ]

        # Mock insert statement with rowcount
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
        mock_insert.return_value = MagicMock()
        mock_insert.return_value.values.return_value = mock_stmt
        mock_session.execute.return_value.rowcount = 1

        result = detect_external_id_conflicts(mock_session, league_code="NBA")

        assert result == 1

    @patch("sports_scraper.services.diagnostics.insert")
    def test_no_conflict_when_games_far_apart(self, mock_insert):
        """Does not detect conflict when games are far apart and same teams."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Mock duplicate external ID found
        mock_session.query.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = [
            ("2024010100",)
        ]

        # Two games with same external ID, far apart, same teams (no conflict)
        mock_game1 = MagicMock()
        mock_game1.id = 100
        mock_game1.game_date = datetime(2024, 1, 1, 19, 0, 0, tzinfo=UTC)
        mock_game1.home_team_id = 1
        mock_game1.away_team_id = 2

        mock_game2 = MagicMock()
        mock_game2.id = 101
        mock_game2.game_date = datetime(2024, 1, 15, 19, 0, 0, tzinfo=UTC)  # 14 days later
        mock_game2.home_team_id = 1  # Same teams
        mock_game2.away_team_id = 2

        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            mock_game1,
            mock_game2,
        ]

        result = detect_external_id_conflicts(mock_session, league_code="NBA")

        # No conflict since games are far apart with same teams
        assert result == 0

    def test_uses_custom_source(self):
        """Uses custom source when provided."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.filter.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

        result = detect_external_id_conflicts(
            mock_session,
            league_code="NBA",
            source="custom_source",
        )

        assert result == 0


class TestModuleImports:
    """Tests for module imports."""

    def test_has_detect_missing_pbp(self):
        """Module has detect_missing_pbp function."""
        from sports_scraper.services import diagnostics
        assert hasattr(diagnostics, 'detect_missing_pbp')

    def test_has_detect_external_id_conflicts(self):
        """Module has detect_external_id_conflicts function."""
        from sports_scraper.services import diagnostics
        assert hasattr(diagnostics, 'detect_external_id_conflicts')

    def test_has_constants(self):
        """Module has required constants."""
        from sports_scraper.services import diagnostics
        assert hasattr(diagnostics, 'PBP_SUPPORTED_LEAGUES')
        assert hasattr(diagnostics, 'PBP_MIN_PLAY_COUNT')
        assert hasattr(diagnostics, 'CONFLICT_OVERLAP_WINDOW_HOURS')
        assert hasattr(diagnostics, 'EXTERNAL_ID_KEYS')
