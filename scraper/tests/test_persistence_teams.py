"""Tests for persistence/teams.py module."""

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


from sports_scraper.persistence.teams import (
    _derive_abbreviation,
    _should_log,
)
from sports_scraper.models import TeamIdentity


class TestDeriveAbbreviation:
    """Tests for _derive_abbreviation function."""

    def test_simple_name(self):
        """Derives abbreviation from simple name."""
        result = _derive_abbreviation("Boston Celtics")
        assert len(result) >= 2
        # BC is the expected abbreviation (first letters of each word)
        assert result.startswith("B")

    def test_uc_prefix(self):
        """Handles UC- prefix."""
        result = _derive_abbreviation("UC Irvine")
        assert result == "UCIR"

    def test_unc_prefix(self):
        """Handles UNC- prefix."""
        result = _derive_abbreviation("UNC Wilmington")
        assert result == "UNCWI"

    def test_empty_name(self):
        """Returns UNK for empty name."""
        result = _derive_abbreviation("")
        assert result == "UNK"

    def test_none_name(self):
        """Returns UNK for None name."""
        result = _derive_abbreviation(None)
        assert result == "UNK"

    def test_single_word(self):
        """Handles single word name."""
        result = _derive_abbreviation("Duke")
        assert len(result) >= 2

    def test_strips_special_chars(self):
        """Strips special characters."""
        result = _derive_abbreviation("Saint Mary's (CA)")
        assert result.isalnum()

    def test_removes_stopwords(self):
        """Removes stopwords like 'of' and 'the'."""
        result = _derive_abbreviation("University of Texas")
        # Should not include 'of'
        assert "O" not in result or result == "UT"

    def test_max_length(self):
        """Result is at most 6 characters."""
        result = _derive_abbreviation("Very Long University Name Here")
        assert len(result) <= 6


class TestShouldLog:
    """Tests for _should_log function."""

    def test_logs_first_occurrence(self):
        """Returns True for first occurrence."""
        result = _should_log("unique_test_key_1")
        assert result is True

    def test_returns_false_for_subsequent(self):
        """Returns False for second occurrence."""
        # First call
        _should_log("unique_test_key_2")
        # Second call should be False
        result = _should_log("unique_test_key_2")
        assert result is False

    def test_logs_at_sample_interval(self):
        """Returns True at sample interval."""
        key = "unique_test_key_3"
        # Call 50 times (default sample)
        for _ in range(49):
            _should_log(key)
        # 50th call should still be False
        result = _should_log(key)
        assert result is False
        # 51st call should be True
        result = _should_log(key)
        assert result is True


class TestTeamIdentityModel:
    """Tests for TeamIdentity model used in teams module."""

    def test_create_minimal_identity(self):
        """Create identity with minimal fields."""
        identity = TeamIdentity(
            league_code="NBA",
            name="Boston Celtics",
        )
        assert identity.name == "Boston Celtics"
        assert identity.league_code == "NBA"

    def test_create_full_identity(self):
        """Create identity with all fields."""
        identity = TeamIdentity(
            league_code="NBA",
            name="Boston Celtics",
            short_name="Celtics",
            abbreviation="BOS",
            external_ref="1610612738",
        )
        assert identity.short_name == "Celtics"
        assert identity.abbreviation == "BOS"
        assert identity.external_ref == "1610612738"
