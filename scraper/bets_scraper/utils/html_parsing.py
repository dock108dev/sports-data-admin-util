"""
Shared HTML / DOM-specific parsing utilities for scrapers.

Contains helpers that depend on BeautifulSoup or other HTML-specific structures.
Generic data-type conversion (ints, floats) should live in parsing.py.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from ..logging import logger


def get_stat_from_row(row: Tag, stat_name: str) -> str | None:
    """
    Extract a stat value from a table row by data-stat attribute.
    
    This is an HTML-specific helper for Sports Reference style tables.
    """
    cell = row.find("td", {"data-stat": stat_name})
    if cell:
        text = cell.text.strip()
        return text if text and text != "" else None
    return None


def extract_all_stats_from_row(row: Tag) -> dict[str, str]:
    """
    Extract all stats from a table row as a dictionary.
    
    Iterates through all td cells and extracts data-stat attributes.
    """
    raw_stats = {}
    for cell in row.find_all("td"):
        stat_name = cell.get("data-stat")
        if stat_name:
            raw_stats[stat_name] = cell.text.strip()
    return raw_stats


def find_table_by_id(soup: BeautifulSoup, table_id: str, alternate_ids: list[str] | None = None) -> Tag | None:
    """Find a table by ID, trying alternate IDs if provided.
    
    Args:
        soup: BeautifulSoup document
        table_id: Primary table ID to search for
        alternate_ids: Optional list of alternate IDs to try
        
    Returns:
        Table Tag if found, None otherwise
    """
    table = soup.find("table", id=table_id)
    if table:
        return table
    
    if alternate_ids:
        for alt_id in alternate_ids:
            table = soup.find("table", id=alt_id)
            if table:
                logger.debug("table_found_alternate", primary_id=table_id, found_id=alt_id)
                return table
    
    return None


def extract_team_stats_from_table(table: Tag, team_abbr: str, table_id: str) -> dict:
    """Extract team stats from a table's tfoot section.
    
    Common pattern across Sports Reference sites:
    - Stats are in tfoot
    - Each cell has a data-stat attribute
    - Values are in cell text
    
    Args:
        table: BeautifulSoup table Tag
        team_abbr: Team abbreviation (for logging)
        table_id: Table ID (for logging)
        
    Returns:
        Dictionary of stat_name -> stat_value
    """
    totals = {}
    tfoot = table.find("tfoot")
    if not tfoot:
        logger.warning("team_stats_tfoot_not_found", table_id=table_id, team_abbr=team_abbr)
        return totals
    
    cells = tfoot.find_all("td")
    for cell in cells:
        stat = cell.get("data-stat")
        if stat:
            totals[stat] = cell.text.strip()
    
    logger.debug(
        "team_stats_extracted",
        team_abbr=team_abbr,
        stat_count=len(totals),
        sample_keys=list(totals.keys())[:5],
    )
    return totals


def find_player_table(soup: BeautifulSoup, table_id: str, alternate_ids: list[str] | None = None) -> Tag | None:
    """Find a player stats table by ID.
    
    Args:
        soup: BeautifulSoup document
        table_id: Primary table ID
        alternate_ids: Optional alternate IDs
        
    Returns:
        Table Tag if found, None otherwise
    """
    return find_table_by_id(soup, table_id, alternate_ids)


def get_table_ids_on_page(soup: BeautifulSoup, limit: int = 15) -> list[str]:
    """Get all table IDs found on a page (for debugging).
    
    Args:
        soup: BeautifulSoup document
        limit: Maximum number of IDs to return
        
    Returns:
        List of table IDs
    """
    all_tables = soup.find_all("table")
    return [t.get("id", "no-id") for t in all_tables[:limit]]

