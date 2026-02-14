"""Internal API client helpers for scraper → API calls."""

from __future__ import annotations


def get_api_headers() -> dict[str, str]:
    """Return headers for internal API calls, including X-API-Key."""
    from .config import settings

    headers: dict[str, str] = {}
    if settings.api_key:
        headers["X-API-Key"] = settings.api_key
    return headers
