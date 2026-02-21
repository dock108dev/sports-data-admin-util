"""Celery tasks for social collection.

These tasks run on the dedicated social-scraper worker for consistent IP/session.

Tasks:
- collect_social_for_league: Main entry point called from scheduled ingestion
- collect_team_social: Scrape tweets for teams in a date range
- map_social_to_games: Assign unmapped tweets to games
"""

from __future__ import annotations

from datetime import date

from celery import shared_task

from ..logging import logger


def _report_social_completion(
    scrape_run_id: int | None,
    result: dict | None,
    error: str | None,
) -> None:
    """Update the SportsScrapeRun summary with actual social stats.

    Replaces the "Social: dispatched to worker" placeholder text with
    real tweet counts. Called from collect_team_social on the social-scraper
    worker after collection finishes.

    All DB work is wrapped in try/except so reporting failures never crash the task.
    """
    try:
        from ..db import db_models, get_session

        # Build the replacement summary string
        if error:
            social_summary = f"Social: error ({error[:80]})"
        elif result:
            tweets = result.get("total_new_tweets", 0)
            mapped = result.get("mapping", {}).get("mapped", 0)
            social_summary = f"Social: {tweets} tweets ({mapped} mapped)"
        else:
            social_summary = "Social: 0 tweets (0 mapped)"

        # Update the SportsScrapeRun summary (replace placeholder)
        if scrape_run_id is not None:
            with get_session() as session:
                run = (
                    session.query(db_models.SportsScrapeRun)
                    .filter(db_models.SportsScrapeRun.id == scrape_run_id)
                    .first()
                )
                if run and run.summary and "Social: dispatched to worker" in run.summary:
                    run.summary = run.summary.replace(
                        "Social: dispatched to worker", social_summary
                    )
                    logger.info(
                        "social_completion_reported",
                        scrape_run_id=scrape_run_id,
                        social_summary=social_summary,
                    )
    except Exception as exc:
        logger.warning(
            "social_completion_report_failed",
            scrape_run_id=scrape_run_id,
            error=str(exc),
        )


@shared_task(name="handle_social_task_failure")
def handle_social_task_failure(
    task_id: str,
    scrape_run_id: int | None = None,
) -> None:
    """Celery link_error callback for collect_team_social failures.

    Called automatically when collect_team_social fails after all retries.
    Celery passes the failed task's ID as the first positional argument,
    followed by the args bound via `.s()`.

    Updates the SportsScrapeRun summary with the error message.
    (SportsJobRun tracking is handled inside collect_team_social itself.)
    """
    from celery.result import AsyncResult

    # Retrieve the exception from the failed task's result backend
    result = AsyncResult(task_id)
    error_msg = str(result.result) if result.result else "unknown error"

    logger.error(
        "social_task_failed_callback",
        task_id=task_id,
        scrape_run_id=scrape_run_id,
        error=error_msg,
    )
    _report_social_completion(scrape_run_id, result=None, error=error_msg)


@shared_task(
    name="collect_social_for_league",
    queue="social-scraper",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def collect_social_for_league(league: str) -> dict:
    """Collect social posts for a league. Runs on dedicated social-scraper worker.

    This is the main entry point for social collection, dispatched from
    run_scheduled_ingestion in scrape_tasks.py. It runs asynchronously
    (fire-and-forget) so sports ingestion doesn't wait for social.

    Collects tweets for all teams that played in the last 3 days, then
    maps unmapped tweets to games.

    Args:
        league: League code (NBA, NHL)

    Returns:
        Summary stats dict with social_posts and games_processed
    """
    from datetime import timedelta

    from ..db import get_session
    from ..social.team_collector import TeamTweetCollector
    from ..social.tweet_mapper import map_unmapped_tweets
    from ..utils.datetime_utils import today_et

    logger.info("social_task_started", league=league)

    end_date = today_et()
    start_date = end_date - timedelta(days=3)

    with get_session() as session:
        collector = TeamTweetCollector()
        result = collector.collect_for_date_range(
            session=session,
            league_code=league,
            start_date=start_date,
            end_date=end_date,
        )

        # Map newly collected tweets to games
        map_result = map_unmapped_tweets(session=session, batch_size=1000)
        result["mapping"] = map_result

    logger.info("social_task_complete", league=league, **{
        k: v for k, v in result.items() if k != "mapping"
    })
    return result


@shared_task(
    name="collect_team_social",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def collect_team_social(
    league_code: str,
    start_date: str,
    end_date: str,
    scrape_run_id: int | None = None,
) -> dict:
    """
    Collect tweets for all teams in a league that played in the date range.

    Job run tracking happens here on the social-scraper worker (not at
    dispatch time on the main scraper) so the SportsJobRun accurately
    reflects actual execution state.

    Args:
        league_code: League code (NBA, NHL, NCAAB)
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        scrape_run_id: Optional parent SportsScrapeRun ID for summary update

    Returns:
        Summary stats dict
    """
    from ..db import get_session
    from ..services.job_runs import track_job_run
    from ..social.team_collector import TeamTweetCollector
    from ..social.tweet_mapper import map_unmapped_tweets

    logger.info(
        "collect_team_social_start",
        league_code=league_code,
        start_date=start_date,
        end_date=end_date,
    )

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    with track_job_run("social", [league_code]) as tracker:
        with get_session() as session:
            collector = TeamTweetCollector()
            result = collector.collect_for_date_range(
                session=session,
                league_code=league_code,
                start_date=start,
                end_date=end,
            )

            # Always map tweets to games after collection
            map_result = map_unmapped_tweets(session=session, batch_size=1000)
            result["mapping"] = map_result

        tracker.summary_data = result

    logger.info(
        "collect_team_social_complete",
        league_code=league_code,
        result=result,
    )

    # Update parent SportsScrapeRun summary (replace "dispatched" placeholder)
    _report_social_completion(scrape_run_id, result, error=None)

    return result


@shared_task(
    name="map_social_to_games",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def map_social_to_games(batch_size: int = 1000) -> dict:
    """
    Map all unmapped tweets to games.

    Tweets are mapped based on posted_at falling within game windows.

    Args:
        batch_size: Number of tweets to process per batch

    Returns:
        Summary stats dict with mapped, no_game counts
    """
    from ..db import get_session
    from ..social.tweet_mapper import map_unmapped_tweets

    logger.info("map_social_to_games_start", batch_size=batch_size)

    with get_session() as session:
        result = map_unmapped_tweets(session=session, batch_size=batch_size)

    logger.info("map_social_to_games_complete", result=result)

    return result


@shared_task(
    name="collect_pregame_social",
    queue="social-scraper",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def collect_pregame_social() -> dict:
    """Collect social posts for teams with games today (runs hourly at :30).

    Queries today's scheduled/pregame/live games across all leagues,
    deduplicates teams, and collects tweets for each. Runs on the
    social-scraper queue with a 3-min cooldown between teams.

    Returns:
        Summary stats dict with teams_processed, total_new_tweets, errors
    """
    import time

    from ..db import db_models, get_session
    from ..services.job_runs import track_job_run
    from ..social.team_collector import TeamTweetCollector
    from ..social.tweet_mapper import map_unmapped_tweets
    from ..utils.datetime_utils import today_et

    game_date = today_et()
    logger.info("collect_pregame_social_start", game_date=str(game_date))

    with track_job_run("collect_pregame_social") as tracker, get_session() as session:
        # Find today's games that are scheduled, pregame, or live
        games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.game_date == game_date,
                db_models.SportsGame.status.in_([
                    db_models.GameStatus.scheduled.value,
                    db_models.GameStatus.pregame.value,
                    db_models.GameStatus.live.value,
                ]),
            )
            .all()
        )

        if not games:
            logger.info("collect_pregame_social_no_games", game_date=str(game_date))
            return {"game_date": str(game_date), "teams_processed": 0, "total_new_tweets": 0}

        # Deduplicate team IDs across all games
        team_ids: set[int] = set()
        for game in games:
            team_ids.add(game.home_team_id)
            team_ids.add(game.away_team_id)

        logger.info(
            "collect_pregame_social_found",
            game_date=str(game_date),
            games=len(games),
            teams=len(team_ids),
        )

        try:
            collector = TeamTweetCollector()
        except RuntimeError as exc:
            logger.error("collect_pregame_social_collector_unavailable", error=str(exc))
            return {
                "game_date": str(game_date),
                "teams_processed": 0,
                "total_new_tweets": 0,
                "error": str(exc),
            }

        total_new = 0
        teams_processed = 0
        errors = 0

        for i, team_id in enumerate(sorted(team_ids)):
            # Inter-team cooldown (3 min) — skip before the first team
            if i > 0:
                time.sleep(180)

            try:
                new_tweets = collector.collect_team_tweets(
                    session=session,
                    team_id=team_id,
                    start_date=game_date,
                    end_date=game_date,
                )
                total_new += new_tweets
                teams_processed += 1
                logger.info(
                    "collect_pregame_social_team_done",
                    team_id=team_id,
                    new_tweets=new_tweets,
                )
            except Exception as exc:
                errors += 1
                logger.warning(
                    "collect_pregame_social_team_error",
                    team_id=team_id,
                    error=str(exc),
                )

        # Map newly collected tweets to games
        map_result = map_unmapped_tweets(session=session, batch_size=1000)

    result = {
        "game_date": str(game_date),
        "teams_processed": teams_processed,
        "total_new_tweets": total_new,
        "mapped": map_result.get("mapped", 0),
        "errors": errors,
    }

    logger.info("collect_pregame_social_complete", **result)
    tracker.summary_data = result

    return result


@shared_task(name="get_social_mapping_stats")
def get_social_mapping_stats() -> dict:
    """
    Get current mapping status distribution for team_social_posts.

    Returns:
        Dict with counts per mapping_status (unmapped, mapped, no_game)
    """
    from ..db import get_session
    from ..social.tweet_mapper import get_mapping_stats

    logger.info("get_social_mapping_stats_start")

    with get_session() as session:
        result = get_mapping_stats(session)

    logger.info("get_social_mapping_stats_complete", result=result)

    return result
