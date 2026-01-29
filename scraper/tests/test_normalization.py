"""Tests for normalization module."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

from sports_scraper.normalization import (
    normalize_team_name,
    TEAM_MAPPINGS,
    NBA_TEAMS,
    NFL_TEAMS,
    NHL_TEAMS,
    MLB_TEAMS,
)


class TestTeamMappings:
    """Tests for team mappings constants."""

    def test_nba_teams_exist(self):
        assert len(NBA_TEAMS) == 30

    def test_nfl_teams_exist(self):
        assert len(NFL_TEAMS) == 32

    def test_nhl_teams_exist(self):
        assert len(NHL_TEAMS) >= 32  # Includes Utah Hockey Club

    def test_mlb_teams_exist(self):
        assert len(MLB_TEAMS) == 30

    def test_mappings_populated(self):
        assert len(TEAM_MAPPINGS["NBA"]) > 0
        assert len(TEAM_MAPPINGS["NFL"]) > 0
        assert len(TEAM_MAPPINGS["NHL"]) > 0
        assert len(TEAM_MAPPINGS["MLB"]) > 0


class TestNormalizeTeamNameNBA:
    """Tests for normalize_team_name with NBA teams."""

    def test_exact_match(self):
        canonical, abbr = normalize_team_name("NBA", "Boston Celtics")
        assert canonical == "Boston Celtics"
        assert abbr == "BOS"

    def test_abbreviation_match(self):
        canonical, abbr = normalize_team_name("NBA", "BOS")
        assert canonical == "Boston Celtics"
        assert abbr == "BOS"

    def test_lowercase_match(self):
        canonical, abbr = normalize_team_name("NBA", "boston celtics")
        assert canonical == "Boston Celtics"
        assert abbr == "BOS"

    def test_variation_match(self):
        canonical, abbr = normalize_team_name("NBA", "Lakers")
        assert canonical == "LA Lakers"
        assert abbr == "LAL"

    def test_la_clippers_variations(self):
        canonical, abbr = normalize_team_name("NBA", "Los Angeles Clippers")
        assert canonical == "LA Clippers"
        assert abbr == "LAC"

    def test_golden_state_warriors(self):
        canonical, abbr = normalize_team_name("NBA", "Golden State Warriors")
        assert abbr == "GSW"

    def test_unknown_team_fallback(self):
        canonical, abbr = normalize_team_name("NBA", "Unknown Team Name")
        assert canonical == "Unknown Team Name"
        assert abbr is not None  # Should generate abbreviation


class TestNormalizeTeamNameNHL:
    """Tests for normalize_team_name with NHL teams."""

    def test_exact_match(self):
        canonical, abbr = normalize_team_name("NHL", "Tampa Bay Lightning")
        assert canonical == "Tampa Bay Lightning"
        assert abbr == "TBL"

    def test_abbreviation_match(self):
        canonical, abbr = normalize_team_name("NHL", "TBL")
        assert canonical == "Tampa Bay Lightning"
        assert abbr == "TBL"

    def test_variation_match(self):
        canonical, abbr = normalize_team_name("NHL", "Lightning")
        assert canonical == "Tampa Bay Lightning"
        assert abbr == "TBL"

    def test_montreal_canadiens(self):
        canonical, abbr = normalize_team_name("NHL", "Montreal Canadiens")
        assert abbr == "MTL"

    def test_utah_hockey_club(self):
        canonical, abbr = normalize_team_name("NHL", "Utah Hockey Club")
        assert abbr == "UTA"


class TestNormalizeTeamNameNFL:
    """Tests for normalize_team_name with NFL teams."""

    def test_exact_match(self):
        canonical, abbr = normalize_team_name("NFL", "New England Patriots")
        assert canonical == "New England Patriots"
        assert abbr == "NE"

    def test_abbreviation_match(self):
        canonical, abbr = normalize_team_name("NFL", "NE")
        assert canonical == "New England Patriots"

    def test_washington_commanders(self):
        canonical, abbr = normalize_team_name("NFL", "Washington Commanders")
        assert abbr == "WAS"

    def test_washington_football_team_legacy(self):
        canonical, abbr = normalize_team_name("NFL", "Washington Football Team")
        assert canonical == "Washington Commanders"


class TestNormalizeTeamNameMLB:
    """Tests for normalize_team_name with MLB teams."""

    def test_exact_match(self):
        canonical, abbr = normalize_team_name("MLB", "Boston Red Sox")
        assert canonical == "Boston Red Sox"
        assert abbr == "BOS"

    def test_chicago_cubs(self):
        canonical, abbr = normalize_team_name("MLB", "Chicago Cubs")
        assert abbr == "CHC"

    def test_chicago_white_sox(self):
        canonical, abbr = normalize_team_name("MLB", "Chicago White Sox")
        assert abbr == "CWS"


class TestNormalizeTeamNameNCAA:
    """Tests for normalize_team_name with NCAAB teams."""

    def test_ncaab_no_abbreviation(self):
        # NCAAB should return None for abbreviation to avoid collisions
        canonical, abbr = normalize_team_name("NCAAB", "Duke Blue Devils")
        assert abbr is None

    def test_ncaab_returns_input(self):
        # NCAAB teams are not mapped, so should return input
        canonical, abbr = normalize_team_name("NCAAB", "Some Random University")
        assert canonical == "Some Random University"
        assert abbr is None


class TestNormalizeTeamNameEdgeCases:
    """Tests for edge cases in normalize_team_name."""

    def test_empty_string(self):
        canonical, abbr = normalize_team_name("NBA", "")
        assert canonical == ""

    def test_whitespace_only(self):
        canonical, _ = normalize_team_name("NBA", "   ")
        # Whitespace-only input triggers fuzzy matching which returns a default
        # Just verify it doesn't crash and returns something
        assert canonical is not None
        assert isinstance(canonical, str)

    def test_unknown_league(self):
        # Unknown leagues should still work with fallback
        canonical, abbr = normalize_team_name("UNKNOWN", "Test Team")
        assert canonical == "Test Team"


class TestFuzzyMatching:
    """Tests for fuzzy matching behavior."""

    def test_partial_match_city(self):
        # "Boston" should match "Boston Celtics"
        canonical, abbr = normalize_team_name("NBA", "Boston")
        assert canonical == "Boston Celtics"

    def test_partial_match_nickname(self):
        # "Celtics" should match "Boston Celtics"
        canonical, abbr = normalize_team_name("NBA", "Celtics")
        assert canonical == "Boston Celtics"

    def test_case_insensitive_fuzzy(self):
        canonical, abbr = normalize_team_name("NBA", "CELTICS")
        assert canonical == "Boston Celtics"
