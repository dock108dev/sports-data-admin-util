"""Tests for persistence/admin.py module."""

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


from sports_scraper.persistence.admin import (
    delete_game,
    delete_games_batch,
    clear_odds_cache,
)


class TestDeleteGame:
    """Tests for delete_game function."""

    def test_returns_not_found_when_game_missing(self):
        """Returns not found status when game doesn't exist."""
        mock_session = MagicMock()
        mock_session.get.return_value = None

        result = delete_game(mock_session, game_id=999)

        assert result["game_id"] == 999
        assert result["found"] is False
        assert result["deleted"] is False

    @patch("sports_scraper.persistence.admin.cache_invalidate_game")
    def test_deletes_existing_game(self, mock_cache_invalidate):
        """Deletes an existing game and returns success."""
        mock_cache_invalidate.return_value = 1

        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.home_team_id = 1
        mock_game.away_team_id = 2
        mock_game.game_date.date.return_value = "2024-01-15"
        mock_game.source_game_key = "GAME123"
        mock_session.get.return_value = mock_game

        result = delete_game(mock_session, game_id=42)

        assert result["game_id"] == 42
        assert result["found"] is True
        assert result["deleted"] is True
        mock_session.delete.assert_called_once_with(mock_game)
        mock_session.flush.assert_called_once()

    @patch("sports_scraper.persistence.admin.cache_invalidate_game")
    def test_clears_cache_by_default(self, mock_cache_invalidate):
        """Clears cache entries by default."""
        mock_cache_invalidate.return_value = 5

        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.game_date.date.return_value = "2024-01-15"
        mock_session.get.return_value = mock_game

        result = delete_game(mock_session, game_id=42)

        mock_cache_invalidate.assert_called_once_with(42)
        assert result["cache_entries_cleared"] == 5

    @patch("sports_scraper.persistence.admin.cache_invalidate_game")
    def test_skips_cache_when_requested(self, mock_cache_invalidate):
        """Skips cache clearing when clear_cache=False."""
        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.game_date.date.return_value = "2024-01-15"
        mock_session.get.return_value = mock_game

        result = delete_game(mock_session, game_id=42, clear_cache=False)

        mock_cache_invalidate.assert_not_called()
        assert result["cache_entries_cleared"] == 0


class TestDeleteGamesBatch:
    """Tests for delete_games_batch function."""

    @patch("sports_scraper.persistence.admin.delete_game")
    @patch("sports_scraper.persistence.admin.cache_clear")
    def test_deletes_multiple_games(self, mock_cache_clear, mock_delete_game):
        """Deletes multiple games in a batch."""
        mock_delete_game.side_effect = [
            {"game_id": 1, "deleted": True, "found": True},
            {"game_id": 2, "deleted": True, "found": True},
            {"game_id": 3, "deleted": False, "found": False},
        ]
        mock_cache_clear.return_value = 10

        mock_session = MagicMock()
        result = delete_games_batch(mock_session, [1, 2, 3])

        assert result["deleted"] == [1, 2]
        assert result["not_found"] == [3]
        assert result["cache_entries_cleared"] == 10

    @patch("sports_scraper.persistence.admin.delete_game")
    @patch("sports_scraper.persistence.admin.cache_clear")
    def test_skips_cache_clear_when_nothing_deleted(self, mock_cache_clear, mock_delete_game):
        """Skips cache clear when no games were deleted."""
        mock_delete_game.return_value = {"game_id": 1, "deleted": False, "found": False}
        mock_cache_clear.return_value = 0

        mock_session = MagicMock()
        result = delete_games_batch(mock_session, [1])

        assert result["deleted"] == []
        assert result["not_found"] == [1]
        # Cache clear should not be called when nothing deleted
        mock_cache_clear.assert_not_called()

    @patch("sports_scraper.persistence.admin.delete_game")
    @patch("sports_scraper.persistence.admin.cache_clear")
    def test_handles_empty_list(self, mock_cache_clear, mock_delete_game):
        """Handles empty game ID list."""
        mock_session = MagicMock()
        result = delete_games_batch(mock_session, [])

        assert result["deleted"] == []
        assert result["not_found"] == []
        mock_delete_game.assert_not_called()


class TestClearOddsCache:
    """Tests for clear_odds_cache function."""

    @patch("sports_scraper.persistence.admin.cache_clear")
    def test_calls_cache_clear(self, mock_cache_clear):
        """Calls underlying cache_clear function."""
        mock_cache_clear.return_value = 42

        result = clear_odds_cache()

        mock_cache_clear.assert_called_once()
        assert result == 42

    @patch("sports_scraper.persistence.admin.cache_clear")
    def test_returns_zero_when_cache_empty(self, mock_cache_clear):
        """Returns zero when cache was already empty."""
        mock_cache_clear.return_value = 0

        result = clear_odds_cache()

        assert result == 0


class TestModuleImports:
    """Tests for admin module imports."""

    def test_has_delete_game(self):
        """Module has delete_game function."""
        from sports_scraper.persistence import admin
        assert hasattr(admin, 'delete_game')

    def test_has_delete_games_batch(self):
        """Module has delete_games_batch function."""
        from sports_scraper.persistence import admin
        assert hasattr(admin, 'delete_games_batch')

    def test_has_clear_odds_cache(self):
        """Module has clear_odds_cache function."""
        from sports_scraper.persistence import admin
        assert hasattr(admin, 'clear_odds_cache')
