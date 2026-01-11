"""Database-backed cache for social polling requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from ..utils.datetime_utils import now_utc

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import db_models


@dataclass
class CacheDecision:
    allowed: bool
    reason: str | None = None
    retry_at: datetime | None = None


class SocialRequestCache:
    """Cache decisions for per-account polling and window fetches."""

    def __init__(self, poll_interval_seconds: int, cache_ttl_seconds: int) -> None:
        self.poll_interval = timedelta(seconds=poll_interval_seconds)
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)

    def should_poll(
        self,
        session: Session,
        *,
        platform: str,
        handle: str,
        window_start: datetime,
        window_end: datetime,
        now: datetime | None = None,
    ) -> CacheDecision:
        current = now or now_utc()

        recent_poll = (
            session.query(db_models.SocialAccountPoll)
            .filter(db_models.SocialAccountPoll.platform == platform)
            .filter(db_models.SocialAccountPoll.handle == handle)
            .order_by(desc(db_models.SocialAccountPoll.created_at))
            .first()
        )
        if recent_poll and recent_poll.created_at:
            if recent_poll.rate_limited_until and recent_poll.rate_limited_until > current:
                return CacheDecision(False, reason="rate_limited", retry_at=recent_poll.rate_limited_until)
            if current - recent_poll.created_at < self.poll_interval:
                retry_at = recent_poll.created_at + self.poll_interval
                return CacheDecision(False, reason="poll_interval", retry_at=retry_at)

        cached_window = (
            session.query(db_models.SocialAccountPoll)
            .filter(db_models.SocialAccountPoll.platform == platform)
            .filter(db_models.SocialAccountPoll.handle == handle)
            .filter(db_models.SocialAccountPoll.window_start == window_start)
            .filter(db_models.SocialAccountPoll.window_end == window_end)
            .order_by(desc(db_models.SocialAccountPoll.created_at))
            .first()
        )
        if cached_window and cached_window.created_at:
            if current - cached_window.created_at < self.cache_ttl:
                retry_at = cached_window.created_at + self.cache_ttl
                return CacheDecision(False, reason="cached_window", retry_at=retry_at)

        return CacheDecision(True)

    def record(
        self,
        session: Session,
        *,
        platform: str,
        handle: str,
        window_start: datetime,
        window_end: datetime,
        status: str,
        posts_found: int = 0,
        rate_limited_until: datetime | None = None,
        error_detail: str | None = None,
    ) -> db_models.SocialAccountPoll:
        record = (
            session.query(db_models.SocialAccountPoll)
            .filter(db_models.SocialAccountPoll.platform == platform)
            .filter(db_models.SocialAccountPoll.handle == handle)
            .filter(db_models.SocialAccountPoll.window_start == window_start)
            .filter(db_models.SocialAccountPoll.window_end == window_end)
            .first()
        )

        if record:
            record.status = status
            record.posts_found = posts_found
            record.rate_limited_until = rate_limited_until
            record.error_detail = error_detail
        else:
            record = db_models.SocialAccountPoll(
                platform=platform,
                handle=handle,
                window_start=window_start,
                window_end=window_end,
                status=status,
                posts_found=posts_found,
                rate_limited_until=rate_limited_until,
                error_detail=error_detail,
            )
            session.add(record)
        session.flush()
        return record
