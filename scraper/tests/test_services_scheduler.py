"""Tests for services/scheduler.py module."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
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
    build_scheduled_window,
    _coerce_date,
    ScheduledIngestionSummary,
)


class TestBuildScheduledWindow:
    """Tests for build_scheduled_window function."""

    def test_returns_tuple(self):
        """Returns a tuple of two datetimes."""
        result = build_scheduled_window()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], datetime)
        assert isinstance(result[1], datetime)

    def test_start_is_96_hours_back(self):
        """Start is 96 hours before anchor."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        start, end = build_scheduled_window(now)
        expected_start = now - timedelta(hours=96)
        assert start == expected_start

    def test_end_is_48_hours_forward(self):
        """End is 48 hours after anchor."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        start, end = build_scheduled_window(now)
        expected_end = now + timedelta(hours=48)
        assert end == expected_end

    def test_uses_utc_timezone(self):
        """All datetimes are in UTC."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        start, end = build_scheduled_window(now)
        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc

    def test_uses_current_time_when_none(self):
        """Uses current time when no argument provided."""
        start, end = build_scheduled_window()
        # Just verify the window is reasonable
        assert end > start
        window_hours = (end - start).total_seconds() / 3600
        assert window_hours == 144  # 96 + 48


class TestCoerceDate:
    """Tests for _coerce_date function."""

    def test_returns_none_for_none(self):
        """Returns None for None input."""
        result = _coerce_date(None)
        assert result is None

    def test_strips_time_components(self):
        """Strips time components from datetime."""
        dt = datetime(2024, 1, 15, 14, 30, 45, 123456, tzinfo=timezone.utc)
        result = _coerce_date(dt)
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0

    def test_preserves_date(self):
        """Preserves the date portion."""
        dt = datetime(2024, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = _coerce_date(dt)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15


class TestScheduledIngestionSummary:
    """Tests for ScheduledIngestionSummary dataclass."""

    def test_create_summary(self):
        """Can create a summary with all fields."""
        summary = ScheduledIngestionSummary(
            runs_created=5,
            runs_skipped=2,
            run_failures=1,
            enqueue_failures=0,
            last_run_at=datetime.now(timezone.utc),
        )
        assert summary.runs_created == 5
        assert summary.runs_skipped == 2
        assert summary.run_failures == 1
        assert summary.enqueue_failures == 0

    def test_summary_is_frozen(self):
        """Summary is immutable."""
        summary = ScheduledIngestionSummary(
            runs_created=5,
            runs_skipped=2,
            run_failures=1,
            enqueue_failures=0,
            last_run_at=datetime.now(timezone.utc),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            summary.runs_created = 10


class TestModuleImports:
    """Tests for scheduler module imports."""

    def test_has_build_scheduled_window(self):
        """Module has build_scheduled_window function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'build_scheduled_window')

    def test_has_create_scrape_run(self):
        """Module has create_scrape_run function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'create_scrape_run')

    def test_has_schedule_ingestion_runs(self):
        """Module has schedule_ingestion_runs function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'schedule_ingestion_runs')

    def test_has_scheduled_ingestion_summary(self):
        """Module has ScheduledIngestionSummary class."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'ScheduledIngestionSummary')
