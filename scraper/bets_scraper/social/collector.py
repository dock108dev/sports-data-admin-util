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
from datetime import datetime
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
    """

    def __init__(
        self,
        max_scrolls: int = 3,
        wait_ms: int = 800,
        timeout_ms: int = 30000,
    ):
        self.max_scrolls = max_scrolls
        self.wait_ms = wait_ms
        self.timeout_ms = timeout_ms

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        if not sync_playwright:
            logger.warning("playwright_not_installed", x_handle=x_handle)
            return []

        url = f"https://x.com/{x_handle.lstrip('@')}"
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
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)

                # Light scrolling to load recent tweets
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
                        or article.query_selector('[data-testid=\"videoPlayer\"]')
                        or article.query_selector('[data-testid=\"videoThumbnail\"]')
                    )

                    # Capture text for spoiler filtering, but do not persist downstream
                    try:
                        text_content = article.inner_text()
                    except Exception:
                        text_content = None

                    posts.append(
                        CollectedPost(
                            post_url=post_url,
                            posted_at=posted_at,
                            has_video=has_video,
                            text=text_content,
                            author_handle=x_handle.lstrip("@"),
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
            for post in posts:
                # Filter spoilers if enabled
                if self.filter_spoilers and post.text and contains_spoiler(post.text):
                    result.posts_filtered += 1
                    continue

                # Check for duplicate
                existing = session.query(db_models.GameSocialPost).filter(
                    db_models.GameSocialPost.post_url == post.post_url
                ).first()

                if existing:
                    continue

                # Create new post
                db_post = db_models.GameSocialPost(
                    game_id=job.game_id,
                    team_id=team.id,
                    post_url=post.post_url,
                    posted_at=post.posted_at,
                    has_video=post.has_video,
                )
                session.add(db_post)
                result.posts_saved += 1

            session.flush()
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
        pre_game_hours: int = 2,
        post_game_hours: int = 1,
    ) -> list[PostCollectionResult]:
        """
        Collect posts for both teams in a game.

        Args:
            session: Database session
            game_id: Game database ID
            pre_game_hours: Hours before game to start collecting
            post_game_hours: Hours after game to stop collecting

        Returns:
            List of PostCollectionResult for each team
        """
        from datetime import timedelta
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

        # Calculate window
        window_start = game.game_date - timedelta(hours=pre_game_hours)
        window_end = game.game_date + timedelta(hours=post_game_hours)

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

