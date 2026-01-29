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
