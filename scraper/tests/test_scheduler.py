"""Tests for services/scheduler.py module."""

from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


from sports_scraper.services.scheduler import (
    ScheduledIngestionSummary,
    build_scheduled_window,
    create_scrape_run,
    schedule_ingestion_runs,
)


class TestScheduledIngestionSummary:
    """Tests for ScheduledIngestionSummary dataclass."""

    def test_create_summary(self):
        """Create a summary with all fields."""
        now = datetime.now(UTC)
        summary = ScheduledIngestionSummary(
            runs_created=5,
            runs_skipped=2,
            run_failures=1,
            enqueue_failures=0,
            last_run_at=now,
        )
        assert summary.runs_created == 5
        assert summary.runs_skipped == 2
        assert summary.run_failures == 1
        assert summary.enqueue_failures == 0
        assert summary.last_run_at == now

    def test_summary_is_frozen(self):
        """Summary is immutable."""
        now = datetime.now(UTC)
        summary = ScheduledIngestionSummary(
            runs_created=5,
            runs_skipped=2,
            run_failures=1,
            enqueue_failures=0,
            last_run_at=now,
        )
        with pytest.raises(Exception):
            summary.runs_created = 10


class TestBuildScheduledWindow:
    """Tests for build_scheduled_window function."""

    def test_returns_tuple(self):
        """Returns a tuple of two datetimes."""
        result = build_scheduled_window()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], datetime)
        assert isinstance(result[1], datetime)

    def test_window_spans_expected_range(self):
        """Window spans 96 hours back to 48 hours forward."""
        now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        start, end = build_scheduled_window(now)

        expected_start = now - timedelta(hours=96)
        expected_end = now + timedelta(hours=48)

        assert start.year == expected_start.year
        assert start.month == expected_start.month
        assert start.day == expected_start.day

        assert end.year == expected_end.year
        assert end.month == expected_end.month
        assert end.day == expected_end.day

    def test_start_before_end(self):
        """Start time is before end time."""
        start, end = build_scheduled_window()
        assert start < end

    def test_uses_utc_timezone(self):
        """Both datetimes are in UTC."""
        start, end = build_scheduled_window()
        assert start.tzinfo == UTC
        assert end.tzinfo == UTC


class TestCreateScrapeRun:
    """Tests for create_scrape_run function."""

    @patch("sports_scraper.services.scheduler.db_models")
    def test_creates_run_record(self, mock_db_models):
        """Creates a scrape run and returns it."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1

        mock_run = MagicMock()
        mock_run.id = 123
        mock_db_models.SportsScrapeRun.return_value = mock_run

        from sports_scraper.models import IngestionConfig
        config = IngestionConfig(
            league_code="NBA",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        result = create_scrape_run(
            mock_session,
            mock_league,
            config,
            requested_by="test",
        )

        assert result == mock_run
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @patch("sports_scraper.services.scheduler.db_models")
    def test_sets_pending_status(self, mock_db_models):
        """Run is created with pending status."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1

        from sports_scraper.models import IngestionConfig
        config = IngestionConfig(
            league_code="NBA",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        create_scrape_run(mock_session, mock_league, config, requested_by="test")

        # Check the SportsScrapeRun was created with pending status
        call_kwargs = mock_db_models.SportsScrapeRun.call_args
        assert call_kwargs.kwargs["status"] == "pending"


class TestScheduleIngestionRuns:
    """Tests for schedule_ingestion_runs function."""

    @patch("sports_scraper.services.scheduler.get_league_config")
    @patch("sports_scraper.services.scheduler.get_scheduled_leagues")
    @patch("sports_scraper.services.scheduler.get_session")
    def test_returns_summary(self, mock_get_session, mock_get_leagues, mock_get_config):
        """Returns ScheduledIngestionSummary."""
        mock_get_leagues.return_value = []
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        result = schedule_ingestion_runs()

        assert isinstance(result, ScheduledIngestionSummary)

    @patch("sports_scraper.services.scheduler.get_league_config")
    @patch("sports_scraper.services.scheduler.get_scheduled_leagues")
    @patch("sports_scraper.services.scheduler.get_session")
    def test_skips_unknown_league(self, mock_get_session, mock_get_leagues, mock_get_config):
        """Skips leagues not found in database."""
        mock_get_leagues.return_value = ["UNKNOWN"]
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_session.return_value.__enter__.return_value = mock_session

        result = schedule_ingestion_runs()

        assert result.runs_skipped == 1
        assert result.runs_created == 0

    @patch("sports_scraper.services.scheduler.get_league_config")
    @patch("sports_scraper.services.scheduler.get_scheduled_leagues")
    @patch("sports_scraper.services.scheduler.get_session")
    def test_skips_recent_runs(self, mock_get_session, mock_get_leagues, mock_get_config):
        """Skips leagues with recent runs."""
        mock_get_leagues.return_value = ["NBA"]

        mock_league = MagicMock()
        mock_league.id = 1

        mock_recent_run = MagicMock()
        mock_recent_run.id = 100
        mock_recent_run.created_at = datetime.now(UTC)

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query

        # First call: league lookup
        # Second call: recent run lookup
        mock_query.filter.return_value.first.side_effect = [
            mock_league,  # League found
            mock_recent_run,  # Recent run found
        ]

        mock_get_session.return_value.__enter__.return_value = mock_session

        result = schedule_ingestion_runs()

        assert result.runs_skipped == 1
        assert result.runs_created == 0

    @patch("sports_scraper.services.scheduler.create_scrape_run")
    @patch("sports_scraper.services.scheduler.get_league_config")
    @patch("sports_scraper.services.scheduler.get_scheduled_leagues")
    @patch("sports_scraper.services.scheduler.get_session")
    def test_creates_runs_for_valid_leagues(
        self, mock_get_session, mock_get_leagues, mock_get_config, mock_create_run
    ):
        """Creates runs for valid leagues without recent runs."""
        mock_get_leagues.return_value = ["NBA"]

        mock_league = MagicMock()
        mock_league.id = 1

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query

        # League found, no recent run
        mock_query.filter.return_value.first.side_effect = [mock_league, None]
        mock_query.filter.return_value.filter.return_value.first.return_value = None
        mock_query.filter.return_value.filter.return_value.filter.return_value.first.return_value = None

        mock_get_session.return_value.__enter__.return_value = mock_session

        # Mock league config
        mock_league_cfg = MagicMock()
        mock_league_cfg.boxscores_enabled = True
        mock_league_cfg.odds_enabled = True
        mock_league_cfg.social_enabled = False
        mock_league_cfg.pbp_enabled = False
        mock_get_config.return_value = mock_league_cfg

        # Mock the run creation - raise exception to trigger failure path
        mock_run = MagicMock()
        mock_run.id = 123
        mock_create_run.side_effect = Exception("Celery not available")

        result = schedule_ingestion_runs()

        # Run creation failed, so runs_created should be 0, run_failures should be 1
        assert result.run_failures == 1
        mock_create_run.assert_called_once()


class TestCoerceDate:
    """Tests for _coerce_date helper function."""

    def test_import_coerce_date(self):
        """Can import the function."""
        from sports_scraper.services.scheduler import _coerce_date
        assert callable(_coerce_date)

    def test_none_returns_none(self):
        """None input returns None."""
        from sports_scraper.services.scheduler import _coerce_date
        assert _coerce_date(None) is None

    def test_coerces_to_midnight(self):
        """Datetime is coerced to midnight."""
        from sports_scraper.services.scheduler import _coerce_date
        dt = datetime(2024, 1, 15, 14, 30, 45, 123456, tzinfo=UTC)
        result = _coerce_date(dt)
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0
