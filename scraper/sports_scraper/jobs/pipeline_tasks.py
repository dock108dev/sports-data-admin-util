"""Celery tasks for pipeline triggering."""

from __future__ import annotations

from celery import shared_task

from ..api_client import get_api_headers
from ..logging import logger


@shared_task(
    name="trigger_game_pipelines",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def trigger_game_pipelines_task(
    league_code: str,
    days_back: int | None = None,
    max_games: int | None = None,
    auto_chain: bool = True,
) -> dict:
    """Trigger pipeline runs for games missing timeline artifacts.

    This is the production task for triggering game pipelines after scraping.
    It finds games with PBP data but no timeline artifacts and starts
    pipeline runs for them.

    Args:
        league_code: League to process (required)
        days_back: How many days back to check (None = ALL games)
        max_games: Maximum number of games to process (None = all)
        auto_chain: Whether pipelines should auto-proceed through stages

    Returns:
        Summary dict with counts of pipelines started
    """
    import httpx

    from ..config import settings
    from ..db import get_session

    logger.info(
        "trigger_game_pipelines_started",
        league=league_code,
        days_back=days_back,
        max_games=max_games,
        auto_chain=auto_chain,
    )

    # Find games missing timelines (reuse existing logic)
    from ..services.timeline_generator import find_games_missing_timelines

    with get_session() as session:
        games = find_games_missing_timelines(session, league_code, days_back)

    if not games:
        logger.info("trigger_game_pipelines_no_games", league=league_code)
        return {
            "games_found": 0,
            "pipelines_started": 0,
            "pipelines_failed": 0,
        }

    # Limit games if specified
    games_to_process = games[:max_games] if max_games else games

    started = 0
    failed = 0

    api_base = settings.api_internal_url

    for game_id, game_date, home_team, away_team in games_to_process:
        logger.info(
            "trigger_game_pipeline",
            game_id=game_id,
            game_date=str(game_date),
            matchup=f"{away_team} @ {home_team}",
        )

        try:
            # Call the pipeline API to run the full pipeline
            response = httpx.post(
                f"{api_base}/api/admin/sports/pipeline/{game_id}/run-full",
                json={"triggered_by": "prod_auto"},
                headers=get_api_headers(),
                timeout=600,  # 10 minute timeout per game
            )
            response.raise_for_status()
            started += 1

        except Exception as e:
            logger.error(
                "trigger_game_pipeline_failed",
                game_id=game_id,
                error=str(e),
            )
            failed += 1

    summary = {
        "games_found": len(games),
        "pipelines_started": started,
        "pipelines_failed": failed,
    }

    logger.info("trigger_game_pipelines_completed", **summary)

    return summary
