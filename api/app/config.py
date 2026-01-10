"""Configuration for the sports-data-admin API."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.validate_env import validate_env


class Settings(BaseSettings):
    """Environment-driven settings with sensible defaults for local/Hetzner."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        env_file_encoding="utf-8",
        extra="allow",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/sports",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/2", alias="REDIS_URL")
    celery_broker_url: str | None = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")
    celery_default_queue: str = Field(default="bets-scraper", alias="CELERY_DEFAULT_QUEUE")
    sql_echo: bool = Field(default=False, alias="SQL_ECHO")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    allowed_cors_origins_raw: str | None = Field(default=None, alias="ALLOWED_CORS_ORIGINS")
    rate_limit_requests: int = Field(default=120, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Allow local dev ports for the web UI."""
        if self.allowed_cors_origins_raw:
            return [origin.strip() for origin in self.allowed_cors_origins_raw.split(",") if origin.strip()]
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:3002",
            "http://127.0.0.1:3002",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or self.celery_broker

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "Settings":
        if self.environment in {"production", "staging"}:
            if not self.allowed_cors_origins_raw:
                raise ValueError("ALLOWED_CORS_ORIGINS must be set for production or staging.")
            if any("localhost" in origin or "127.0.0.1" in origin for origin in self.allowed_cors_origins):
                raise ValueError("ALLOWED_CORS_ORIGINS must not include localhost in production or staging.")
        if self.rate_limit_requests <= 0 or self.rate_limit_window_seconds <= 0:
            raise ValueError("Rate limit settings must be positive integers.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    validate_env()
    return Settings()


settings = get_settings()
