"""Celery tasks for story/flow generation."""

from __future__ import annotations

from celery import shared_task

from ..logging import logger


@shared_task(
    name="run_scheduled_nba_flow_generation",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def run_scheduled_nba_flow_generation() -> dict:
    """
    Scheduled task to generate flows for NBA games in the last 72 hours.

    Runs 15 minutes after NCAAB ingestion completes.
    Only generates flows for games that don't already have them (force=False).

    Uses a 3-day (72 hour) window: today, yesterday, and 2 days ago.
    """
    import httpx
    import time
    from datetime import date, timedelta
    from ..config import settings

    # Calculate 72-hour window: 2 days ago through today
    today = date.today()
    start_date = today - timedelta(days=2)
    end_date = today

    logger.info(
        "scheduled_nba_flow_gen_start",
        start_date=str(start_date),
        end_date=str(end_date),
    )

    api_base = settings.api_internal_url

    try:
        # Start the bulk generation job - NBA only, don't force regenerate
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{api_base}/api/admin/sports/pipeline/bulk-generate-async",
                json={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "leagues": ["NBA"],
                    "force": False,  # Don't regenerate existing flows
                },
            )
            response.raise_for_status()
            job_data = response.json()

        job_id = job_data["job_id"]
        logger.info("scheduled_nba_flow_gen_job_started", job_id=job_id)

        # Poll for completion (max 30 minutes, check every 30 seconds)
        max_polls = 60
        poll_interval = 30

        for poll_num in range(max_polls):
            time.sleep(poll_interval)

            with httpx.Client(timeout=30.0) as client:
                status_response = client.get(
                    f"{api_base}/api/admin/sports/pipeline/bulk-generate-status/{job_id}"
                )
                status_response.raise_for_status()
                status = status_response.json()

            state = status.get("state", "UNKNOWN")

            if state == "PROGRESS":
                logger.info(
                    "scheduled_nba_flow_gen_progress",
                    job_id=job_id,
                    current=status.get("current"),
                    total=status.get("total"),
                    successful=status.get("successful"),
                    failed=status.get("failed"),
                    skipped=status.get("skipped"),
                )
            elif state == "SUCCESS":
                result = status.get("result", {})
                logger.info(
                    "scheduled_nba_flow_gen_complete",
                    job_id=job_id,
                    total_games=result.get("total_games", 0),
                    successful=result.get("successful", 0),
                    failed=result.get("failed", 0),
                    skipped=result.get("skipped", 0),
                    generated=result.get("generated", 0),
                )
                return {
                    "job_id": job_id,
                    "state": "SUCCESS",
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "leagues": ["NBA"],
                    **result,
                }
            elif state == "FAILURE":
                logger.error(
                    "scheduled_nba_flow_gen_failed",
                    job_id=job_id,
                    status=status.get("status"),
                )
                return {
                    "job_id": job_id,
                    "state": "FAILURE",
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "leagues": ["NBA"],
                    "error": status.get("status"),
                }

        # Timed out waiting for completion
        logger.warning(
            "scheduled_nba_flow_gen_timeout",
            job_id=job_id,
            max_wait_minutes=max_polls * poll_interval / 60,
        )
        return {
            "job_id": job_id,
            "state": "TIMEOUT",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "leagues": ["NBA"],
            "error": "Timed out waiting for job completion",
        }

    except httpx.HTTPStatusError as exc:
        logger.error(
            "scheduled_nba_flow_gen_http_error",
            status_code=exc.response.status_code,
            error=exc.response.text,
        )
        return {
            "state": "ERROR",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "leagues": ["NBA"],
            "error": f"HTTP {exc.response.status_code}: {exc.response.text}",
        }
    except Exception as exc:
        logger.exception(
            "scheduled_nba_flow_gen_error",
            error=str(exc),
        )
        raise  # Let Celery retry


@shared_task(
    name="run_scheduled_story_generation",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def run_scheduled_story_generation() -> dict:
    """
    Scheduled task to generate stories for games in the last 3 days.

    This runs after timeline generation completes and generates stories for all
    games with PBP data that haven't had stories generated yet.

    Uses a 3-day window: today, yesterday, and 2 days ago.
    For example, if run on 1/23, generates stories for 1/21, 1/22, and 1/23.
    """
    import httpx
    import time
    from datetime import date, timedelta
    from ..config import settings
    from ..config_sports import get_scheduled_leagues

    # Calculate 3-day window: 2 days ago through today
    today = date.today()
    start_date = today - timedelta(days=2)
    end_date = today

    leagues = list(get_scheduled_leagues())

    logger.info(
        "scheduled_story_gen_start",
        start_date=str(start_date),
        end_date=str(end_date),
        leagues=leagues,
    )

    api_base = settings.api_internal_url

    try:
        # Start the bulk generation job
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{api_base}/api/admin/sports/games/bulk-generate-async",
                json={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "leagues": leagues,
                    "force": False,  # Don't regenerate existing stories
                },
            )
            response.raise_for_status()
            job_data = response.json()

        job_id = job_data["job_id"]
        logger.info("scheduled_story_gen_job_started", job_id=job_id)

        # Poll for completion (max 30 minutes, check every 30 seconds)
        max_polls = 60
        poll_interval = 30

        for poll_num in range(max_polls):
            time.sleep(poll_interval)

            with httpx.Client(timeout=30.0) as client:
                status_response = client.get(
                    f"{api_base}/api/admin/sports/games/bulk-generate-status/{job_id}"
                )
                status_response.raise_for_status()
                status = status_response.json()

            state = status.get("state", "UNKNOWN")

            if state == "PROGRESS":
                logger.info(
                    "scheduled_story_gen_progress",
                    job_id=job_id,
                    current=status.get("current"),
                    total=status.get("total"),
                    successful=status.get("successful"),
                    failed=status.get("failed"),
                    skipped=status.get("skipped"),
                )
            elif state == "SUCCESS":
                result = status.get("result", {})
                logger.info(
                    "scheduled_story_gen_complete",
                    job_id=job_id,
                    total_games=result.get("total_games", 0),
                    successful=result.get("successful", 0),
                    failed=result.get("failed", 0),
                    skipped=result.get("skipped", 0),
                    generated=result.get("generated", 0),
                )
                return {
                    "job_id": job_id,
                    "state": "SUCCESS",
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "leagues": leagues,
                    **result,
                }
            elif state == "FAILURE":
                logger.error(
                    "scheduled_story_gen_failed",
                    job_id=job_id,
                    status=status.get("status"),
                )
                return {
                    "job_id": job_id,
                    "state": "FAILURE",
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "leagues": leagues,
                    "error": status.get("status"),
                }

        # Timed out waiting for completion
        logger.warning(
            "scheduled_story_gen_timeout",
            job_id=job_id,
            max_wait_minutes=max_polls * poll_interval / 60,
        )
        return {
            "job_id": job_id,
            "state": "TIMEOUT",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "leagues": leagues,
            "error": "Timed out waiting for job completion",
        }

    except httpx.HTTPStatusError as exc:
        logger.error(
            "scheduled_story_gen_http_error",
            status_code=exc.response.status_code,
            error=exc.response.text,
        )
        return {
            "state": "ERROR",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "leagues": leagues,
            "error": f"HTTP {exc.response.status_code}: {exc.response.text}",
        }
    except Exception as exc:
        logger.exception(
            "scheduled_story_gen_error",
            error=str(exc),
        )
        raise  # Let Celery retry
