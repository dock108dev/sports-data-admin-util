"""Playwright-backed collector for public X posts."""

from __future__ import annotations

from datetime import datetime, timedelta

from tenacity import retry, stop_after_attempt, wait_fixed

from ..logging import logger
from .collector_base import XCollectorStrategy
from .models import CollectedPost

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None


def playwright_available() -> bool:
    return sync_playwright is not None


class PlaywrightXCollector(XCollectorStrategy):
    """
    Headless collector that visits public X profiles and extracts recent posts.

    This avoids X API dependency. It scrapes minimal metadata:
    - post URL
    - timestamp
    - has_video flag
    Caption text is read only to allow spoiler filtering but is not stored.

    Authentication:
        Set X_AUTH_TOKEN and X_CT0 environment variables from your browser cookies.
        These are required for search functionality.

        To get these values:
        1. Log into x.com in your browser
        2. Open DevTools > Application > Cookies > x.com
        3. Copy the values of 'auth_token' and 'ct0' cookies

    Rate Limiting:
        - Polite delay of 5-9 seconds between requests (like sports reference scraping)
        - Random jitter to appear more human-like
    """

    def __init__(
        self,
        max_scrolls: int = 3,
        wait_ms: int = 800,
        timeout_ms: int = 30000,
        auth_token: str | None = None,
        ct0: str | None = None,
        min_delay_seconds: float = 5.0,
        max_delay_seconds: float = 9.0,
    ):
        import os

        self.max_scrolls = max_scrolls
        self.wait_ms = wait_ms
        self.timeout_ms = timeout_ms
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self._last_request_time = 0.0
        # Load auth from params or environment
        self.auth_token = auth_token or os.environ.get("X_AUTH_TOKEN")
        self.ct0 = ct0 or os.environ.get("X_CT0")

        if not self.auth_token:
            logger.warning("x_auth_missing", message="X_AUTH_TOKEN not set - search may not work")

    def _polite_delay(self) -> None:
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

    def _mark_request_done(self) -> None:
        """Mark that a request just completed (for polite delay calculation)."""
        import time

        self._last_request_time = time.time()

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    def _build_search_url(self, x_handle: str, window_start: datetime, window_end: datetime) -> str:
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

    def _parse_post_time(self, datetime_str: str) -> datetime | None:
        try:
            from dateutil import parser
            return parser.isoparse(datetime_str)
        except Exception:
            return None

    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        if not sync_playwright:
            logger.warning("x_playwright_missing", handle=x_handle)
            return []

        posts: list[CollectedPost] = []
        logger.info(
            "x_playwright_collect_start",
            handle=x_handle,
            window_start=str(window_start),
            window_end=str(window_end),
        )

        self._polite_delay()

        with sync_playwright() as p:
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

                page.goto(search_url, timeout=self.timeout_ms)
                page.wait_for_timeout(self.wait_ms)

                # Scroll to load more posts
                for _ in range(self.max_scrolls):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(self.wait_ms)

                self._mark_request_done()

                # Find tweets in timeline
                articles = page.query_selector_all('article[data-testid="tweet"]')

                for article in articles:
                    # Extract post URL
                    anchor = article.query_selector('a[href*="/status/"]')
                    post_url = None
                    if anchor:
                        href = anchor.get_attribute("href")
                        if href:
                            post_url = f"https://x.com{href}" if href.startswith("/") else href

                    if not post_url:
                        continue

                    # Extract timestamp
                    time_el = article.query_selector("time")
                    posted_at = None
                    if time_el:
                        datetime_str = time_el.get_attribute("datetime")
                        if datetime_str:
                            posted_at = self._parse_post_time(datetime_str)

                    if not posted_at:
                        continue

                    # Filter by window
                    if posted_at < window_start or posted_at > window_end:
                        continue

                    # Extract text content
                    text_content = None
                    text_el = article.query_selector('[data-testid="tweetText"]')
                    if text_el:
                        text_content = text_el.inner_text()

                    # Detect media (video/image)
                    has_video = article.query_selector("video") is not None
                    video_url = None
                    image_url = None
                    media_type = "none"

                    if has_video:
                        media_type = "video"
                        video_el = article.query_selector("video")
                        if video_el:
                            video_url = video_el.get_attribute("src")

                    if not image_url:
                        img_el = article.query_selector('[data-testid="tweetPhoto"] img')
                        if img_el:
                            image_url = img_el.get_attribute("src")
                            if not media_type or media_type == "none":
                                media_type = "image"

                    # If we detected video presence but couldn't extract media URLs,
                    # still mark the post as video so downstream UI can handle it.
                    if has_video and media_type == "none":
                        media_type = "video"

                    posts.append(
                        CollectedPost(
                            post_url=post_url,
                            posted_at=posted_at,
                            has_video=has_video,
                            text=text_content,
                            author_handle=x_handle.lstrip("@"),
                            video_url=video_url,
                            image_url=image_url,
                            media_type=media_type,
                        )
                    )

            finally:
                browser.close()

        logger.info("x_playwright_collect_done", handle=x_handle, count=len(posts))
        return posts
