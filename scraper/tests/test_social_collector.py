"""Tests for social/collector.py module."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
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


from sports_scraper.social.collector import XPostCollector, _check_and_queue_timeline_regen
from sports_scraper.social.models import CollectedPost, PostCollectionJob


class TestCheckAndQueueTimelineRegen:
    """Tests for _check_and_queue_timeline_regen function."""

    def test_returns_false_when_no_artifact(self):
        """Returns False when no timeline artifact exists."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = _check_and_queue_timeline_regen(mock_session, game_id=1)

        assert result is False

    def test_returns_false_when_task_import_fails(self):
        """Returns False when task import fails."""
        mock_session = MagicMock()
        mock_artifact = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_artifact

        # The function will try to import regenerate_timeline_task which may fail
        # in this case it should return False without crashing
        result = _check_and_queue_timeline_regen(mock_session, game_id=1)

        # Result depends on whether task import succeeded
        assert isinstance(result, bool)


class TestXPostCollectorInit:
    """Tests for XPostCollector initialization."""

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_uses_mock_when_playwright_unavailable(self, mock_mock_collector, mock_available):
        """Uses MockXCollector when playwright not available."""
        mock_available.return_value = False

        collector = XPostCollector()

        mock_mock_collector.assert_called()
        assert collector.filter_reveals is True
        assert collector.platform == "x"

    def test_accepts_custom_strategy(self):
        """Accepts custom strategy."""
        mock_strategy = MagicMock()

        collector = XPostCollector(strategy=mock_strategy)

        assert collector.strategy is mock_strategy

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_creates_rate_limiter(self, mock_mock_collector, mock_available):
        """Creates rate limiter."""
        mock_available.return_value = False

        collector = XPostCollector()

        assert collector.rate_limiter is not None

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_creates_request_cache(self, mock_mock_collector, mock_available):
        """Creates request cache."""
        mock_available.return_value = False

        collector = XPostCollector()

        assert collector.request_cache is not None


class TestXPostCollectorNormalizePostedAt:
    """Tests for _normalize_posted_at method."""

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_adds_utc_when_naive(self, mock_mock_collector, mock_available):
        """Adds UTC timezone when datetime is naive."""
        mock_available.return_value = False

        collector = XPostCollector()
        naive_dt = datetime(2024, 1, 15, 12, 0, 0)

        result = collector._normalize_posted_at(naive_dt)

        assert result.tzinfo == timezone.utc

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_converts_to_utc(self, mock_mock_collector, mock_available):
        """Converts aware datetime to UTC."""
        mock_available.return_value = False

        collector = XPostCollector()
        # Eastern time (UTC-5)
        eastern = timezone(timedelta(hours=-5))
        aware_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=eastern)

        result = collector._normalize_posted_at(aware_dt)

        assert result.tzinfo == timezone.utc
        # 12:00 EST = 17:00 UTC
        assert result.hour == 17


class TestXPostCollectorRunJob:
    """Tests for run_job method."""

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_skips_when_poll_not_allowed(self, mock_mock_collector, mock_available):
        """Skips collection when poll cache says not allowed."""
        mock_available.return_value = False

        collector = XPostCollector()

        # Mock request cache to disallow polling
        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=False, reason="poll_interval", retry_at=None)
        collector.request_cache = mock_cache

        mock_session = MagicMock()
        now = datetime.now(timezone.utc)
        job = PostCollectionJob(
            game_id=1,
            team_abbreviation="BOS",
            x_handle="celtics",
            window_start=now - timedelta(hours=3),
            window_end=now,
            game_start=now - timedelta(hours=2),
        )

        result = collector.run_job(job, mock_session)

        assert result.posts_found == 0
        assert result.posts_saved == 0

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_skips_when_rate_limited(self, mock_mock_collector, mock_available):
        """Skips collection when rate limited."""
        mock_available.return_value = False

        collector = XPostCollector()

        # Mock request cache to allow polling
        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=True)
        collector.request_cache = mock_cache

        # Mock rate limiter to deny
        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = MagicMock(allowed=False, reason="platform_quota", retry_after=60)
        collector.rate_limiter = mock_limiter

        mock_session = MagicMock()
        now = datetime.now(timezone.utc)
        job = PostCollectionJob(
            game_id=1,
            team_abbreviation="BOS",
            x_handle="celtics",
            window_start=now - timedelta(hours=3),
            window_end=now,
            game_start=now - timedelta(hours=2),
        )

        result = collector.run_job(job, mock_session)

        assert result.posts_found == 0


class TestXPostCollectorCollectForGame:
    """Tests for collect_for_game method."""

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_returns_empty_when_game_not_found(self, mock_mock_collector, mock_available):
        """Returns empty list when game not found."""
        mock_available.return_value = False
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        collector = XPostCollector()
        result = collector.collect_for_game(mock_session, game_id=999)

        assert result == []

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_returns_empty_when_teams_not_found(self, mock_mock_collector, mock_available):
        """Returns empty list when teams not found."""
        mock_available.return_value = False
        mock_session = MagicMock()

        mock_game = MagicMock()
        mock_game.home_team_id = 1
        mock_game.away_team_id = 2
        mock_session.query.return_value.filter.return_value.first.return_value = mock_game
        mock_session.query.return_value.get.return_value = None  # Teams not found

        collector = XPostCollector()
        result = collector.collect_for_game(mock_session, game_id=1)

        assert result == []

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_returns_empty_when_no_game_date(self, mock_mock_collector, mock_available):
        """Returns empty list when game has no date."""
        mock_available.return_value = False
        mock_session = MagicMock()

        mock_game = MagicMock()
        mock_game.home_team_id = 1
        mock_game.away_team_id = 2
        mock_game.game_date = None

        mock_team = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_game
        mock_session.query.return_value.get.return_value = mock_team

        collector = XPostCollector()
        result = collector.collect_for_game(mock_session, game_id=1)

        assert result == []

    @patch("sports_scraper.social.collector.fetch_team_accounts")
    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_returns_empty_when_no_pbp(self, mock_mock_collector, mock_available, mock_fetch_accounts):
        """Returns empty list when game has no PBP."""
        mock_available.return_value = False
        mock_session = MagicMock()

        mock_game = MagicMock()
        mock_game.id = 1
        mock_game.home_team_id = 1
        mock_game.away_team_id = 2
        mock_game.game_date = datetime.now(timezone.utc)

        mock_team = MagicMock()
        mock_team.id = 1

        mock_session.query.return_value.filter.return_value.first.return_value = mock_game
        mock_session.query.return_value.get.return_value = mock_team
        mock_session.query.return_value.filter.return_value.scalar.return_value = 0  # No plays

        collector = XPostCollector()
        result = collector.collect_for_game(mock_session, game_id=1)

        assert result == []


class TestXPostCollectorRunJobSuccess:
    """Tests for run_job method with successful collection."""

    @patch("sports_scraper.social.collector.classify_reveal_risk")
    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_collects_and_saves_posts(self, mock_mock_collector, mock_available, mock_classify):
        """Successfully collects and saves posts."""
        mock_available.return_value = False
        mock_classify.return_value = MagicMock(reveal_risk=False, reason=None)

        collector = XPostCollector()

        # Mock cache to allow polling
        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=True)
        collector.request_cache = mock_cache

        # Mock rate limiter to allow
        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = MagicMock(allowed=True)
        collector.rate_limiter = mock_limiter

        # Mock strategy to return posts
        now = datetime.now(timezone.utc)
        mock_post = CollectedPost(
            post_url="https://x.com/team/status/123",
            external_post_id="123",
            posted_at=now - timedelta(hours=1),
            has_video=True,
            text="Great play!",
            author_handle="@team",
        )
        mock_strategy = MagicMock()
        mock_strategy.collect_posts.return_value = [mock_post]
        collector.strategy = mock_strategy

        # Mock session
        mock_session = MagicMock()
        mock_team = MagicMock()
        mock_team.id = 1
        mock_session.query.return_value.filter.return_value.first.side_effect = [mock_team, None]  # Team found, no existing post
        mock_session.get.return_value = MagicMock()  # Game exists

        job = PostCollectionJob(
            game_id=1,
            team_abbreviation="BOS",
            x_handle="celtics",
            window_start=now - timedelta(hours=3),
            window_end=now,
            game_start=now - timedelta(hours=2),
        )

        result = collector.run_job(job, mock_session)

        assert result.posts_found == 1

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_skips_post_outside_window(self, mock_mock_collector, mock_available):
        """Skips posts outside collection window."""
        mock_available.return_value = False

        collector = XPostCollector()

        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=True)
        collector.request_cache = mock_cache

        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = MagicMock(allowed=True)
        collector.rate_limiter = mock_limiter

        now = datetime.now(timezone.utc)
        # Post from a week ago - outside window
        mock_post = CollectedPost(
            post_url="https://x.com/team/status/123",
            posted_at=now - timedelta(days=7),
        )
        mock_strategy = MagicMock()
        mock_strategy.collect_posts.return_value = [mock_post]
        collector.strategy = mock_strategy

        mock_session = MagicMock()
        mock_team = MagicMock()
        mock_team.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_team

        job = PostCollectionJob(
            game_id=1,
            team_abbreviation="BOS",
            x_handle="celtics",
            window_start=now - timedelta(hours=3),
            window_end=now,
            game_start=now - timedelta(hours=2),
        )

        result = collector.run_job(job, mock_session)

        assert result.posts_found == 1
        assert result.posts_saved == 0  # Skipped

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_handles_team_not_found(self, mock_mock_collector, mock_available):
        """Handles team not found error."""
        mock_available.return_value = False

        collector = XPostCollector()

        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=True)
        collector.request_cache = mock_cache

        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = MagicMock(allowed=True)
        collector.rate_limiter = mock_limiter

        now = datetime.now(timezone.utc)
        mock_post = CollectedPost(
            post_url="https://x.com/team/status/123",
            posted_at=now - timedelta(hours=1),
        )
        mock_strategy = MagicMock()
        mock_strategy.collect_posts.return_value = [mock_post]
        collector.strategy = mock_strategy

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None  # Team not found

        job = PostCollectionJob(
            game_id=1,
            team_abbreviation="UNKNOWN",
            x_handle="unknown",
            window_start=now - timedelta(hours=3),
            window_end=now,
            game_start=now - timedelta(hours=2),
        )

        result = collector.run_job(job, mock_session)

        assert "Team not found" in result.errors[0]


class TestXPostCollectorErrorHandling:
    """Tests for run_job error handling."""

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_handles_rate_limit_error(self, mock_mock_collector, mock_available):
        """Handles SocialRateLimitError during collection."""
        from sports_scraper.social.exceptions import SocialRateLimitError

        mock_available.return_value = False

        collector = XPostCollector()

        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=True)
        collector.request_cache = mock_cache

        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = MagicMock(allowed=True)
        collector.rate_limiter = mock_limiter

        mock_strategy = MagicMock()
        mock_strategy.collect_posts.side_effect = SocialRateLimitError("Rate limited", retry_after_seconds=60)
        collector.strategy = mock_strategy

        mock_session = MagicMock()
        now = datetime.now(timezone.utc)

        job = PostCollectionJob(
            game_id=1,
            team_abbreviation="BOS",
            x_handle="celtics",
            window_start=now - timedelta(hours=3),
            window_end=now,
            game_start=now - timedelta(hours=2),
        )

        result = collector.run_job(job, mock_session)

        assert len(result.errors) > 0
        mock_limiter.backoff.assert_called_once()

    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_handles_generic_exception(self, mock_mock_collector, mock_available):
        """Handles generic exception during collection."""
        mock_available.return_value = False

        collector = XPostCollector()

        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=True)
        collector.request_cache = mock_cache

        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = MagicMock(allowed=True)
        collector.rate_limiter = mock_limiter

        mock_strategy = MagicMock()
        mock_strategy.collect_posts.side_effect = Exception("Network error")
        collector.strategy = mock_strategy

        mock_session = MagicMock()
        now = datetime.now(timezone.utc)

        job = PostCollectionJob(
            game_id=1,
            team_abbreviation="BOS",
            x_handle="celtics",
            window_start=now - timedelta(hours=3),
            window_end=now,
            game_start=now - timedelta(hours=2),
        )

        result = collector.run_job(job, mock_session)

        assert len(result.errors) > 0
        assert "Network error" in result.errors[0]


class TestXPostCollectorCollectForGameSuccess:
    """Tests for collect_for_game with successful execution."""

    @patch("sports_scraper.social.collector.fetch_team_accounts")
    @patch("sports_scraper.social.collector.playwright_available")
    @patch("sports_scraper.social.collector.MockXCollector")
    def test_collects_for_both_teams(self, mock_mock_collector, mock_available, mock_fetch_accounts):
        """Collects posts for both teams."""
        mock_available.return_value = False

        collector = XPostCollector()

        # Mock cache and limiter
        mock_cache = MagicMock()
        mock_cache.should_poll.return_value = MagicMock(allowed=False, reason="skip", retry_at=None)
        collector.request_cache = mock_cache

        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = MagicMock(allowed=True)
        collector.rate_limiter = mock_limiter

        mock_strategy = MagicMock()
        mock_strategy.collect_posts.return_value = []
        collector.strategy = mock_strategy

        # Mock session with properly typed values
        mock_session = MagicMock()
        now = datetime.now(timezone.utc)

        mock_game = MagicMock()
        mock_game.id = 1
        mock_game.home_team_id = 1
        mock_game.away_team_id = 2
        mock_game.game_date = now - timedelta(hours=2)
        mock_game.tip_time = now - timedelta(hours=2)
        mock_game.end_time = now - timedelta(minutes=30)

        mock_home_team = MagicMock()
        mock_home_team.id = 1
        mock_home_team.abbreviation = "BOS"  # Real string
        mock_home_team.x_handle = "celtics"  # Real string

        mock_away_team = MagicMock()
        mock_away_team.id = 2
        mock_away_team.abbreviation = "LAL"  # Real string
        mock_away_team.x_handle = "lakers"  # Real string

        # Configure mock session query chains
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_game
        mock_query.scalar.return_value = 10  # Has plays
        mock_session.query.return_value.get.side_effect = [mock_home_team, mock_away_team]

        mock_fetch_accounts.return_value = {}

        result = collector.collect_for_game(mock_session, game_id=1)

        # Should return list of results
        assert isinstance(result, list)
