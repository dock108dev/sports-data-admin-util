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
    _upsert_team,
    _normalize_ncaab_name_for_matching,
    _NCAAB_STOPWORDS,
    _derive_abbreviation,
    _NCAAB_ABBREV_EXPANSIONS,
)
from sports_scraper.models import TeamIdentity


class TestNcaabStopwords:
    """Tests for NCAAB stopwords constant."""

    def test_contains_mascots(self):
        """Contains common mascot names."""
        # These are mascots, not words like "university"
        assert "tigers" in _NCAAB_STOPWORDS
        assert "eagles" in _NCAAB_STOPWORDS
        assert "bulldogs" in _NCAAB_STOPWORDS

    def test_is_set(self):
        """Is a set for fast lookups."""
        assert isinstance(_NCAAB_STOPWORDS, (set, frozenset))


class TestNormalizeNcaabNameForMatching:
    """Tests for _normalize_ncaab_name_for_matching function."""

    def test_lowercases_name(self):
        """Lowercases team name."""
        result = _normalize_ncaab_name_for_matching("Duke")
        assert result == result.lower()

    def test_removes_mascots(self):
        """Removes mascot stopwords."""
        result = _normalize_ncaab_name_for_matching("Missouri Tigers")
        # "tigers" is in _NCAAB_STOPWORDS
        assert "tigers" not in result

    def test_handles_empty_string(self):
        """Handles empty string input."""
        result = _normalize_ncaab_name_for_matching("")
        assert result == ""

    def test_expands_st_to_state(self):
        """Expands 'St' (without period) to 'State'."""
        result = _normalize_ncaab_name_for_matching("Ohio St")
        assert "state" in result


class TestUpsertTeam:
    """Tests for _upsert_team function."""

    def test_upserts_team_and_returns_id(self):
        """Upserts team and returns the ID from the database."""
        mock_session = MagicMock()
        # _upsert_team uses session.execute(stmt).scalar_one() to get the ID
        mock_session.execute.return_value.scalar_one.return_value = 42
        # Also mock session.get for league lookup
        mock_league = MagicMock(code="NBA")
        mock_session.get.return_value = mock_league

        identity = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        result = _upsert_team(mock_session, league_id=1, identity=identity)

        assert result == 42

    def test_creates_new_team(self):
        """Creates new team when not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Mock the execute to return a new team ID
        mock_result = MagicMock()
        mock_result.inserted_primary_key = [100]
        mock_session.execute.return_value = mock_result

        identity = TeamIdentity(league_code="NBA", name="New Team", abbreviation="NEW")
        result = _upsert_team(mock_session, league_id=1, identity=identity)

        assert mock_session.execute.called or mock_session.add.called


class TestDeriveAbbreviation:
    """Tests for _derive_abbreviation function."""

    def test_derives_abbreviation_from_multi_word_name(self):
        """Derives abbreviation from multi-word team name."""
        result = _derive_abbreviation("Boston Celtics")
        # Should take first letter of each word: BC
        assert len(result) >= 2
        assert result[0] == "B"

    def test_handles_empty_string(self):
        """Handles empty string input."""
        result = _derive_abbreviation("")
        assert result == "UNK"

    def test_handles_none_input(self):
        """Handles None input gracefully."""
        result = _derive_abbreviation(None)
        assert result == "UNK"

    def test_removes_stopwords(self):
        """Removes stopwords like 'of' and 'the'."""
        result = _derive_abbreviation("University of Michigan")
        # "of" is a stopword, so should be UM not UOM
        assert "O" not in result or len(result) <= 3

    def test_uc_prefix_expansion(self):
        """Handles UC prefix for schools like UC Irvine."""
        result = _derive_abbreviation("UC Irvine")
        # Should become UCI (UC + first 2 letters of Irvine)
        assert result.startswith("UC")
        assert len(result) <= 6

    def test_unc_prefix_expansion(self):
        """Handles UNC prefix for North Carolina schools."""
        result = _derive_abbreviation("UNC Wilmington")
        # Should become UNCWI or similar
        assert result.startswith("UNC")

    def test_single_word_name(self):
        """Handles single word team name."""
        result = _derive_abbreviation("Duke")
        # Should extend to at least 3 chars
        assert len(result) >= 3
        assert result[0] == "D"

    def test_max_length_six(self):
        """Abbreviation is max 6 characters."""
        result = _derive_abbreviation("Very Long Team Name That Goes On Forever")
        assert len(result) <= 6

    def test_special_characters_removed(self):
        """Removes special characters from name."""
        result = _derive_abbreviation("St. John's")
        # Should still produce valid abbreviation
        assert result.isalpha() or result.isalnum()
        assert len(result) >= 1


class TestNcaabAbbrevExpansions:
    """Tests for NCAAB abbreviation expansions."""

    def test_byu_expands(self):
        """BYU expands to Brigham Young."""
        assert _NCAAB_ABBREV_EXPANSIONS.get("byu") == "brigham young"

    def test_uconn_expands(self):
        """UConn expands to Connecticut."""
        assert _NCAAB_ABBREV_EXPANSIONS.get("uconn") == "connecticut"

    def test_lsu_expands(self):
        """LSU expands to Louisiana State."""
        assert _NCAAB_ABBREV_EXPANSIONS.get("lsu") == "louisiana state"

    def test_expansions_are_lowercase(self):
        """All expansion keys are lowercase."""
        for key in _NCAAB_ABBREV_EXPANSIONS.keys():
            assert key == key.lower()


class TestNormalizeNcaabNameForMatchingAdvanced:
    """Advanced tests for _normalize_ncaab_name_for_matching function."""

    def test_removes_parenthetical_qualifiers(self):
        """Removes parenthetical qualifiers like (NY)."""
        result = _normalize_ncaab_name_for_matching("St. John's (NY)")
        assert "(ny)" not in result
        assert "ny" not in result.split()

    def test_handles_hyphenated_names(self):
        """Handles hyphenated team names."""
        result = _normalize_ncaab_name_for_matching("Arkansas-Pine Bluff")
        # Should still process the name
        assert len(result) > 0

    def test_normalizes_whitespace(self):
        """Normalizes multiple whitespace to single space."""
        result = _normalize_ncaab_name_for_matching("Duke    Blue    Devils")
        assert "  " not in result

    def test_expands_u_to_university(self):
        """Expands 'U' to 'University'."""
        result = _normalize_ncaab_name_for_matching("Miami U")
        assert "university" in result

    def test_preserves_saint_abbreviation(self):
        """Preserves St. (with period) as Saint."""
        result = _normalize_ncaab_name_for_matching("St. John's")
        # St. should NOT become State. - period indicates Saint
        assert "state" not in result

    def test_expands_common_abbreviations(self):
        """Expands common abbreviations like BYU."""
        result = _normalize_ncaab_name_for_matching("BYU Cougars")
        # BYU should expand to "brigham young", and "cougars" is a stopword
        assert "brigham" in result or "byu" in result


class TestNcaabStopwordsAdvanced:
    """Advanced tests for NCAAB stopwords."""

    def test_contains_colors(self):
        """Contains color words commonly in team names."""
        assert "blue" in _NCAAB_STOPWORDS
        assert "red" in _NCAAB_STOPWORDS
        assert "gold" in _NCAAB_STOPWORDS
        assert "golden" in _NCAAB_STOPWORDS

    def test_contains_common_mascots(self):
        """Contains commonly duplicated mascots."""
        assert "wildcats" in _NCAAB_STOPWORDS
        assert "cardinals" in _NCAAB_STOPWORDS
        assert "spartans" in _NCAAB_STOPWORDS
        assert "trojans" in _NCAAB_STOPWORDS

    def test_does_not_contain_school_words(self):
        """Does not contain school-type words."""
        # These should NOT be stopwords
        assert "university" not in _NCAAB_STOPWORDS
        assert "college" not in _NCAAB_STOPWORDS
        assert "state" not in _NCAAB_STOPWORDS


class TestFindTeamByName:
    """Tests for _find_team_by_name function."""

    def test_function_exists(self):
        """Function exists in module."""
        from sports_scraper.persistence.teams import _find_team_by_name
        assert callable(_find_team_by_name)

    def test_function_signature(self):
        """Function has expected parameters."""
        from sports_scraper.persistence.teams import _find_team_by_name
        import inspect
        sig = inspect.signature(_find_team_by_name)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "league_id" in params
        assert "team_name" in params
        assert "team_abbr" in params

    def test_returns_none_when_not_found(self):
        """Returns None when team not found."""
        from sports_scraper.persistence.teams import _find_team_by_name

        mock_session = MagicMock()
        mock_league = MagicMock(code="NBA")
        mock_session.get.return_value = mock_league
        mock_session.execute.return_value.all.return_value = []
        mock_session.execute.return_value.scalar.return_value = None

        result = _find_team_by_name(mock_session, league_id=1, team_name="Nonexistent Team")

        assert result is None

    def test_handles_ncaab_override(self):
        """Uses NCAAB override mappings."""
        from sports_scraper.persistence.teams import _NCAAB_OVERRIDES

        # Verify overrides exist
        assert "george washington colonials" in _NCAAB_OVERRIDES
        assert _NCAAB_OVERRIDES["george washington colonials"] == "George Washington"


class TestShouldLogTeams:
    """Tests for _should_log helper in teams module."""

    def test_logs_first_occurrence(self):
        """_should_log returns True for first occurrence."""
        from sports_scraper.persistence.teams import _should_log, _LOG_COUNTERS

        # Use unique key to avoid state from other tests
        import time
        key = f"test_event_{time.time()}"
        result = _should_log(key)
        assert result is True

    def test_skips_intermediate_occurrences(self):
        """_should_log returns False for intermediate occurrences."""
        from sports_scraper.persistence.teams import _should_log

        import time
        key = f"test_event_repeat_{time.time()}"

        _should_log(key)  # 1st - True
        result = _should_log(key)  # 2nd - False
        assert result is False


class TestUpsertTeamAdvanced:
    """Advanced tests for _upsert_team function."""

    def test_handles_missing_abbreviation(self):
        """Handles identity without abbreviation."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one.return_value = 42
        mock_league = MagicMock(code="NCAAB")
        mock_session.get.return_value = mock_league

        identity = TeamIdentity(league_code="NCAAB", name="Some University", abbreviation=None)
        result = _upsert_team(mock_session, league_id=9, identity=identity)

        assert result == 42
        mock_session.execute.assert_called_once()

    def test_uses_short_name_from_identity(self):
        """Uses short_name from identity when provided."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one.return_value = 42
        mock_league = MagicMock(code="NBA")
        mock_session.get.return_value = mock_league

        identity = TeamIdentity(
            league_code="NBA",
            name="Boston Celtics",
            abbreviation="BOS",
            short_name="Celtics"
        )
        result = _upsert_team(mock_session, league_id=1, identity=identity)

        assert result == 42

    def test_uses_external_ref(self):
        """Uses external_ref from identity."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one.return_value = 42
        mock_league = MagicMock(code="NBA")
        mock_session.get.return_value = mock_league

        identity = TeamIdentity(
            league_code="NBA",
            name="Boston Celtics",
            abbreviation="BOS",
            external_ref="nba_team_123"
        )
        result = _upsert_team(mock_session, league_id=1, identity=identity)

        assert result == 42


class TestNcaabOverrides:
    """Tests for NCAAB name override mappings."""

    def test_has_common_overrides(self):
        """Has common NCAAB overrides."""
        from sports_scraper.persistence.teams import _NCAAB_OVERRIDES

        assert isinstance(_NCAAB_OVERRIDES, dict)
        assert len(_NCAAB_OVERRIDES) > 0

    def test_override_keys_are_lowercase(self):
        """Override keys are lowercase."""
        from sports_scraper.persistence.teams import _NCAAB_OVERRIDES

        for key in _NCAAB_OVERRIDES.keys():
            assert key == key.lower()


class TestAbbrStopwords:
    """Tests for abbreviation stopwords."""

    def test_has_common_stopwords(self):
        """Has common stopwords for abbreviation derivation."""
        from sports_scraper.persistence.teams import _ABBR_STOPWORDS

        assert "of" in _ABBR_STOPWORDS
        assert "the" in _ABBR_STOPWORDS
        assert "and" in _ABBR_STOPWORDS
        assert "at" in _ABBR_STOPWORDS

    def test_is_set(self):
        """Is a set for fast lookups."""
        from sports_scraper.persistence.teams import _ABBR_STOPWORDS

        assert isinstance(_ABBR_STOPWORDS, (set, frozenset))
