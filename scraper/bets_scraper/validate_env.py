"""Fail-fast environment validation for the scraper/worker service."""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse


ALLOWED_ENVIRONMENTS = {"development", "staging", "production"}


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required and must be set before startup.")
    return value.strip()


def _validate_environment_value(environment: str) -> None:
    if environment not in ALLOWED_ENVIRONMENTS:
        allowed = ", ".join(sorted(ALLOWED_ENVIRONMENTS))
        raise RuntimeError(f"ENVIRONMENT must be one of: {allowed}.")


def _validate_non_local_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    host = parsed.hostname
    if not host:
        raise RuntimeError(f"{name} must be a valid URL (missing hostname).")
    if host in {"localhost", "127.0.0.1"}:
        raise RuntimeError(f"{name} must not point to localhost in production.")


def _validate_database_credentials(value: str) -> None:
    parsed = urlparse(value)
    if parsed.username == "postgres" and parsed.password == "postgres":
        raise RuntimeError("DATABASE_URL must not use default postgres credentials in production.")


def _validate_social_credentials() -> None:
    bearer_token = os.getenv("X_BEARER_TOKEN")
    auth_token = os.getenv("X_AUTH_TOKEN")
    ct0 = os.getenv("X_CT0")
    if bearer_token:
        return
    if auth_token and ct0:
        return
    raise RuntimeError(
        "Production social scraping requires X_BEARER_TOKEN or X_AUTH_TOKEN + X_CT0."
    )


@lru_cache(maxsize=1)
def validate_env() -> None:
    """Validate required environment variables before the worker starts."""
    environment = _require_env("ENVIRONMENT")
    _validate_environment_value(environment)

    database_url = _require_env("DATABASE_URL")
    redis_url = _require_env("REDIS_URL")

    if environment == "production":
        _validate_non_local_url("DATABASE_URL", database_url)
        _validate_database_credentials(database_url)
        _validate_non_local_url("REDIS_URL", redis_url)

        _require_env("ODDS_API_KEY")
        _validate_social_credentials()
