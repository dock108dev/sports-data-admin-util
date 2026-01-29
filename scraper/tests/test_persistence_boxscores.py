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
    persist_team_boxscores,
    persist_player_boxscores,
    persist_game_payload,
)
from sports_scraper.models import (
    NormalizedTeamBoxscore,
    NormalizedPlayerBoxscore,
    NormalizedGame,
    TeamIdentity,
    GameIdentification,
)


class TestPersistTeamBoxscores:
    """Tests for persist_team_boxscores function."""

    def test_persists_empty_list(self):
        """Handles empty boxscore list."""
        mock_session = MagicMock()

        result = persist_team_boxscores(mock_session, game_id=1, boxscores=[])

        assert result == 0

    def test_persists_team_boxscores(self):
        """Persists team boxscores to database."""
        mock_session = MagicMock()

        boxscores = [
            NormalizedTeamBoxscore(
                team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
                is_home=True,
                points=110,
                field_goals_made=40,
                field_goals_attempted=85,
                three_pointers_made=12,
                three_pointers_attempted=30,
                free_throws_made=18,
                free_throws_attempted=22,
                offensive_rebounds=10,
                defensive_rebounds=35,
                total_rebounds=45,
                assists=25,
                steals=8,
                blocks=5,
                turnovers=12,
                personal_fouls=18,
            ),
        ]

        with patch("sports_scraper.persistence.boxscores._upsert_team") as mock_upsert:
            mock_upsert.return_value = 10  # team_id
            result = persist_team_boxscores(mock_session, game_id=1, boxscores=boxscores)

        assert result == 1


class TestPersistPlayerBoxscores:
    """Tests for persist_player_boxscores function."""

    def test_persists_empty_list(self):
        """Handles empty boxscore list."""
        mock_session = MagicMock()

        result = persist_player_boxscores(mock_session, game_id=1, boxscores=[])

        assert result == 0

    def test_persists_player_boxscores(self):
        """Persists player boxscores to database."""
        mock_session = MagicMock()

        boxscores = [
            NormalizedPlayerBoxscore(
                player_name="Jayson Tatum",
                team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
                minutes=36.5,
                points=28,
                field_goals_made=10,
                field_goals_attempted=18,
                three_pointers_made=3,
                three_pointers_attempted=7,
                free_throws_made=5,
                free_throws_attempted=6,
                offensive_rebounds=1,
                defensive_rebounds=7,
                total_rebounds=8,
                assists=5,
                steals=2,
                blocks=1,
                turnovers=3,
                personal_fouls=2,
            ),
        ]

        with patch("sports_scraper.persistence.boxscores._upsert_team") as mock_upsert:
            mock_upsert.return_value = 10  # team_id
            result = persist_player_boxscores(mock_session, game_id=1, boxscores=boxscores)

        assert result == 1


class TestPersistGamePayload:
    """Tests for persist_game_payload function."""

    def test_persists_game_with_boxscores(self):
        """Persists full game payload with boxscores."""
        mock_session = MagicMock()

        game = NormalizedGame(
            identification=GameIdentification(
                league_code="NBA",
                game_date=datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc),
                home_team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
                away_team=TeamIdentity(league_code="NBA", name="New York Knicks", abbreviation="NYK"),
            ),
            status="final",
            home_score=110,
            away_score=102,
            venue="TD Garden",
        )

        with patch("sports_scraper.persistence.boxscores.upsert_game_stub") as mock_upsert:
            mock_upsert.return_value = (1, True)  # game_id, is_new
            with patch("sports_scraper.persistence.boxscores.persist_team_boxscores") as mock_team:
                mock_team.return_value = 2
                with patch("sports_scraper.persistence.boxscores.persist_player_boxscores") as mock_player:
                    mock_player.return_value = 10
                    result = persist_game_payload(
                        mock_session,
                        game=game,
                        team_boxscores=[],
                        player_boxscores=[],
                    )

        assert result == 1
