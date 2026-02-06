"""Edge-triggered flow generation: dispatch when a game goes final.

Instead of generating flows on a fixed schedule hours after ingestion,
we trigger flow generation as soon as a game transitions live → final
and has sufficient PBP data.

The daily sweep (sweep_tasks.py) serves as a fallback for games that
were missed by the edge trigger.
"""

from __future__ import annotations

from celery import shared_task

from ..db import get_session
from ..logging import logger


@shared_task(
    name="trigger_flow_for_game",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    # Retry schedule: 5 min, 15 min, 30 min
    default_retry_delay=300,
)
def trigger_flow_for_game(game_id: int) -> dict:
    """Generate flows for a single game that just went final.

    Steps:
    1. Verify game is final and has PBP data
    2. Call the API pipeline endpoint for a single game
    3. If PBP incomplete, Celery retry handles backoff

    Args:
        game_id: The sports_games.id to generate flows for

    Returns:
        dict with generation result
    """
    from ..db import db_models
    from sqlalchemy import exists

    with get_session() as session:
        game = session.query(db_models.SportsGame).get(game_id)

        if not game:
            logger.warning("flow_trigger_game_not_found", game_id=game_id)
            return {"game_id": game_id, "status": "not_found"}

        if game.status != db_models.GameStatus.final.value:
            logger.info(
                "flow_trigger_skip_not_final",
                game_id=game_id,
                status=game.status,
            )
            return {"game_id": game_id, "status": "skipped", "reason": "not_final"}

        # Check if game has PBP data
        has_pbp = session.query(
            exists().where(db_models.SportsGamePlay.game_id == game_id)
        ).scalar()

        if not has_pbp:
            logger.warning(
                "flow_trigger_no_pbp",
                game_id=game_id,
            )
            # Retry will kick in via Celery's autoretry
            raise Exception(f"Game {game_id} has no PBP data yet — will retry")

        # Check if flows already exist (skip if so)
        has_artifacts = session.query(
            exists().where(db_models.SportsGameTimelineArtifact.game_id == game_id)
        ).scalar()

        if has_artifacts:
            logger.info(
                "flow_trigger_skip_exists",
                game_id=game_id,
            )
            return {"game_id": game_id, "status": "skipped", "reason": "already_exists"}

        # Get league code for the API call
        league = session.query(db_models.SportsLeague).get(game.league_id)
        league_code = league.code if league else "UNKNOWN"

    # Call the API pipeline endpoint
    return _call_pipeline_api(game_id, league_code)


def _call_pipeline_api(game_id: int, league_code: str) -> dict:
    """Call the internal API to generate flows for a single game."""
    import httpx
    from ..config import settings

    api_base = settings.api_internal_url

    logger.info(
        "flow_trigger_api_call",
        game_id=game_id,
        league=league_code,
    )

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{api_base}/api/admin/sports/pipeline/generate/{game_id}",
                json={"force": False},
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "flow_trigger_success",
            game_id=game_id,
            league=league_code,
            result=result,
        )
        return {
            "game_id": game_id,
            "league": league_code,
            "status": "success",
            "result": result,
        }

    except httpx.HTTPStatusError as exc:
        logger.error(
            "flow_trigger_http_error",
            game_id=game_id,
            league=league_code,
            status_code=exc.response.status_code,
            error=exc.response.text,
        )
        # Don't retry on 4xx errors (bad request, not found)
        if 400 <= exc.response.status_code < 500:
            return {
                "game_id": game_id,
                "league": league_code,
                "status": "error",
                "error": f"HTTP {exc.response.status_code}",
            }
        raise  # 5xx errors will trigger Celery retry

    except Exception as exc:
        logger.exception(
            "flow_trigger_error",
            game_id=game_id,
            league=league_code,
            error=str(exc),
        )
        raise  # Let Celery retry
