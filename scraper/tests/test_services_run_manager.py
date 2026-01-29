"""Tests for services/run_manager.py module."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
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


from sports_scraper.services.run_manager import (
    RunManager,
    RunStatus,
)


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_has_pending_status(self):
        """Has pending status value."""
        assert hasattr(RunStatus, "PENDING") or hasattr(RunStatus, "pending")

    def test_has_running_status(self):
        """Has running status value."""
        assert hasattr(RunStatus, "RUNNING") or hasattr(RunStatus, "running")

    def test_has_completed_status(self):
        """Has completed status value."""
        assert hasattr(RunStatus, "COMPLETED") or hasattr(RunStatus, "completed")

    def test_has_failed_status(self):
        """Has failed status value."""
        assert hasattr(RunStatus, "FAILED") or hasattr(RunStatus, "failed")


class TestRunManager:
    """Tests for RunManager class."""

    def test_init_with_session(self):
        """Initializes with database session."""
        mock_session = MagicMock()
        manager = RunManager(mock_session)
        assert manager.session == mock_session

    def test_create_run(self):
        """Creates a new run record."""
        mock_session = MagicMock()
        manager = RunManager(mock_session)

        run = manager.create_run(job_type="test_job")

        assert mock_session.add.called or mock_session.execute.called

    def test_update_run_status(self):
        """Updates run status."""
        mock_session = MagicMock()
        manager = RunManager(mock_session)

        # Create a mock run
        mock_run = MagicMock(id=1)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run

        manager.update_run_status(run_id=1, status=RunStatus.COMPLETED)

        # Status should be updated
        assert mock_session.commit.called or mock_session.flush.called

    def test_get_run(self):
        """Gets run by ID."""
        mock_session = MagicMock()
        mock_run = MagicMock(id=1, job_type="test_job")
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run

        manager = RunManager(mock_session)
        result = manager.get_run(run_id=1)

        assert result == mock_run

    def test_get_run_returns_none_for_missing(self):
        """Returns None for missing run."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        manager = RunManager(mock_session)
        result = manager.get_run(run_id=999)

        assert result is None
