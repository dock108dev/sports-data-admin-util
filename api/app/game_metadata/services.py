"""Service layer for game metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .models import StandingsEntry, TeamRatings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
MOCK_STANDINGS_FILE = BASE_DIR / "mock_standings.json"
MOCK_RATINGS_FILE = BASE_DIR / "mock_ratings.json"

ERROR_INVALID_LEAGUE = "league is required"
ERROR_INVALID_MOCK_DATA = "mock data must be a list"
ERROR_LOADING_TEMPLATE = "Failed to load mock data from %s"


def _load_mock_file(path: Path) -> list[dict[str, Any]]:
    """Load mock JSON data from disk."""
    try:
        contents = path.read_text(encoding="utf-8")
        data = json.loads(contents)
    except (OSError, json.JSONDecodeError):
        logger.exception(ERROR_LOADING_TEMPLATE, path)
        raise

    if not isinstance(data, list):
        raise ValueError(ERROR_INVALID_MOCK_DATA)

    return data


def _parse_standings_entries(raw_entries: list[dict[str, Any]]) -> list[StandingsEntry]:
    """Parse standings entries into models."""
    return [StandingsEntry.model_validate(entry) for entry in raw_entries]


def _parse_ratings(raw_entries: list[dict[str, Any]]) -> list[TeamRatings]:
    """Parse rating entries into models."""
    return [TeamRatings.model_validate(entry) for entry in raw_entries]


class StandingsService:
    """Service for retrieving standings data."""

    def get_standings(self, league: str) -> list[StandingsEntry]:
        """Return mock standings data for a given league."""
        if not league:
            raise ValueError(ERROR_INVALID_LEAGUE)
        raw_entries = _load_mock_file(MOCK_STANDINGS_FILE)
        return _parse_standings_entries(raw_entries)


class RatingsService:
    """Service for retrieving team rating data."""

    def get_ratings(self, league: str) -> list[TeamRatings]:
        """Return mock rating data for a given league."""
        if not league:
            raise ValueError(ERROR_INVALID_LEAGUE)
        raw_entries = _load_mock_file(MOCK_RATINGS_FILE)
        return _parse_ratings(raw_entries)
