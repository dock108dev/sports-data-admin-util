"""Structured request logging middleware."""

from __future__ import annotations

import json
import logging
import time
from typing import Callable

from fastapi import Request, Response


class StructuredLoggingMiddleware:
    """Log request/response details in JSON."""

    def __init__(self, app: Callable) -> None:
        self.app = app
        self.logger = logging.getLogger("api.access")

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        request = Request(scope, receive=receive)

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                elapsed_ms = (time.perf_counter() - start) * 1000
                log_payload = {
                    "method": request.method,
                    "path": request.url.path,
                    "query": request.url.query,
                    "status_code": message["status"],
                    "client_ip": request.client.host if request.client else None,
                    "duration_ms": round(elapsed_ms, 2),
                    "user_agent": request.headers.get("user-agent"),
                }
                self.logger.info(json.dumps(log_payload))
            await send(message)

        await self.app(scope, receive, send_wrapper)
