"""Tweet-to-game mapping for the two-phase social architecture.

Phase 2 (MAP): This module assigns unmapped tweets to games based on
posted_at timestamps falling within game windows.

Phase 1 (COLLECT): See team_collector.py for collecting team tweets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ..logging import logger
from ..utils.datetime_utils import now_utc

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Default game window configuration
# These values define when a tweet is considered part of a game
DEFAULT_PREGAME_HOURS = 3  # Hours before tip_time to include
DEFAULT_POSTGAME_HOURS = 3  # Hours after estimated game end to include
DEFAULT_GAME_DURATION_HOURS = 3  # Estimated game duration


def get_game_window(
    game,
    pregame_hours: int = DEFAULT_PREGAME_HOURS,
    postgame_hours: int = DEFAULT_POSTGAME_HOURS,
    game_duration_hours: int = DEFAULT_GAME_DURATION_HOURS,
) -> tuple[datetime, datetime]:
    """
    Calculate the tweet window for a game.

    The window includes:
    - pregame_hours before tip_time
    - The game itself (estimated game_duration_hours)
    - postgame_hours after game end

    Args:
        game: SportsGame object
        pregame_hours: Hours before game to include
        postgame_hours: Hours after game end to include
        game_duration_hours: Estimated game duration

    Returns:
        Tuple of (window_start, window_end) as timezone-aware datetimes
    """
    # Prefer tip_time if available, otherwise fall back to game_date
    if game.tip_time:
        game_start = game.tip_time
    else:
        game_start = game.game_date
        # If game_date is at midnight, estimate 7 PM ET (00:00 UTC + 19h)
        if game_start.hour == 0 and game_start.minute == 0:
            game_start = game_start + timedelta(hours=19)

    # Ensure timezone awareness
    if game_start.tzinfo is None:
        game_start = game_start.replace(tzinfo=timezone.utc)

    # Use actual end_time if available and reasonable, otherwise estimate
    if game.end_time and game.end_time > game_start:
        game_end = game.end_time
        if game_end.tzinfo is None:
            game_end = game_end.replace(tzinfo=timezone.utc)
    else:
        game_end = game_start + timedelta(hours=game_duration_hours)

    # Calculate window
    window_start = game_start - timedelta(hours=pregame_hours)
    window_end = game_end + timedelta(hours=postgame_hours)

    return window_start, window_end


def map_unmapped_tweets(
    session: "Session",
    batch_size: int = 1000,
) -> dict:
    """
    Assign unmapped tweets to games.

    For each unmapped tweet:
    1. Find games where the tweet's team played
    2. Check if posted_at falls within a game's window
    3. Set game_id and mapping_status='mapped', or 'no_game' if no match

    Args:
        session: Database session
        batch_size: Number of tweets to process per batch

    Returns:
        Summary stats dict with mapped, no_game, errors counts
    """
    from ..db import db_models
    from sqlalchemy import or_

    # Counters
    total_processed = 0
    mapped_count = 0
    no_game_count = 0
    errors: list[str] = []

    logger.info("tweet_mapper_start", batch_size=batch_size)

    # Process in batches to avoid memory issues
    while True:
        # Get batch of unmapped tweets
        unmapped_tweets = (
            session.query(db_models.TeamSocialPost)
            .filter(db_models.TeamSocialPost.mapping_status == "unmapped")
            .limit(batch_size)
            .all()
        )

        if not unmapped_tweets:
            break

        logger.debug("tweet_mapper_batch", batch_count=len(unmapped_tweets))

        for tweet in unmapped_tweets:
            total_processed += 1

            try:
                # Ensure posted_at is timezone-aware
                posted_at = tweet.posted_at
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)

                # Find games where this team played around the tweet time
                # Look for games in a wider window first (7 days before and after)
                search_start = posted_at - timedelta(days=1)
                search_end = posted_at + timedelta(days=1)

                potential_games = (
                    session.query(db_models.SportsGame)
                    .filter(
                        or_(
                            db_models.SportsGame.home_team_id == tweet.team_id,
                            db_models.SportsGame.away_team_id == tweet.team_id,
                        ),
                        db_models.SportsGame.game_date >= search_start,
                        db_models.SportsGame.game_date <= search_end,
                    )
                    .all()
                )

                # Check each potential game's window
                matched_game = None
                for game in potential_games:
                    window_start, window_end = get_game_window(game)
                    if window_start <= posted_at <= window_end:
                        matched_game = game
                        break

                if matched_game:
                    tweet.game_id = matched_game.id
                    tweet.mapping_status = "mapped"
                    tweet.updated_at = now_utc()
                    mapped_count += 1
                    logger.debug(
                        "tweet_mapper_matched",
                        tweet_id=tweet.id,
                        game_id=matched_game.id,
                        posted_at=str(posted_at),
                    )
                else:
                    tweet.mapping_status = "no_game"
                    tweet.updated_at = now_utc()
                    no_game_count += 1
                    logger.debug(
                        "tweet_mapper_no_match",
                        tweet_id=tweet.id,
                        team_id=tweet.team_id,
                        posted_at=str(posted_at),
                    )

            except Exception as exc:
                error_msg = f"Tweet {tweet.id}: {str(exc)}"
                errors.append(error_msg)
                logger.exception(
                    "tweet_mapper_error",
                    tweet_id=tweet.id,
                    error=str(exc),
                )

        # Commit batch
        session.commit()

        logger.debug(
            "tweet_mapper_batch_complete",
            total_processed=total_processed,
            mapped=mapped_count,
            no_game=no_game_count,
        )

    logger.info(
        "tweet_mapper_complete",
        total_processed=total_processed,
        mapped=mapped_count,
        no_game=no_game_count,
        errors_count=len(errors),
    )

    return {
        "total_processed": total_processed,
        "mapped": mapped_count,
        "no_game": no_game_count,
        "errors": errors if errors else None,
    }


def map_tweets_for_team(
    session: "Session",
    team_id: int,
) -> dict:
    """
    Map unmapped tweets for a specific team.

    Args:
        session: Database session
        team_id: Team ID to process

    Returns:
        Summary stats dict
    """
    from ..db import db_models

    logger.info("tweet_mapper_team_start", team_id=team_id)

    # Get unmapped tweets for this team
    unmapped_tweets = (
        session.query(db_models.TeamSocialPost)
        .filter(
            db_models.TeamSocialPost.team_id == team_id,
            db_models.TeamSocialPost.mapping_status == "unmapped",
        )
        .all()
    )

    if not unmapped_tweets:
        logger.info("tweet_mapper_team_no_unmapped", team_id=team_id)
        return {"team_id": team_id, "processed": 0, "mapped": 0, "no_game": 0}

    # Process each tweet
    mapped_count = 0
    no_game_count = 0

    for tweet in unmapped_tweets:
        posted_at = tweet.posted_at
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)

        # Find games
        search_start = posted_at - timedelta(days=1)
        search_end = posted_at + timedelta(days=1)

        potential_games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.home_team_id == team_id,
                db_models.SportsGame.game_date >= search_start,
                db_models.SportsGame.game_date <= search_end,
            )
            .union(
                session.query(db_models.SportsGame).filter(
                    db_models.SportsGame.away_team_id == team_id,
                    db_models.SportsGame.game_date >= search_start,
                    db_models.SportsGame.game_date <= search_end,
                )
            )
            .all()
        )

        matched_game = None
        for game in potential_games:
            window_start, window_end = get_game_window(game)
            if window_start <= posted_at <= window_end:
                matched_game = game
                break

        if matched_game:
            tweet.game_id = matched_game.id
            tweet.mapping_status = "mapped"
            tweet.updated_at = now_utc()
            mapped_count += 1
        else:
            tweet.mapping_status = "no_game"
            tweet.updated_at = now_utc()
            no_game_count += 1

    session.commit()

    logger.info(
        "tweet_mapper_team_complete",
        team_id=team_id,
        processed=len(unmapped_tweets),
        mapped=mapped_count,
        no_game=no_game_count,
    )

    return {
        "team_id": team_id,
        "processed": len(unmapped_tweets),
        "mapped": mapped_count,
        "no_game": no_game_count,
    }


def get_mapping_stats(session: "Session") -> dict:
    """
    Get current mapping status distribution.

    Args:
        session: Database session

    Returns:
        Dict with counts per mapping_status
    """
    from ..db import db_models
    from sqlalchemy import func

    results = (
        session.query(
            db_models.TeamSocialPost.mapping_status,
            func.count(db_models.TeamSocialPost.id),
        )
        .group_by(db_models.TeamSocialPost.mapping_status)
        .all()
    )

    return {status: count for status, count in results}
