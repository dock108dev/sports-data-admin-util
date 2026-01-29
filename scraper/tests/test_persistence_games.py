"""Tests for persistence/games.py module."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
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


from sports_scraper.persistence.games import (
    _normalize_status,
    resolve_status_transition,
    merge_external_ids,
)


class TestNormalizeStatus:
    """Tests for _normalize_status function."""

    def test_normalizes_final(self):
        """Normalizes 'final' status."""
        result = _normalize_status("final")
        assert result == "final"

    def test_normalizes_completed(self):
        """Normalizes 'completed' to 'final'."""
        result = _normalize_status("completed")
        assert result == "final"

    def test_normalizes_scheduled(self):
        """Normalizes 'scheduled' status."""
        result = _normalize_status("scheduled")
        assert result == "scheduled"

    def test_normalizes_none(self):
        """Normalizes None to 'scheduled'."""
        result = _normalize_status(None)
        assert result == "scheduled"

    def test_normalizes_empty_string(self):
        """Normalizes empty string to 'scheduled'."""
        result = _normalize_status("")
        assert result == "scheduled"

    def test_normalizes_live(self):
        """Normalizes 'live' status."""
        result = _normalize_status("live")
        assert result == "live"

    def test_normalizes_in_progress(self):
        """Normalizes 'in_progress' falls through to 'scheduled' (not explicitly handled)."""
        result = _normalize_status("in_progress")
        # Note: Only "live" is explicitly handled, not "in_progress"
        assert result == "scheduled"


class TestResolveStatusTransition:
    """Tests for resolve_status_transition function."""

    def test_keeps_final_status(self):
        """Keeps final status when already final."""
        result = resolve_status_transition("final", "scheduled")
        assert result == "final"

    def test_upgrades_to_final(self):
        """Upgrades status to final."""
        result = resolve_status_transition("scheduled", "final")
        assert result == "final"

    def test_upgrades_scheduled_to_live(self):
        """Upgrades scheduled to live."""
        result = resolve_status_transition("scheduled", "live")
        assert result == "live"

    def test_handles_none_current(self):
        """Handles None current status."""
        result = resolve_status_transition(None, "final")
        assert result == "final"

    def test_handles_none_incoming(self):
        """Handles None incoming status."""
        result = resolve_status_transition("scheduled", None)
        assert result == "scheduled"

    def test_live_can_go_to_final(self):
        """Live status can transition to final."""
        result = resolve_status_transition("live", "final")
        assert result == "final"

    def test_final_cannot_go_back(self):
        """Final status cannot transition backwards."""
        result = resolve_status_transition("final", "live")
        assert result == "final"


class TestMergeExternalIds:
    """Tests for merge_external_ids function."""

    def test_merges_new_ids(self):
        """Merges new external IDs."""
        existing = {"nhl_game_pk": "123"}
        new_ids = {"cbb_game_id": "456"}

        result = merge_external_ids(existing, new_ids)

        assert result["nhl_game_pk"] == "123"
        assert result["cbb_game_id"] == "456"

    def test_handles_none_existing(self):
        """Handles None existing IDs."""
        result = merge_external_ids(None, {"cbb_game_id": "456"})

        assert result["cbb_game_id"] == "456"

    def test_handles_none_new(self):
        """Handles None new IDs."""
        existing = {"nhl_game_pk": "123"}
        result = merge_external_ids(existing, None)

        assert result["nhl_game_pk"] == "123"

    def test_handles_both_none(self):
        """Handles both None."""
        result = merge_external_ids(None, None)

        assert result == {} or result is None

    def test_handles_empty_existing(self):
        """Handles empty existing dict."""
        existing = {}
        new_ids = {"cbb_game_id": "456"}

        result = merge_external_ids(existing, new_ids)

        assert result["cbb_game_id"] == "456"

    def test_handles_empty_new(self):
        """Handles empty new dict."""
        existing = {"nhl_game_pk": "123"}
        new_ids = {}

        result = merge_external_ids(existing, new_ids)

        assert result["nhl_game_pk"] == "123"
