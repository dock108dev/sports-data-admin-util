"""Scheduled ingestion orchestration for periodic scraping runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..utils.datetime_utils import now_utc


SCHEDULED_INGESTION_LEAGUES = ("NBA", "NHL", "NCAAB")


@dataclass(frozen=True)
class ScheduledIngestionSummary:
    runs_created: int
    runs_skipped: int
    run_failures: int
    enqueue_failures: int
    last_run_at: datetime


def build_scheduled_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Build the scheduled ingestion window (yesterday -> now + 24h in UTC)."""
    anchor = now or now_utc()
    start = (anchor - timedelta(days=1)).replace(tzinfo=timezone.utc)
    end = (anchor + timedelta(hours=24)).replace(tzinfo=timezone.utc)
    return start, end


def _coerce_date(value: datetime | None) -> datetime | None:
    if not value:
        return None
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def create_scrape_run(
    session: Session,
    league: db_models.SportsLeague,
    config: IngestionConfig,
    requested_by: str,
    scraper_type: str = "scheduled_ingestion",
) -> db_models.SportsScrapeRun:
    """Create a scrape run record for a scheduled ingestion."""
    run = db_models.SportsScrapeRun(
        scraper_type=scraper_type,
        league_id=league.id,
        season=config.season,
        season_type=config.season_type,
        start_date=_coerce_date(
            datetime.combine(config.start_date, datetime.min.time(), tzinfo=timezone.utc)
            if config.start_date
            else None
        ),
        end_date=_coerce_date(
            datetime.combine(config.end_date, datetime.min.time(), tzinfo=timezone.utc)
            if config.end_date
            else None
        ),
        status="pending",
        requested_by=requested_by,
        config=config.model_dump(mode="json"),
    )
    session.add(run)
    session.flush()
    return run


def schedule_ingestion_runs(
    *,
    leagues: Iterable[str] = SCHEDULED_INGESTION_LEAGUES,
    requested_by: str = "scheduler",
    now: datetime | None = None,
) -> ScheduledIngestionSummary:
    """Create scheduled scrape runs and enqueue them for execution."""
    start_dt, end_dt = build_scheduled_window(now)
    start_date = start_dt.date()
    end_date = end_dt.date()
    cutoff = now_utc() - timedelta(minutes=14)
    runs_created = 0
    runs_skipped = 0
    run_failures = 0
    enqueue_failures = 0

    logger.info(
        "scheduled_ingestion_start",
        leagues=list(leagues),
        window_start=str(start_dt),
        window_end=str(end_dt),
    )

    with get_session() as session:
        for league_code in leagues:
            league = (
                session.query(db_models.SportsLeague)
                .filter(db_models.SportsLeague.code == league_code)
                .first()
            )
            if not league:
                logger.warning("scheduled_ingestion_unknown_league", league=league_code)
                runs_skipped += 1
                continue

            recent_run = (
                session.query(db_models.SportsScrapeRun)
                .filter(db_models.SportsScrapeRun.league_id == league.id)
                .filter(db_models.SportsScrapeRun.scraper_type == "scheduled_ingestion")
                .filter(db_models.SportsScrapeRun.created_at >= cutoff)
                .first()
            )
            if recent_run:
                logger.info(
                    "scheduled_ingestion_recent_run_skipped",
                    league=league_code,
                    run_id=recent_run.id,
                    created_at=str(recent_run.created_at),
                )
                runs_skipped += 1
                continue

            config = IngestionConfig(
                league_code=league_code,
                start_date=start_date,
                end_date=end_date,
                boxscores=True,
                odds=True,
                social=league_code in ("NBA", "NHL"),
                pbp=True,
                only_missing=False,
            )

            try:
                run = create_scrape_run(session, league, config, requested_by=requested_by)
                runs_created += 1
            except Exception as exc:
                run_failures += 1
                logger.exception(
                    "scheduled_ingestion_run_create_failed",
                    league=league_code,
                    error=str(exc),
                )
                continue

            try:
                from ..celery_app import app as celery_app

                async_result = celery_app.send_task(
                    "run_scrape_job",
                    args=[run.id, config.model_dump(mode="json")],
                    queue="bets-scraper",
                    routing_key="bets-scraper",
                )
                run.job_id = async_result.id
                logger.info(
                    "scheduled_ingestion_enqueued",
                    league=league_code,
                    run_id=run.id,
                    job_id=run.job_id,
                )
            except Exception as exc:
                run.status = "error"
                run.error_details = f"Failed to enqueue scheduled ingestion: {exc}"
                enqueue_failures += 1
                logger.exception(
                    "scheduled_ingestion_enqueue_failed",
                    league=league_code,
                    run_id=run.id,
                    error=str(exc),
                )

    summary = ScheduledIngestionSummary(
        runs_created=runs_created,
        runs_skipped=runs_skipped,
        run_failures=run_failures,
        enqueue_failures=enqueue_failures,
        last_run_at=now_utc(),
    )
    logger.info(
        "scheduled_ingestion_complete",
        runs_created=summary.runs_created,
        runs_skipped=summary.runs_skipped,
        run_failures=summary.run_failures,
        enqueue_failures=summary.enqueue_failures,
        last_run_at=str(summary.last_run_at),
    )
    return summary
