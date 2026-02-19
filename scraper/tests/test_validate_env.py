"""Tests for role-based environment validation (validate_env)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from sports_scraper.validate_env import (
    ALLOWED_SCRAPER_ROLES,
    validate_env,
)


def _prod_base_env() -> dict[str, str]:
    """Minimal env vars that every production worker needs."""
    return {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+psycopg://user:secret@db.prod:5432/app",
        "REDIS_URL": "redis://redis.prod:6379/2",
    }


class TestValidateEnvRoleWorker:
    """SCRAPER_ROLE=worker (default) requires ODDS_API_KEY, not social creds."""

    def test_worker_requires_odds_api_key(self):
        env = _prod_base_env()
        # No ODDS_API_KEY, no SCRAPER_ROLE (defaults to worker)
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            with pytest.raises(RuntimeError, match="ODDS_API_KEY"):
                validate_env()

    def test_worker_passes_with_odds_key(self):
        env = {**_prod_base_env(), "ODDS_API_KEY": "key123"}
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            validate_env()  # should not raise

    def test_worker_does_not_require_social_creds(self):
        env = {**_prod_base_env(), "ODDS_API_KEY": "key123"}
        # No X_AUTH_TOKEN, X_CT0, or X_BEARER_TOKEN
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            validate_env()  # should not raise


class TestValidateEnvRoleBeat:
    """SCRAPER_ROLE=beat requires ODDS_API_KEY, not social creds."""

    def test_beat_requires_odds_api_key(self):
        env = {**_prod_base_env(), "SCRAPER_ROLE": "beat"}
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            with pytest.raises(RuntimeError, match="ODDS_API_KEY"):
                validate_env()

    def test_beat_passes_with_odds_key(self):
        env = {**_prod_base_env(), "SCRAPER_ROLE": "beat", "ODDS_API_KEY": "key123"}
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            validate_env()  # should not raise


class TestValidateEnvRoleSocial:
    """SCRAPER_ROLE=social requires social creds, not ODDS_API_KEY."""

    def test_social_requires_social_creds(self):
        env = {**_prod_base_env(), "SCRAPER_ROLE": "social"}
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            with pytest.raises(RuntimeError, match="X_BEARER_TOKEN or X_AUTH_TOKEN"):
                validate_env()

    def test_social_does_not_require_odds_key(self):
        env = {
            **_prod_base_env(),
            "SCRAPER_ROLE": "social",
            "X_AUTH_TOKEN": "tok",
            "X_CT0": "ct0val",
        }
        # No ODDS_API_KEY
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            validate_env()  # should not raise

    def test_social_accepts_bearer_token(self):
        env = {
            **_prod_base_env(),
            "SCRAPER_ROLE": "social",
            "X_BEARER_TOKEN": "bearer123",
        }
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            validate_env()  # should not raise

    def test_social_accepts_auth_token_plus_ct0(self):
        env = {
            **_prod_base_env(),
            "SCRAPER_ROLE": "social",
            "X_AUTH_TOKEN": "tok",
            "X_CT0": "ct0val",
        }
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            validate_env()  # should not raise


class TestValidateEnvInvalidRole:
    def test_invalid_role_raises(self):
        env = {**_prod_base_env(), "SCRAPER_ROLE": "unknown"}
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            with pytest.raises(RuntimeError, match="SCRAPER_ROLE must be one of"):
                validate_env()


class TestValidateEnvDevelopment:
    """In development mode, role-specific checks are skipped entirely."""

    def test_dev_skips_all_production_checks(self):
        env = {
            "ENVIRONMENT": "development",
            "DATABASE_URL": "postgresql://sports:sports@localhost:5432/sports",
            "REDIS_URL": "redis://localhost:6379/2",
        }
        with patch.dict(os.environ, env, clear=True):
            validate_env.cache_clear()
            validate_env()  # should not raise


class TestAllowedScraperRoles:
    def test_roles_set(self):
        assert {"worker", "beat", "social"} == ALLOWED_SCRAPER_ROLES
