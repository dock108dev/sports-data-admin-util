"""Extended tests for persistence/boxscores.py module."""

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


from sports_scraper.persistence.boxscores import (
    upsert_player,
    _validate_nhl_player_boxscore,
    _build_team_stats,
)
from sports_scraper.models import NormalizedPlayerBoxscore, NormalizedTeamBoxscore, TeamIdentity


class TestUpsertPlayer:
    """Tests for upsert_player function."""

    def test_upserts_player_and_returns_id(self):
        """Upserts a player and returns their ID."""
        mock_session = MagicMock()
        # upsert_player uses session.query().filter().first().id to get the ID
        mock_player = MagicMock()
        mock_player.id = 42
        mock_session.query.return_value.filter.return_value.first.return_value = mock_player

        result = upsert_player(
            mock_session,
            league_id=1,
            external_id="12345",
            name="Test Player",
            position="C",
            sweater_number=21,
            team_id=10,
        )

        assert result == 42
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_handles_all_parameters(self):
        """Handles all parameters correctly."""
        mock_session = MagicMock()
        mock_player = MagicMock()
        mock_player.id = 99
        mock_session.query.return_value.filter.return_value.first.return_value = mock_player

        result = upsert_player(
            mock_session,
            league_id=2,
            external_id="67890",
            name="Another Player",
            position="LW",
            sweater_number=88,
            team_id=5,
        )

        assert result == 99

    def test_returns_zero_when_player_not_found(self):
        """Returns 0 when player query returns None."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = upsert_player(
            mock_session,
            league_id=1,
            external_id="12345",
            name="Test Player",
        )

        assert result == 0


class TestValidateNhlPlayerBoxscore:
    """Tests for _validate_nhl_player_boxscore function."""

    def test_returns_none_for_non_nhl(self):
        """Returns None for non-NHL leagues (no validation)."""
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        boxscore = NormalizedPlayerBoxscore(
            player_id="12345",
            player_name="Test Player",
            team=team,
        )

        result = _validate_nhl_player_boxscore(boxscore, game_id=1)
        assert result is None

    def test_rejects_missing_player_name(self):
        """Rejects boxscore with missing player name."""
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning", abbreviation="TBL")
        boxscore = NormalizedPlayerBoxscore(
            player_id="12345",
            player_name="",  # Empty name
            team=team,
            player_role="skater",
        )

        result = _validate_nhl_player_boxscore(boxscore, game_id=1)
        assert result == "missing_player_name"

    def test_validates_player_name_required(self):
        """Validates that player_name is required by Pydantic."""
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning", abbreviation="TBL")
        # player_name=None would raise Pydantic validation error
        # Instead test with empty string which _validate_nhl_player_boxscore checks
        import pytest
        with pytest.raises(Exception):  # Pydantic validation error
            NormalizedPlayerBoxscore(
                player_id="12345",
                player_name=None,
                team=team,
                player_role="skater",
            )

    def test_rejects_missing_player_role(self):
        """Rejects boxscore with missing player role."""
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning", abbreviation="TBL")
        boxscore = NormalizedPlayerBoxscore(
            player_id="12345",
            player_name="Test Player",
            team=team,
            player_role=None,  # No role
        )

        result = _validate_nhl_player_boxscore(boxscore, game_id=1)
        assert result == "missing_player_role"

    def test_rejects_skater_with_no_stats(self):
        """Rejects skater boxscore with no stats."""
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning", abbreviation="TBL")
        boxscore = NormalizedPlayerBoxscore(
            player_id="12345",
            player_name="Test Player",
            team=team,
            player_role="skater",
            # All stats are None by default
        )

        result = _validate_nhl_player_boxscore(boxscore, game_id=1)
        assert result == "all_stats_null"

    def test_accepts_skater_with_stats(self):
        """Accepts skater boxscore with at least one stat."""
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning", abbreviation="TBL")
        boxscore = NormalizedPlayerBoxscore(
            player_id="12345",
            player_name="Test Player",
            team=team,
            player_role="skater",
            goals=2,  # Has a stat
        )

        result = _validate_nhl_player_boxscore(boxscore, game_id=1)
        assert result is None

    def test_rejects_goalie_with_no_stats(self):
        """Rejects goalie boxscore with no stats."""
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning", abbreviation="TBL")
        boxscore = NormalizedPlayerBoxscore(
            player_id="12345",
            player_name="Test Goalie",
            team=team,
            player_role="goalie",
            # All stats are None by default
        )

        result = _validate_nhl_player_boxscore(boxscore, game_id=1)
        assert result == "all_stats_null"

    def test_accepts_goalie_with_stats(self):
        """Accepts goalie boxscore with at least one stat."""
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning", abbreviation="TBL")
        boxscore = NormalizedPlayerBoxscore(
            player_id="12345",
            player_name="Test Goalie",
            team=team,
            player_role="goalie",
            saves=30,  # Has a stat
        )

        result = _validate_nhl_player_boxscore(boxscore, game_id=1)
        assert result is None


class TestBuildTeamStats:
    """Tests for _build_team_stats function."""

    def test_builds_basic_stats(self):
        """Builds basic team stats dict."""
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        boxscore = NormalizedTeamBoxscore(
            team=team,
            is_home=True,
            points=110,
            rebounds=45,
            assists=25,
            turnovers=12,
        )

        result = _build_team_stats(boxscore)

        assert isinstance(result, dict)
        assert result.get("points") == 110
        assert result.get("rebounds") == 45
        assert result.get("assists") == 25
        assert result.get("turnovers") == 12

    def test_builds_empty_stats(self):
        """Builds empty stats dict when no stats provided."""
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        boxscore = NormalizedTeamBoxscore(team=team, is_home=False)

        result = _build_team_stats(boxscore)

        assert isinstance(result, dict)
        assert len(result) == 0

    def test_includes_raw_stats(self):
        """Includes raw_stats in output."""
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        boxscore = NormalizedTeamBoxscore(
            team=team,
            is_home=True,
            points=100,
            raw_stats={"custom_stat": 42, "another": "value"},
        )

        result = _build_team_stats(boxscore)

        assert result.get("points") == 100
        assert result.get("custom_stat") == 42
        assert result.get("another") == "value"

    def test_excludes_none_values(self):
        """Excludes fields that are None."""
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        boxscore = NormalizedTeamBoxscore(
            team=team,
            is_home=True,
            points=100,
            rebounds=None,  # Explicitly None
            assists=20,
        )

        result = _build_team_stats(boxscore)

        assert "points" in result
        assert "assists" in result
        assert "rebounds" not in result  # None values excluded


class TestModuleImports:
    """Tests for boxscores module imports."""

    def test_has_upsert_player(self):
        """Module has upsert_player function."""
        from sports_scraper.persistence import boxscores
        assert hasattr(boxscores, 'upsert_player')

    def test_has_validate_nhl_player_boxscore(self):
        """Module has _validate_nhl_player_boxscore function."""
        from sports_scraper.persistence import boxscores
        assert hasattr(boxscores, '_validate_nhl_player_boxscore')

    def test_has_build_team_stats(self):
        """Module has _build_team_stats function."""
        from sports_scraper.persistence import boxscores
        assert hasattr(boxscores, '_build_team_stats')
