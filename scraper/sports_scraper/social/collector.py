"""
X (Twitter) post collector for game timelines.

This module provides infrastructure to collect posts from team X accounts
through pluggable strategies. The orchestrator handles persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ..logging import logger
from ..config import settings
from ..utils.datetime_utils import now_utc
from .cache import SocialRequestCache
from .exceptions import SocialRateLimitError
from .models import PostCollectionJob, PostCollectionResult
from .playwright_collector import PlaywrightXCollector, playwright_available
from .rate_limit import PlatformRateLimiter
from .registry import fetch_team_accounts
from .utils import extract_x_post_id

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _check_and_queue_timeline_regen(session: "Session", game_id: int) -> bool:
    """
    Check if game has an existing timeline artifact and queue regeneration if so.
    
    Returns True if regeneration was queued, False otherwise.
    """
    from ..db import db_models
    
    # Check if timeline artifact exists for this game
    artifact = (
        session.query(db_models.SportsGameTimelineArtifact)
        .filter(db_models.SportsGameTimelineArtifact.game_id == game_id)
        .first()
    )
    
    if artifact:
        # Queue timeline regeneration via Celery task
        try:
            from ..jobs.tasks import regenerate_timeline_task
            regenerate_timeline_task.apply_async(
                kwargs={"game_id": game_id, "reason": "social_backfill"},
                countdown=60,  # Wait 60 seconds before regenerating
            )
            logger.info(
                "timeline_regen_queued",
                game_id=game_id,
                reason="social_backfill",
            )
            return True
        except Exception as exc:
            logger.warning(
                "timeline_regen_queue_failed",
                game_id=game_id,
                error=str(exc),
            )
    return False


class XPostCollector:
    """
    Main X post collector that orchestrates collection and storage.

    Supports running collection jobs for specific games and persisting
    results to the database.
    """

    def __init__(
        self,
        strategy: PlaywrightXCollector | None = None,
    ):
        if strategy:
            self.strategy = strategy
        elif playwright_available():
            self.strategy = PlaywrightXCollector()
        else:
            raise RuntimeError("Playwright is required for social collection but not installed")
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
                is_backfill=job.is_backfill,
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
                    rate_limited_until=now_utc()
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
            for post in posts:
                normalized_posted_at = self._normalize_posted_at(post.posted_at)

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
                    existing.updated_at = now_utc()
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
                        updated_at=now_utc(),
                    )
                    session.add(db_post)
                    result.posts_saved += 1

            # Only cache as "success" if we found posts - 0 results might be
            # a transient failure (page didn't load, rate limited, etc.)
            # "empty" status allows retry on next run
            cache_status = "success" if result.posts_found > 0 else "empty"
            self.request_cache.record(
                session,
                platform=self.platform,
                handle=job.x_handle,
                window_start=job.window_start,
                window_end=job.window_end,
                status=cache_status,
                posts_found=result.posts_found,
            )
            if result.posts_saved > 0 or posts_updated > 0:
                game = session.get(db_models.SportsGame, job.game_id)
                if game:
                    game.last_social_at = now_utc()
                session.commit()
                logger.debug(
                    "x_posts_committed",
                    game_id=job.game_id,
                    team=job.team_abbreviation,
                    saved=result.posts_saved,
                    updated=posts_updated,
                )
                # Queue timeline regeneration if game already has a timeline artifact
                _check_and_queue_timeline_regen(session, job.game_id)
            else:
                session.commit()

            result.completed_at = now_utc()

            logger.info(
                "x_collection_job_complete",
                game_id=job.game_id,
                team=job.team_abbreviation,
                found=result.posts_found,
                saved=result.posts_saved,
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
                rate_limited_until=now_utc() + timedelta(seconds=retry_after),
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
        is_backfill: bool = False,
    ) -> list[PostCollectionResult]:
        """
        Collect posts for both teams in a game.

        Window calculation:
        - Uses tip_time if available (actual scheduled start from Odds API/Live Feed)
        - Falls back to game_date + 19h offset if only midnight date available
        - Window: [tip_time - pregame_minutes] to [tip_time + 3h game + postgame_minutes]
        - Default pregame/postgame: 180 minutes (3 hours) each

        Args:
            session: Database session
            game_id: Game database ID

        Returns:
            List of PostCollectionResult for each team
        """
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

        # Use tip_time if available (actual scheduled start), otherwise fall back to game_date
        if game.tip_time:
            game_start_utc = game.tip_time.replace(tzinfo=timezone.utc) if game.tip_time.tzinfo is None else game.tip_time
        else:
            game_start_utc = game.game_date.replace(tzinfo=timezone.utc) if game.game_date.tzinfo is None else game.game_date
            # Detect if we only have a date (midnight) instead of actual tip time
            # If so, assume 7 PM ET = midnight UTC + 19 hours
            if game_start_utc.hour == 0 and game_start_utc.minute == 0:
                game_start_utc = game_start_utc + timedelta(hours=19)
                logger.debug(
                    "x_using_estimated_tip_time",
                    game_id=game_id,
                    estimated_start=str(game_start_utc),
                )
        
        # Use pregame/postgame windows from config (default: 3 hours each)
        pregame_minutes = settings.social_config.pregame_window_minutes
        postgame_minutes = settings.social_config.postgame_window_minutes
        
        # Window: pregame_minutes before game start to ~3h game duration + postgame buffer
        window_start = game_start_utc - timedelta(minutes=pregame_minutes)
        # Don't trust end_time (it's often set to scrape time, not actual end)
        # Estimate 3 hours for game duration + postgame buffer
        window_end = game_start_utc + timedelta(hours=3) + timedelta(minutes=postgame_minutes)

        logger.debug(
            "x_game_window_calculated",
            game_id=game_id,
            game_start=str(game_start_utc),
            pregame_minutes=pregame_minutes,
            postgame_minutes=postgame_minutes,
            window_start=str(window_start),
            window_end=str(window_end),
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

            # Estimate game_end from tip_time + ~2.5h if not set
            game_end = game.end_time
            if game_end is None and game.tip_time:
                game_end = game.tip_time + timedelta(hours=2, minutes=30)
            elif game_end is None:
                game_end = game_start_utc + timedelta(hours=2, minutes=30)

            job = PostCollectionJob(
                game_id=game_id,
                team_abbreviation=team.abbreviation,
                x_handle=handle,
                window_start=window_start,
                window_end=window_end,
                game_start=game_start_utc,  # Use calculated tip time
                game_end=game_end,
                is_backfill=is_backfill,
            )

            result = self.run_job(job, session)
            results.append(result)

        if results:
            saved_total = sum(r.posts_saved for r in results)
            logger.info(
                "x_collection_summary",
                game_id=game_id,
                saved=saved_total,
            )

        return results
