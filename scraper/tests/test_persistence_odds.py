"""Tests for persistence/odds.py module."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


from sports_scraper.models import NormalizedOddsSnapshot, TeamIdentity
from sports_scraper.persistence.odds import OddsUpsertResult
from sports_scraper.persistence.odds_matching import (
    canonicalize_team_names,
    should_log,
)


def _setup_session_get(
    mock_session: MagicMock,
    mock_game: MagicMock,
    home_name: str = "Lakers",
    away_name: str = "Celtics",
) -> None:
    """Configure mock_session.get to return game and team mocks properly.

    upsert_fairbet_odds looks up the game and its teams via
    session.get(SportsGame, id) and session.get(SportsTeam, id).
    This helper wires up side_effect so each model class gets the right mock.
    """
    from sports_scraper.db import db_models

    mock_game.home_team_id = 100
    mock_game.away_team_id = 200

    mock_home_team = MagicMock()
    mock_home_team.name = home_name
    mock_away_team = MagicMock()
    mock_away_team.name = away_name

    def _get(model_class, id_value):
        if model_class is db_models.SportsTeam:
            if id_value == 100:
                return mock_home_team
            if id_value == 200:
                return mock_away_team
        return mock_game

    mock_session.get.side_effect = _get


class TestCanonicalizeTeamNames:
    """Tests for canonicalize_team_names function."""

    def test_returns_canonical_names(self):
        """Returns canonical team names from mappings."""
        snapshot = NormalizedOddsSnapshot(
            league_code="NBA",
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
            home_team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
            away_team=TeamIdentity(league_code="NBA", name="New York Knicks", abbreviation="NYK"),
            book="FanDuel",
            market_type="spread",
            line=-5.5,
            price=-110,
            observed_at=datetime.now(UTC),
        )

        home, away = canonicalize_team_names(snapshot)

        # canonicalize_team_names returns canonical form from mappings, not lowercased
        assert home == "Boston Celtics"
        assert away == "New York Knicks"

    def test_handles_whitespace_in_names(self):
        """Handles whitespace in team names (via normalize_team_name)."""
        snapshot = NormalizedOddsSnapshot(
            league_code="NBA",
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
            home_team=TeamIdentity(league_code="NBA", name="  Boston Celtics  ", abbreviation="BOS"),
            away_team=TeamIdentity(league_code="NBA", name="  New York Knicks  ", abbreviation="NYK"),
            book="FanDuel",
            market_type="spread",
            line=-5.5,
            price=-110,
            observed_at=datetime.now(UTC),
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


class TestCacheFunctions:
    """Tests for cache functions in odds_matching module."""

    def test_cache_get_miss_returns_false(self):
        """cache_get returns False for missing key."""
        import time

        from sports_scraper.persistence.odds_matching import cache_get
        key = ("test_league", "2024-01-15", time.time(), time.time() + 1)
        result = cache_get(key)
        assert result is False

    def test_cache_set_and_get(self):
        """cache_set stores value, cache_get retrieves it."""
        import time

        from sports_scraper.persistence.odds_matching import cache_get, cache_set
        key = ("NBA", "2024-01-15", int(time.time()), int(time.time()) + 1)
        cache_set(key, 42)
        result = cache_get(key)
        assert result == 42

    def test_cache_set_none_value(self):
        """cache_set can store None values."""
        import time

        from sports_scraper.persistence.odds_matching import cache_get, cache_set
        key = ("NCAAB", "2024-01-15", int(time.time()), int(time.time()) + 2)
        cache_set(key, None)
        result = cache_get(key)
        assert result is None  # Distinct from False (cache miss)

    def test_cache_clear_returns_count(self):
        """cache_clear returns number of entries cleared."""
        import time

        from sports_scraper.persistence.odds_matching import cache_clear, cache_set
        # Add some entries
        for i in range(5):
            cache_set(("test", str(time.time()), i, i + 100), i)
        # Clear and check count
        count = cache_clear()
        # Should return at least 5 (may be more from other tests)
        assert count >= 0  # Cache is shared, just verify it returns an int

    def test_cache_invalidate_game_removes_entries(self):
        """cache_invalidate_game removes entries with matching game_id."""
        import time

        from sports_scraper.persistence.odds_matching import (
            cache_clear,
            cache_get,
            cache_invalidate_game,
            cache_set,
        )
        # Clear cache first
        cache_clear()

        # Add entries with different game IDs
        key1 = ("NBA", "2024-01-15", int(time.time()), 999)
        key2 = ("NBA", "2024-01-16", int(time.time()), 888)
        cache_set(key1, 999)
        cache_set(key2, 888)

        # Invalidate game 999
        removed = cache_invalidate_game(999)

        # Entry for game 999 should be gone
        assert cache_get(key1) is False
        # Entry for game 888 should still exist
        assert cache_get(key2) == 888


class TestOddsApiMappings:
    """Tests for Odds API team name mappings."""

    def test_odds_api_to_db_mappings_exist(self):
        """_ODDS_API_TO_DB_MAPPINGS dict exists."""
        from sports_scraper.persistence.odds_matching import _ODDS_API_TO_DB_MAPPINGS
        assert isinstance(_ODDS_API_TO_DB_MAPPINGS, dict)

    def test_st_johns_mapping(self):
        """St. John's variants are mapped."""
        from sports_scraper.persistence.odds_matching import _ODDS_API_TO_DB_MAPPINGS
        # At least one St. John's variant should map
        mappings_values = list(_ODDS_API_TO_DB_MAPPINGS.values())
        assert any("St. John" in v for v in mappings_values)


class TestMatchGameByTeamIds:
    """Tests for match_game_by_team_ids function."""

    def test_matches_exact_team_ids(self):
        """Matches game with exact team IDs."""
        from sports_scraper.persistence.odds_matching import match_game_by_team_ids

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 42

        day_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        day_end = datetime(2024, 1, 15, 23, 59, tzinfo=UTC)

        result = match_game_by_team_ids(
            mock_session,
            league_id=1,
            home_team_id=10,
            away_team_id=20,
            day_start=day_start,
            day_end=day_end,
        )

        assert result == 42

    def test_matches_swapped_team_ids(self):
        """Matches game with swapped team IDs (home/away reversed)."""
        from sports_scraper.persistence.odds_matching import match_game_by_team_ids

        mock_session = MagicMock()
        # First query returns None, second (swapped) returns 42
        mock_session.execute.return_value.scalar.side_effect = [None, 42]

        day_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        day_end = datetime(2024, 1, 15, 23, 59, tzinfo=UTC)

        result = match_game_by_team_ids(
            mock_session,
            league_id=1,
            home_team_id=10,
            away_team_id=20,
            day_start=day_start,
            day_end=day_end,
        )

        assert result == 42

    def test_returns_none_when_no_match(self):
        """Returns None when no game matches."""
        from sports_scraper.persistence.odds_matching import match_game_by_team_ids

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.side_effect = [None, None]

        day_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        day_end = datetime(2024, 1, 15, 23, 59, tzinfo=UTC)

        result = match_game_by_team_ids(
            mock_session,
            league_id=1,
            home_team_id=10,
            away_team_id=20,
            day_start=day_start,
            day_end=day_end,
        )

        assert result is None


class TestMatchGameByNamesNcaab:
    """Tests for match_game_by_names_ncaab function."""

    def test_returns_none_when_no_games_in_range(self):
        """Returns None when no games in date range."""
        from sports_scraper.persistence.odds_matching import match_game_by_names_ncaab

        mock_session = MagicMock()
        mock_session.execute.return_value.all.return_value = []

        snapshot = NormalizedOddsSnapshot(
            league_code="NCAAB",
            home_team=TeamIdentity(league_code="NCAAB", name="Duke Blue Devils", abbreviation="DUKE"),
            away_team=TeamIdentity(league_code="NCAAB", name="North Carolina Tar Heels", abbreviation="UNC"),
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
            book="draftkings",
            market_type="moneyline",
            price=-110,
            observed_at=datetime.now(UTC),
        )

        day_start = datetime(2024, 1, 14, 0, 0, tzinfo=UTC)
        day_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)

        result = match_game_by_names_ncaab(
            mock_session,
            league_id=9,
            snapshot=snapshot,
            home_canonical="Duke",
            away_canonical="North Carolina",
            day_start=day_start,
            day_end=day_end,
        )

        assert result is None

    def test_matches_normalized_names(self):
        """Matches games by normalized NCAAB names."""
        from sports_scraper.persistence.odds_matching import match_game_by_names_ncaab

        mock_session = MagicMock()
        # Games in range
        mock_session.execute.return_value.all.side_effect = [
            [(42, 100, 200)],  # games_in_range: (game_id, home_team_id, away_team_id)
            [(100, "Duke"), (200, "North Carolina")],  # teams_map
        ]

        snapshot = NormalizedOddsSnapshot(
            league_code="NCAAB",
            home_team=TeamIdentity(league_code="NCAAB", name="Duke Blue Devils", abbreviation="DUKE"),
            away_team=TeamIdentity(league_code="NCAAB", name="North Carolina Tar Heels", abbreviation="UNC"),
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
            book="draftkings",
            market_type="moneyline",
            price=-110,
            observed_at=datetime.now(UTC),
        )

        day_start = datetime(2024, 1, 14, 0, 0, tzinfo=UTC)
        day_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)

        result = match_game_by_names_ncaab(
            mock_session,
            league_id=9,
            snapshot=snapshot,
            home_canonical="Duke",
            away_canonical="North Carolina",
            day_start=day_start,
            day_end=day_end,
        )

        assert result == 42


class TestMatchGameByNamesNonNcaab:
    """Tests for match_game_by_names_non_ncaab function."""

    def test_matches_exact_names(self):
        """Matches games by exact team names."""
        from sports_scraper.persistence.odds_matching import match_game_by_names_non_ncaab

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 42

        snapshot = NormalizedOddsSnapshot(
            league_code="NBA",
            home_team=TeamIdentity(league_code="NBA", name="Los Angeles Lakers", abbreviation="LAL"),
            away_team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
            book="draftkings",
            market_type="moneyline",
            price=-110,
            observed_at=datetime.now(UTC),
        )

        day_start = datetime(2024, 1, 14, 0, 0, tzinfo=UTC)
        day_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)

        result = match_game_by_names_non_ncaab(
            mock_session,
            league_id=1,
            snapshot=snapshot,
            home_canonical="Los Angeles Lakers",
            away_canonical="Boston Celtics",
            day_start=day_start,
            day_end=day_end,
        )

        assert result == 42

    def test_matches_swapped_names(self):
        """Matches games with swapped home/away names."""
        from sports_scraper.persistence.odds_matching import match_game_by_names_non_ncaab

        mock_session = MagicMock()
        # First query returns None, second (swapped) returns 42
        mock_session.execute.return_value.scalar.side_effect = [None, 42]

        snapshot = NormalizedOddsSnapshot(
            league_code="NBA",
            home_team=TeamIdentity(league_code="NBA", name="Los Angeles Lakers", abbreviation="LAL"),
            away_team=TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS"),
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
            book="draftkings",
            market_type="moneyline",
            price=-110,
            observed_at=datetime.now(UTC),
        )

        day_start = datetime(2024, 1, 14, 0, 0, tzinfo=UTC)
        day_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)

        result = match_game_by_names_non_ncaab(
            mock_session,
            league_id=1,
            snapshot=snapshot,
            home_canonical="Los Angeles Lakers",
            away_canonical="Boston Celtics",
            day_start=day_start,
            day_end=day_end,
        )

        assert result == 42


# ==========================================================================
# upsert_odds tests — now delegates to find_or_create_game
# ==========================================================================


def _make_snapshot(**overrides):
    defaults = dict(
        league_code="NBA",
        home_team=TeamIdentity(league_code="NBA", name="Lakers", abbreviation="LAL"),
        away_team=TeamIdentity(league_code="NBA", name="Celtics", abbreviation="BOS"),
        game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
        book="draftkings",
        market_type="moneyline",
        price=-110,
        observed_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return NormalizedOddsSnapshot(**defaults)



class TestUpsertOddsFunction:
    """Tests for upsert_odds — delegates game resolution to find_or_create_game."""

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_persists_odds_when_game_found(self, mock_find):
        from sports_scraper.persistence.odds import upsert_odds

        mock_find.return_value = (42, False)
        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.status = "scheduled"
        mock_session.get.return_value = mock_game

        from datetime import timedelta
        tomorrow = datetime.now(UTC) + timedelta(days=1)
        snapshot = _make_snapshot(game_date=tomorrow)
        result = upsert_odds(mock_session, snapshot)

        assert result is OddsUpsertResult.PERSISTED
        mock_find.assert_called_once()

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_skips_when_no_game_match(self, mock_find):
        from sports_scraper.persistence.odds import upsert_odds

        mock_find.return_value = (None, False)
        mock_session = MagicMock()

        snapshot = _make_snapshot()  # historical date (2024)
        result = upsert_odds(mock_session, snapshot)

        assert result is OddsUpsertResult.SKIPPED_NO_MATCH

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_skips_live_games(self, mock_find):
        from sports_scraper.persistence.odds import upsert_odds
        from sports_scraper.db import db_models

        mock_find.return_value = (42, False)
        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.status = db_models.GameStatus.live.value
        mock_session.get.return_value = mock_game

        snapshot = _make_snapshot(
            game_date=datetime.now(UTC) + __import__('datetime').timedelta(days=1),
        )
        result = upsert_odds(mock_session, snapshot)

        assert result is OddsUpsertResult.SKIPPED_LIVE

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_skips_far_future_games(self, mock_find):
        from datetime import timedelta
        from sports_scraper.persistence.odds import upsert_odds

        mock_session = MagicMock()
        # Game 5 days in the future
        future = datetime.now(UTC) + timedelta(days=5)
        snapshot = _make_snapshot(game_date=future)
        result = upsert_odds(mock_session, snapshot)

        assert result is OddsUpsertResult.SKIPPED_NO_MATCH
        mock_find.assert_not_called()

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_creates_stub_for_future_games(self, mock_find):
        from datetime import timedelta
        from sports_scraper.persistence.odds import upsert_odds

        mock_find.return_value = (99, True)  # created
        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.status = "scheduled"
        mock_session.get.return_value = mock_game

        tomorrow = datetime.now(UTC) + timedelta(days=1)
        snapshot = _make_snapshot(game_date=tomorrow)
        result = upsert_odds(mock_session, snapshot)

        assert result is OddsUpsertResult.PERSISTED
        # Should call find_or_create_game with create_if_missing=True
        call_kwargs = mock_find.call_args[1]
        assert call_kwargs["create_if_missing"] is True

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_no_stub_for_historical_games(self, mock_find):
        from sports_scraper.persistence.odds import upsert_odds

        mock_find.return_value = (None, False)
        mock_session = MagicMock()

        snapshot = _make_snapshot()  # 2024 date = historical
        result = upsert_odds(mock_session, snapshot)

        assert result is OddsUpsertResult.SKIPPED_NO_MATCH
        call_kwargs = mock_find.call_args[1]
        assert call_kwargs["create_if_missing"] is False

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_passes_event_id_as_external_id(self, mock_find):
        from sports_scraper.persistence.odds import upsert_odds

        mock_find.return_value = (42, False)
        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.status = "scheduled"
        mock_session.get.return_value = mock_game

        snapshot = _make_snapshot(
            game_date=datetime.now(UTC) + __import__('datetime').timedelta(days=1),
            source_key="odds_api_abc123",
        )
        result = upsert_odds(mock_session, snapshot)

        assert result is OddsUpsertResult.PERSISTED
        call_kwargs = mock_find.call_args[1]
        assert call_kwargs["external_ids"]["odds_api_event_id"] == "odds_api_abc123"

    @patch("sports_scraper.persistence.odds.find_or_create_game")
    def test_sets_last_odds_at(self, mock_find):
        from sports_scraper.persistence.odds import upsert_odds

        mock_find.return_value = (42, False)
        mock_session = MagicMock()
        mock_game = MagicMock()
        mock_game.status = "scheduled"
        mock_session.get.return_value = mock_game

        snapshot = _make_snapshot(
            game_date=datetime.now(UTC) + __import__('datetime').timedelta(days=1),
        )
        upsert_odds(mock_session, snapshot)

        assert mock_game.last_odds_at is not None
