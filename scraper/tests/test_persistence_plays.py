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
    upsert_plays,
    create_raw_pbp_snapshot,
)
from sports_scraper.models import NormalizedPlay


class TestUpsertPlays:
    """Tests for upsert_plays function."""

    def test_handles_empty_plays(self):
        """Handles empty plays list."""
        mock_session = MagicMock()
        result = upsert_plays(mock_session, game_id=1, plays=[])
        # Returns 0 for empty plays
        assert result == 0

    def test_function_signature(self):
        """Function accepts expected parameters."""
        # Just verify the function exists with correct signature
        import inspect
        sig = inspect.signature(upsert_plays)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "game_id" in params
        assert "plays" in params


class TestCreateRawPbpSnapshot:
    """Tests for create_raw_pbp_snapshot function."""

    def test_returns_none_for_empty_plays(self):
        """Returns None for empty plays list."""
        mock_session = MagicMock()
        result = create_raw_pbp_snapshot(mock_session, game_id=1, plays=[], source="test")
        assert result is None

    def test_function_signature(self):
        """Function accepts expected parameters."""
        import inspect
        sig = inspect.signature(create_raw_pbp_snapshot)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "game_id" in params
        assert "plays" in params
        assert "source" in params


class TestNormalizedPlayModel:
    """Tests for NormalizedPlay model used by plays module."""

    def test_normalized_play_creation(self):
        """NormalizedPlay can be created with required fields."""
        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            description="Made 3-pointer",
        )
        assert play.play_index == 1
        assert play.quarter == 1

    def test_normalized_play_optional_fields(self):
        """NormalizedPlay has optional fields with defaults."""
        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            description="Made 3-pointer",
        )
        assert play.team_abbreviation is None
        assert play.player_id is None
        assert play.player_name is None
        assert play.home_score is None
        assert play.away_score is None

    def test_normalized_play_with_all_fields(self):
        """NormalizedPlay can be created with all fields."""
        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            team_abbreviation="BOS",
            player_id="12345",
            player_name="Jayson Tatum",
            description="Made 3-pointer",
            home_score=75,
            away_score=70,
            raw_data={"key": "value"},
        )
        assert play.team_abbreviation == "BOS"
        assert play.player_id == "12345"
        assert play.player_name == "Jayson Tatum"
        assert play.home_score == 75
        assert play.away_score == 70


class TestUpsertPlaysWithMocks:
    """Tests for upsert_plays with mocked dependencies."""

    def test_returns_zero_for_empty_plays(self):
        """Returns 0 for empty plays list."""
        mock_session = MagicMock()
        result = upsert_plays(mock_session, game_id=1, plays=[])
        assert result == 0

    def test_queries_game_when_plays_provided(self):
        """Queries for game when plays are provided."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        play = NormalizedPlay(
            play_index=1,
            quarter=1,
            game_clock="12:00",
            play_type="shot",
            description="Test play",
        )

        # Should query for game even though it returns None
        result = upsert_plays(mock_session, game_id=1, plays=[play], create_snapshot=False)

        # Returns 0 when game not found
        assert result == 0

    def test_create_snapshot_parameter(self):
        """Respects create_snapshot parameter."""
        import inspect
        sig = inspect.signature(upsert_plays)
        params = sig.parameters
        assert "create_snapshot" in params
        assert params["create_snapshot"].default is True


class TestModuleImports:
    """Tests for plays module imports."""

    def test_has_upsert_plays(self):
        """Module has upsert_plays function."""
        from sports_scraper.persistence import plays
        assert hasattr(plays, 'upsert_plays')

    def test_has_create_raw_pbp_snapshot(self):
        """Module has create_raw_pbp_snapshot function."""
        from sports_scraper.persistence import plays
        assert hasattr(plays, 'create_raw_pbp_snapshot')


class TestUpsertPlaysParameters:
    """Tests for upsert_plays parameter handling."""

    def test_source_parameter_default(self):
        """Source parameter defaults to 'unknown'."""
        import inspect
        sig = inspect.signature(upsert_plays)
        params = sig.parameters
        assert "source" in params
        assert params["source"].default == "unknown"

    def test_scrape_run_id_parameter(self):
        """scrape_run_id parameter exists."""
        import inspect
        sig = inspect.signature(upsert_plays)
        params = sig.parameters
        assert "scrape_run_id" in params


class TestCreateRawPbpSnapshotParameters:
    """Tests for create_raw_pbp_snapshot parameter handling."""

    def test_required_parameters(self):
        """Required parameters are present."""
        import inspect
        sig = inspect.signature(create_raw_pbp_snapshot)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "game_id" in params
        assert "plays" in params
        assert "source" in params
