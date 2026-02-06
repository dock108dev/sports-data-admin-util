"""Playwright-backed collector for public X posts."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from tenacity import retry, stop_after_attempt, wait_fixed

from ..config import settings
from ..logging import logger
from .collector_base import XCollectorStrategy
from .exceptions import XCircuitBreakerError
from .models import CollectedPost
from .utils import extract_x_post_id

from importlib.util import find_spec

if find_spec("playwright.sync_api") is not None:
    from playwright.sync_api import sync_playwright
else:  # pragma: no cover - optional dependency
    sync_playwright = None


def playwright_available() -> bool:  # pragma: no cover
    return sync_playwright is not None


# Retry constants
_BACKOFF_SECONDS = 90  # Fixed 90 second backoff on retryable error
_MAX_ATTEMPTS = 3  # Try up to 3 times, then fail the job


class PlaywrightXCollector(XCollectorStrategy):
    """
    Headless collector that visits public X profiles and extracts recent posts.

    This avoids X API dependency. It scrapes minimal metadata:
    - post URL
    - timestamp
    - has_video flag

    Authentication:
        Set X_AUTH_TOKEN and X_CT0 environment variables from your browser cookies.
        These are required for search functionality.

        To get these values:
        1. Log into x.com in your browser
        2. Open DevTools > Application > Cookies > x.com
        3. Copy the values of 'auth_token' and 'ct0' cookies

    Rate Limiting:
        - Polite delay of 10-15 seconds between requests
        - Random jitter to appear more human-like
        - Concurrency=1 in Celery naturally caps throughput

    Retry Logic:
        - On "login wall" or "Something went wrong": sleep 90s, retry up to 3 times
        - On "No results": return empty list (not an error)
        - After 3 failures: raise XCircuitBreakerError to fail the job
        - No class-level state — each collect_posts() call is self-contained
    """

    # Track whether we've already seeded the profile this worker lifetime
    _profile_seeded: bool = False

    def __init__(  # pragma: no cover - browser config
        self,
        max_scrolls: int = 8,
        wait_ms: int = 2000,  # X's JS needs time to render
        timeout_ms: int = 30000,
        auth_token: str | None = None,
        ct0: str | None = None,
        min_delay_seconds: float = 10.0,
        max_delay_seconds: float = 15.0,
        profile_dir: str | None = None,
    ):
        import os

        self.max_scrolls = max_scrolls
        self.wait_ms = wait_ms
        self.timeout_ms = timeout_ms
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self._last_request_time = 0.0

        # Persistent browser profile (preferred - auto-refreshes tokens)
        self.profile_dir = profile_dir or os.environ.get("PLAYWRIGHT_PROFILE_DIR")

        # Seed tokens: used to bootstrap profile on first boot
        self.auth_token = auth_token or os.environ.get("X_AUTH_TOKEN")
        self.ct0 = ct0 or os.environ.get("X_CT0")

        if self.profile_dir:
            logger.info("x_using_persistent_profile", profile_dir=self.profile_dir)
            # Seed the profile from tokens on first boot of this worker
            if not PlaywrightXCollector._profile_seeded:
                self._maybe_seed_profile()
        elif not self.auth_token:
            logger.warning("x_auth_missing", message="Neither PLAYWRIGHT_PROFILE_DIR nor X_AUTH_TOKEN set - search may not work")

    def _maybe_seed_profile(self) -> None:  # pragma: no cover
        """Seed the persistent profile from X_AUTH_TOKEN/X_CT0.

        Always wipes existing profile contents and reseeds from tokens.
        This fixes cross-platform incompatibility (macOS profile on Linux)
        and stale profile issues. The _profile_seeded class flag prevents
        re-seeding during the same worker lifetime.
        """
        import os
        import shutil

        if not self.profile_dir or not self.auth_token or not self.ct0:
            return

        if not sync_playwright:
            return

        logger.info("x_profile_seeding_start", profile_dir=self.profile_dir)

        # Wipe existing profile contents (may be stale or cross-platform incompatible)
        try:
            if os.path.exists(self.profile_dir):
                for item in os.listdir(self.profile_dir):
                    item_path = os.path.join(self.profile_dir, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                logger.debug("x_profile_wiped", profile_dir=self.profile_dir)
        except Exception as exc:
            logger.warning("x_profile_wipe_failed", error=str(exc))

        os.makedirs(self.profile_dir, exist_ok=True)

        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    self.profile_dir,
                    headless=True,
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                # Inject auth cookies
                context.add_cookies([
                    {"name": "auth_token", "value": self.auth_token, "domain": ".x.com", "path": "/"},
                    {"name": "ct0", "value": self.ct0, "domain": ".x.com", "path": "/"},
                ])
                # Navigate to x.com so the cookies get persisted to the profile
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://x.com", timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                context.close()

            PlaywrightXCollector._profile_seeded = True
            logger.info("x_profile_seeded_successfully", profile_dir=self.profile_dir)
        except Exception as exc:
            logger.warning("x_profile_seed_failed", error=str(exc))

    def _polite_delay(self) -> None:  # pragma: no cover - timing-dependent
        """Wait between requests to be a good citizen (10-15 seconds)."""
        import random
        import time

        if self._last_request_time == 0:
            return

        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
        if elapsed < delay:
            wait_time = delay - elapsed
            logger.debug("x_polite_delay", wait_seconds=round(wait_time, 1))
            time.sleep(wait_time)

    def _mark_request_done(self) -> None:  # pragma: no cover - timing-dependent
        """Mark that a request just completed (for polite delay calculation)."""
        import time

        self._last_request_time = time.time()

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    def _build_search_url(self, x_handle: str, window_start: datetime, window_end: datetime) -> str:  # pragma: no cover
        """
        Build X search URL for historical tweet lookup.

        Uses X's advanced search syntax:
            from:handle since:YYYY-MM-DD until:YYYY-MM-DD
        """
        handle_clean = x_handle.lstrip("@")
        start_date = window_start.strftime("%Y-%m-%d")
        end_date = (window_end + timedelta(days=1)).strftime("%Y-%m-%d")
        query = f"from:{handle_clean} since:{start_date} until:{end_date}"
        from urllib.parse import quote

        return f"https://x.com/search?q={quote(query)}&src=typed_query&f=live"

    def _parse_post_time(self, datetime_str: str) -> datetime | None:  # pragma: no cover
        try:
            from dateutil import parser
            return parser.isoparse(datetime_str)
        except Exception:
            return None

    def _scrape_once(  # pragma: no cover - requires browser
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[list[CollectedPost], str | None]:
        """Execute a single scrape attempt.

        Returns:
            Tuple of (posts, error_message). error_message is None on success
            or "no_results" for empty-but-valid responses.
        """
        posts: list[CollectedPost] = []
        page_error_message: str | None = None

        with sync_playwright() as p:
            browser = None
            context = None

            if self.profile_dir:
                context = p.chromium.launch_persistent_context(
                    self.profile_dir,
                    headless=True,
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()

                if self.auth_token and self.ct0:
                    context.add_cookies(
                        [
                            {"name": "auth_token", "value": self.auth_token, "domain": ".x.com", "path": "/"},
                            {"name": "ct0", "value": self.ct0, "domain": ".x.com", "path": "/"},
                        ]
                    )

                page = context.new_page()

            try:
                search_url = self._build_search_url(x_handle, window_start, window_end)
                logger.debug("x_playwright_search_url", url=search_url)

                page.goto(search_url, timeout=self.timeout_ms, wait_until="domcontentloaded")

                # Wait for tweets to appear (up to 10 seconds)
                try:
                    page.wait_for_selector(
                        'article[data-testid="tweet"]',
                        timeout=10000,
                        state="attached"
                    )
                except Exception:
                    # No tweets found - check for error conditions
                    content = page.content()
                    if "Something went wrong" in content:
                        page_error_message = "X returned 'Something went wrong' - possible rate limit or auth issue"
                        logger.error("x_page_error", handle=x_handle, error=page_error_message)
                    elif "Log in" in content or "Sign in" in content:
                        page_error_message = "X returned login wall - auth tokens may be expired"
                        logger.error("x_page_error", handle=x_handle, error=page_error_message)
                    elif "No results" in content:
                        logger.debug("x_page_no_results", handle=x_handle)
                        page_error_message = "no_results"

                page.wait_for_timeout(self.wait_ms)

                def extract_posts_from_page() -> set[str]:
                    """Extract all posts currently visible and return set of post IDs."""
                    extracted_ids: set[str] = set()
                    articles = page.query_selector_all('article[data-testid="tweet"]')

                    for article in articles:
                        # Skip retweets
                        social_context = article.query_selector('[data-testid="socialContext"]')
                        if social_context:
                            context_text = social_context.inner_text()
                            if context_text and "Retweeted" in context_text:
                                continue

                        # Extract post URL
                        anchor = article.query_selector('a[href*="/status/"]')
                        post_url = None
                        if anchor:
                            href = anchor.get_attribute("href")
                            if href:
                                post_url = f"https://x.com{href}" if href.startswith("/") else href

                        if not post_url:
                            continue

                        post_id = extract_x_post_id(post_url)
                        if not post_id or post_id in seen_post_ids:
                            continue

                        extracted_ids.add(post_id)
                        seen_post_ids.add(post_id)

                        # Extract timestamp
                        time_el = article.query_selector("time")
                        posted_at = None
                        if time_el:
                            datetime_str = time_el.get_attribute("datetime")
                            if datetime_str:
                                posted_at = self._parse_post_time(datetime_str)

                        if not posted_at:
                            continue

                        # Extract text content
                        text_content = None
                        text_el = article.query_selector('[data-testid="tweetText"]')
                        if text_el:
                            text_content = text_el.inner_text()

                        # Detect media
                        video_url = None
                        image_url = None
                        media_type = "none"

                        video_container = (
                            article.query_selector('[data-testid="videoPlayer"]')
                            or article.query_selector('[data-testid="videoComponent"]')
                            or article.query_selector('[data-testid="previewInterstitial"]')
                            or article.query_selector('video')
                        )
                        has_video = video_container is not None

                        if has_video:
                            media_type = "video"
                            video_el = article.query_selector("video")
                            if video_el:
                                video_url = video_el.get_attribute("src")
                        else:
                            img_el = article.query_selector('[data-testid="tweetPhoto"] img')
                            if img_el:
                                image_url = img_el.get_attribute("src")
                                media_type = "image"

                        posts.append(
                            CollectedPost(
                                post_url=post_url,
                                external_post_id=post_id,
                                posted_at=posted_at,
                                has_video=has_video,
                                text=text_content,
                                author_handle=x_handle.lstrip("@"),
                                video_url=video_url,
                                image_url=image_url,
                                media_type=media_type,
                            )
                        )

                    return extracted_ids

                # Track seen posts to dedupe across scrolls
                seen_post_ids: set[str] = set()

                # Initial extraction
                new_ids = extract_posts_from_page()
                logger.debug("x_initial_extract", handle=x_handle, new_posts=len(new_ids), total=len(posts))

                # Scroll and extract until no new posts appear
                for scroll_num in range(self.max_scrolls):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(self.wait_ms)

                    new_ids = extract_posts_from_page()
                    logger.debug(
                        "x_scroll_extract",
                        handle=x_handle,
                        scroll=scroll_num + 1,
                        new_posts=len(new_ids),
                        total=len(posts),
                    )

                    # Stop early if no new posts found (reached end of results)
                    if len(new_ids) == 0:
                        logger.debug("x_scroll_complete_early", handle=x_handle, reason="no_new_posts")
                        break

                self._mark_request_done()

            finally:
                if browser:
                    browser.close()
                elif context:
                    context.close()

        return posts, page_error_message

    def collect_posts(  # pragma: no cover - requires browser
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        if not sync_playwright:
            logger.warning("x_playwright_missing", handle=x_handle)
            return []

        logger.info(
            "x_playwright_collect_start",
            handle=x_handle,
            window_start=str(window_start),
            window_end=str(window_end),
        )

        self._polite_delay()

        last_error: str = ""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            posts, error_message = self._scrape_once(x_handle, window_start, window_end)

            # "no_results" is not an error — just no tweets in that window
            if error_message == "no_results":
                logger.info("x_playwright_collect_done", handle=x_handle, count=0)
                return []

            # Success — got posts (or no error and no posts)
            if error_message is None:
                logger.info("x_playwright_collect_done", handle=x_handle, count=len(posts))
                return posts

            # Retryable error (login wall, "Something went wrong")
            last_error = error_message
            logger.warning(
                "x_scrape_retry",
                handle=x_handle,
                attempt=attempt,
                max_attempts=_MAX_ATTEMPTS,
                error=error_message,
                backoff_seconds=_BACKOFF_SECONDS,
            )

            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS)

        # All attempts exhausted — fail the job loudly
        logger.error(
            "x_scrape_failed_permanently",
            handle=x_handle,
            attempts=_MAX_ATTEMPTS,
            error=last_error,
        )
        raise XCircuitBreakerError(
            f"X scrape failed after {_MAX_ATTEMPTS} attempts: {last_error}",
            retry_after_seconds=0,
        )
