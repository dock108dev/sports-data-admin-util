"""Tests for services/pbp_ingestion.py module."""

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


# Test constants and simple functions that don't require complex mocking
class TestPbpIngestionConstants:
    """Tests for PBP ingestion module constants and simple utilities."""

    def test_module_imports(self):
        """Module can be imported without errors."""
        from sports_scraper.services import pbp_ingestion
        assert hasattr(pbp_ingestion, 'ingest_pbp_via_nhl_api')
        assert hasattr(pbp_ingestion, 'ingest_pbp_via_ncaab_api')

    def test_has_selection_functions(self):
        """Module has game selection functions."""
        from sports_scraper.services import pbp_ingestion
        assert hasattr(pbp_ingestion, 'select_games_for_pbp_nhl_api')
        assert hasattr(pbp_ingestion, 'select_games_for_pbp_ncaab_api')

    def test_has_populate_functions(self):
        """Module has populate functions."""
        from sports_scraper.services import pbp_ingestion
        assert hasattr(pbp_ingestion, 'populate_nhl_game_ids')
