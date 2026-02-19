"""Comprehensive tests for social modules."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


# ============================================================================
# Tests for social/models.py
# ============================================================================

from sports_scraper.social.models import CollectedPost


class TestCollectedPost:
    """Tests for CollectedPost model."""

    def test_create_minimal(self):
        """Create post with minimal required fields."""
        post = CollectedPost(
            post_url="https://x.com/user/status/123",
            posted_at=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
        )
        assert post.post_url == "https://x.com/user/status/123"
        assert post.platform == "x"
        assert post.has_video is False

    def test_create_with_all_fields(self):
        """Create post with all fields."""
        post = CollectedPost(
            post_url="https://x.com/user/status/456",
            external_post_id="456",
            platform="x",
            posted_at=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
            has_video=True,
            text="Game highlights!",
            author_handle="@team",
            video_url="https://video.twimg.com/123.mp4",
            image_url="https://pbs.twimg.com/123.jpg",
            media_type="video",
        )
        assert post.external_post_id == "456"
        assert post.has_video is True
        assert post.text == "Game highlights!"
        assert post.video_url is not None
        assert post.media_type == "video"



# ============================================================================
# Tests for social/exceptions.py
# ============================================================================

from sports_scraper.social.exceptions import (
    SocialRateLimitError,
    XCircuitBreakerError,
)


class TestSocialExceptions:
    """Tests for social exception classes."""

    def test_social_rate_limit_error(self):
        """Test SocialRateLimitError."""
        error = SocialRateLimitError("Rate limited by X API")
        assert str(error) == "Rate limited by X API"
        assert isinstance(error, RuntimeError)
        assert error.retry_after_seconds is None

    def test_social_rate_limit_error_with_retry(self):
        """Test SocialRateLimitError with retry_after."""
        error = SocialRateLimitError("Rate limited", retry_after_seconds=60)
        assert error.retry_after_seconds == 60

    def test_x_circuit_breaker_error(self):
        """Test XCircuitBreakerError."""
        error = XCircuitBreakerError("Circuit breaker triggered", retry_after_seconds=300)
        assert str(error) == "Circuit breaker triggered"
        assert isinstance(error, RuntimeError)
        assert error.retry_after_seconds == 300


# ============================================================================
# Tests for social/rate_limit.py
# ============================================================================

from sports_scraper.social.rate_limit import (
    PlatformRateLimiter,
    RateLimitDecision,
)


class TestRateLimitDecision:
    """Tests for RateLimitDecision dataclass."""

    def test_create_allowed_decision(self):
        """Create an allowed decision."""
        decision = RateLimitDecision(allowed=True)
        assert decision.allowed is True
        assert decision.reason is None
        assert decision.retry_after is None

    def test_create_denied_decision(self):
        """Create a denied decision with reason."""
        decision = RateLimitDecision(allowed=False, reason="backoff", retry_after=60)
        assert decision.allowed is False
        assert decision.reason == "backoff"
        assert decision.retry_after == 60


class TestPlatformRateLimiter:
    """Tests for PlatformRateLimiter class."""

    def test_create_limiter(self):
        """Create rate limiter."""
        limiter = PlatformRateLimiter(max_requests=10, window_seconds=60)
        assert limiter.max_requests == 10
        assert limiter.window == timedelta(seconds=60)

    def test_allow_succeeds_initially(self):
        """Allow returns True when under limit."""
        limiter = PlatformRateLimiter(max_requests=10, window_seconds=60)
        decision = limiter.allow()
        assert decision.allowed is True

    def test_record_tracks_requests(self):
        """Record adds timestamp to request history."""
        limiter = PlatformRateLimiter(max_requests=10, window_seconds=60)
        assert len(limiter._requests) == 0
        limiter.record()
        assert len(limiter._requests) == 1

    def test_allow_denied_after_max_requests(self):
        """Allow returns False when max requests reached."""
        limiter = PlatformRateLimiter(max_requests=2, window_seconds=60)
        now = datetime.now(UTC)
        # Record 2 requests
        limiter.record(now)
        limiter.record(now)
        # Third request should be denied
        decision = limiter.allow(now)
        assert decision.allowed is False
        assert decision.reason == "platform_quota"

    def test_backoff_blocks_requests(self):
        """Backoff blocks future requests."""
        limiter = PlatformRateLimiter(max_requests=10, window_seconds=60)
        limiter.backoff(retry_after_seconds=300)
        # Request should be blocked
        decision = limiter.allow()
        assert decision.allowed is False
        assert decision.reason == "backoff"
        assert decision.retry_after is not None

    def test_old_requests_expire(self):
        """Old requests outside window are pruned."""
        limiter = PlatformRateLimiter(max_requests=2, window_seconds=60)
        old_time = datetime.now(UTC) - timedelta(seconds=120)
        now = datetime.now(UTC)
        # Record old requests
        limiter.record(old_time)
        limiter.record(old_time)
        # New request should be allowed (old ones expired)
        decision = limiter.allow(now)
        assert decision.allowed is True


# ============================================================================
# Tests for social/utils.py
# ============================================================================

from sports_scraper.social.utils import extract_x_post_id


class TestExtractXPostId:
    """Tests for extract_x_post_id function."""

    def test_extract_from_x_url(self):
        """Extract post ID from x.com URL."""
        url = "https://x.com/warriors/status/1234567890123456789"
        post_id = extract_x_post_id(url)
        assert post_id == "1234567890123456789"

    def test_extract_from_twitter_url(self):
        """Extract post ID from twitter.com URL."""
        url = "https://twitter.com/warriors/status/1234567890123456789"
        post_id = extract_x_post_id(url)
        assert post_id == "1234567890123456789"

    def test_returns_none_for_invalid_url(self):
        """Return None for non-matching URL."""
        url = "https://example.com/not-a-post"
        post_id = extract_x_post_id(url)
        assert post_id is None

    def test_returns_none_for_none_input(self):
        """Return None for None input."""
        post_id = extract_x_post_id(None)
        assert post_id is None

    def test_returns_none_for_empty_string(self):
        """Return None for empty string."""
        post_id = extract_x_post_id("")
        assert post_id is None

    def test_extract_with_query_params(self):
        """Extract post ID from URL with query parameters."""
        url = "https://x.com/warriors/status/1234567890?s=20"
        post_id = extract_x_post_id(url)
        assert post_id == "1234567890"


# ============================================================================
# Tests for social/registry.py
# ============================================================================

from sports_scraper.social.registry import (
    TeamSocialAccountEntry,
    fetch_team_accounts,
)


class TestTeamSocialAccountEntry:
    """Tests for TeamSocialAccountEntry dataclass."""

    def test_create_entry(self):
        """Create a team social account entry."""
        entry = TeamSocialAccountEntry(
            team_id=1,
            league_id=1,
            platform="x",
            handle="warriors",
        )
        assert entry.team_id == 1
        assert entry.league_id == 1
        assert entry.platform == "x"
        assert entry.handle == "warriors"

    def test_entry_is_frozen(self):
        """Entry is immutable."""
        entry = TeamSocialAccountEntry(
            team_id=1, league_id=1, platform="x", handle="warriors"
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            entry.team_id = 2


class TestFetchTeamAccounts:
    """Tests for fetch_team_accounts function."""

    def test_fetch_returns_dict(self):
        """Fetch returns dictionary of accounts."""
        # Create mock session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = fetch_team_accounts(
            mock_session,
            team_ids=[1, 2],
            platform="x",
        )
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_fetch_with_results(self):
        """Fetch returns populated dictionary."""
        # Create mock account
        mock_account = MagicMock()
        mock_account.team_id = 1
        mock_account.league_id = 1
        mock_account.platform = "x"
        mock_account.handle = "warriors"

        # Create mock session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_account]

        result = fetch_team_accounts(
            mock_session,
            team_ids=[1],
            platform="x",
        )
        assert 1 in result
        assert result[1].handle == "warriors"


# ============================================================================
# Tests for social/cache.py
# ============================================================================

from sports_scraper.social.cache import CacheDecision, SocialRequestCache


class TestCacheDecision:
    """Tests for CacheDecision dataclass."""

    def test_create_allowed(self):
        """Create allowed decision."""
        decision = CacheDecision(allowed=True)
        assert decision.allowed is True
        assert decision.reason is None
        assert decision.retry_at is None

    def test_create_denied(self):
        """Create denied decision with retry time."""
        retry_at = datetime.now(UTC) + timedelta(minutes=5)
        decision = CacheDecision(allowed=False, reason="poll_interval", retry_at=retry_at)
        assert decision.allowed is False
        assert decision.reason == "poll_interval"
        assert decision.retry_at == retry_at


class TestSocialRequestCache:
    """Tests for SocialRequestCache class."""

    def test_create_cache(self):
        """Create social request cache."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        assert cache.poll_interval == timedelta(seconds=60)
        assert cache.cache_ttl == timedelta(seconds=3600)

    def test_should_poll_no_history(self):
        """Should poll when no history exists."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        now = datetime.now(UTC)

        # Create mock session with no records
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        decision = cache.should_poll(
            mock_session,
            platform="x",
            handle="warriors",
            window_start=now - timedelta(hours=3),
            window_end=now,
        )
        assert decision.allowed is True

    def test_should_poll_rate_limited(self):
        """Should not poll when rate limited."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        now = datetime.now(UTC)

        # Create mock recent poll record with rate limit
        mock_poll = MagicMock()
        mock_poll.created_at = now - timedelta(seconds=30)
        mock_poll.rate_limited_until = now + timedelta(minutes=5)

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_poll

        decision = cache.should_poll(
            mock_session,
            platform="x",
            handle="warriors",
            window_start=now - timedelta(hours=3),
            window_end=now,
            now=now,
        )
        assert decision.allowed is False
        assert decision.reason == "rate_limited"

    def test_should_poll_poll_interval(self):
        """Should not poll when within poll interval."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        now = datetime.now(UTC)

        # Create mock recent poll record within interval (no rate limit)
        # Poll interval is only enforced for successful polls with posts found
        mock_poll = MagicMock()
        mock_poll.created_at = now - timedelta(seconds=30)  # 30 seconds ago
        mock_poll.rate_limited_until = None
        mock_poll.status = "success"
        mock_poll.posts_found = 5

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_poll

        decision = cache.should_poll(
            mock_session,
            platform="x",
            handle="warriors",
            window_start=now - timedelta(hours=3),
            window_end=now,
            now=now,
            is_backfill=False,
        )
        assert decision.allowed is False
        assert decision.reason == "poll_interval"

    def test_should_poll_skips_interval_for_backfill(self):
        """Should skip poll interval for backfill."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        now = datetime.now(UTC)

        # Create mock recent poll record within interval
        # Note: We don't set status/posts_found here because the mock is reused
        # for both recent_poll and cached_window queries. This test specifically
        # verifies that is_backfill=True skips the poll_interval check.
        mock_poll = MagicMock()
        mock_poll.created_at = now - timedelta(seconds=30)
        mock_poll.rate_limited_until = None

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_poll

        decision = cache.should_poll(
            mock_session,
            platform="x",
            handle="warriors",
            window_start=now - timedelta(hours=3),
            window_end=now,
            now=now,
            is_backfill=True,  # Backfill skips interval
        )
        assert decision.allowed is True

    def test_should_poll_cached_window(self):
        """Should not poll when window is cached with success."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=3)
        window_end = now

        # No recent poll (outside interval)
        mock_recent = MagicMock()
        mock_recent.created_at = now - timedelta(seconds=120)
        mock_recent.rate_limited_until = None

        # Cached window with success and posts
        mock_cached = MagicMock()
        mock_cached.created_at = now - timedelta(minutes=30)  # Within TTL
        mock_cached.status = "success"
        mock_cached.posts_found = 5  # Found posts

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.side_effect = [mock_recent, mock_cached]

        decision = cache.should_poll(
            mock_session,
            platform="x",
            handle="warriors",
            window_start=window_start,
            window_end=window_end,
            now=now,
        )
        assert decision.allowed is False
        assert decision.reason == "cached_window"

    def test_record_creates_new_entry(self):
        """Record creates new poll entry."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        now = datetime.now(UTC)

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No existing record

        result = cache.record(
            mock_session,
            platform="x",
            handle="warriors",
            window_start=now - timedelta(hours=3),
            window_end=now,
            status="success",
            posts_found=10,
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_record_updates_existing_entry(self):
        """Record updates existing poll entry."""
        cache = SocialRequestCache(poll_interval_seconds=60, cache_ttl_seconds=3600)
        now = datetime.now(UTC)

        mock_existing = MagicMock()
        mock_existing.status = "pending"
        mock_existing.posts_found = 0

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_existing

        result = cache.record(
            mock_session,
            platform="x",
            handle="warriors",
            window_start=now - timedelta(hours=3),
            window_end=now,
            status="success",
            posts_found=10,
        )

        assert mock_existing.status == "success"
        assert mock_existing.posts_found == 10
        mock_session.flush.assert_called_once()


