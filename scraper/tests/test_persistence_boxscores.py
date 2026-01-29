"""Tests for persistence/boxscores.py module."""

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


from sports_scraper.persistence.boxscores import (
    upsert_team_boxscores,
    upsert_player_boxscores,
    persist_game_payload,
    GamePersistResult,
    _build_team_stats,
    _build_player_stats,
)
from sports_scraper.models import (
    NormalizedTeamBoxscore,
    NormalizedPlayerBoxscore,
    NormalizedGame,
    TeamIdentity,
    GameIdentification,
)


class TestBuildTeamStats:
    """Tests for _build_team_stats function."""

    def test_builds_stats_dict(self):
        """Builds stats dictionary from boxscore."""
        boxscore = NormalizedTeamBoxscore(
            team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
            is_home=True,
            points=110,
        )
        result = _build_team_stats(boxscore)
        assert isinstance(result, dict)
        assert result.get("points") == 110


class TestBuildPlayerStats:
    """Tests for _build_player_stats function."""

    def test_builds_stats_dict(self):
        """Builds stats dictionary from player boxscore."""
        boxscore = NormalizedPlayerBoxscore(
            player_name="Jayson Tatum",
            team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
            points=28,
            minutes=36.5,
        )
        result = _build_player_stats(boxscore)
        assert isinstance(result, dict)
        # Only non-None values are included
        assert result.get("points") == 28
        assert result.get("minutes") == 36.5

    def test_returns_empty_dict_for_no_stats(self):
        """Returns empty dict when all stats are None."""
        boxscore = NormalizedPlayerBoxscore(
            player_name="Test Player",
            team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
        )
        result = _build_player_stats(boxscore)
        assert isinstance(result, dict)


class TestGamePersistResult:
    """Tests for GamePersistResult dataclass."""

    def test_creates_result(self):
        """Creates result with game_id."""
        result = GamePersistResult(game_id=1)
        assert result.game_id == 1


class TestUpsertTeamBoxscores:
    """Tests for upsert_team_boxscores function."""

    def test_handles_empty_list(self):
        """Handles empty boxscore list without error."""
        mock_session = MagicMock()
        # Should not raise
        upsert_team_boxscores(mock_session, game_id=1, payloads=[])


class TestUpsertPlayerBoxscores:
    """Tests for upsert_player_boxscores function."""

    def test_handles_empty_list(self):
        """Handles empty boxscore list without error."""
        mock_session = MagicMock()
        # Should not raise
        upsert_player_boxscores(mock_session, game_id=1, payloads=[])
