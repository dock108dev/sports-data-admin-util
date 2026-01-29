"""Tests for persistence/plays.py module."""

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


from sports_scraper.persistence.plays import (
    create_raw_pbp_snapshot,
    upsert_plays,
)
from sports_scraper.models import NormalizedPlay


class TestCreateRawPbpSnapshot:
    """Tests for create_raw_pbp_snapshot function."""

    def test_empty_plays_returns_none(self):
        """Returns None when plays is empty."""
        mock_session = MagicMock()
        result = create_raw_pbp_snapshot(mock_session, 1, [], "test_source")
        assert result is None

    @patch("sports_scraper.persistence.plays.db_models")
    def test_missing_model_returns_none(self, mock_db_models):
        """Returns None when PBPSnapshot model missing."""
        mock_session = MagicMock()
        # Remove the PBPSnapshot attribute
        del mock_db_models.PBPSnapshot

        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            description="Made shot",
        )

        result = create_raw_pbp_snapshot(mock_session, 1, [play], "test_source")
        assert result is None

    @patch("sports_scraper.persistence.plays.db_models")
    def test_creates_snapshot_successfully(self, mock_db_models):
        """Creates snapshot and returns ID."""
        mock_session = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.id = 123
        mock_db_models.PBPSnapshot.return_value = mock_snapshot

        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            team_abbreviation="BOS",
            player_name="Player A",
            description="Made shot",
            home_score=2,
            away_score=0,
        )

        result = create_raw_pbp_snapshot(mock_session, 1, [play], "test_source", scrape_run_id=10)

        assert result == 123
        mock_session.add.assert_called_once_with(mock_snapshot)
        mock_session.flush.assert_called_once()

    @patch("sports_scraper.persistence.plays.db_models")
    def test_handles_exception(self, mock_db_models):
        """Handles exception and returns None."""
        mock_session = MagicMock()
        mock_db_models.PBPSnapshot.side_effect = Exception("Test error")

        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            description="Made shot",
        )

        result = create_raw_pbp_snapshot(mock_session, 1, [play], "test_source")
        assert result is None


class TestUpsertPlays:
    """Tests for upsert_plays function."""

    def test_empty_plays_returns_zero(self):
        """Returns 0 when plays is empty."""
        mock_session = MagicMock()
        result = upsert_plays(mock_session, 1, [])
        assert result == 0

    @patch("sports_scraper.persistence.plays.create_raw_pbp_snapshot")
    @patch("sports_scraper.persistence.plays.db_models")
    def test_game_not_found_returns_zero(self, mock_db_models, mock_snapshot):
        """Returns 0 when game not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            description="Made shot",
        )

        result = upsert_plays(mock_session, 999, [play])
        assert result == 0

    @patch("sports_scraper.persistence.plays.insert")
    @patch("sports_scraper.persistence.plays.now_utc")
    @patch("sports_scraper.persistence.plays.create_raw_pbp_snapshot")
    def test_upserts_plays_successfully(self, mock_snapshot, mock_now, mock_insert):
        """Upserts plays and returns count."""
        mock_now.return_value = datetime.now(timezone.utc)
        mock_session = MagicMock()

        # Mock game
        mock_game = MagicMock()
        mock_game.home_team = MagicMock()
        mock_game.home_team.abbreviation = "BOS"
        mock_game.home_team.name = "Boston Celtics"
        mock_game.home_team.id = 1
        mock_game.away_team = MagicMock()
        mock_game.away_team.abbreviation = "LAL"
        mock_game.away_team.name = "LA Lakers"
        mock_game.away_team.id = 2
        mock_game.league_id = 1
        mock_game.status = "final"
        mock_game.tip_time = datetime.now(timezone.utc)
        mock_game.end_time = None

        mock_session.query.return_value.filter.return_value.first.return_value = mock_game
        mock_session.query.return_value.filter.return_value.all.return_value = []

        mock_snapshot.return_value = 1

        # Mock the insert chain
        mock_stmt = MagicMock()
        mock_insert.return_value.values.return_value.on_conflict_do_update.return_value = mock_stmt

        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            team_abbreviation="BOS",
            description="Made shot",
        )

        result = upsert_plays(mock_session, 1, [play], source="test")

        assert result == 1
        mock_session.execute.assert_called()
        mock_session.flush.assert_called()

    @patch("sports_scraper.persistence.plays.insert")
    @patch("sports_scraper.persistence.plays.now_utc")
    @patch("sports_scraper.persistence.plays.create_raw_pbp_snapshot")
    def test_resolves_team_ids(self, mock_snapshot, mock_now, mock_insert):
        """Resolves team IDs from abbreviations."""
        mock_now.return_value = datetime.now(timezone.utc)
        mock_session = MagicMock()

        mock_game = MagicMock()
        mock_game.home_team = MagicMock()
        mock_game.home_team.abbreviation = "BOS"
        mock_game.home_team.name = "Boston"
        mock_game.home_team.id = 1
        mock_game.away_team = MagicMock()
        mock_game.away_team.abbreviation = "LAL"
        mock_game.away_team.name = "Lakers"
        mock_game.away_team.id = 2
        mock_game.league_id = 1
        mock_game.status = "live"
        mock_game.end_time = None

        mock_session.query.return_value.filter.return_value.first.return_value = mock_game
        mock_session.query.return_value.filter.return_value.all.return_value = []

        mock_snapshot.return_value = 1

        # Mock the insert chain
        mock_stmt = MagicMock()
        mock_insert.return_value.values.return_value.on_conflict_do_update.return_value = mock_stmt

        plays = [
            NormalizedPlay(
                play_index=1,
                quarter=1,
                game_clock="12:00",
                play_type="shot",
                team_abbreviation="BOS",
                description="Boston scores",
            ),
            NormalizedPlay(
                play_index=2,
                quarter=1,
                game_clock="11:30",
                play_type="shot",
                team_abbreviation="LAL",
                description="Lakers scores",
            ),
        ]

        result = upsert_plays(mock_session, 1, plays, source="test")

        assert result == 2

    @patch("sports_scraper.persistence.plays.create_raw_pbp_snapshot")
    @patch("sports_scraper.persistence.plays.db_models")
    def test_skip_snapshot_creation(self, mock_db_models, mock_snapshot):
        """Can skip snapshot creation."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            description="Made shot",
        )

        result = upsert_plays(mock_session, 1, [play], create_snapshot=False)

        mock_snapshot.assert_not_called()


class TestNormalizedPlayModel:
    """Tests for NormalizedPlay model used in plays module."""

    def test_create_minimal_play(self):
        """Create play with minimal fields."""
        play = NormalizedPlay(
            play_index=1,
            quarter=1,
        )
        assert play.play_index == 1
        assert play.quarter == 1
        assert play.game_clock is None

    def test_create_full_play(self):
        """Create play with all fields."""
        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            team_abbreviation="BOS",
            player_id="player123",
            player_name="Test Player",
            description="Made 3PT shot",
            home_score=3,
            away_score=0,
            raw_data={"original": "data"},
        )
        assert play.play_type == "shot"
        assert play.team_abbreviation == "BOS"
        assert play.player_name == "Test Player"
        assert play.home_score == 3
        assert play.raw_data == {"original": "data"}
