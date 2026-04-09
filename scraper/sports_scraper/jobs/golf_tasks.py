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
    from ..services.job_runs import track_job_run

    with track_job_run("golf_sync_schedule", ["PGA"]) as tracker:
        result = sync_schedule(tour=tour, season=season)
        tracker.summary_data = result
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
    from ..services.job_runs import track_job_run

    with track_job_run("golf_sync_players", ["PGA"]) as tracker:
        result = sync_players()
        tracker.summary_data = result
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
    from ..services.job_runs import track_job_run

    with track_job_run("golf_sync_field", ["PGA"]) as tracker:
        result = sync_field(tour=tour)
        tracker.summary_data = result
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
    from ..services.job_runs import track_job_run

    with track_job_run("golf_sync_leaderboard", ["PGA"]) as tracker:
        result = sync_leaderboard()
        tracker.summary_data = result
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
    from ..services.job_runs import track_job_run

    markets = ["win", "top_5", "top_10", "make_cut"]
    results: dict[str, dict] = {}
    total_odds = 0

    with track_job_run("golf_sync_odds", ["PGA"]) as tracker:
        for market in markets:
            try:
                result = sync_odds(tour=tour, market=market)
                results[market] = result
                total_odds += result.get("odds_upserted", 0)
            except Exception as exc:
                logger.exception("golf_sync_odds_market_failed", tour=tour, market=market, error=str(exc))
                results[market] = {"status": "error", "error": str(exc)}

        summary = {"tour": tour, "markets": results, "total_odds": total_odds}
        tracker.summary_data = summary
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
    from ..services.job_runs import track_job_run

    sites = ["draftkings", "fanduel", "yahoo"]
    results: dict[str, dict] = {}
    total_projections = 0

    with track_job_run("golf_sync_dfs", ["PGA"]) as tracker:
        for site in sites:
            try:
                result = sync_dfs_projections(site=site, tour=tour)
                results[site] = result
                total_projections += result.get("projections_upserted", 0)
            except Exception as exc:
                logger.exception("golf_sync_dfs_site_failed", tour=tour, site=site, error=str(exc))
                results[site] = {"status": "error", "error": str(exc)}

        summary = {"tour": tour, "sites": results, "total_projections": total_projections}
        tracker.summary_data = summary
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
    from ..services.job_runs import track_job_run

    with track_job_run("golf_sync_stats", ["PGA"]) as tracker:
        result = sync_stats(tour=tour)
        tracker.summary_data = result
    return result


@shared_task(
    name="golf_score_pools",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def golf_score_pools() -> dict:
    """Score all live golf pools and write materialized results."""
    from ..db import get_session
    from ..golf.pool_scoring import score_all_live_pools
    from ..services.job_runs import track_job_run

    with track_job_run("golf_score_pools", ["PGA"]) as tracker:
        with get_session() as session:
            result = score_all_live_pools(session)
        tracker.summary_data = result
    return result


@shared_task(
    name="rescore_golf_pool",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def rescore_golf_pool(pool_id: int) -> dict:
    """Rescore a single golf pool by ID (manual admin trigger)."""
    from ..db import get_session
    from ..golf.pool_scoring import score_single_pool
    from ..services.job_runs import track_job_run

    with track_job_run("rescore_golf_pool", ["PGA"]) as tracker:
        with get_session() as session:
            result = score_single_pool(session, pool_id)
        tracker.summary_data = result
    return result
