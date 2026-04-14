"""Data freshness computation for game API responses.

Computes staleness state from ingestion timestamps and game status,
with configurable thresholds per game state category.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .game_status import FINAL_STATUSES, LIVE_STATUSES, PREGAME_STATUSES


class StalenessState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    VERY_STALE = "very_stale"


class _Thresholds(BaseModel):
    stale_seconds: int
    very_stale_seconds: int


class FreshnessConfig(BaseSettings):
    """Config-driven staleness thresholds per game state category."""

    model_config = SettingsConfigDict(env_prefix="FRESHNESS_", extra="ignore")

    live_stale_seconds: int = Field(default=60, alias="FRESHNESS_LIVE_STALE_SECONDS")
    live_very_stale_seconds: int = Field(default=300, alias="FRESHNESS_LIVE_VERY_STALE_SECONDS")
    pregame_stale_seconds: int = Field(default=600, alias="FRESHNESS_PREGAME_STALE_SECONDS")
    pregame_very_stale_seconds: int = Field(default=1800, alias="FRESHNESS_PREGAME_VERY_STALE_SECONDS")
    default_source_delay_seconds: int = Field(default=15, alias="FRESHNESS_DEFAULT_SOURCE_DELAY_SECONDS")

    def thresholds_for_status(self, status: str | None) -> _Thresholds | None:
        """Return thresholds for a game status, or None for FINAL games."""
        if not status:
            return _Thresholds(
                stale_seconds=self.pregame_stale_seconds,
                very_stale_seconds=self.pregame_very_stale_seconds,
            )
        s = status.lower().strip()
        if s in FINAL_STATUSES:
            return None
        if s in LIVE_STATUSES:
            return _Thresholds(
                stale_seconds=self.live_stale_seconds,
                very_stale_seconds=self.live_very_stale_seconds,
            )
        if s in PREGAME_STATUSES:
            return _Thresholds(
                stale_seconds=self.pregame_stale_seconds,
                very_stale_seconds=self.pregame_very_stale_seconds,
            )
        return _Thresholds(
            stale_seconds=self.pregame_stale_seconds,
            very_stale_seconds=self.pregame_very_stale_seconds,
        )


_config: FreshnessConfig | None = None


def get_freshness_config() -> FreshnessConfig:
    global _config
    if _config is None:
        _config = FreshnessConfig()
    return _config


def compute_staleness_state(
    status: str | None,
    data_updated_at: datetime | None,
    now: datetime | None = None,
) -> StalenessState:
    """Compute staleness state for a game based on its status and last update time.

    FINAL games are always fresh. For other states, staleness is determined
    by comparing the age of data_updated_at against config thresholds.
    """
    config = get_freshness_config()
    thresholds = config.thresholds_for_status(status)

    if thresholds is None:
        return StalenessState.FRESH

    if data_updated_at is None:
        return StalenessState.VERY_STALE

    if now is None:
        now = datetime.now(timezone.utc)

    if data_updated_at.tzinfo is None:
        data_updated_at = data_updated_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_seconds = (now - data_updated_at).total_seconds()

    if age_seconds > thresholds.very_stale_seconds:
        return StalenessState.VERY_STALE
    if age_seconds > thresholds.stale_seconds:
        return StalenessState.STALE
    return StalenessState.FRESH


def get_data_updated_at(
    last_ingested_at: datetime | None,
    last_scraped_at: datetime | None,
) -> datetime | None:
    """Pick the most recent data update timestamp from available sources."""
    candidates = [t for t in (last_ingested_at, last_scraped_at) if t is not None]
    return max(candidates) if candidates else None


def get_source_delay_seconds() -> int:
    """Return the configured default source delay."""
    return get_freshness_config().default_source_delay_seconds
