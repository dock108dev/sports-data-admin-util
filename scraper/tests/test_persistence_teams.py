"""Tests for persistence/teams.py module."""

from __future__ import annotations

import os
import sys
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


from sports_scraper.persistence.teams import (
    _upsert_team,
    _normalize_ncaab_name_for_matching,
    _NCAAB_STOPWORDS,
)
from sports_scraper.models import TeamIdentity


class TestNcaabStopwords:
    """Tests for NCAAB stopwords constant."""

    def test_contains_common_words(self):
        """Contains common school name stopwords."""
        assert "university" in _NCAAB_STOPWORDS
        assert "college" in _NCAAB_STOPWORDS
        assert "state" in _NCAAB_STOPWORDS

    def test_is_set(self):
        """Is a set for fast lookups."""
        assert isinstance(_NCAAB_STOPWORDS, (set, frozenset))


class TestNormalizeNcaabNameForMatching:
    """Tests for _normalize_ncaab_name_for_matching function."""

    def test_lowercases_name(self):
        """Lowercases team name."""
        result = _normalize_ncaab_name_for_matching("Duke Blue Devils")
        assert result == result.lower()

    def test_removes_stopwords(self):
        """Removes common stopwords."""
        result = _normalize_ncaab_name_for_matching("Duke University Blue Devils")
        assert "university" not in result

    def test_handles_empty_string(self):
        """Handles empty string input."""
        result = _normalize_ncaab_name_for_matching("")
        assert result == ""

    def test_handles_none(self):
        """Handles None input gracefully."""
        # May raise or return empty string depending on implementation
        try:
            result = _normalize_ncaab_name_for_matching(None)
            assert result == "" or result is None
        except (TypeError, AttributeError):
            pass  # Expected behavior


class TestUpsertTeam:
    """Tests for _upsert_team function."""

    def test_finds_existing_team(self):
        """Returns ID for existing team."""
        mock_session = MagicMock()
        mock_team = MagicMock(id=42)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_team

        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        result = _upsert_team(mock_session, league_id=1, team=team)

        assert result == 42

    def test_creates_new_team(self):
        """Creates new team when not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Mock the execute to return a new team ID
        mock_result = MagicMock()
        mock_result.inserted_primary_key = [100]
        mock_session.execute.return_value = mock_result

        team = TeamIdentity(league_code="NBA", name="New Team", abbreviation="NEW")
        result = _upsert_team(mock_session, league_id=1, team=team)

        assert mock_session.execute.called or mock_session.add.called
