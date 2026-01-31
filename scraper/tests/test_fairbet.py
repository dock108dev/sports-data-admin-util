"""Tests for odds/fairbet.py module."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

from sports_scraper.odds.fairbet import build_selection_key, slugify


class TestSlugify:
    """Tests for slugify function."""

    def test_basic_text(self):
        """Converts basic text to slug."""
        assert slugify("Los Angeles Lakers") == "los_angeles_lakers"

    def test_over_under(self):
        """Handles Over/Under."""
        assert slugify("Over") == "over"
        assert slugify("Under") == "under"

    def test_player_name(self):
        """Handles player names."""
        assert slugify("LeBron James") == "lebron_james"
        assert slugify("Nikola Jokic") == "nikola_jokic"

    def test_special_characters(self):
        """Removes special characters."""
        assert slugify("St. John's") == "st_johns"
        assert slugify("Texas A&M") == "texas_am"

    def test_hyphens(self):
        """Converts hyphens to underscores."""
        assert slugify("Arkansas-Little Rock") == "arkansas_little_rock"

    def test_multiple_spaces(self):
        """Collapses multiple spaces."""
        assert slugify("Los  Angeles   Lakers") == "los_angeles_lakers"

    def test_empty_string(self):
        """Returns empty string for empty input."""
        assert slugify("") == ""

    def test_only_special_chars(self):
        """Returns empty for string with only special chars."""
        assert slugify("@#$%") == ""


class TestBuildSelectionKey:
    """Tests for build_selection_key function."""

    def test_moneyline_home_team(self):
        """Builds key for moneyline bet on home team."""
        key = build_selection_key(
            market_type="moneyline",
            side="Los Angeles Lakers",
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "team:los_angeles_lakers"

    def test_moneyline_away_team(self):
        """Builds key for moneyline bet on away team."""
        key = build_selection_key(
            market_type="moneyline",
            side="Boston Celtics",
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "team:boston_celtics"

    def test_spread_home_team(self):
        """Builds key for spread bet on home team."""
        key = build_selection_key(
            market_type="spread",
            side="Los Angeles Lakers",
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "team:los_angeles_lakers"

    def test_total_over(self):
        """Builds key for total over bet."""
        key = build_selection_key(
            market_type="total",
            side="Over",
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "total:over"

    def test_total_under(self):
        """Builds key for total under bet."""
        key = build_selection_key(
            market_type="total",
            side="Under",
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "total:under"

    def test_partial_team_match(self):
        """Matches team when side contains team name."""
        key = build_selection_key(
            market_type="moneyline",
            side="Lakers",
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "team:los_angeles_lakers"

    def test_none_side(self):
        """Returns unknown for None side."""
        key = build_selection_key(
            market_type="moneyline",
            side=None,
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "unknown"

    def test_unmatched_side_fallback(self):
        """Falls back to slugified side when no team match."""
        key = build_selection_key(
            market_type="moneyline",
            side="Mystery Team",
            home_team_name="Los Angeles Lakers",
            away_team_name="Boston Celtics",
        )
        assert key == "team:mystery_team"
