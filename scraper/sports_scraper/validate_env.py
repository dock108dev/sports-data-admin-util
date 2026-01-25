"""Fail-fast environment validation for the scraper/worker service."""

from __future__ import annotations

import os
from functools import lru_cache

from app.utils.validation_base import (
    require_env,
    validate_database_credentials,
    validate_environment_value,
    validate_non_local_url,
)


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
    environment = require_env("ENVIRONMENT")
    validate_environment_value(environment)

    database_url = require_env("DATABASE_URL")
    redis_url = require_env("REDIS_URL")

    if environment == "production":
        validate_non_local_url("DATABASE_URL", database_url)
        validate_database_credentials(database_url)
        validate_non_local_url("REDIS_URL", redis_url)

        require_env("ODDS_API_KEY")
        _validate_social_credentials()
