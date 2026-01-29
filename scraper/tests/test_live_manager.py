"""Tests for live/manager.py module."""

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


from sports_scraper.live.manager import (
    LiveFeedSummary,
    LiveFeedManager,
    _iter_dates,
    _filter_new_plays,
    _should_skip_pbp,
    _max_play_index,
    _find_game_by_abbr,
)
from sports_scraper.models import IngestionConfig, NormalizedPlay


class TestLiveFeedSummary:
    """Tests for LiveFeedSummary dataclass."""

    def test_create_summary(self):
        """Can create a summary with all fields."""
        summary = LiveFeedSummary(
            games_touched=10,
            pbp_games=5,
            pbp_events=150,
        )
        assert summary.games_touched == 10
        assert summary.pbp_games == 5
        assert summary.pbp_events == 150

    def test_summary_is_frozen(self):
        """Summary is immutable."""
        summary = LiveFeedSummary(games_touched=10, pbp_games=5, pbp_events=150)
        with pytest.raises(Exception):  # FrozenInstanceError
            summary.games_touched = 20

    def test_zero_summary(self):
        """Can create a zero summary."""
        summary = LiveFeedSummary(games_touched=0, pbp_games=0, pbp_events=0)
        assert summary.games_touched == 0
        assert summary.pbp_games == 0
        assert summary.pbp_events == 0


class TestIterDates:
    """Tests for _iter_dates helper function."""

    def test_single_day(self):
        """Returns single day for same start and end."""
        result = _iter_dates(date(2024, 1, 15), date(2024, 1, 15))
        assert result == [date(2024, 1, 15)]

    def test_multiple_days(self):
        """Returns all days in range."""
        result = _iter_dates(date(2024, 1, 15), date(2024, 1, 17))
        assert result == [
            date(2024, 1, 15),
            date(2024, 1, 16),
            date(2024, 1, 17),
        ]

    def test_month_boundary(self):
        """Handles month boundary correctly."""
        result = _iter_dates(date(2024, 1, 30), date(2024, 2, 2))
        assert len(result) == 4
        assert result[0] == date(2024, 1, 30)
        assert result[-1] == date(2024, 2, 2)

    def test_empty_range(self):
        """Returns empty list when end before start."""
        result = _iter_dates(date(2024, 1, 17), date(2024, 1, 15))
        assert result == []


class TestFilterNewPlays:
    """Tests for _filter_new_plays helper function."""

    def test_all_plays_when_max_none(self):
        """Returns all plays when max_index is None."""
        plays = [
            NormalizedPlay(play_index=1, quarter=1, game_clock="12:00", play_type="shot", description="test"),
            NormalizedPlay(play_index=2, quarter=1, game_clock="11:45", play_type="shot", description="test"),
        ]
        result = _filter_new_plays(plays, None)
        assert len(result) == 2

    def test_filters_old_plays(self):
        """Filters plays with index <= max_index."""
        plays = [
            NormalizedPlay(play_index=1, quarter=1, game_clock="12:00", play_type="shot", description="test"),
            NormalizedPlay(play_index=2, quarter=1, game_clock="11:45", play_type="shot", description="test"),
            NormalizedPlay(play_index=3, quarter=1, game_clock="11:30", play_type="shot", description="test"),
        ]
        result = _filter_new_plays(plays, 2)
        assert len(result) == 1
        assert result[0].play_index == 3

    def test_returns_empty_when_all_old(self):
        """Returns empty when all plays are old."""
        plays = [
            NormalizedPlay(play_index=1, quarter=1, game_clock="12:00", play_type="shot", description="test"),
            NormalizedPlay(play_index=2, quarter=1, game_clock="11:45", play_type="shot", description="test"),
        ]
        result = _filter_new_plays(plays, 5)
        assert result == []

    def test_empty_plays_list(self):
        """Handles empty plays list."""
        result = _filter_new_plays([], 5)
        assert result == []


class TestShouldSkipPbp:
    """Tests for _should_skip_pbp helper function."""

    def test_returns_false_when_no_filters(self):
        """Returns False when no filters applied."""
        mock_session = MagicMock()
        result = _should_skip_pbp(mock_session, game_id=1, only_missing=False, updated_before=None)
        assert result is False

    def test_skips_when_only_missing_and_has_plays(self):
        """Skips when only_missing=True and game has plays."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 10  # 10 plays exist

        result = _should_skip_pbp(mock_session, game_id=1, only_missing=True, updated_before=None)
        assert result is True

    def test_continues_when_only_missing_and_no_plays(self):
        """Continues when only_missing=True and game has no plays."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 0

        result = _should_skip_pbp(mock_session, game_id=1, only_missing=True, updated_before=None)
        assert result is False

    def test_skips_when_recently_updated(self):
        """Skips when plays were updated after updated_before."""
        mock_session = MagicMock()
        now = datetime.now(timezone.utc)
        mock_session.execute.return_value.scalar.return_value = now  # Updated now

        result = _should_skip_pbp(
            mock_session,
            game_id=1,
            only_missing=False,
            updated_before=now - timedelta(hours=1),  # Cutoff was 1 hour ago
        )
        assert result is True

    def test_continues_when_stale(self):
        """Continues when plays are stale."""
        mock_session = MagicMock()
        old_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_session.execute.return_value.scalar.return_value = old_time

        result = _should_skip_pbp(
            mock_session,
            game_id=1,
            only_missing=False,
            updated_before=datetime.now(timezone.utc),
        )
        assert result is False


class TestMaxPlayIndex:
    """Tests for _max_play_index helper function."""

    def test_returns_max_index(self):
        """Returns the maximum play index."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 42

        result = _max_play_index(mock_session, game_id=1)
        assert result == 42

    def test_returns_none_when_no_plays(self):
        """Returns None when game has no plays."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = None

        result = _max_play_index(mock_session, game_id=1)
        assert result is None


class TestFindGameByAbbr:
    """Tests for _find_game_by_abbr helper function."""

    def test_returns_none_when_no_league(self):
        """Returns None when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = _find_game_by_abbr(mock_session, "NBA", "BOS", "LAL", date(2024, 1, 15))
        assert result is None

    def test_returns_none_when_team_not_found(self):
        """Returns None when team not found."""
        mock_session = MagicMock()
        mock_league = MagicMock(id=1)
        # First call returns league, second returns None (team not found)
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_league,  # League found
            None,  # Home team not found
        ]
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = None

        result = _find_game_by_abbr(mock_session, "NBA", "XXX", "YYY", date(2024, 1, 15))
        # Should return None because teams not found
        assert result is None


class TestLiveFeedManager:
    """Tests for LiveFeedManager class."""

    @patch("sports_scraper.live.manager.NHLLiveFeedClient")
    @patch("sports_scraper.live.manager.NBALiveFeedClient")
    def test_init_creates_clients(self, mock_nba_client, mock_nhl_client):
        """__init__ creates NBA and NHL clients."""
        manager = LiveFeedManager()
        mock_nba_client.assert_called_once()
        mock_nhl_client.assert_called_once()

    @patch("sports_scraper.live.manager.NHLLiveFeedClient")
    @patch("sports_scraper.live.manager.NBALiveFeedClient")
    def test_ingest_ncaab_returns_empty_summary(self, mock_nba_client, mock_nhl_client):
        """ingest_live_data for NCAAB returns empty summary (no live feed)."""
        manager = LiveFeedManager()
        mock_session = MagicMock()
        config = IngestionConfig(
            league_code="NCAAB",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        result = manager.ingest_live_data(mock_session, config=config, updated_before=None)

        assert result.games_touched == 0
        assert result.pbp_games == 0
        assert result.pbp_events == 0

    @patch("sports_scraper.live.manager.NHLLiveFeedClient")
    @patch("sports_scraper.live.manager.NBALiveFeedClient")
    def test_ingest_unknown_league_returns_empty_summary(self, mock_nba_client, mock_nhl_client):
        """ingest_live_data for unknown league returns empty summary."""
        manager = LiveFeedManager()
        mock_session = MagicMock()
        config = IngestionConfig(
            league_code="UNKNOWN",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        result = manager.ingest_live_data(mock_session, config=config, updated_before=None)

        assert result.games_touched == 0
        assert result.pbp_games == 0
        assert result.pbp_events == 0

    @patch("sports_scraper.live.manager.NHLLiveFeedClient")
    @patch("sports_scraper.live.manager.NBALiveFeedClient")
    def test_sync_nba_returns_empty_when_no_dates(self, mock_nba_client, mock_nhl_client):
        """_sync_nba returns empty summary when no dates."""
        manager = LiveFeedManager()
        mock_session = MagicMock()
        config = IngestionConfig(
            league_code="NBA",
            start_date=None,
            end_date=None,
        )

        result = manager._sync_nba(mock_session, config, updated_before=None)

        assert result.games_touched == 0
        assert result.pbp_games == 0
        assert result.pbp_events == 0

    @patch("sports_scraper.live.manager.NHLLiveFeedClient")
    @patch("sports_scraper.live.manager.NBALiveFeedClient")
    def test_sync_nhl_returns_empty_when_no_dates(self, mock_nba_client, mock_nhl_client):
        """_sync_nhl returns empty summary when no dates."""
        manager = LiveFeedManager()
        mock_session = MagicMock()
        config = IngestionConfig(
            league_code="NHL",
            start_date=None,
            end_date=None,
        )

        result = manager._sync_nhl(mock_session, config, updated_before=None)

        assert result.games_touched == 0
        assert result.pbp_games == 0
        assert result.pbp_events == 0

    @patch("sports_scraper.live.manager.NHLLiveFeedClient")
    @patch("sports_scraper.live.manager.NBALiveFeedClient")
    def test_sync_nba_handles_no_games(self, mock_nba_client_class, mock_nhl_client_class):
        """_sync_nba handles empty scoreboard."""
        mock_nba_client = MagicMock()
        mock_nba_client.fetch_scoreboard.return_value = []
        mock_nba_client_class.return_value = mock_nba_client

        manager = LiveFeedManager()
        mock_session = MagicMock()
        config = IngestionConfig(
            league_code="NBA",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        result = manager._sync_nba(mock_session, config, updated_before=None)

        assert result.games_touched == 0

    @patch("sports_scraper.live.manager.upsert_game_stub")
    @patch("sports_scraper.live.manager.NHLLiveFeedClient")
    @patch("sports_scraper.live.manager.NBALiveFeedClient")
    def test_sync_nhl_upserts_games(self, mock_nba_client_class, mock_nhl_client_class, mock_upsert):
        """_sync_nhl upserts games from schedule."""
        from sports_scraper.models import TeamIdentity

        mock_nhl_client = MagicMock()
        mock_live_game = MagicMock()
        mock_live_game.game_id = 2025020001
        mock_live_game.game_date = datetime(2024, 10, 15, 19, 0, tzinfo=timezone.utc)
        mock_live_game.home_team = TeamIdentity(league_code="NHL", name="TBL", abbreviation="TBL")
        mock_live_game.away_team = TeamIdentity(league_code="NHL", name="BOS", abbreviation="BOS")
        mock_live_game.status = "final"
        mock_live_game.home_score = 4
        mock_live_game.away_score = 3
        mock_nhl_client.fetch_schedule.return_value = [mock_live_game]
        mock_nhl_client_class.return_value = mock_nhl_client

        mock_upsert.return_value = (1, True)  # game_id=1, created=True

        manager = LiveFeedManager()
        mock_session = MagicMock()
        mock_session.get.return_value = None  # Game not found after upsert (skip PBP)

        config = IngestionConfig(
            league_code="NHL",
            start_date=date(2024, 10, 15),
            end_date=date(2024, 10, 15),
        )

        result = manager._sync_nhl(mock_session, config, updated_before=None)

        assert result.games_touched == 1
        mock_upsert.assert_called_once()


class TestModuleImports:
    """Tests for manager module imports."""

    def test_has_live_feed_summary(self):
        """Module has LiveFeedSummary class."""
        from sports_scraper.live import manager
        assert hasattr(manager, 'LiveFeedSummary')

    def test_has_live_feed_manager(self):
        """Module has LiveFeedManager class."""
        from sports_scraper.live import manager
        assert hasattr(manager, 'LiveFeedManager')

    def test_has_iter_dates(self):
        """Module has _iter_dates helper."""
        from sports_scraper.live import manager
        assert hasattr(manager, '_iter_dates')

    def test_has_filter_new_plays(self):
        """Module has _filter_new_plays helper."""
        from sports_scraper.live import manager
        assert hasattr(manager, '_filter_new_plays')

    def test_has_should_skip_pbp(self):
        """Module has _should_skip_pbp helper."""
        from sports_scraper.live import manager
        assert hasattr(manager, '_should_skip_pbp')
