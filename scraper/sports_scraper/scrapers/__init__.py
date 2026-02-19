"""Sports Reference scrapers for supported leagues."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseSportsReferenceScraper, ScraperError
from .ncaab_sportsref import NCAABSportsReferenceScraper

if TYPE_CHECKING:
    from typing import Dict, Type

__all__ = [
    "BaseSportsReferenceScraper",
    "ScraperError",
    "NCAABSportsReferenceScraper",
    "get_scraper",
    "get_all_scrapers",
]


# Scraper registry - maps league codes to scraper classes
# NBA uses NBA CDN API for boxscores and NBA API for PBP (see services/nba_boxscore_ingestion.py)
# NHL uses the official NHL API for boxscores and PBP (see live/nhl.py)
_SCRAPER_REGISTRY: dict[str, type[BaseSportsReferenceScraper]] = {
    "NCAAB": NCAABSportsReferenceScraper,
}


def get_scraper(league_code: str) -> BaseSportsReferenceScraper | None:
    """Get a scraper instance for a league code.

    Args:
        league_code: League code (NBA, NCAAB, etc.)

    Returns:
        Scraper instance or None if not found
    """
    scraper_class = _SCRAPER_REGISTRY.get(league_code.upper())
    if scraper_class:
        return scraper_class()
    return None


def get_all_scrapers() -> dict[str, BaseSportsReferenceScraper]:
    """Get all registered scrapers as a dictionary.

    Returns:
        Dictionary mapping league codes to scraper instances
    """
    return {code: get_scraper(code) for code in _SCRAPER_REGISTRY if get_scraper(code) is not None}
