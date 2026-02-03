"""API key authentication dependency."""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.config import settings

logger = logging.getLogger(__name__)

# Header name for API key
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Depends(API_KEY_HEADER),
) -> str:
    """Validate API key from request header.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        request: The incoming request (for logging context).
        api_key: The API key from the X-API-Key header.

    Returns:
        The validated API key.

    Raises:
        HTTPException: 401 if key is missing or invalid.
    """
    if not settings.api_key:
        # If no API key is configured, allow all requests (dev mode)
        # This should never happen in production due to config validation
        logger.warning("API_KEY not configured - allowing unauthenticated request")
        return ""

    if not api_key:
        logger.warning(
            "Missing API key",
            extra={
                "client_ip": request.client.host if request.client else "unknown",
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(api_key, settings.api_key):
        logger.warning(
            "Invalid API key attempt",
            extra={
                "client_ip": request.client.host if request.client else "unknown",
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key
