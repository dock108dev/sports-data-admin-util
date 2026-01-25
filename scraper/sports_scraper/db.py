"""
Database helpers for the scraper service.

This module provides synchronous database session management for Celery tasks.
It reuses the ORM models from the sports-data-admin API to maintain consistency
across services and avoid duplicate model definitions.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .logging import logger

# Ensure the sports-data-admin API package is importable so we can reuse ORM models
# This avoids duplicating model definitions and ensures schema consistency
SPORTS_API_PATH = Path(__file__).resolve().parents[2] / "api"
if str(SPORTS_API_PATH) not in sys.path:
    sys.path.append(str(SPORTS_API_PATH))

try:
    from app import db_models  # type: ignore
except ImportError as exc:
    raise RuntimeError(
        "Unable to import sports-data-admin api app.db_models. "
        "Did you install the API service dependencies?"
    ) from exc


engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    class_=Session
)


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Provide a transactional database session context manager.
    
    Use this in Celery tasks and other synchronous code paths.
    Automatically handles commit/rollback and session cleanup.
    
    Usage:
        with get_session() as session:
            # Use session here
            session.add(object)
            # Commit happens automatically on exit
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:  # pragma: no cover
        session.rollback()
        logger.exception("DB session rollback", error=str(exc))
        raise
    finally:
        session.close()


__all__ = ["get_session", "db_models", "engine"]

