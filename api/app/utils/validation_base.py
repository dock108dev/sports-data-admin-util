"""Shared environment validation helpers."""

from __future__ import annotations

import os
from urllib.parse import urlparse

ALLOWED_ENVIRONMENTS = {"development", "staging", "production"}


def require_env(name: str) -> str:
    """Fetch an environment variable or raise RuntimeError if missing."""
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required and must be set before startup.")
    return value.strip()


def validate_environment_value(environment: str) -> None:
    """Ensure ENVIRONMENT is one of the allowed values."""
    if environment not in ALLOWED_ENVIRONMENTS:
        allowed = ", ".join(sorted(ALLOWED_ENVIRONMENTS))
        raise RuntimeError(f"ENVIRONMENT must be one of: {allowed}.")


def validate_non_local_url(name: str, value: str) -> None:
    """Ensure a URL does not point to localhost in production."""
    parsed = urlparse(value)
    host = parsed.hostname
    if not host:
        raise RuntimeError(f"{name} must be a valid URL (missing hostname).")
    if host in {"localhost", "127.0.0.1"}:
        raise RuntimeError(f"{name} must not point to localhost in production.")


def validate_database_credentials(value: str) -> None:
    """Ensure DATABASE_URL does not use default credentials in production."""
    parsed = urlparse(value)
    if parsed.username == "postgres" and parsed.password == "postgres":
        raise RuntimeError("DATABASE_URL must not use default postgres credentials in production.")
