"""Celery tasks for golf data ingestion.

Each task wraps a corresponding function from ``golf.ingestion`` and
follows the ``@shared_task(name=...)`` pattern used by other task modules.
"""

from __future__ import annotations

from celery import shared_task

from ..logging import logger


@shared_task(
    name="golf_sync_schedule",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_sync_schedule(tour: str = "pga", season: int | None = None) -> dict:
    """Sync the tour schedule from DataGolf."""
    from ..golf.ingestion import sync_schedule

    logger.info("golf_sync_schedule_start", tour=tour, season=season)
    result = sync_schedule(tour=tour, season=season)
    logger.info("golf_sync_schedule_done", **result)
    return result


@shared_task(
    name="golf_sync_players",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_sync_players() -> dict:
    """Sync the full player catalog from DataGolf."""
    from ..golf.ingestion import sync_players

    logger.info("golf_sync_players_start")
    result = sync_players()
    logger.info("golf_sync_players_done", **result)
    return result


@shared_task(
    name="golf_sync_field",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_sync_field(tour: str = "pga") -> dict:
    """Sync tournament field updates from DataGolf."""
    from ..golf.ingestion import sync_field

    logger.info("golf_sync_field_start", tour=tour)
    result = sync_field(tour=tour)
    logger.info("golf_sync_field_done", **result)
    return result


@shared_task(
    name="golf_sync_leaderboard",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_sync_leaderboard() -> dict:
    """Sync live leaderboard and tournament stats from DataGolf."""
    from ..golf.ingestion import sync_leaderboard

    logger.info("golf_sync_leaderboard_start")
    result = sync_leaderboard()
    logger.info("golf_sync_leaderboard_done", **result)
    return result


@shared_task(
    name="golf_sync_odds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_sync_odds(tour: str = "pga") -> dict:
    """Sync outright odds for all markets (win, top_5, top_10, make_cut)."""
    from ..golf.ingestion import sync_odds

    markets = ["win", "top_5", "top_10", "make_cut"]
    results: dict[str, dict] = {}
    total_odds = 0

    logger.info("golf_sync_odds_start", tour=tour, markets=markets)

    for market in markets:
        try:
            result = sync_odds(tour=tour, market=market)
            results[market] = result
            total_odds += result.get("odds_upserted", 0)
        except Exception as exc:
            logger.exception("golf_sync_odds_market_failed", tour=tour, market=market, error=str(exc))
            results[market] = {"status": "error", "error": str(exc)}

    summary = {"tour": tour, "markets": results, "total_odds": total_odds}
    logger.info("golf_sync_odds_done", **summary)
    return summary


@shared_task(
    name="golf_sync_dfs",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_sync_dfs(tour: str = "pga") -> dict:
    """Sync DFS projections for all supported sites."""
    from ..golf.ingestion import sync_dfs_projections

    sites = ["draftkings", "fanduel", "yahoo"]
    results: dict[str, dict] = {}
    total_projections = 0

    logger.info("golf_sync_dfs_start", tour=tour, sites=sites)

    for site in sites:
        try:
            result = sync_dfs_projections(site=site, tour=tour)
            results[site] = result
            total_projections += result.get("projections_upserted", 0)
        except Exception as exc:
            logger.exception("golf_sync_dfs_site_failed", tour=tour, site=site, error=str(exc))
            results[site] = {"status": "error", "error": str(exc)}

    summary = {"tour": tour, "sites": results, "total_projections": total_projections}
    logger.info("golf_sync_dfs_done", **summary)
    return summary


@shared_task(
    name="golf_sync_stats",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_sync_stats(tour: str = "pga") -> dict:
    """Sync player skill ratings from DataGolf."""
    from ..golf.ingestion import sync_stats

    logger.info("golf_sync_stats_start", tour=tour)
    result = sync_stats(tour=tour)
    logger.info("golf_sync_stats_done", **result)
    return result
