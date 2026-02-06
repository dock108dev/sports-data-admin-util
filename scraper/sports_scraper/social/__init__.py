"""
Social media integration for game timeline posts.

This module provides infrastructure for collecting and managing
social posts from team X accounts.

Two-phase collection architecture:
- team_collector: Scrape tweets for teams in a date range (Phase 1)
- tweet_mapper: Assign unmapped tweets to games (Phase 2)
"""

from .collector import XPostCollector
from .collector_base import XCollectorStrategy
from .exceptions import SocialRateLimitError, XCircuitBreakerError
from .models import CollectedPost, PostCollectionJob, PostCollectionResult
from .playwright_collector import PlaywrightXCollector
from .rate_limit import PlatformRateLimiter
from .cache import SocialRequestCache
from .strategies import MockXCollector
from .team_collector import TeamTweetCollector
from .tweet_mapper import map_unmapped_tweets, get_game_window, get_mapping_stats

__all__ = [
    "CollectedPost",
    "PostCollectionJob",
    "PostCollectionResult",
    "XPostCollector",
    "XCollectorStrategy",
    "MockXCollector",
    "PlaywrightXCollector",
    "SocialRateLimitError",
    "XCircuitBreakerError",
    "PlatformRateLimiter",
    "SocialRequestCache",
    # Team-centric collection (Phase 1 & 2)
    "TeamTweetCollector",
    "map_unmapped_tweets",
    "get_game_window",
    "get_mapping_stats",
]
