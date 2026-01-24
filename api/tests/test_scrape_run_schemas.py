"""Tests for scrape run schema validation.

These tests ensure the schema properly handles date ranges for different use cases,
including future dates for odds fetching.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

# Set required env vars before imports
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from app.routers.sports.schemas import ScrapeRunConfig


class TestScrapeRunConfigDateValidation:
    """Tests for ScrapeRunConfig end_date validation."""

    def test_end_date_none_defaults_to_today(self) -> None:
        """When end_date is None, it should default to today."""
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=date.today() - timedelta(days=3),
            end_date=None,
        )
        assert config.end_date == date.today()

    def test_end_date_today_unchanged(self) -> None:
        """Today's date should be unchanged."""
        today = date.today()
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=today - timedelta(days=1),
            end_date=today,
        )
        assert config.end_date == today

    def test_end_date_past_unchanged(self) -> None:
        """Past dates should be unchanged."""
        past = date.today() - timedelta(days=5)
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=past - timedelta(days=2),
            end_date=past,
        )
        assert config.end_date == past

    def test_end_date_near_future_allowed(self) -> None:
        """Dates up to 7 days in future should be allowed for odds fetching."""
        today = date.today()
        future_2_days = today + timedelta(days=2)
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=today,
            end_date=future_2_days,
        )
        assert config.end_date == future_2_days

    def test_end_date_7_days_future_allowed(self) -> None:
        """Exactly 7 days in future should be allowed."""
        today = date.today()
        future_7_days = today + timedelta(days=7)
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=today,
            end_date=future_7_days,
        )
        assert config.end_date == future_7_days

    def test_end_date_beyond_7_days_capped(self) -> None:
        """Dates more than 7 days in future should be capped."""
        today = date.today()
        future_14_days = today + timedelta(days=14)
        max_future = today + timedelta(days=7)
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=today,
            end_date=future_14_days,
        )
        assert config.end_date == max_future


class TestScrapeRunConfigOddsOnly:
    """Tests for odds-only scrape run configuration."""

    def test_odds_only_config(self) -> None:
        """Odds-only config should work correctly."""
        today = date.today()
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=today - timedelta(days=4),
            end_date=today + timedelta(days=2),
            odds=True,
            boxscores=False,
            pbp=False,
            social=False,
        )
        assert config.odds is True
        assert config.boxscores is False
        assert config.pbp is False
        assert config.social is False
        # Future date should be preserved
        assert config.end_date == today + timedelta(days=2)

    def test_worker_payload_includes_dates(self) -> None:
        """Worker payload should include properly formatted dates."""
        today = date.today()
        start = today - timedelta(days=4)
        end = today + timedelta(days=2)
        config = ScrapeRunConfig(
            league_code="NHL",
            start_date=start,
            end_date=end,
            odds=True,
            boxscores=False,
        )
        payload = config.to_worker_payload()

        assert payload["league_code"] == "NHL"
        assert payload["start_date"] == start.isoformat()
        assert payload["end_date"] == end.isoformat()
        assert payload["odds"] is True
        assert payload["boxscores"] is False


class TestScrapeRunConfigLeagueCode:
    """Tests for league code handling."""

    def test_nhl_league_code(self) -> None:
        """NHL league code should be accepted."""
        config = ScrapeRunConfig(league_code="NHL")
        assert config.league_code == "NHL"

    def test_nba_league_code(self) -> None:
        """NBA league code should be accepted."""
        config = ScrapeRunConfig(league_code="NBA")
        assert config.league_code == "NBA"

    def test_worker_payload_uppercases_league(self) -> None:
        """Worker payload should uppercase league code."""
        config = ScrapeRunConfig(league_code="nhl")
        payload = config.to_worker_payload()
        assert payload["league_code"] == "NHL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
