"""Celery utility tasks."""

from __future__ import annotations

from celery import shared_task

from ..logging import logger


@shared_task(name="clear_scraper_cache")
def clear_scraper_cache_task(league_code: str, days: int = 7) -> dict:
    """Clear cached scoreboard HTML files for the last N days.

    This allows manually refreshing recent data before a scrape run.
    Only clears scoreboard pages (not boxscores or PBP which are immutable).

    Args:
        league_code: League to clear cache for (e.g., "NBA", "NHL")
        days: Number of days back to clear (default 7)

    Returns:
        Summary dict with count of deleted files
    """
    from ..config import settings
    from ..utils.cache import HTMLCache

    logger.info(
        "clear_cache_started",
        league=league_code,
        days=days,
    )

    cache = HTMLCache(
        settings.scraper_config.html_cache_dir,
        league_code,
    )

    result = cache.clear_recent_scoreboards(days=days)

    logger.info(
        "clear_cache_completed",
        league=league_code,
        days=days,
        deleted_count=result["deleted_count"],
    )

    return {
        "league": league_code,
        "days": days,
        **result,
    }
