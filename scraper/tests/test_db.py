"""Tests for db.py module."""

from __future__ import annotations

import os
import sys
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


class TestGetSession:
    """Tests for get_session context manager."""

    def test_yields_session_and_commits(self):
        """get_session yields a session and commits on success."""
        from sports_scraper.db import SessionLocal

        with patch.object(SessionLocal, '__call__') as mock_session_factory:
            mock_session = MagicMock()
            mock_session_factory.return_value = mock_session

            from sports_scraper.db import get_session
            with get_session() as session:
                assert session is mock_session

            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()

    def test_rolls_back_on_exception(self):
        """get_session rolls back on exception."""
        from sports_scraper.db import SessionLocal

        with patch.object(SessionLocal, '__call__') as mock_session_factory:
            mock_session = MagicMock()
            mock_session_factory.return_value = mock_session

            from sports_scraper.db import get_session
            with pytest.raises(ValueError):
                with get_session() as session:
                    raise ValueError("test error")

            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()
            mock_session.commit.assert_not_called()

    def test_closes_session_always(self):
        """get_session always closes the session."""
        from sports_scraper.db import SessionLocal

        with patch.object(SessionLocal, '__call__') as mock_session_factory:
            mock_session = MagicMock()
            mock_session_factory.return_value = mock_session

            from sports_scraper.db import get_session
            try:
                with get_session() as session:
                    raise RuntimeError("error")
            except RuntimeError:
                pass

            mock_session.close.assert_called_once()


class TestModuleExports:
    """Tests for db module exports."""

    def test_exports_get_session(self):
        """Module exports get_session."""
        from sports_scraper import db
        assert hasattr(db, 'get_session')
        assert callable(db.get_session)

    def test_exports_db_models(self):
        """Module exports db_models."""
        from sports_scraper import db
        assert hasattr(db, 'db_models')

    def test_exports_engine(self):
        """Module exports engine."""
        from sports_scraper import db
        assert hasattr(db, 'engine')

    def test_all_contains_exports(self):
        """__all__ contains expected exports."""
        from sports_scraper import db
        assert "get_session" in db.__all__
        assert "db_models" in db.__all__
        assert "engine" in db.__all__


class TestSessionLocal:
    """Tests for SessionLocal factory."""

    def test_session_local_exists(self):
        """SessionLocal factory exists."""
        from sports_scraper.db import SessionLocal
        assert SessionLocal is not None

    def test_creates_session(self):
        """SessionLocal creates session objects."""
        from sports_scraper.db import SessionLocal
        # Just verify it's callable
        assert callable(SessionLocal)


class TestEngine:
    """Tests for database engine."""

    def test_engine_exists(self):
        """Engine exists."""
        from sports_scraper.db import engine
        assert engine is not None

    def test_engine_has_url(self):
        """Engine has a URL configured."""
        from sports_scraper.db import engine
        assert engine.url is not None
