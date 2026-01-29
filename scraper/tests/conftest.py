"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

# Set required environment variables before any imports
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx client."""
    client = MagicMock()
    client.get.return_value = MagicMock(status_code=200, json=lambda: {}, text="")
    return client


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def sample_nhl_play():
    """Sample NHL play data for testing."""
    return {
        "eventId": 151,
        "periodDescriptor": {"number": 1, "periodType": "REG"},
        "timeInPeriod": "04:00",
        "timeRemaining": "16:00",
        "situationCode": "1551",
        "typeDescKey": "goal",
        "sortOrder": 67,
        "details": {
            "scoringPlayerId": 8480840,
            "eventOwnerTeamId": 25,
            "homeScore": 1,
            "awayScore": 0,
            "shotType": "snap",
        },
    }


@pytest.fixture
def sample_ncaab_play():
    """Sample NCAAB play data for testing."""
    return {
        "period": 1,
        "sequenceNumber": 10,
        "clock": "15:30",
        "playType": "JumpShot",
        "team": "Duke",
        "playerId": 12345,
        "player": "John Doe",
        "homeScore": 10,
        "awayScore": 8,
        "description": "Made 3-pointer",
    }


@pytest.fixture
def sample_nba_play():
    """Sample NBA play data for testing."""
    return {
        "actionNumber": 5,
        "period": 1,
        "clock": "PT11M22.00S",
        "actionType": "2pt",
        "subType": "Layup",
        "description": "J. Tatum Layup",
        "scoreHome": "2",
        "scoreAway": "0",
        "teamTricode": "BOS",
        "personId": 1628369,
    }
