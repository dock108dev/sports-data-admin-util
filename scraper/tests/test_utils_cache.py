"""Tests for utils/cache.py module."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
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


from sports_scraper.utils.cache import (
    HTMLCache,
    MIN_SCOREBOARD_SIZE_BYTES,
)


class TestHTMLCacheInit:
    """Tests for HTMLCache initialization."""

    def test_creates_with_path(self):
        """Creates cache with given path."""
        cache = HTMLCache("/tmp/test_cache", "NBA")
        assert cache.cache_dir == Path("/tmp/test_cache")
        assert cache.league_code == "NBA"

    def test_creates_with_path_object(self):
        """Creates cache with Path object."""
        cache = HTMLCache(Path("/tmp/test_cache"), "NHL")
        assert cache.cache_dir == Path("/tmp/test_cache")

    def test_force_refresh_default_false(self):
        """force_refresh defaults to False."""
        cache = HTMLCache("/tmp/test_cache", "NBA")
        assert cache.force_refresh is False

    def test_force_refresh_can_be_set(self):
        """force_refresh can be set to True."""
        cache = HTMLCache("/tmp/test_cache", "NBA", force_refresh=True)
        assert cache.force_refresh is True


class TestHTMLCacheGetCachePath:
    """Tests for _get_cache_path method."""

    def test_boxscore_url_extracts_filename(self):
        """Boxscore URL extracts game key as filename."""
        cache = HTMLCache("/tmp/cache", "NHL")
        url = "https://www.hockey-reference.com/boxscores/202410220BOS.html"
        path = cache._get_cache_path(url)
        assert path.name == "202410220BOS.html"

    def test_pbp_url_prefixes_filename(self):
        """PBP URL prefixes filename with 'pbp_'."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/boxscores/pbp/202401150BOS.html"
        path = cache._get_cache_path(url)
        assert path.name.startswith("pbp_")
        assert "202401150BOS" in path.name

    def test_scoreboard_url_uses_query_params(self):
        """Scoreboard URL creates filename from query params."""
        cache = HTMLCache("/tmp/cache", "NHL")
        url = "https://www.hockey-reference.com/boxscores/?month=10&day=22&year=2024"
        path = cache._get_cache_path(url)
        assert "scoreboard" in path.name
        assert "month" in path.name or "10" in path.name

    def test_path_includes_league(self):
        """Cache path includes league code."""
        cache = HTMLCache("/tmp/cache", "NCAAB")
        url = "https://example.com/page.html"
        path = cache._get_cache_path(url)
        assert "NCAAB" in str(path)


class TestHTMLCacheIsScoreboardUrl:
    """Tests for _is_scoreboard_url method."""

    def test_scoreboard_url_detected(self):
        """Detects scoreboard URLs."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/boxscores/?month=1&day=15&year=2024"
        assert cache._is_scoreboard_url(url) is True

    def test_boxscore_url_not_detected(self):
        """Boxscore URLs are not detected as scoreboard."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/boxscores/202401150BOS.html"
        assert cache._is_scoreboard_url(url) is False

    def test_pbp_url_not_detected(self):
        """PBP URLs are not detected as scoreboard."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/boxscores/pbp/202401150BOS.html"
        assert cache._is_scoreboard_url(url) is False


class TestHTMLCacheGet:
    """Tests for get method."""

    def test_returns_none_when_not_cached(self):
        """Returns None when file not in cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            result = cache.get("https://example.com/page.html")
            assert result is None

    def test_returns_cached_content(self):
        """Returns cached content when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            url = "https://www.basketball-reference.com/boxscores/202401150BOS.html"

            # Manually create cache file
            cache_path = cache._get_cache_path(url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text("<html>cached content</html>")

            result = cache.get(url)
            assert result == "<html>cached content</html>"

    def test_returns_none_when_force_refresh(self):
        """Returns None when force_refresh is True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA", force_refresh=True)
            url = "https://www.basketball-reference.com/boxscores/202401150BOS.html"

            # Create cache file
            cache_path = cache._get_cache_path(url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text("<html>cached content</html>")

            result = cache.get(url)
            assert result is None


class TestHTMLCachePut:
    """Tests for put method."""

    def test_saves_html_to_cache(self):
        """Saves HTML content to cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            url = "https://www.basketball-reference.com/boxscores/202401150BOS.html"
            html = "<html>test content</html>"

            result_path = cache.put(url, html)

            assert result_path is not None
            assert result_path.exists()
            assert result_path.read_text() == html

    def test_creates_directories(self):
        """Creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            url = "https://www.basketball-reference.com/boxscores/202401150BOS.html"
            html = "<html>test content</html>"

            result_path = cache.put(url, html)

            assert result_path.parent.exists()

    def test_skips_small_scoreboard(self):
        """Skips saving small scoreboard content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            # Scoreboard URL with small content
            url = "https://www.basketball-reference.com/boxscores/?month=1&day=15&year=2024"
            html = "<html>small</html>"  # Much smaller than MIN_SCOREBOARD_SIZE_BYTES

            result_path = cache.put(url, html)

            assert result_path is None


class TestMinScoreboardSizeBytes:
    """Tests for MIN_SCOREBOARD_SIZE_BYTES constant."""

    def test_is_integer(self):
        """Constant is an integer."""
        assert isinstance(MIN_SCOREBOARD_SIZE_BYTES, int)

    def test_is_reasonable_size(self):
        """Constant is a reasonable size (between 1KB and 100KB)."""
        assert MIN_SCOREBOARD_SIZE_BYTES >= 1000
        assert MIN_SCOREBOARD_SIZE_BYTES <= 100000


class TestModuleImports:
    """Tests for cache module imports."""

    def test_has_html_cache(self):
        """Module has HTMLCache class."""
        from sports_scraper.utils import cache
        assert hasattr(cache, 'HTMLCache')

    def test_has_min_scoreboard_size(self):
        """Module has MIN_SCOREBOARD_SIZE_BYTES constant."""
        from sports_scraper.utils import cache
        assert hasattr(cache, 'MIN_SCOREBOARD_SIZE_BYTES')
