"""
X (Twitter) post collector for game timelines.

This module provides infrastructure to collect posts from team X accounts
through pluggable strategies. The orchestrator handles persistence and
reveal filtering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ..logging import logger
from ..config import settings
from ..utils.datetime_utils import utcnow
from .cache import SocialRequestCache
from .collector_base import XCollectorStrategy
from .exceptions import SocialRateLimitError
from .models import CollectedPost, PostCollectionJob, PostCollectionResult
from .playwright_collector import PlaywrightXCollector, playwright_available
from .rate_limit import PlatformRateLimiter
from .registry import fetch_team_accounts
from .reveal_filter import classify_reveal_risk
from .utils import extract_x_post_id

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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

        import httpx

        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        base_url = "https://api.x.com/2"
        handle_clean = x_handle.lstrip("@")

        with httpx.Client(timeout=15) as client:
            user_resp = client.get(
                f"{base_url}/users/by/username/{handle_clean}",
                headers=headers,
                params={"user.fields": "id"},
            )
            if user_resp.status_code == 429:
                retry_after = int(user_resp.headers.get("retry-after", "60"))
                raise SocialRateLimitError("X API rate limit hit", retry_after_seconds=retry_after)
            user_resp.raise_for_status()
            user_data = user_resp.json().get("data")
            if not user_data or "id" not in user_data:
                logger.warning("x_api_user_not_found", handle=handle_clean)
                return []

            user_id = user_data["id"]
            posts: list[CollectedPost] = []
            next_token: str | None = None

            while True:
                params = {
                    "start_time": window_start.isoformat(),
                    "end_time": window_end.isoformat(),
                    "max_results": 100,
                    "exclude": "retweets",
                    "tweet.fields": "created_at",
                    "expansions": "attachments.media_keys",
                    "media.fields": "type,url,preview_image_url",
                }
                if next_token:
                    params["pagination_token"] = next_token

                resp = client.get(
                    f"{base_url}/users/{user_id}/tweets",
                    headers=headers,
                    params=params,
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", "60"))
                    raise SocialRateLimitError("X API rate limit hit", retry_after_seconds=retry_after)
                resp.raise_for_status()
                payload = resp.json()
                tweets = payload.get("data", [])
                media_map = {
                    item["media_key"]: item
                    for item in payload.get("includes", {}).get("media", [])
                    if "media_key" in item
                }

                for tweet in tweets:
                    tweet_id = str(tweet.get("id"))
                    created_at = tweet.get("created_at")
                    if not tweet_id or not created_at:
                        continue
                    posted_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    post_url = f"https://x.com/{handle_clean}/status/{tweet_id}"

                    media_type = "none"
                    has_video = False
                    video_url = None
                    image_url = None
                    media_keys = tweet.get("attachments", {}).get("media_keys", [])
                    for key in media_keys:
                        media = media_map.get(key, {})
                        media_kind = media.get("type")
                        if media_kind == "video":
                            has_video = True
                            media_type = "video"
                            video_url = media.get("url") or video_url
                            image_url = media.get("preview_image_url") or image_url
                        elif media_kind == "photo":
                            media_type = "image"
                            image_url = media.get("url") or image_url

                    posts.append(
                        CollectedPost(
                            post_url=post_url,
                            external_post_id=tweet_id,
                            posted_at=posted_at,
                            has_video=has_video,
                            text=tweet.get("text"),
                            author_handle=handle_clean,
                            video_url=video_url,
                            image_url=image_url,
                            media_type=media_type,
                        )
                    )

                next_token = payload.get("meta", {}).get("next_token")
                if not next_token:
                    break

        return posts


class XPostCollector:
    """
    Main X post collector that orchestrates collection and storage.

    Supports running collection jobs for specific games, persisting
    results to the database, and filtering reveal-sensitive content.
    """

    def __init__(
        self,
        strategy: XCollectorStrategy | None = None,
        filter_reveals: bool = True,
    ):
        if strategy:
            self.strategy = strategy
        else:
            self.strategy = PlaywrightXCollector() if playwright_available() else MockXCollector()
        self.filter_reveals = filter_reveals
        self.platform = "x"
        social_config = settings.social_config
        self.rate_limiter = PlatformRateLimiter(
            max_requests=social_config.platform_rate_limit_max_requests,
            window_seconds=social_config.platform_rate_limit_window_seconds,
        )
        self.request_cache = SocialRequestCache(
            poll_interval_seconds=social_config.team_poll_interval_seconds,
            cache_ttl_seconds=social_config.request_cache_ttl_seconds,
        )

    def _normalize_posted_at(self, posted_at: datetime) -> datetime:
        if posted_at.tzinfo is None:
            return posted_at.replace(tzinfo=timezone.utc)
        return posted_at.astimezone(timezone.utc)

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
        result = PostCollectionResult(job=job)
        errors: list[str] = []

        try:
            window_decision = self.request_cache.should_poll(
                session,
                platform=self.platform,
                handle=job.x_handle,
                window_start=job.window_start,
                window_end=job.window_end,
            )
            if not window_decision.allowed:
                logger.info(
                    "x_collection_skipped",
                    game_id=job.game_id,
                    team=job.team_abbreviation,
                    handle=job.x_handle,
                    reason=window_decision.reason,
                    retry_at=str(window_decision.retry_at) if window_decision.retry_at else None,
                )
                return result

            rate_decision = self.rate_limiter.allow()
            if not rate_decision.allowed:
                retry_after = rate_decision.retry_after or settings.social_config.platform_rate_limit_window_seconds
                logger.warning(
                    "x_collection_rate_limited",
                    game_id=job.game_id,
                    team=job.team_abbreviation,
                    handle=job.x_handle,
                    reason=rate_decision.reason,
                    retry_after=retry_after,
                )
                self.request_cache.record(
                    session,
                    platform=self.platform,
                    handle=job.x_handle,
                    window_start=job.window_start,
                    window_end=job.window_end,
                    status="rate_limited",
                    rate_limited_until=utcnow()
                    + timedelta(seconds=retry_after),
                )
                session.commit()
                return result

            logger.info(
                "x_account_poll_start",
                game_id=job.game_id,
                team=job.team_abbreviation,
                handle=job.x_handle,
                window_start=str(job.window_start),
                window_end=str(job.window_end),
            )
            posts = self.strategy.collect_posts(
                x_handle=job.x_handle,
                window_start=job.window_start,
                window_end=job.window_end,
            )
            self.rate_limiter.record()
            result.posts_found = len(posts)

            team = session.query(db_models.SportsTeam).filter(
                db_models.SportsTeam.abbreviation.ilike(job.team_abbreviation)
            ).first()

            if not team:
                errors.append(f"Team not found: {job.team_abbreviation}")
                result.errors = errors
                return result

            posts_updated = 0
            posts_skipped = 0
            for post in posts:
                normalized_posted_at = self._normalize_posted_at(post.posted_at)
                # Timestamp attachment rule: only link posts that fall inside the game window.
                if normalized_posted_at < job.window_start or normalized_posted_at > job.window_end:
                    posts_skipped += 1
                    logger.debug(
                        "x_post_outside_window",
                        post_url=post.post_url,
                        posted_at=str(normalized_posted_at),
                        window_start=str(job.window_start),
                        window_end=str(job.window_end),
                    )
                    continue

                reveal_result = classify_reveal_risk(post.text)
                # Reveal logic: post-game content stays attached but is always flagged.
                if job.game_end and normalized_posted_at > job.game_end:
                    reveal_result = reveal_result._replace(reveal_risk=True, reason="postgame")

                external_id = post.external_post_id or extract_x_post_id(post.post_url)
                existing = None
                if external_id:
                    existing = (
                        session.query(db_models.GameSocialPost)
                        .filter(db_models.GameSocialPost.platform == self.platform)
                        .filter(db_models.GameSocialPost.external_post_id == external_id)
                        .first()
                    )
                if not existing:
                    existing = session.query(db_models.GameSocialPost).filter(
                        db_models.GameSocialPost.post_url == post.post_url
                    ).first()

                if reveal_result.reveal_risk:
                    result.posts_flagged_reveal += 1

                if existing:
                    existing.posted_at = normalized_posted_at
                    existing.has_video = post.has_video
                    existing.tweet_text = post.text
                    existing.source_handle = post.author_handle
                    existing.video_url = post.video_url
                    existing.image_url = post.image_url
                    existing.media_type = post.media_type or "none"
                    existing.platform = self.platform
                    existing.external_post_id = external_id
                    existing.reveal_risk = reveal_result.reveal_risk
                    existing.reveal_reason = reveal_result.reason
                    existing.updated_at = datetime.now(timezone.utc)
                    posts_updated += 1
                else:
                    db_post = db_models.GameSocialPost(
                        game_id=job.game_id,
                        team_id=team.id,
                        post_url=post.post_url,
                        platform=self.platform,
                        external_post_id=external_id,
                        posted_at=normalized_posted_at,
                        has_video=post.has_video,
                        tweet_text=post.text,
                        source_handle=post.author_handle,
                        video_url=post.video_url,
                        image_url=post.image_url,
                        media_type=post.media_type or "none",
                        reveal_risk=reveal_result.reveal_risk,
                        reveal_reason=reveal_result.reason,
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(db_post)
                    result.posts_saved += 1

            self.request_cache.record(
                session,
                platform=self.platform,
                handle=job.x_handle,
                window_start=job.window_start,
                window_end=job.window_end,
                status="success",
                posts_found=result.posts_found,
            )
            if result.posts_saved > 0 or posts_updated > 0:
                game = session.get(db_models.SportsGame, job.game_id)
                if game:
                    game.last_social_at = utcnow()
                session.commit()
                logger.debug(
                    "x_posts_committed",
                    game_id=job.game_id,
                    team=job.team_abbreviation,
                    saved=result.posts_saved,
                    updated=posts_updated,
                )
            else:
                session.commit()

            result.completed_at = utcnow()

            logger.info(
                "x_collection_job_complete",
                game_id=job.game_id,
                team=job.team_abbreviation,
                found=result.posts_found,
                saved=result.posts_saved,
                reveals=result.posts_flagged_reveal,
                skipped=posts_skipped,
            )

        except SocialRateLimitError as e:
            errors.append(str(e))
            retry_after = e.retry_after_seconds or settings.social_config.platform_rate_limit_window_seconds
            self.rate_limiter.backoff(retry_after)
            self.request_cache.record(
                session,
                platform=self.platform,
                handle=job.x_handle,
                window_start=job.window_start,
                window_end=job.window_end,
                status="rate_limited",
                rate_limited_until=utcnow() + timedelta(seconds=retry_after),
                error_detail=str(e),
            )
            session.commit()
            logger.warning(
                "x_collection_rate_limit_error",
                game_id=job.game_id,
                team=job.team_abbreviation,
                handle=job.x_handle,
                retry_after=retry_after,
            )
        except Exception as e:
            errors.append(str(e))
            self.request_cache.record(
                session,
                platform=self.platform,
                handle=job.x_handle,
                window_start=job.window_start,
                window_end=job.window_end,
                status="error",
                error_detail=str(e),
            )
            session.commit()
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
        from datetime import time
        from ..db import db_models
        from sqlalchemy import func

        game = session.query(db_models.SportsGame).filter(db_models.SportsGame.id == game_id).first()

        if not game:
            logger.warning("x_collect_game_not_found", game_id=game_id)
            return []

        home_team = session.query(db_models.SportsTeam).get(game.home_team_id)
        away_team = session.query(db_models.SportsTeam).get(game.away_team_id)

        if not home_team or not away_team:
            logger.warning("x_collect_teams_not_found", game_id=game_id)
            return []

        if not game.game_date:
            logger.warning("x_collect_missing_start_time", game_id=game_id)
            return []

        plays_count = session.query(func.count(db_models.SportsGamePlay.id)).filter(
            db_models.SportsGamePlay.game_id == game.id
        ).scalar()
        if not plays_count:
            logger.warning("x_collect_missing_pbp", game_id=game_id)
            return []

        now = utcnow()
        pregame_window = timedelta(minutes=settings.social_config.pregame_window_minutes)
        postgame_window = timedelta(minutes=settings.social_config.postgame_window_minutes)
        window_start = game.game_date - pregame_window
        window_end = (game.end_time + postgame_window) if game.end_time else now

        logger.debug(
            "x_window_calculated",
            game_id=game_id,
            window_start_utc=str(window_start),
            window_end_utc=str(window_end),
        )

        results = []

        team_ids = [team.id for team in [home_team, away_team] if team]
        account_map = fetch_team_accounts(session, team_ids=team_ids, platform=self.platform)

        for team in [home_team, away_team]:
            if not team:
                continue
            account_entry = account_map.get(team.id)
            handle = account_entry.handle if account_entry else team.x_handle
            if not handle:
                logger.debug("x_collect_no_handle", team=team.abbreviation)
                continue

            job = PostCollectionJob(
                game_id=game_id,
                team_abbreviation=team.abbreviation,
                x_handle=handle,
                window_start=window_start,
                window_end=window_end,
                game_start=game.game_date,
                game_end=game.end_time,
            )

            result = self.run_job(job, session)
            results.append(result)

        if results:
            reveal_total = sum(r.posts_flagged_reveal for r in results)
            saved_total = sum(r.posts_saved for r in results)
            logger.info(
                "x_reveal_summary",
                game_id=game_id,
                reveals=reveal_total,
                saved=saved_total,
            )

        return results
