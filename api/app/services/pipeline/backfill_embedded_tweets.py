"""Backfill embedded tweets for game flows missing social data.

When the pipeline and social scraping run concurrently, VALIDATE_BLOCKS
may find zero in_game tweets, leaving all blocks with
embedded_social_post_id = NULL. This module retroactively attaches
tweets once they become available.

Two entry points:
1. backfill_embedded_tweets_for_game() — single game, called from
   final_whistle_tasks after social scrape completes
2. find_and_backfill_all() — bulk scan, called from the daily sweep
"""

from __future__ import annotations

import logging
from datetime import timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import attributes

from ...db import AsyncSession
from ...db.social import TeamSocialPost
from ...db.sports import SportsGame
from ...db.story import SportsGameFlow
from .stages.embedded_tweets import select_and_assign_embedded_tweets

logger = logging.getLogger(__name__)

STORY_VERSION = "v2-moments"


async def backfill_embedded_tweets_for_game(
    session: AsyncSession,
    game_id: int,
) -> dict[str, Any]:
    """Backfill embedded tweets for a single game's flow.

    Eligibility: flow exists, all blocks have embedded_social_post_id is None,
    and in_game tweets are now available.

    Args:
        session: Async database session.
        game_id: ID of the game to backfill.

    Returns:
        Dict with status and details of the backfill operation.
    """
    # Load the flow
    flow_result = await session.execute(
        select(SportsGameFlow).where(
            SportsGameFlow.game_id == game_id,
            SportsGameFlow.story_version == STORY_VERSION,
        )
    )
    flow = flow_result.scalar_one_or_none()

    if not flow:
        logger.debug("backfill_embedded_tweets_no_flow", game_id=game_id)
        return {"game_id": game_id, "status": "no_flow"}

    blocks = flow.blocks_json
    if not blocks:
        logger.debug("backfill_embedded_tweets_no_blocks", game_id=game_id)
        return {"game_id": game_id, "status": "no_blocks"}

    # Check eligibility: ALL blocks must have embedded_social_post_id is None
    has_any_tweet = any(
        b.get("embedded_social_post_id") is not None for b in blocks
    )
    if has_any_tweet:
        logger.debug(
            "backfill_embedded_tweets_already_has_tweets", game_id=game_id
        )
        return {"game_id": game_id, "status": "already_has_tweets"}

    # Load game for tip_time
    game_result = await session.execute(
        select(SportsGame).where(SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()
    if not game:
        return {"game_id": game_id, "status": "game_not_found"}

    game_start = game.tip_time or game.game_date
    if game_start and game_start.tzinfo is None:
        game_start = game_start.replace(tzinfo=timezone.utc)

    # Load social posts (same query as _attach_embedded_tweets in validate_blocks)
    social_result = await session.execute(
        select(TeamSocialPost)
        .where(
            TeamSocialPost.game_id == game_id,
            TeamSocialPost.mapping_status == "mapped",
        )
        .order_by(TeamSocialPost.posted_at)
    )
    social_posts = social_result.scalars().all()

    if not social_posts:
        logger.debug("backfill_embedded_tweets_no_social", game_id=game_id)
        return {"game_id": game_id, "status": "no_social_posts"}

    # Convert to dict format (same as validate_blocks._attach_embedded_tweets)
    tweets: list[dict[str, Any]] = []
    for post in social_posts:
        if not post.tweet_text:
            continue
        tweets.append({
            "id": post.id,
            "posted_at": post.posted_at,
            "text": post.tweet_text,
            "author": post.source_handle or "",
            "phase": post.game_phase or "in_game",
            "has_media": post.has_video or bool(post.image_url),
            "media_type": post.media_type,
            "post_url": post.post_url,
            "is_team_account": bool(post.source_handle),
        })

    # Only in-game tweets belong in narrative blocks
    tweets = [t for t in tweets if t["phase"] == "in_game"]

    if not tweets:
        logger.debug(
            "backfill_embedded_tweets_no_in_game", game_id=game_id
        )
        return {"game_id": game_id, "status": "no_in_game_tweets"}

    # Run the same selection + assignment logic used during pipeline
    updated_blocks, selection = select_and_assign_embedded_tweets(
        tweets=tweets,
        blocks=blocks,
        game_start=game_start,
    )

    assigned_count = sum(
        1 for b in updated_blocks if b.get("embedded_social_post_id")
    )

    if assigned_count == 0:
        logger.info(
            "backfill_embedded_tweets_none_assigned",
            game_id=game_id,
            candidates=len(tweets),
        )
        return {
            "game_id": game_id,
            "status": "no_tweets_assigned",
            "candidates": len(tweets),
        }

    # Persist updated blocks
    flow.blocks_json = updated_blocks
    attributes.flag_modified(flow, "blocks_json")

    logger.info(
        "backfill_embedded_tweets_success",
        game_id=game_id,
        flow_id=flow.id,
        assigned=assigned_count,
        candidates=selection.total_candidates,
    )

    return {
        "game_id": game_id,
        "status": "backfilled",
        "flow_id": flow.id,
        "tweets_assigned": assigned_count,
        "candidates": selection.total_candidates,
    }


async def find_and_backfill_all(
    session: AsyncSession,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """Scan recent flows and backfill any with all-NULL embedded tweets.

    Args:
        session: Async database session.
        lookback_days: How many days back to scan.

    Returns:
        Aggregate results dict.
    """
    from ...utils.datetime_utils import now_utc

    cutoff = now_utc() - timedelta(days=lookback_days)

    flow_result = await session.execute(
        select(SportsGameFlow).where(
            SportsGameFlow.story_version == STORY_VERSION,
            SportsGameFlow.blocks_json.isnot(None),
            SportsGameFlow.generated_at >= cutoff,
        )
    )
    flows = flow_result.scalars().all()

    results: list[dict[str, Any]] = []
    total_backfilled = 0

    for flow in flows:
        result = await backfill_embedded_tweets_for_game(session, flow.game_id)
        results.append(result)
        if result.get("status") == "backfilled":
            total_backfilled += 1

    logger.info(
        "backfill_embedded_tweets_bulk_complete",
        checked=len(flows),
        backfilled=total_backfilled,
        lookback_days=lookback_days,
    )

    return {
        "total_checked": len(flows),
        "total_backfilled": total_backfilled,
        "results": results,
    }
