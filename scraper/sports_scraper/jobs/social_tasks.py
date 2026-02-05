"""Celery tasks for team-centric social collection.

These tasks implement the two-phase social collection architecture:
1. collect_team_social: Scrape tweets for teams in a date range
2. map_social_to_games: Assign unmapped tweets to games
"""

from __future__ import annotations

from datetime import date

from celery import shared_task

from ..logging import logger


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
) -> dict:
    """
    Collect tweets for all teams in a league that played in the date range.

    This is Phase 1 of the two-phase social collection architecture.
    Tweets are saved to team_social_posts with mapping_status='unmapped'.

    Args:
        league_code: League code (NBA, NHL, NCAAB)
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        Summary stats dict
    """
    from ..db import get_session
    from ..social.team_collector import TeamTweetCollector

    logger.info(
        "collect_team_social_start",
        league_code=league_code,
        start_date=start_date,
        end_date=end_date,
    )

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    with get_session() as session:
        collector = TeamTweetCollector()
        result = collector.collect_for_date_range(
            session=session,
            league_code=league_code,
            start_date=start,
            end_date=end,
        )

    logger.info(
        "collect_team_social_complete",
        league_code=league_code,
        result=result,
    )

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

    This is Phase 2 of the two-phase social collection architecture.
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
