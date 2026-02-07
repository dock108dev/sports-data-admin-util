"""Tests for tweet-to-game mapping (two-phase social architecture)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sports_scraper.social.tweet_mapper import (
    get_game_window,
    get_mapping_stats,
    map_tweets_for_team,
    map_unmapped_tweets,
)


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _make_game(**kwargs) -> MagicMock:
    game = MagicMock()
    game.id = kwargs.get("id", 1)
    game.tip_time = kwargs.get("tip_time")
    game.game_date = kwargs.get("game_date", _utc(2025, 6, 15, 0, 0))
    game.end_time = kwargs.get("end_time")
    game.home_team_id = kwargs.get("home_team_id", 100)
    game.away_team_id = kwargs.get("away_team_id", 200)
    return game


def _make_tweet(**kwargs) -> MagicMock:
    tweet = MagicMock()
    tweet.id = kwargs.get("id", 1)
    tweet.team_id = kwargs.get("team_id", 100)
    tweet.posted_at = kwargs.get("posted_at", _utc(2025, 6, 15, 20, 0))
    tweet.mapping_status = kwargs.get("mapping_status", "unmapped")
    tweet.game_id = kwargs.get("game_id", None)
    tweet.game_phase = kwargs.get("game_phase", None)
    tweet.updated_at = kwargs.get("updated_at", None)
    return tweet


# ---------------------------------------------------------------------------
# get_game_window
# ---------------------------------------------------------------------------
class TestGetGameWindow:
    def test_tip_time_available(self):
        game = _make_game(tip_time=_utc(2025, 6, 15, 19, 0))
        start, end = get_game_window(game)
        assert start == _utc(2025, 6, 15, 16, 0)  # 3h before
        assert end == _utc(2025, 6, 16, 1, 0)      # 3h after estimated end (19+3+3)

    def test_falls_back_to_game_date(self):
        game = _make_game(tip_time=None, game_date=_utc(2025, 6, 15, 15, 0))
        start, end = get_game_window(game)
        assert start == _utc(2025, 6, 15, 12, 0)  # 3h before 15:00

    def test_midnight_estimates_7pm_et(self):
        game = _make_game(tip_time=None, game_date=_utc(2025, 6, 15, 0, 0))
        start, end = get_game_window(game)
        # 7 PM ET = 23:00 UTC (in summer EDT)
        assert start.hour < 23  # pregame window before 7pm ET

    def test_uses_actual_end_time(self):
        game = _make_game(
            tip_time=_utc(2025, 6, 15, 19, 0),
            end_time=_utc(2025, 6, 15, 22, 30),
        )
        start, end = get_game_window(game)
        assert end == _utc(2025, 6, 16, 1, 30)  # 3h after actual end

    def test_ignores_end_time_before_start(self):
        game = _make_game(
            tip_time=_utc(2025, 6, 15, 19, 0),
            end_time=_utc(2025, 6, 15, 18, 0),  # before tip
        )
        start, end = get_game_window(game)
        # Falls back to estimated end (tip + 3h duration)
        assert end == _utc(2025, 6, 16, 1, 0)

    def test_naive_datetime_gets_utc(self):
        naive_tip = datetime(2025, 6, 15, 19, 0)  # no tzinfo
        game = _make_game(tip_time=naive_tip)
        start, end = get_game_window(game)
        assert start.tzinfo is not None
        assert end.tzinfo is not None

    def test_custom_window_params(self):
        game = _make_game(tip_time=_utc(2025, 6, 15, 19, 0))
        start, end = get_game_window(game, pregame_hours=1, postgame_hours=1, game_duration_hours=2)
        assert start == _utc(2025, 6, 15, 18, 0)
        assert end == _utc(2025, 6, 15, 22, 0)  # 19+2+1


# ---------------------------------------------------------------------------
# map_unmapped_tweets
# ---------------------------------------------------------------------------
class TestMapUnmappedTweets:
    @patch("sports_scraper.social.tweet_mapper.now_utc", return_value=_utc(2025, 6, 15, 23, 0))
    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_maps_tweet_to_matching_game(self, mock_db, mock_now):
        game = _make_game(
            id=10,
            tip_time=_utc(2025, 6, 15, 19, 0),
            home_team_id=100,
        )
        tweet = _make_tweet(
            team_id=100,
            posted_at=_utc(2025, 6, 15, 20, 0),
        )

        session = MagicMock()
        # First call returns tweets, second call returns empty (end loop)
        session.query.return_value.filter.return_value.limit.return_value.all.side_effect = [
            [tweet], []
        ]
        session.query.return_value.filter.return_value.all.return_value = [game]

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_unmapped_tweets(session)

        assert result["mapped"] == 1
        assert result["no_game"] == 0
        assert tweet.mapping_status == "mapped"
        assert tweet.game_id == 10

    @patch("sports_scraper.social.tweet_mapper.now_utc", return_value=_utc(2025, 6, 15, 23, 0))
    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_marks_no_game(self, mock_db, mock_now):
        tweet = _make_tweet(
            team_id=100,
            posted_at=_utc(2025, 6, 15, 20, 0),
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.limit.return_value.all.side_effect = [
            [tweet], []
        ]
        # No matching games
        session.query.return_value.filter.return_value.all.return_value = []

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_unmapped_tweets(session)

        assert result["no_game"] == 1
        assert tweet.mapping_status == "no_game"

    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_empty_batch(self, mock_db):
        session = MagicMock()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_unmapped_tweets(session)

        assert result["total_processed"] == 0
        assert result["mapped"] == 0
        assert result["no_game"] == 0

    @patch("sports_scraper.social.tweet_mapper.now_utc", return_value=_utc(2025, 6, 15, 23, 0))
    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_exception_per_tweet_logged(self, mock_db, mock_now):
        tweet = _make_tweet(team_id=100)
        # Force an exception by making posted_at.tzinfo raise
        tweet.posted_at = MagicMock()
        tweet.posted_at.tzinfo = None
        tweet.posted_at.replace.side_effect = RuntimeError("bad datetime")

        session = MagicMock()
        session.query.return_value.filter.return_value.limit.return_value.all.side_effect = [
            [tweet], []
        ]

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_unmapped_tweets(session)

        assert len(result["errors"]) == 1
        assert result["total_processed"] == 1

    @patch("sports_scraper.social.tweet_mapper.now_utc", return_value=_utc(2025, 6, 15, 23, 0))
    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_returns_summary_stats(self, mock_db, mock_now):
        session = MagicMock()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_unmapped_tweets(session)

        assert "total_processed" in result
        assert "mapped" in result
        assert "no_game" in result
        assert "errors" in result


# ---------------------------------------------------------------------------
# map_tweets_for_team
# ---------------------------------------------------------------------------
class TestMapTweetsForTeam:
    @patch("sports_scraper.social.tweet_mapper.now_utc", return_value=_utc(2025, 6, 15, 23, 0))
    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_maps_for_specific_team(self, mock_db, mock_now):
        game = _make_game(
            id=10,
            tip_time=_utc(2025, 6, 15, 19, 0),
        )
        tweet = _make_tweet(
            team_id=100,
            posted_at=_utc(2025, 6, 15, 20, 0),
        )

        session = MagicMock()
        # Unmapped tweets query
        session.query.return_value.filter.return_value.all.return_value = [tweet]
        # Union query for potential games
        session.query.return_value.filter.return_value.union.return_value.all.return_value = [game]

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_tweets_for_team(session, team_id=100)

        assert result["mapped"] == 1
        assert tweet.mapping_status == "mapped"

    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_zero_unmapped_early_return(self, mock_db):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_tweets_for_team(session, team_id=100)

        assert result["processed"] == 0
        assert result["mapped"] == 0
        assert result["no_game"] == 0

    @patch("sports_scraper.social.tweet_mapper.now_utc", return_value=_utc(2025, 6, 15, 23, 0))
    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_no_matching_game_marks_no_game(self, mock_db, mock_now):
        tweet = _make_tweet(
            team_id=100,
            posted_at=_utc(2025, 6, 15, 20, 0),
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [tweet]
        # No matching games from union query
        session.query.return_value.filter.return_value.union.return_value.all.return_value = []

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = map_tweets_for_team(session, team_id=100)

        assert result["no_game"] == 1
        assert tweet.mapping_status == "no_game"


# ---------------------------------------------------------------------------
# get_mapping_stats
# ---------------------------------------------------------------------------
class TestGetMappingStats:
    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_returns_status_counts(self, mock_db):
        session = MagicMock()
        session.query.return_value.group_by.return_value.all.return_value = [
            ("mapped", 50),
            ("unmapped", 10),
            ("no_game", 5),
        ]

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = get_mapping_stats(session)

        assert result == {"mapped": 50, "unmapped": 10, "no_game": 5}

    @patch("sports_scraper.social.tweet_mapper.db_models", create=True)
    def test_empty_result(self, mock_db):
        session = MagicMock()
        session.query.return_value.group_by.return_value.all.return_value = []

        with patch("sports_scraper.social.tweet_mapper.db_models", mock_db):
            result = get_mapping_stats(session)

        assert result == {}
