"""Playwright-backed collector for public X posts."""

from __future__ import annotations

import time
from collections import deque
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


# Circuit breaker constants
_BACKOFF_SECONDS = 90  # Fixed 90 second backoff on rate limit
_MAX_RETRIES = 3  # Fail loudly after 3 retries
_HOURLY_WINDOW_SECONDS = 3600


class PlaywrightXCollector(XCollectorStrategy):
    """
    Headless collector that visits public X profiles and extracts recent posts.

    This avoids X API dependency. It scrapes minimal metadata:
    - post URL
    - timestamp
    - has_video flag
    Caption text is read only to allow reveal filtering but is not stored.

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
        - Global hourly request cap (default: 100/hour)

    Circuit Breaker:
        - On error: wait 90 seconds, then retry
        - After 3 consecutive errors: fail the scrape loudly with actual error
        - No exponential backoff - simple and predictable
    """

    # Class-level circuit breaker state (shared across instances in same worker)
    _consecutive_errors: int = 0
    _circuit_open_until: float = 0.0
    _last_error_message: str = ""  # Store actual error for loud failure
    # Hourly request tracking (sliding window)
    _hourly_requests: deque = deque()

    def __init__(  # pragma: no cover - browser config
        self,
        max_scrolls: int = 8,  # Increased to capture more posts in longer windows
        wait_ms: int = 2000,  # X's JS needs time to render
        timeout_ms: int = 30000,
        auth_token: str | None = None,
        ct0: str | None = None,
        min_delay_seconds: float = 10.0,  # Increased from 5.0
        max_delay_seconds: float = 15.0,  # Increased from 9.0
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

        # Fallback: load auth from params or environment
        self.auth_token = auth_token or os.environ.get("X_AUTH_TOKEN")
        self.ct0 = ct0 or os.environ.get("X_CT0")

        if self.profile_dir:
            logger.info("x_using_persistent_profile", profile_dir=self.profile_dir)
        elif not self.auth_token:
            logger.warning("x_auth_missing", message="Neither PLAYWRIGHT_PROFILE_DIR nor X_AUTH_TOKEN set - search may not work")

    def _check_circuit_breaker(self) -> None:  # pragma: no cover - class-level state
        """Check if circuit breaker is open and raise if so."""
        if time.time() < PlaywrightXCollector._circuit_open_until:
            remaining = int(PlaywrightXCollector._circuit_open_until - time.time())
            logger.warning(
                "x_circuit_open",
                remaining_seconds=remaining,
                retry_at=datetime.fromtimestamp(PlaywrightXCollector._circuit_open_until).isoformat(),
            )
            raise XCircuitBreakerError(
                f"Circuit breaker open, retry in {remaining}s",
                retry_after_seconds=remaining,
            )

    def _check_hourly_cap(self) -> None:  # pragma: no cover - class-level state
        """Check if hourly request cap is exceeded and raise if so."""
        now = time.time()
        hourly_cap = settings.social_config.hourly_request_cap
        
        # Prune requests older than 1 hour
        cutoff = now - _HOURLY_WINDOW_SECONDS
        while PlaywrightXCollector._hourly_requests and PlaywrightXCollector._hourly_requests[0] < cutoff:
            PlaywrightXCollector._hourly_requests.popleft()
        
        current_count = len(PlaywrightXCollector._hourly_requests)
        if current_count >= hourly_cap:
            # Calculate when oldest request will expire
            oldest = PlaywrightXCollector._hourly_requests[0]
            retry_after = int(oldest + _HOURLY_WINDOW_SECONDS - now) + 1
            logger.warning(
                "x_hourly_cap_exceeded",
                current_count=current_count,
                hourly_cap=hourly_cap,
                retry_after_seconds=retry_after,
            )
            raise XCircuitBreakerError(
                f"Hourly request cap ({hourly_cap}) exceeded, retry in {retry_after}s",
                retry_after_seconds=retry_after,
            )

    def _record_hourly_request(self) -> None:  # pragma: no cover - class-level state
        """Record a request for hourly cap tracking."""
        PlaywrightXCollector._hourly_requests.append(time.time())

    def _record_error(self, error_message: str) -> None:  # pragma: no cover - class-level state
        """Record an error and trigger circuit breaker.

        Simple behavior:
        - On first error: log it, set 90s backoff
        - On 2nd error: log it, set 90s backoff
        - On 3rd error: FAIL LOUDLY with the actual error message
        """
        PlaywrightXCollector._consecutive_errors += 1
        PlaywrightXCollector._last_error_message = error_message

        logger.error(
            "x_scrape_error",
            error=error_message,
            attempt=PlaywrightXCollector._consecutive_errors,
            max_retries=_MAX_RETRIES,
        )

        if PlaywrightXCollector._consecutive_errors >= _MAX_RETRIES:
            # 3 strikes - fail loudly with the actual error
            logger.error(
                "x_scrape_failed_permanently",
                error=error_message,
                attempts=PlaywrightXCollector._consecutive_errors,
                message="Failing social scrape after max retries",
            )
            raise XCircuitBreakerError(
                f"X scrape failed after {_MAX_RETRIES} attempts: {error_message}",
                retry_after_seconds=0,  # Don't retry
            )

        # Not at max yet - set 90 second backoff
        PlaywrightXCollector._circuit_open_until = time.time() + _BACKOFF_SECONDS
        logger.warning(
            "x_backoff_started",
            error=error_message,
            attempt=PlaywrightXCollector._consecutive_errors,
            backoff_seconds=_BACKOFF_SECONDS,
            retry_at=datetime.fromtimestamp(PlaywrightXCollector._circuit_open_until).isoformat(),
        )

    def _record_success(self, posts_found: int) -> None:  # pragma: no cover - class-level state
        """Record a successful request and reset error counter."""
        if PlaywrightXCollector._consecutive_errors > 0:
            logger.info(
                "x_errors_reset",
                previous_errors=PlaywrightXCollector._consecutive_errors,
                posts_found=posts_found,
            )
        PlaywrightXCollector._consecutive_errors = 0
        PlaywrightXCollector._last_error_message = ""

    def _polite_delay(self) -> None:  # pragma: no cover - timing-dependent
        """Wait between requests to be a good citizen (5-9 seconds like sports reference)."""
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

        This allows finding tweets from any date, not just recent ones.
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

    def collect_posts(  # pragma: no cover - requires browser
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        if not sync_playwright:
            logger.warning("x_playwright_missing", handle=x_handle)
            return []

        # Check circuit breaker and hourly cap before making request
        self._check_circuit_breaker()
        self._check_hourly_cap()

        posts: list[CollectedPost] = []
        page_error_message: str | None = None
        logger.info(
            "x_playwright_collect_start",
            handle=x_handle,
            window_start=str(window_start),
            window_end=str(window_end),
        )

        self._polite_delay()

        with sync_playwright() as p:
            browser = None
            context = None

            if self.profile_dir:
                # Persistent context - reuses saved browser state (cookies, local storage)
                # This is preferred as it auto-refreshes tokens during usage
                context = p.chromium.launch_persistent_context(
                    self.profile_dir,
                    headless=True,
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = context.pages[0] if context.pages else context.new_page()
            else:
                # Fallback: launch browser and inject cookies manually
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
                    # Continue anyway - might be legitimately no tweets

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
                logger.info("x_total_posts_collected", handle=x_handle, total=len(posts))

            finally:
                # Close browser/context appropriately
                if browser:
                    browser.close()
                elif context:
                    context.close()

        # Record this request for hourly cap tracking
        self._record_hourly_request()

        # Update circuit breaker state based on result
        if page_error_message:
            self._record_error(page_error_message)
        else:
            self._record_success(posts_found=len(posts))

        logger.info("x_playwright_collect_done", handle=x_handle, count=len(posts))
        return posts
