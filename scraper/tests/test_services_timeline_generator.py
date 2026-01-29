"""Tests for services/timeline_generator.py module."""

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


from sports_scraper.services.timeline_generator import (
    SCHEDULED_DAYS_BACK,
    find_games_missing_timelines,
    find_games_needing_regeneration,
    find_all_games_needing_timelines,
    generate_timeline_for_game,
    generate_missing_timelines,
    generate_all_needed_timelines,
)


class TestScheduledDaysBack:
    """Tests for SCHEDULED_DAYS_BACK constant."""

    def test_default_is_4_days(self):
        """Default window is 4 days."""
        assert SCHEDULED_DAYS_BACK == 4

    def test_is_positive_integer(self):
        """Constant is a positive integer."""
        assert isinstance(SCHEDULED_DAYS_BACK, int)
        assert SCHEDULED_DAYS_BACK > 0


class TestFindGamesMissingTimelines:
    """Tests for find_games_missing_timelines function."""

    def test_returns_empty_when_no_games(self):
        """Returns empty list when no games match criteria."""
        mock_session = MagicMock()
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = find_games_missing_timelines(mock_session)

        assert result == []

    def test_queries_with_date_filter(self):
        """Queries games with scheduled_days_back filter."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        find_games_missing_timelines(mock_session, scheduled_days_back=7)

        assert mock_session.query.called


class TestFindGamesNeedingRegeneration:
    """Tests for find_games_needing_regeneration function."""

    def test_returns_empty_when_no_games(self):
        """Returns empty list when no games need regeneration."""
        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = find_games_needing_regeneration(mock_session)

        assert result == []


class TestFindAllGamesNeedingTimelines:
    """Tests for find_all_games_needing_timelines function."""

    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    @patch("sports_scraper.services.timeline_generator.find_games_needing_regeneration")
    def test_combines_missing_and_regeneration(self, mock_regen, mock_missing):
        """Combines results from both finder functions."""
        mock_session = MagicMock()
        mock_missing.return_value = [(1, "NBA", date(2024, 1, 15))]
        mock_regen.return_value = [(2, "NHL", date(2024, 1, 16))]

        result = find_all_games_needing_timelines(mock_session)

        assert len(result) == 2


class TestGenerateTimelineForGame:
    """Tests for generate_timeline_for_game function."""

    def test_returns_none_when_no_plays(self):
        """Returns None when game has no plays."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []

        result = generate_timeline_for_game(mock_session, game_id=1)

        assert result is None


class TestGenerateMissingTimelines:
    """Tests for generate_missing_timelines function."""

    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    @patch("sports_scraper.services.timeline_generator.generate_timeline_for_game")
    def test_generates_for_missing_games(self, mock_generate, mock_find):
        """Generates timelines for games missing them."""
        mock_session = MagicMock()
        mock_find.return_value = [(1, "NBA", date(2024, 1, 15))]
        mock_generate.return_value = MagicMock()

        result = generate_missing_timelines(mock_session)

        assert result == 1
        mock_generate.assert_called_once()


class TestGenerateAllNeededTimelines:
    """Tests for generate_all_needed_timelines function."""

    @patch("sports_scraper.services.timeline_generator.find_all_games_needing_timelines")
    @patch("sports_scraper.services.timeline_generator.generate_timeline_for_game")
    def test_generates_for_all_needed_games(self, mock_generate, mock_find):
        """Generates timelines for all games needing them."""
        mock_session = MagicMock()
        mock_find.return_value = [(1, "NBA", date(2024, 1, 15)), (2, "NHL", date(2024, 1, 16))]
        mock_generate.return_value = MagicMock()

        result = generate_all_needed_timelines(mock_session)

        assert result == 2
        assert mock_generate.call_count == 2
