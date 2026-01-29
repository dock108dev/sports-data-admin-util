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

    def test_contains_mascots(self):
        """Contains common mascot names."""
        # These are mascots, not words like "university"
        assert "tigers" in _NCAAB_STOPWORDS
        assert "eagles" in _NCAAB_STOPWORDS
        assert "bulldogs" in _NCAAB_STOPWORDS

    def test_is_set(self):
        """Is a set for fast lookups."""
        assert isinstance(_NCAAB_STOPWORDS, (set, frozenset))


class TestNormalizeNcaabNameForMatching:
    """Tests for _normalize_ncaab_name_for_matching function."""

    def test_lowercases_name(self):
        """Lowercases team name."""
        result = _normalize_ncaab_name_for_matching("Duke")
        assert result == result.lower()

    def test_removes_mascots(self):
        """Removes mascot stopwords."""
        result = _normalize_ncaab_name_for_matching("Missouri Tigers")
        # "tigers" is in _NCAAB_STOPWORDS
        assert "tigers" not in result

    def test_handles_empty_string(self):
        """Handles empty string input."""
        result = _normalize_ncaab_name_for_matching("")
        assert result == ""

    def test_expands_st_to_state(self):
        """Expands 'St' (without period) to 'State'."""
        result = _normalize_ncaab_name_for_matching("Ohio St")
        assert "state" in result


class TestUpsertTeam:
    """Tests for _upsert_team function."""

    def test_upserts_team_and_returns_id(self):
        """Upserts team and returns the ID from the database."""
        mock_session = MagicMock()
        # _upsert_team uses session.execute(stmt).scalar_one() to get the ID
        mock_session.execute.return_value.scalar_one.return_value = 42
        # Also mock session.get for league lookup
        mock_league = MagicMock(code="NBA")
        mock_session.get.return_value = mock_league

        identity = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        result = _upsert_team(mock_session, league_id=1, identity=identity)

        assert result == 42

    def test_creates_new_team(self):
        """Creates new team when not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Mock the execute to return a new team ID
        mock_result = MagicMock()
        mock_result.inserted_primary_key = [100]
        mock_session.execute.return_value = mock_result

        identity = TeamIdentity(league_code="NBA", name="New Team", abbreviation="NEW")
        result = _upsert_team(mock_session, league_id=1, identity=identity)

        assert mock_session.execute.called or mock_session.add.called
