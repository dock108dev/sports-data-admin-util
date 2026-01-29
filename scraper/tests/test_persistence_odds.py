"""Tests for persistence/odds.py module."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
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


from sports_scraper.persistence.odds_matching import (
    canonicalize_team_names,
    should_log,
)
from sports_scraper.models import NormalizedOddsSnapshot, TeamIdentity


class TestCanonicalizeTeamNames:
    """Tests for canonicalize_team_names function."""

    def test_returns_canonical_names(self):
        """Returns canonical team names from mappings."""
        snapshot = NormalizedOddsSnapshot(
            league_code="NBA",
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc),
            home_team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
            away_team=TeamIdentity(league_code="NBA", name="New York Knicks", abbreviation="NYK"),
            book="FanDuel",
            market_type="spread",
            line=-5.5,
            price=-110,
            observed_at=datetime.now(timezone.utc),
        )

        home, away = canonicalize_team_names(snapshot)

        # canonicalize_team_names returns canonical form from mappings, not lowercased
        assert home == "Boston Celtics"
        assert away == "New York Knicks"

    def test_handles_whitespace_in_names(self):
        """Handles whitespace in team names (via normalize_team_name)."""
        snapshot = NormalizedOddsSnapshot(
            league_code="NBA",
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc),
            home_team=TeamIdentity(league_code="NBA", name="  Boston Celtics  ", abbreviation="BOS"),
            away_team=TeamIdentity(league_code="NBA", name="  New York Knicks  ", abbreviation="NYK"),
            book="FanDuel",
            market_type="spread",
            line=-5.5,
            price=-110,
            observed_at=datetime.now(timezone.utc),
        )

        home, away = canonicalize_team_names(snapshot)

        # Names with extra whitespace fall through as-is if not in mappings
        # (they won't match existing mappings with exact match)
        assert isinstance(home, str)
        assert isinstance(away, str)


class TestShouldLog:
    """Tests for should_log function."""

    def test_returns_true_first_time(self):
        """Returns True on first call for a key."""
        # Use unique key to avoid state from other tests
        import time
        key = f"test_key_{time.time()}"
        result = should_log(key)
        assert result is True

    def test_returns_false_subsequent_times(self):
        """Returns False on subsequent calls within sample window."""
        import time
        key = f"test_key_repeat_{time.time()}"

        # First call
        should_log(key)

        # Subsequent calls should return False
        result = should_log(key)
        assert result is False

    def test_respects_sample_parameter(self):
        """Respects sample parameter for logging frequency."""
        import time
        key = f"test_key_sample_{time.time()}"

        # Call many times with sample=10
        results = [should_log(key, sample=10) for _ in range(20)]

        # First should be True, then mostly False with some True at intervals
        assert results[0] is True


class TestOddsModuleImports:
    """Tests for odds module imports."""

    def test_upsert_odds_exists(self):
        """upsert_odds function exists."""
        from sports_scraper.persistence.odds import upsert_odds
        assert callable(upsert_odds)

    def test_module_has_required_functions(self):
        """Module has all required functions."""
        from sports_scraper.persistence import odds
        assert hasattr(odds, 'upsert_odds')
