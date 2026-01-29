"""Tests for services/timeline_generator.py module."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
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
        """Returns empty sequence when no games match criteria."""
        mock_session = MagicMock()
        # Setup mock chain
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = find_games_missing_timelines(mock_session, league_code="NBA")

        assert len(result) == 0


class TestFindGamesNeedingRegeneration:
    """Tests for find_games_needing_regeneration function."""

    def test_returns_empty_when_no_games(self):
        """Returns empty sequence when no games need regeneration."""
        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.outerjoin.return_value.filter.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = find_games_needing_regeneration(mock_session, league_code="NBA")

        assert len(result) == 0


class TestFindAllGamesNeedingTimelines:
    """Tests for find_all_games_needing_timelines function."""

    def test_returns_empty_when_no_games(self):
        """Returns empty sequence when no games need timelines."""
        mock_session = MagicMock()
        # Mock both underlying queries to return empty
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []
        mock_session.query.return_value.join.return_value.outerjoin.return_value.filter.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = find_all_games_needing_timelines(mock_session, league_code="NBA")

        assert len(result) == 0


class TestModuleImports:
    """Tests for module imports."""

    def test_has_find_functions(self):
        """Module has find functions."""
        from sports_scraper.services import timeline_generator
        assert hasattr(timeline_generator, 'find_games_missing_timelines')
        assert hasattr(timeline_generator, 'find_games_needing_regeneration')
        assert hasattr(timeline_generator, 'find_all_games_needing_timelines')

    def test_has_generate_functions(self):
        """Module has generate functions."""
        from sports_scraper.services import timeline_generator
        assert hasattr(timeline_generator, 'generate_timeline_for_game')
        assert hasattr(timeline_generator, 'generate_missing_timelines')
        assert hasattr(timeline_generator, 'generate_all_needed_timelines')
