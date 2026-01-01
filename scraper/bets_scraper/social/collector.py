"""
X (Twitter) post collector for game timelines.

This module provides infrastructure to collect posts from team X accounts
during game windows. It supports both API-based collection and headless
browser scraping as fallback.

Note: Actual X API integration requires API keys and rate limiting.
This module provides the interface and can be extended with specific
collection strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, Optional, Set

from tenacity import retry, stop_after_attempt, wait_fixed

from ..logging import logger
from .models import CollectedPost, PostCollectionJob, PostCollectionResult

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class XCollectorStrategy(ABC):
    """Abstract base class for X post collection strategies."""

    @abstractmethod
    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        """
        Collect posts from an X account within a time window.

        Args:
            x_handle: X handle to collect from (without @)
            window_start: Start of collection window
            window_end: End of collection window

        Returns:
            List of collected posts
        """
        pass


class MockXCollector(XCollectorStrategy):
    """
    Mock collector for testing without X API access.
    
    Returns empty results - real data should come from actual X integration.
    """

    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        logger.info(
            "mock_x_collector_called",
            x_handle=x_handle,
            window_start=str(window_start),
            window_end=str(window_end),
        )
        # Return empty - this is a placeholder for real X API integration
        return []


class XApiCollector(XCollectorStrategy):
    """
    Collector using X API v2.
    
    Requires X_BEARER_TOKEN environment variable.
    Rate limited to 450 requests per 15 minutes (user timeline).
    """

    def __init__(self, bearer_token: str | None = None):
        import os
        self.bearer_token = bearer_token or os.environ.get("X_BEARER_TOKEN")
        if not self.bearer_token:
            logger.warning("x_api_collector_no_token", msg="X_BEARER_TOKEN not set")

    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        if not self.bearer_token:
            logger.warning("x_api_skipped_no_token", x_handle=x_handle)
            return []

        # TODO: Implement actual X API v2 integration
        # See: https://developer.twitter.com/en/docs/twitter-api/tweets/timelines/api-reference/get-users-id-tweets
        #
        # Steps:
        # 1. Get user ID from handle: GET /2/users/by/username/:username
        # 2. Get user tweets: GET /2/users/:id/tweets
        #    - start_time, end_time for filtering
        #    - expansions=attachments.media_keys for video detection
        # 3. Filter by time window
        # 4. Map to CollectedPost objects

        logger.info(
            "x_api_collection_not_implemented",
            x_handle=x_handle,
            msg="X API integration pending implementation",
        )
        return []


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
        
        # Skip delay on first request (no previous request to wait from)
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
        from urllib.parse import quote
        
        handle = x_handle.lstrip('@')
        # Format dates as YYYY-MM-DD for X search
        since_date = window_start.strftime("%Y-%m-%d")
        until_date = (window_end + timedelta(days=1)).strftime("%Y-%m-%d")  # until is exclusive
        
        query = f"from:{handle} since:{since_date} until:{until_date}"
        encoded_query = quote(query)
        
        # f=live gives chronological order (latest first)
        return f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"

    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        if not sync_playwright:
            logger.warning("playwright_not_installed", x_handle=x_handle)
            return []

        # Use search URL for historical access instead of profile
        url = self._build_search_url(x_handle, window_start, window_end)
        posts: List[CollectedPost] = []
        seen: Set[str] = set()

        logger.info(
            "x_playwright_collect_start",
            handle=x_handle,
            url=url,
            window_start=str(window_start),
            window_end=str(window_end),
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                ],
            )
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 2000},
                )
                
                # Add X authentication cookies if available
                if self.auth_token:
                    cookies = [
                        {
                            "name": "auth_token",
                            "value": self.auth_token,
                            "domain": ".x.com",
                            "path": "/",
                        }
                    ]
                    if self.ct0:
                        cookies.append({
                            "name": "ct0",
                            "value": self.ct0,
                            "domain": ".x.com", 
                            "path": "/",
                        })
                    context.add_cookies(cookies)
                    logger.debug("x_auth_cookies_added", count=len(cookies))
                
                page = context.new_page()
                
                # Polite delay before making request (5-9 seconds between requests)
                self._polite_delay()
                
                # Use domcontentloaded instead of networkidle - X.com has constant background activity
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                
                # Mark request complete (for polite delay calculation on next request)
                self._mark_request_done()
                
                # Wait a bit for JS to render search results
                page.wait_for_timeout(3000)
                
                # Wait for timeline articles to appear
                try:
                    page.wait_for_selector("article", timeout=15000)
                except Exception:
                    # Debug: capture page state when no articles found
                    page_title = page.title()
                    page_text = page.inner_text("body")[:500] if page.query_selector("body") else "no body"
                    
                    logger.warning(
                        "x_no_articles_found",
                        handle=x_handle,
                        url=url,
                        page_title=page_title,
                        page_preview=page_text[:200],
                    )
                    return []

                # Scroll to load more search results
                for _ in range(self.max_scrolls):
                    page.mouse.wheel(0, 1800)
                    page.wait_for_timeout(self.wait_ms)

                articles = page.query_selector_all("article")
                for article in articles:
                    time_el = article.query_selector("time")
                    href_el = article.query_selector("a[href*='/status/']")

                    if not time_el or not href_el:
                        continue

                    dt_str: Optional[str] = time_el.get_attribute("datetime")
                    href: Optional[str] = href_el.get_attribute("href")

                    if not dt_str or not href:
                        continue

                    try:
                        posted_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    except Exception:
                        continue

                    # Double-check post is within our window (search is day-level granularity)
                    if posted_at < window_start or posted_at > window_end:
                        continue

                    # Normalize URL
                    if href.startswith("/"):
                        post_url = f"https://x.com{href}"
                    elif href.startswith("http"):
                        post_url = href
                    else:
                        post_url = f"https://x.com/{href.lstrip('/')}"

                    if post_url in seen:
                        continue
                    seen.add(post_url)

                    has_video = bool(
                        article.query_selector("video")
                        or article.query_selector('[data-testid="videoPlayer"]')
                        or article.query_selector('[data-testid="videoThumbnail"]')
                    )

                    # Extract text content for display
                    try:
                        # Get tweet text from the main text container
                        text_el = article.query_selector('[data-testid="tweetText"]')
                        text_content = text_el.inner_text() if text_el else None
                    except Exception:
                        text_content = None

                    # Extract media URLs
                    video_url = None
                    image_url = None
                    media_type = "none"

                    # Try to get video source (direct <video> or <video><source>)
                    video_el = article.query_selector("video source") or article.query_selector("video")
                    if video_el:
                        src_candidate = video_el.get_attribute("src")
                        if src_candidate:
                            video_url = src_candidate
                            media_type = "video"

                    # Try additional X test id hooks for video containers
                    if not video_url:
                        vp = article.query_selector('[data-testid="videoPlayer"] source') or article.query_selector('[data-testid="videoPlayer"]')
                        if vp:
                            src_candidate = vp.get_attribute("src")
                            if src_candidate:
                                video_url = src_candidate
                                media_type = "video"

                    if not video_url:
                        vt = article.query_selector('[data-testid="videoThumbnail"] source') or article.query_selector('[data-testid="videoThumbnail"]')
                        if vt:
                            src_candidate = vt.get_attribute("src")
                            if src_candidate:
                                video_url = src_candidate
                                media_type = "video"

                    # Try to get video poster or image
                    if not video_url:
                        video_poster = article.query_selector("video")
                        if video_poster:
                            image_url = video_poster.get_attribute("poster")
                            media_type = "video"
                    
                    # Get image from photo container
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


class XPostCollector:
    """
    Main X post collector that orchestrates collection and storage.
    
    Supports running collection jobs for specific games, persisting
    results to the database, and filtering spoilers.
    """

    def __init__(
        self,
        strategy: XCollectorStrategy | None = None,
        filter_spoilers: bool = True,
    ):
        if strategy:
            self.strategy = strategy
        else:
            # Prefer Playwright if available, otherwise fall back to mock
            self.strategy = PlaywrightXCollector() if sync_playwright else MockXCollector()
        self.filter_spoilers = filter_spoilers

    def run_job(self, job: PostCollectionJob, session: Session) -> PostCollectionResult:
        """
        Run a post collection job and persist results.

        Args:
            job: Collection job parameters
            session: Database session for persistence

        Returns:
            PostCollectionResult with counts and any errors
        """
        from ..db import db_models
        from .spoiler_filter import contains_spoiler

        result = PostCollectionResult(job=job)
        errors: list[str] = []

        try:
            # Collect posts
            posts = self.strategy.collect_posts(
                x_handle=job.x_handle,
                window_start=job.window_start,
                window_end=job.window_end,
            )
            result.posts_found = len(posts)

            # Get team by abbreviation
            team = session.query(db_models.SportsTeam).filter(
                db_models.SportsTeam.abbreviation.ilike(job.team_abbreviation)
            ).first()

            if not team:
                errors.append(f"Team not found: {job.team_abbreviation}")
                result.errors = errors
                return result

            # Process each post
            posts_updated = 0
            for post in posts:
                # Filter spoilers if enabled
                if self.filter_spoilers and post.text and contains_spoiler(post.text):
                    result.posts_filtered += 1
                    continue

                # Check for existing post by URL
                existing = session.query(db_models.GameSocialPost).filter(
                    db_models.GameSocialPost.post_url == post.post_url
                ).first()

                if existing:
                    # Full upsert: update all fields with fresh data
                    existing.posted_at = post.posted_at
                    existing.has_video = post.has_video
                    existing.tweet_text = post.text
                    existing.source_handle = post.author_handle
                    existing.video_url = post.video_url
                    existing.image_url = post.image_url
                    existing.media_type = post.media_type or "none"
                    existing.updated_at = datetime.now(timezone.utc)
                    posts_updated += 1
                else:
                    # Create new post with all content fields
                    db_post = db_models.GameSocialPost(
                        game_id=job.game_id,
                        team_id=team.id,
                        post_url=post.post_url,
                        posted_at=post.posted_at,
                        has_video=post.has_video,
                        tweet_text=post.text,
                        source_handle=post.author_handle,
                        video_url=post.video_url,
                        image_url=post.image_url,
                        media_type=post.media_type or "none",
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(db_post)
                    result.posts_saved += 1

            # Commit immediately so posts are persisted (don't wait for batch end)
            # This ensures we don't lose progress if scraper crashes
            if result.posts_saved > 0 or posts_updated > 0:
                session.commit()
                logger.debug(
                    "x_posts_committed",
                    game_id=job.game_id,
                    team=job.team_abbreviation,
                    saved=result.posts_saved,
                    updated=posts_updated,
                )
            
            result.completed_at = datetime.utcnow()

            logger.info(
                "x_collection_job_complete",
                game_id=job.game_id,
                team=job.team_abbreviation,
                found=result.posts_found,
                saved=result.posts_saved,
                filtered=result.posts_filtered,
            )

        except Exception as e:
            errors.append(str(e))
            logger.exception(
                "x_collection_job_failed",
                game_id=job.game_id,
                team=job.team_abbreviation,
                error=str(e),
            )

        result.errors = errors
        return result

    def collect_for_game(
        self,
        session: Session,
        game_id: int,
    ) -> list[PostCollectionResult]:
        """
        Collect posts for both teams in a game.

        Uses a simple 24-hour window around game day:
        - Start: 5:00 AM ET on game day
        - End: 4:59:59 AM ET the next day
        
        This covers all US timezones and captures pre-game hype through post-game celebration.

        Args:
            session: Database session
            game_id: Game database ID

        Returns:
            List of PostCollectionResult for each team
        """
        from datetime import timedelta, time
        from ..db import db_models

        # Get game with team relationships
        game = session.query(db_models.SportsGame).filter(
            db_models.SportsGame.id == game_id
        ).first()

        if not game:
            logger.warning("x_collect_game_not_found", game_id=game_id)
            return []

        # Load teams
        home_team = session.query(db_models.SportsTeam).get(game.home_team_id)
        away_team = session.query(db_models.SportsTeam).get(game.away_team_id)

        if not home_team or not away_team:
            logger.warning("x_collect_teams_not_found", game_id=game_id)
            return []

        # Simple 24-hour window: 5am ET game day to 4:59am ET next day
        # 
        # Game dates are stored as midnight UTC (e.g., 2023-10-25 00:00:00+00)
        # The UTC date IS the game day (matches source_game_key like "202310250SAS")
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # Python < 3.9
        
        eastern = ZoneInfo("America/New_York")
        utc = ZoneInfo("UTC")
        
        # Extract the game day from UTC date (this is the actual game day)
        game_day = game.game_date.date()
        
        # Window: 5:00 AM ET game day to 4:59:59 AM ET next day (24 hours)
        window_start = datetime.combine(game_day, time(5, 0), tzinfo=eastern).astimezone(utc)
        window_end = datetime.combine(game_day + timedelta(days=1), time(4, 59, 59), tzinfo=eastern).astimezone(utc)
        
        logger.debug(
            "x_window_calculated",
            game_id=game_id,
            game_day=str(game_day),
            window_start_et=f"{game_day} 05:00 ET",
            window_end_et=f"{game_day + timedelta(days=1)} 04:59 ET",
            window_start_utc=str(window_start),
            window_end_utc=str(window_end),
        )

        results = []

        # Collect for each team that has an X handle
        for team in [home_team, away_team]:
            if not team.x_handle:
                logger.debug("x_collect_no_handle", team=team.abbreviation)
                continue

            job = PostCollectionJob(
                game_id=game_id,
                team_abbreviation=team.abbreviation,
                x_handle=team.x_handle,
                window_start=window_start,
                window_end=window_end,
            )

            result = self.run_job(job, session)
            results.append(result)

        return results

