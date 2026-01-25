"""Rate limiting helpers for social ingestion."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from ..utils.datetime_utils import now_utc

from ..logging import logger


@dataclass
class RateLimitDecision:
    allowed: bool
    reason: str | None = None
    retry_after: int | None = None


class PlatformRateLimiter:
    """In-memory rate limiter per platform window."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self._requests: deque[datetime] = deque()
        self._blocked_until: datetime | None = None

    def allow(self, now: datetime | None = None) -> RateLimitDecision:
        current = now or now_utc()
        if self._blocked_until and current < self._blocked_until:
            retry_after = int((self._blocked_until - current).total_seconds())
            return RateLimitDecision(False, reason="backoff", retry_after=retry_after)

        cutoff = current - self.window
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()

        if len(self._requests) >= self.max_requests:
            return RateLimitDecision(False, reason="platform_quota")

        return RateLimitDecision(True)

    def record(self, now: datetime | None = None) -> None:
        current = now or now_utc()
        self._requests.append(current)

    def backoff(self, retry_after_seconds: int) -> None:
        current = now_utc()
        self._blocked_until = current + timedelta(seconds=retry_after_seconds)
        logger.warning(
            "social_rate_limited",
            retry_after_seconds=retry_after_seconds,
            blocked_until=str(self._blocked_until),
        )
