"""Structured request logging middleware."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from urllib.parse import parse_qs

from fastapi import Request


class StructuredLoggingMiddleware:
    """Log request/response details in JSON.

    If the incoming request includes an ``X-Request-ID`` header, that value is
    preserved; otherwise a new UUID is generated.  The ID is included in the
    structured log entry and returned in the response headers so callers can
    correlate frontend actions with backend logs.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app
        self.logger = logging.getLogger("api.access")
        self._sensitive_query_keys = {
            "token",
            "access_token",
            "refresh_token",
            "api_key",
            "apikey",
            "key",
            "secret",
            "signature",
            "auth",
            "authorization",
            "password",
        }

    def _truncate_value(self, value: str | None, limit: int = 200) -> str | None:
        if value is None:
            return None
        if len(value) <= limit:
            return value
        return f"{value[:limit]}..."

    def _redact_query_params(self, raw_query: str) -> dict[str, list[str] | str]:
        if not raw_query:
            return {}
        parsed = parse_qs(raw_query, keep_blank_values=True)
        redacted: dict[str, list[str] | str] = {}
        for key, values in parsed.items():
            if key.lower() in self._sensitive_query_keys:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = [self._truncate_value(value, 100) or "" for value in values]
        return redacted

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        request = Request(scope, receive=receive)

        # Resolve or generate a request ID for correlation
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                # Inject X-Request-ID into response headers
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers

                elapsed_ms = (time.perf_counter() - start) * 1000
                log_payload = {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query_params": self._redact_query_params(request.url.query),
                    "status_code": message["status"],
                    "client_ip": request.client.host if request.client else None,
                    "duration_ms": round(elapsed_ms, 2),
                    "user_agent": self._truncate_value(request.headers.get("user-agent"), 200),
                }
                self.logger.info("http_request", extra=log_payload)
            await send(message)

        await self.app(scope, receive, send_wrapper)
