"""Final-whistle social scrape: Social Scrape #1 triggered when a game goes FINAL.

Collects pregame and in-game tweets for both teams, maps them to the game.
Postgame tweets are discarded — they are captured later by Social Scrape #2
in the daily sweep. Flow generation is dispatched independently from
polling_tasks.py with a 60-min delay.

Non-negotiable rules:
- Exactly two social scrapes per game (this is #1)
- No social scraping while a game is live
- No social post is ever stored twice (dedup via external_post_id)
- Game Flow structure is generated once and never mutates — the sole
  exception is embedded_social_post_id backfill, which attaches tweet
  references to blocks whose embedded_social_post_id was NULL at
  generation time (see backfill_embedded_tweets module)
- Postgame socials never alter the Game Flow
"""

from __future__ import annotations

import time

from celery import shared_task

from ..db import get_session
from ..logging import logger

# Cooldown between games (seconds) — rate limit protection for X scraping.
# Since the social-scraper queue runs concurrency=1, this sleep at the end
# of each task ensures a gap before the next game's scrape starts.
_INTER_GAME_COOLDOWN_SECONDS = 180


@shared_task(
    name="run_final_whistle_social",
    queue="social-scraper",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_final_whistle_social(game_id: int) -> dict:
    """Social Scrape #1: collect game-day tweets after game goes FINAL.

    Steps:
    1. Validate game is FINAL and social_scrape_1_at is NULL
    2. Collect tweets for each team (home then away, no cooldown between them)
    3. Map to game, tag phase (pregame/in_game only; discard postgame)
    4. Set game.social_scrape_1_at = now()
    5. Backfill embedded tweets if flow already exists
    6. Sleep 3 min as inter-game cooldown (rate limit protection)

    Rate limiting: This runs on the social-scraper queue (concurrency=1).
    If 5 games finish simultaneously, tasks queue up and execute one at a time.
    The 3-minute cooldown between games keeps X scraping sustainable.
    """
    from ..db import db_models
    from ..services.job_runs import complete_job_run, start_job_run
    from ..social.team_collector import TeamTweetCollector
    from ..social.tweet_mapper import map_tweets_for_team
    from ..utils.datetime_utils import now_utc

    logger.info("final_whistle_social_start", game_id=game_id)

    with get_session() as session:
        game = session.query(db_models.SportsGame).get(game_id)

        if not game:
            logger.warning("final_whistle_game_not_found", game_id=game_id)
            return {"game_id": game_id, "status": "not_found"}

        if game.status != db_models.GameStatus.final.value:
            logger.info(
                "final_whistle_skip_not_final",
                game_id=game_id,
                status=game.status,
            )
            return {"game_id": game_id, "status": "skipped", "reason": "not_final"}

        if game.social_scrape_1_at is not None:
            logger.info(
                "final_whistle_skip_already_scraped",
                game_id=game_id,
                scraped_at=str(game.social_scrape_1_at),
            )
            return {"game_id": game_id, "status": "skipped", "reason": "already_scraped"}

        # Start tracking job run (after skip checks, so skips don't create rows)
        job_run_id = start_job_run("final_whistle_social", [])

        # Determine game_date for collection window
        game_date = game.game_date.date() if hasattr(game.game_date, "date") else game.game_date

        # Collect tweets for both teams
        team_ids = [game.home_team_id, game.away_team_id]
        total_new = 0
        teams_scraped = 0

        try:
            collector = TeamTweetCollector()
        except RuntimeError as exc:
            logger.error(
                "final_whistle_collector_unavailable",
                game_id=game_id,
                error=str(exc),
            )
            return {"game_id": game_id, "status": "error", "reason": "collector_unavailable"}

        for team_id in team_ids:
            try:
                new_tweets = collector.collect_team_tweets(
                    session=session,
                    team_id=team_id,
                    start_date=game_date,
                    end_date=game_date,
                )
                total_new += new_tweets
                teams_scraped += 1
                logger.info(
                    "final_whistle_team_collected",
                    game_id=game_id,
                    team_id=team_id,
                    new_tweets=new_tweets,
                )
            except Exception as exc:
                logger.warning(
                    "final_whistle_team_collect_error",
                    game_id=game_id,
                    team_id=team_id,
                    error=str(exc),
                )

        # Map unmapped tweets for both teams to this game
        mapped_total = 0
        for team_id in team_ids:
            try:
                result = map_tweets_for_team(session, team_id)
                mapped_total += result.get("mapped", 0)
            except Exception as exc:
                logger.warning(
                    "final_whistle_map_error",
                    game_id=game_id,
                    team_id=team_id,
                    error=str(exc),
                )

        # Discard postgame tweets: set mapping_status back to 'no_game' for any
        # tweets mapped to this game with game_phase='postgame'
        postgame_discarded = (
            session.query(db_models.TeamSocialPost)
            .filter(
                db_models.TeamSocialPost.game_id == game_id,
                db_models.TeamSocialPost.mapping_status == "mapped",
                db_models.TeamSocialPost.game_phase == "postgame",
            )
            .update(
                {"mapping_status": "no_game", "game_id": None, "game_phase": None},
                synchronize_session="fetch",
            )
        )
        if postgame_discarded:
            logger.info(
                "final_whistle_postgame_discarded",
                game_id=game_id,
                count=postgame_discarded,
            )

        # Mark Social Scrape #1 complete
        game.social_scrape_1_at = now_utc()
        game.last_social_at = now_utc()
        session.commit()

    # Flow generation is now dispatched independently from polling_tasks.py
    # with a 60-min delay (countdown=3600), decoupled from social scraping.

    # Backfill embedded tweets if a flow already exists for this game
    try:
        _backfill_tweets_for_game(game_id)
    except Exception as exc:
        logger.warning(
            "final_whistle_backfill_tweets_error",
            game_id=game_id,
            error=str(exc),
        )

    # Inter-game cooldown: sleep so the next game's task doesn't hit X too fast
    logger.info(
        "final_whistle_cooldown",
        game_id=game_id,
        seconds=_INTER_GAME_COOLDOWN_SECONDS,
    )
    time.sleep(_INTER_GAME_COOLDOWN_SECONDS)

    logger.info(
        "final_whistle_social_complete",
        game_id=game_id,
        teams_scraped=teams_scraped,
        total_new=total_new,
        mapped=mapped_total,
        postgame_discarded=postgame_discarded,
    )

    complete_job_run(
        job_run_id,
        status="success",
        summary_data={
            "game_id": game_id,
            "teams_scraped": teams_scraped,
            "total_new_tweets": total_new,
            "mapped": mapped_total,
            "postgame_discarded": postgame_discarded,
        },
    )

    return {
        "game_id": game_id,
        "status": "success",
        "teams_scraped": teams_scraped,
        "total_new_tweets": total_new,
        "mapped": mapped_total,
        "postgame_discarded": postgame_discarded,
    }


def _backfill_tweets_for_game(game_id: int) -> dict:
    """Call the API to backfill embedded tweets for a single game.

    Safe to call regardless of flow state:
    - No flow exists -> returns "no_flow", harmless no-op
    - Flow already has tweets -> returns "already_has_tweets", no-op
    - Flow has all-NULL tweets and in_game tweets exist -> backfills them
    """
    import httpx

    from ..api_client import get_api_headers
    from ..config import settings

    api_base = settings.api_internal_url
    url = f"{api_base}/api/admin/sports/pipeline/backfill-embedded-tweets"

    with httpx.Client(timeout=30.0, headers=get_api_headers()) as client:
        response = client.post(url, params={"game_id": game_id})
        response.raise_for_status()
        result = response.json()

    logger.info(
        "final_whistle_backfill_tweets_result",
        game_id=game_id,
        total_backfilled=result.get("total_backfilled", 0),
    )

    return result
