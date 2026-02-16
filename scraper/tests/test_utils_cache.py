"""Tests for utils/cache.py module."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import date, timedelta
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
    FINAL_STATES,
    HTMLCache,
    MIN_SCOREBOARD_SIZE_BYTES,
    should_cache_final,
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


class TestHTMLCacheIsBoxscoreUrl:
    """Tests for _is_boxscore_url method."""

    def test_boxscore_url_detected(self):
        """Detects individual boxscore URLs."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/boxscores/202401150BOS.html"
        assert cache._is_boxscore_url(url) is True

    def test_scoreboard_url_not_detected(self):
        """Scoreboard URLs are not boxscores."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/boxscores/?month=1&day=15&year=2024"
        assert cache._is_boxscore_url(url) is False

    def test_pbp_url_not_detected(self):
        """PBP URLs are not boxscores."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/boxscores/pbp/202401150BOS.html"
        assert cache._is_boxscore_url(url) is False

    def test_non_boxscore_url_not_detected(self):
        """Non-boxscore URLs are not detected."""
        cache = HTMLCache("/tmp/cache", "NBA")
        url = "https://www.basketball-reference.com/teams/BOS/2024.html"
        assert cache._is_boxscore_url(url) is False


class TestHTMLCacheRecentBoxscoreStaleness:
    """Tests for boxscore cache staleness bypass.

    Recent boxscores (game within last 3 days) with cache age < 12 hours
    should be bypassed to avoid serving incomplete data cached too soon
    after game end.
    """

    BOXSCORE_URL = "https://www.basketball-reference.com/boxscores/202401150BOS.html"

    def _create_cached_file(self, cache: HTMLCache, url: str, age_hours: float) -> Path:
        """Helper: create a cached file and backdate its mtime."""
        cache_path = cache._get_cache_path(url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("<html>boxscore content</html>")
        target_mtime = time.time() - (age_hours * 3600)
        os.utime(cache_path, (target_mtime, target_mtime))
        return cache_path

    @patch("sports_scraper.utils.cache.today_et")
    def test_bypasses_cache_when_recent_and_young(self, mock_today):
        """Returns None for a boxscore cached <12h ago for a game within 3 days."""
        mock_today.return_value = date(2024, 1, 16)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=6)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result is None

    @patch("sports_scraper.utils.cache.today_et")
    def test_returns_content_when_recent_and_old_enough(self, mock_today):
        """Returns content for a boxscore cached >=12h ago (data is stable)."""
        mock_today.return_value = date(2024, 1, 16)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=13)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result == "<html>boxscore content</html>"

    @patch("sports_scraper.utils.cache.today_et")
    def test_returns_content_when_game_older_than_3_days(self, mock_today):
        """Returns content when game is >3 days old regardless of cache age."""
        mock_today.return_value = date(2024, 1, 20)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=2)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result == "<html>boxscore content</html>"

    @patch("sports_scraper.utils.cache.today_et")
    def test_returns_content_when_no_game_date(self, mock_today):
        """Returns content when game_date is not provided (no staleness check)."""
        mock_today.return_value = date(2024, 1, 16)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=1)

            result = cache.get(self.BOXSCORE_URL)
            assert result == "<html>boxscore content</html>"

    @patch("sports_scraper.utils.cache.today_et")
    def test_bypasses_at_boundary_3_days(self, mock_today):
        """Bypasses cache for a game exactly 3 days old with young cache."""
        mock_today.return_value = date(2024, 1, 18)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=4)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result is None

    @patch("sports_scraper.utils.cache.today_et")
    def test_returns_content_at_boundary_4_days(self, mock_today):
        """Returns content for a game exactly 4 days old (outside window)."""
        mock_today.return_value = date(2024, 1, 19)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=4)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result == "<html>boxscore content</html>"

    @patch("sports_scraper.utils.cache.today_et")
    def test_bypasses_at_boundary_12_hours(self, mock_today):
        """Bypasses cache at just under 12 hours old."""
        mock_today.return_value = date(2024, 1, 16)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=11.9)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result is None

    @patch("sports_scraper.utils.cache.today_et")
    def test_returns_content_at_exactly_12_hours(self, mock_today):
        """Returns content when cache is exactly 12 hours old."""
        mock_today.return_value = date(2024, 1, 16)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=12.1)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result == "<html>boxscore content</html>"

    @patch("sports_scraper.utils.cache.today_et")
    def test_does_not_apply_to_scoreboard_urls(self, mock_today):
        """Staleness check does not apply to scoreboard URLs."""
        mock_today.return_value = date(2024, 1, 16)
        scoreboard_url = "https://www.basketball-reference.com/boxscores/?month=1&day=15&year=2024"

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            cache_path = cache._get_cache_path(scoreboard_url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            content = '<div class="game_summary">' + "x" * MIN_SCOREBOARD_SIZE_BYTES
            cache_path.write_text(content)
            target_mtime = time.time() - 3600
            os.utime(cache_path, (target_mtime, target_mtime))

            result = cache.get(scoreboard_url, game_date=date(2024, 1, 15))
            assert result is not None

    @patch("sports_scraper.utils.cache.today_et")
    def test_does_not_apply_to_pbp_urls(self, mock_today):
        """Staleness check does not apply to PBP URLs."""
        mock_today.return_value = date(2024, 1, 16)
        pbp_url = "https://www.basketball-reference.com/boxscores/pbp/202401150BOS.html"

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            cache_path = cache._get_cache_path(pbp_url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text("<html>pbp content</html>")
            target_mtime = time.time() - 3600
            os.utime(cache_path, (target_mtime, target_mtime))

            result = cache.get(pbp_url, game_date=date(2024, 1, 15))
            assert result == "<html>pbp content</html>"

    @patch("sports_scraper.utils.cache.today_et")
    def test_bypasses_same_day_game(self, mock_today):
        """Bypasses cache for game_date == today (0 days ago) with young cache."""
        mock_today.return_value = date(2024, 1, 15)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HTMLCache(tmpdir, "NBA")
            self._create_cached_file(cache, self.BOXSCORE_URL, age_hours=2)

            result = cache.get(self.BOXSCORE_URL, game_date=date(2024, 1, 15))
            assert result is None


class TestShouldCacheFinal:
    """Tests for should_cache_final() caching gate."""

    # --- positive cases: should cache ---

    def test_nba_final_with_data(self):
        """Caches NBA game at status 3 (final) with player data."""
        assert should_cache_final(True, 3) is True

    def test_nhl_off_with_data(self):
        """Caches NHL game at state 'OFF' with player data."""
        assert should_cache_final(True, "OFF") is True

    def test_nhl_final_with_data(self):
        """Caches NHL game at state 'FINAL' with player data."""
        assert should_cache_final(True, "FINAL") is True

    def test_ncaab_final_with_data(self):
        """Caches NCAAB game at normalized status 'final' with play data."""
        assert should_cache_final(True, "final") is True

    # --- negative cases: should NOT cache ---

    def test_nba_scheduled_with_data(self):
        """Does not cache scheduled NBA game (status 1)."""
        assert should_cache_final(True, 1) is False

    def test_nba_live_with_data(self):
        """Does not cache live NBA game (status 2)."""
        assert should_cache_final(True, 2) is False

    def test_nhl_fut_with_data(self):
        """Does not cache future NHL game."""
        assert should_cache_final(True, "FUT") is False

    def test_nhl_pre_with_data(self):
        """Does not cache pregame NHL game."""
        assert should_cache_final(True, "PRE") is False

    def test_nhl_live_with_data(self):
        """Does not cache live NHL game."""
        assert should_cache_final(True, "LIVE") is False

    def test_ncaab_scheduled_with_data(self):
        """Does not cache scheduled NCAAB game."""
        assert should_cache_final(True, "scheduled") is False

    def test_ncaab_live_with_data(self):
        """Does not cache live NCAAB game."""
        assert should_cache_final(True, "live") is False

    def test_ncaab_final_without_data(self):
        """Does not cache final NCAAB game when payload is empty."""
        assert should_cache_final(False, "final") is False

    def test_final_without_data(self):
        """Does not cache final game when payload is empty."""
        assert should_cache_final(False, 3) is False

    def test_nhl_off_without_data(self):
        """Does not cache NHL 'OFF' game when payload is empty."""
        assert should_cache_final(False, "OFF") is False

    def test_no_data_no_status(self):
        """Does not cache when both data and status are missing."""
        assert should_cache_final(False, None) is False

    def test_data_but_none_status(self):
        """Does not cache when status is None even with data."""
        assert should_cache_final(True, None) is False

    def test_data_but_unknown_status_string(self):
        """Does not cache for unrecognized status strings."""
        assert should_cache_final(True, "POSTPONED") is False

    def test_data_but_unknown_status_int(self):
        """Does not cache for unrecognized status integers."""
        assert should_cache_final(True, 99) is False


class TestFinalStates:
    """Tests for the FINAL_STATES constant."""

    def test_contains_nba_final(self):
        """Contains NBA final status (int 3)."""
        assert 3 in FINAL_STATES

    def test_contains_nhl_off(self):
        """Contains NHL 'OFF' state."""
        assert "OFF" in FINAL_STATES

    def test_contains_nhl_final(self):
        """Contains NHL 'FINAL' state."""
        assert "FINAL" in FINAL_STATES

    def test_contains_ncaab_final(self):
        """Contains NCAAB normalized 'final' state."""
        assert "final" in FINAL_STATES

    def test_does_not_contain_live_states(self):
        """Does not contain any live/pregame states."""
        for state in [1, 2, "FUT", "PRE", "LIVE"]:
            assert state not in FINAL_STATES


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