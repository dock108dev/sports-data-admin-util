"""Sports Reference scrapers for multiple leagues."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseSportsReferenceScraper, ScraperError
from .mlb_sportsref import MLBSportsReferenceScraper
from .nba_sportsref import NBASportsReferenceScraper
from .ncaab_sportsref import NCAABSportsReferenceScraper
from .ncaaf_sportsref import NCAAFSportsReferenceScraper
from .nfl_sportsref import NFLSportsReferenceScraper
from .nhl_sportsref import NHLSportsReferenceScraper

if TYPE_CHECKING:
    from typing import Dict, Type

__all__ = [
    "BaseSportsReferenceScraper",
    "ScraperError",
    "NBASportsReferenceScraper",
    "NCAABSportsReferenceScraper",
    "NFLSportsReferenceScraper",
    "NCAAFSportsReferenceScraper",
    "MLBSportsReferenceScraper",
    "NHLSportsReferenceScraper",
    "get_scraper",
    "get_all_scrapers",
]


# Scraper registry - maps league codes to scraper classes
_SCRAPER_REGISTRY: Dict[str, Type[BaseSportsReferenceScraper]] = {
    "NBA": NBASportsReferenceScraper,
    "NCAAB": NCAABSportsReferenceScraper,
    "NFL": NFLSportsReferenceScraper,
    "NCAAF": NCAAFSportsReferenceScraper,
    "MLB": MLBSportsReferenceScraper,
    "NHL": NHLSportsReferenceScraper,
}


def get_scraper(league_code: str) -> BaseSportsReferenceScraper | None:
    """Get a scraper instance for a league code.
    
    Args:
        league_code: League code (NBA, NFL, etc.)
        
    Returns:
        Scraper instance or None if not found
    """
    scraper_class = _SCRAPER_REGISTRY.get(league_code.upper())
    if scraper_class:
        return scraper_class()
    return None


def get_all_scrapers() -> Dict[str, BaseSportsReferenceScraper]:
    """Get all registered scrapers as a dictionary.
    
    Returns:
        Dictionary mapping league codes to scraper instances
    """
    return {code: get_scraper(code) for code in _SCRAPER_REGISTRY.keys() if get_scraper(code) is not None}
