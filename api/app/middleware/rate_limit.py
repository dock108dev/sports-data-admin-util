"""Basic in-memory rate limiting middleware."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque

from fastapi import Request
from starlette.responses import JSONResponse

from app.config import settings


class RateLimitMiddleware:
    """Sliding window limiter based on client IP."""

    def __init__(self, app: Callable) -> None:
        self.app = app
        self._requests: dict[str, Deque[float]] = defaultdict(deque)

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = settings.rate_limit_window_seconds
        limit = settings.rate_limit_requests

        request_times = self._requests[client_ip]
        while request_times and request_times[0] <= now - window:
            request_times.popleft()

        if len(request_times) >= limit:
            response = JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
            await response(scope, receive, send)
            return

        request_times.append(now)
        await self.app(scope, receive, send)
