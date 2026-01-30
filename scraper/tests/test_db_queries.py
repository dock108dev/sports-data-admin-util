"""Tests for utils/db_queries.py module."""

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


from sports_scraper.utils.db_queries import (
    get_league_id,
    count_team_games,
    has_player_boxscores,
    has_odds,
    find_games_in_date_range,
)


class TestGetLeagueId:
    """Tests for get_league_id function."""

    def test_returns_id_when_found(self):
        """Returns league ID when found."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 1

        result = get_league_id(mock_session, "NBA")

        assert result == 1
        mock_session.execute.assert_called_once()

    def test_raises_when_not_found(self):
        """Raises ValueError when league not found."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = None

        with pytest.raises(ValueError, match="League code UNKNOWN not found"):
            get_league_id(mock_session, "UNKNOWN")


class TestCountTeamGames:
    """Tests for count_team_games function."""

    def test_returns_count(self):
        """Returns game count for team."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 50

        result = count_team_games(mock_session, team_id=1)

        assert result == 50

    def test_returns_zero_when_no_games(self):
        """Returns 0 when team has no games."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = None

        result = count_team_games(mock_session, team_id=999)

        assert result == 0


class TestHasPlayerBoxscores:
    """Tests for has_player_boxscores function."""

    def test_returns_true_when_exists(self):
        """Returns True when player boxscores exist."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = True

        result = has_player_boxscores(mock_session, game_id=1)

        assert result is True

    def test_returns_false_when_not_exists(self):
        """Returns False when no player boxscores."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = False

        result = has_player_boxscores(mock_session, game_id=999)

        assert result is False

    def test_returns_false_for_none(self):
        """Returns False when scalar returns None."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = None

        result = has_player_boxscores(mock_session, game_id=1)

        assert result is False


class TestHasOdds:
    """Tests for has_odds function."""

    def test_returns_true_when_exists(self):
        """Returns True when odds exist."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = True

        result = has_odds(mock_session, game_id=1)

        assert result is True

    def test_returns_false_when_not_exists(self):
        """Returns False when no odds."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = False

        result = has_odds(mock_session, game_id=999)

        assert result is False

    def test_returns_false_for_none(self):
        """Returns False when scalar returns None."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = None

        result = has_odds(mock_session, game_id=1)

        assert result is False


class TestFindGamesInDateRange:
    """Tests for find_games_in_date_range function."""

    def test_returns_games(self):
        """Returns games in date range."""
        mock_session = MagicMock()

        mock_game = MagicMock()
        mock_game.id = 1
        mock_game.source_game_key = "ABC123"
        mock_game.game_date = datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc)

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [(1, "ABC123", datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc))]

        result = find_games_in_date_range(
            mock_session,
            league_id=1,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        assert len(result) == 1
        assert result[0][0] == 1
        assert result[0][1] == "ABC123"

    def test_returns_empty_when_no_games(self):
        """Returns empty when no games found."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = find_games_in_date_range(
            mock_session,
            league_id=1,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        assert len(result) == 0

    def test_filters_missing_players(self):
        """Applies missing_players filter."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = find_games_in_date_range(
            mock_session,
            league_id=1,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            missing_players=True,
        )

        # Filter should have been applied
        assert mock_query.filter.call_count >= 2  # Base filter + missing_players

    def test_filters_missing_odds(self):
        """Applies missing_odds filter."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = find_games_in_date_range(
            mock_session,
            league_id=1,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            missing_odds=True,
        )

        # Filter should have been applied
        assert mock_query.filter.call_count >= 2  # Base filter + missing_odds

    def test_skips_source_key_filter(self):
        """Skips source_key filter when not required."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = find_games_in_date_range(
            mock_session,
            league_id=1,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            require_source_key=False,
        )

        # Should still work without source_key filter
        assert mock_query.all.called
