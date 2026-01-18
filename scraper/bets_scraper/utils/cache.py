"""HTML caching utilities for scrapers."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from ..logging import logger

# Scoreboards within this many days of today are always re-fetched
RECENT_DAYS_THRESHOLD = 7

# Minimum file size (bytes) for a valid scoreboard cache entry
# Empty scoreboards are typically < 5KB, valid ones with games are > 20KB
MIN_SCOREBOARD_SIZE_BYTES = 5000


class HTMLCache:
    """Local file cache for scraped HTML pages.
    
    Stores HTML in a structured directory:
      {cache_dir}/{league}/{season}/{filename}.html
    
    This ensures we only scrape each page once, making us a good citizen
    and allowing re-parsing without network requests.
    """
    
    def __init__(self, cache_dir: str | Path, league_code: str, *, force_refresh: bool = False) -> None:
        self.cache_dir = Path(cache_dir)
        self.league_code = league_code
        self.force_refresh = force_refresh
        
    def _get_cache_path(self, url: str, game_date: date | None = None) -> Path:
        """Build cache path for a URL.
        
        For boxscore URLs, extracts game key (e.g., 202410220BOS.html).
        For scoreboard URLs, uses date-based filename.
        """
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        
        # Build filename from URL (season is no longer part of path to avoid stale year segments)
        if "/pbp/" in parsed.path and path_parts[-1].endswith(".html"):
            # Play-by-play URL: .../boxscores/pbp/202410220BOS.html
            filename = f"pbp_{path_parts[-1]}"
        elif "boxscores" in parsed.path and path_parts[-1].endswith(".html"):
            # Boxscore URL: .../boxscores/202410220BOS.html
            filename = path_parts[-1]
        elif "boxscores" in parsed.path and parsed.query:
            # Scoreboard URL: .../boxscores/?month=10&day=22&year=2024
            # Extract date from query params
            filename = f"scoreboard_{parsed.query.replace('&', '_').replace('=', '')}.html"
        else:
            # Fallback: hash the URL
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            filename = f"page_{url_hash}.html"
        
        # Drop year/season directory to avoid mis-bucketing when season differs from current year
        return self.cache_dir / self.league_code / filename
    
    def _is_recent_date(self, game_date: date | None) -> bool:
        """Check if the game_date is within RECENT_DAYS_THRESHOLD of today."""
        if game_date is None:
            return False
        today = date.today()
        return abs((today - game_date).days) <= RECENT_DAYS_THRESHOLD

    def _is_scoreboard_url(self, url: str) -> bool:
        """Check if the URL is a scoreboard page (vs boxscore or PBP)."""
        return "boxscores" in url and "?" in url and "month=" in url

    def get(self, url: str, game_date: date | None = None) -> str | None:
        """Load HTML from cache if it exists.
        
        Cache is bypassed (returns None) in these cases:
        1. force_refresh is True
        2. game_date is within RECENT_DAYS_THRESHOLD days of today
        3. Cached scoreboard file is too small (likely empty/no games)
        """
        cache_path = self._get_cache_path(url, game_date)
        
        # Check if this is a recent date that should always be refreshed
        if self._is_recent_date(game_date):
            logger.info(
                "cache_skip_recent_date",
                url=url,
                game_date=str(game_date),
                threshold_days=RECENT_DAYS_THRESHOLD,
                league=self.league_code,
            )
            return None
        
        if cache_path.exists():
            if self.force_refresh:
                logger.info(
                    "cache_refresh_forced",
                    url=url,
                    path=str(cache_path),
                    league=self.league_code,
                )
                return None
            
            # Check if cached scoreboard is too small (likely empty)
            file_stat = cache_path.stat()
            if self._is_scoreboard_url(url) and file_stat.st_size < MIN_SCOREBOARD_SIZE_BYTES:
                logger.info(
                    "cache_skip_small_scoreboard",
                    url=url,
                    path=str(cache_path),
                    size_bytes=file_stat.st_size,
                    min_size=MIN_SCOREBOARD_SIZE_BYTES,
                    league=self.league_code,
                )
                return None
            
            logger.info(
                "cache_hit",
                url=url,
                path=str(cache_path),
                league=self.league_code,
            )
            return cache_path.read_text(encoding="utf-8")
        logger.debug("cache_miss", url=url, path=str(cache_path), league=self.league_code)
        return None
    
    def put(self, url: str, html: str, game_date: date | None = None) -> Path | None:
        """Save HTML to cache.
        
        Returns None without saving if:
        1. game_date is within RECENT_DAYS_THRESHOLD (would be skipped on read anyway)
        2. Scoreboard page is too small (likely empty, no games)
        """
        # Don't cache recent dates - they'll be refreshed on next read anyway
        if self._is_recent_date(game_date):
            logger.info(
                "cache_skip_save_recent_date",
                url=url,
                game_date=str(game_date),
                threshold_days=RECENT_DAYS_THRESHOLD,
                league=self.league_code,
            )
            return None
        
        # Don't cache small scoreboards (likely empty/no games)
        if self._is_scoreboard_url(url) and len(html) < MIN_SCOREBOARD_SIZE_BYTES:
            logger.info(
                "cache_skip_save_small_scoreboard",
                url=url,
                size_bytes=len(html),
                min_size=MIN_SCOREBOARD_SIZE_BYTES,
                league=self.league_code,
            )
            return None
        
        cache_path = self._get_cache_path(url, game_date)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")
        logger.info("cache_saved", url=url, path=str(cache_path), size_kb=len(html) // 1024)
        return cache_path

