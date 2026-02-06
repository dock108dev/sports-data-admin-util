"""
Social media integration for game timeline posts.

Two-phase collection architecture:
- team_collector: Scrape tweets for teams in a date range (collect)
- tweet_mapper: Assign unmapped tweets to games (map)
"""

from .collector import XPostCollector
from .exceptions import SocialRateLimitError, XCircuitBreakerError
from .models import CollectedPost, PostCollectionJob, PostCollectionResult
from .playwright_collector import PlaywrightXCollector
from .rate_limit import PlatformRateLimiter
from .cache import SocialRequestCache
from .team_collector import TeamTweetCollector
from .tweet_mapper import map_unmapped_tweets, get_game_window, get_mapping_stats

__all__ = [
    "CollectedPost",
    "PostCollectionJob",
    "PostCollectionResult",
    "XPostCollector",
    "PlaywrightXCollector",
    "SocialRateLimitError",
    "XCircuitBreakerError",
    "PlatformRateLimiter",
    "SocialRequestCache",
    "TeamTweetCollector",
    "map_unmapped_tweets",
    "get_game_window",
    "get_mapping_stats",
]
