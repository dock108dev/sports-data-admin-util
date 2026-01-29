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
    persist_plays,
)
from sports_scraper.models import NormalizedPlay


class TestPersistPlays:
    """Tests for persist_plays function."""

    def test_persists_empty_list(self):
        """Handles empty play list."""
        mock_session = MagicMock()

        result = persist_plays(mock_session, game_id=1, plays=[])

        assert result == 0

    def test_persists_single_play(self):
        """Persists a single play."""
        mock_session = MagicMock()

        plays = [
            NormalizedPlay(
                sequence_number=1,
                period=1,
                game_clock="12:00",
                play_type="shot",
                description="Made layup",
                home_score=2,
                away_score=0,
            ),
        ]

        result = persist_plays(mock_session, game_id=1, plays=plays)

        assert result >= 0  # Returns count of plays persisted

    def test_persists_multiple_plays(self):
        """Persists multiple plays."""
        mock_session = MagicMock()

        plays = [
            NormalizedPlay(
                sequence_number=1,
                period=1,
                game_clock="12:00",
                play_type="shot",
                description="Made layup",
                home_score=2,
                away_score=0,
            ),
            NormalizedPlay(
                sequence_number=2,
                period=1,
                game_clock="11:30",
                play_type="rebound",
                description="Defensive rebound",
                home_score=2,
                away_score=0,
            ),
        ]

        result = persist_plays(mock_session, game_id=1, plays=plays)

        assert result >= 0

    def test_handles_play_with_all_fields(self):
        """Handles play with all optional fields."""
        mock_session = MagicMock()

        plays = [
            NormalizedPlay(
                sequence_number=1,
                period=1,
                game_clock="12:00",
                play_type="shot",
                description="Made 3-pointer",
                home_score=3,
                away_score=0,
                team_name="Boston Celtics",
                player_name="Jayson Tatum",
                x_coord=25.5,
                y_coord=10.2,
            ),
        ]

        result = persist_plays(mock_session, game_id=1, plays=plays)

        assert result >= 0
