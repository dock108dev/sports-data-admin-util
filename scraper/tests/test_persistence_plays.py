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
from sports_scraper.models import NormalizedPlay, NormalizedPlayByPlay


class TestUpsertPlays:
    """Tests for upsert_plays function."""

    def test_handles_empty_pbp(self):
        """Handles empty play-by-play without error."""
        mock_session = MagicMock()
        pbp = NormalizedPlayByPlay(plays=[])
        # Should not raise
        upsert_plays(mock_session, game_id=1, pbp=pbp)

    def test_handles_pbp_with_plays(self):
        """Handles PBP with plays."""
        mock_session = MagicMock()
        pbp = NormalizedPlayByPlay(plays=[
            NormalizedPlay(
                sequence_number=1,
                period=1,
                game_clock="12:00",
                play_type="shot",
                description="Made layup",
                home_score=2,
                away_score=0,
            ),
        ])
        # Should not raise
        upsert_plays(mock_session, game_id=1, pbp=pbp)


class TestCreateRawPbpSnapshot:
    """Tests for create_raw_pbp_snapshot function."""

    def test_creates_snapshot(self):
        """Creates raw PBP snapshot."""
        mock_session = MagicMock()
        raw_data = {"plays": [{"id": 1, "type": "shot"}]}

        # Should not raise
        create_raw_pbp_snapshot(mock_session, game_id=1, raw_data=raw_data)
