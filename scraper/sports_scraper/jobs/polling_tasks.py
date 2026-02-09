"""Polling tasks for game-state-machine architecture.

These tasks run at high frequency (3-5 min) and only touch games that
need attention right now, unlike the old batch sweeps that processed
everything for the last 96 hours.

Rate limit safeguards:
- Redis lock per task (prevents overlap from slow execution)
- 1-2s random jitter between API calls
- Max 30 API calls per PBP cycle
- 429 response → back off 60s, skip remaining games
"""

from __future__ import annotations

import random
import time

from celery import shared_task

from ..db import get_session
from ..logging import logger

# Maximum API calls per PBP polling cycle to stay within rate limits
_MAX_PBP_CALLS_PER_CYCLE = 30

# Jitter between API calls (seconds)
_JITTER_MIN = 1.0
_JITTER_MAX = 2.0

# Backoff on 429 responses
_RATE_LIMIT_BACKOFF_SECONDS = 60


from ..utils.redis_lock import acquire_redis_lock as _acquire_redis_lock
from ..utils.redis_lock import release_redis_lock as _release_redis_lock
from ..utils.redis_lock import LOCK_TIMEOUT_5MIN, LOCK_TIMEOUT_10MIN


@shared_task(name="update_game_states")
def update_game_states_task() -> dict:
    """Promote games through lifecycle states (runs every 3 min).

    Pure DB — no external API calls. Handles:
    - scheduled → pregame (within pregame_window_hours of tip_time)
    - final → archived (>7 days with timeline artifacts)
    """
    from ..services.game_state_updater import update_game_states

    if not _acquire_redis_lock("lock:update_game_states", timeout=180):
        logger.debug("update_game_states_skipped_locked")
        return {"skipped": True, "reason": "locked"}

    try:
        with get_session() as session:
            counts = update_game_states(session)
        return counts
    finally:
        _release_redis_lock("lock:update_game_states")


@shared_task(name="poll_live_pbp")
def poll_live_pbp_task() -> dict:
    """Poll PBP + status for pregame/live games (runs every 5 min).

    For each game needing PBP:
    1. Check scoreboard/schedule API for current game status
    2. If API says "live" and game is pregame → transition to live
    3. If API says "final" → transition to final, set end_time
    4. Fetch fresh PBP data

    NCAAB skipped initially (too many games for live polling).
    """
    from ..services.active_games import ActiveGamesResolver
    from ..persistence.games import resolve_status_transition
    from ..db import db_models
    from ..utils.datetime_utils import now_utc

    if not _acquire_redis_lock("lock:poll_live_pbp", timeout=LOCK_TIMEOUT_5MIN):
        logger.debug("poll_live_pbp_skipped_locked")
        return {"skipped": True, "reason": "locked"}

    try:
        resolver = ActiveGamesResolver()

        with get_session() as session:
            games = resolver.get_games_needing_pbp(session)

            if not games:
                logger.debug("poll_live_pbp_no_games")
                return {"games_polled": 0}

            logger.info("poll_live_pbp_start", games_count=len(games))

            api_calls = 0
            games_polled = 0
            transitions: list[dict] = []
            pbp_updated = 0
            rate_limited = False

            for game in games:
                if api_calls >= _MAX_PBP_CALLS_PER_CYCLE:
                    logger.info("poll_live_pbp_max_calls_reached", api_calls=api_calls)
                    break

                if rate_limited:
                    break

                # Add jitter between calls
                if api_calls > 0:
                    time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

                try:
                    result = _poll_single_game_pbp(session, game)
                    api_calls += result.get("api_calls", 1)
                    games_polled += 1

                    if result.get("transition"):
                        transitions.append(result["transition"])
                        # Edge-trigger: dispatch social scrape #1 → flow on live→final
                        tr = result["transition"]
                        if tr["to"] == "final":
                            try:
                                from .final_whistle_tasks import run_final_whistle_social
                                run_final_whistle_social.apply_async(
                                    args=[tr["game_id"]],
                                    countdown=300,  # 5 min buffer for PBP to settle
                                    queue="social-scraper",
                                )
                                logger.info(
                                    "final_whistle_social_dispatched",
                                    game_id=tr["game_id"],
                                )
                            except Exception as flow_exc:
                                logger.warning(
                                    "final_whistle_social_dispatch_error",
                                    game_id=tr["game_id"],
                                    error=str(flow_exc),
                                )
                    if result.get("pbp_events", 0) > 0:
                        pbp_updated += 1

                except _RateLimitError:
                    logger.warning(
                        "poll_live_pbp_rate_limited",
                        game_id=game.id,
                        api_calls_so_far=api_calls,
                    )
                    rate_limited = True
                    time.sleep(_RATE_LIMIT_BACKOFF_SECONDS)

                except Exception as exc:
                    logger.warning(
                        "poll_live_pbp_game_error",
                        game_id=game.id,
                        error=str(exc),
                    )
                    continue

            logger.info(
                "poll_live_pbp_complete",
                games_polled=games_polled,
                api_calls=api_calls,
                transitions=len(transitions),
                pbp_updated=pbp_updated,
                rate_limited=rate_limited,
            )

            return {
                "games_polled": games_polled,
                "api_calls": api_calls,
                "transitions": transitions,
                "pbp_updated": pbp_updated,
                "rate_limited": rate_limited,
            }

    finally:
        _release_redis_lock("lock:poll_live_pbp")


class _RateLimitError(Exception):
    """Raised when an API returns 429."""


def _poll_single_game_pbp(session, game) -> dict:
    """Poll a single game for status + PBP updates.

    Returns dict with api_calls count, transition info, and pbp_events.
    """
    from ..db import db_models
    from ..persistence.games import resolve_status_transition
    from ..persistence.plays import upsert_plays
    from ..utils.datetime_utils import now_utc

    league = session.query(db_models.SportsLeague).get(game.league_id)
    if not league:
        return {"api_calls": 0}

    league_code = league.code
    result: dict = {"api_calls": 0}

    if league_code == "NBA":
        result = _poll_nba_game(session, game)
    elif league_code == "NHL":
        result = _poll_nhl_game(session, game)

    return result


def _poll_nba_game(session, game) -> dict:
    """Poll a single NBA game via the NBA live API."""
    from ..live.nba import NBALiveFeedClient
    from ..db import db_models
    from ..persistence.plays import upsert_plays
    from ..persistence.games import resolve_status_transition
    from ..utils.datetime_utils import now_utc

    nba_game_id = (game.external_ids or {}).get("nba_game_id")
    if not nba_game_id:
        logger.debug("poll_nba_skip_no_game_id", game_id=game.id)
        return {"api_calls": 0}

    client = NBALiveFeedClient()
    result: dict = {"api_calls": 0}

    # Fetch scoreboard for status check
    try:
        game_day = game.game_date.date() if game.game_date else None
        if game_day:
            scoreboard_games = client.fetch_scoreboard(game_day)
            result["api_calls"] += 1

            # Find this game in the scoreboard
            for sg in scoreboard_games:
                if sg.game_id == nba_game_id:
                    # Check for status transition
                    new_status = resolve_status_transition(game.status, sg.status)
                    if new_status != game.status:
                        old_status = game.status
                        game.status = new_status
                        game.updated_at = now_utc()

                        # Set end_time when transitioning to final
                        if new_status == db_models.GameStatus.final.value and game.end_time is None:
                            game.end_time = now_utc()

                        result["transition"] = {
                            "game_id": game.id,
                            "from": old_status,
                            "to": new_status,
                        }
                        logger.info(
                            "poll_pbp_status_transition",
                            game_id=game.id,
                            league="NBA",
                            from_status=old_status,
                            to_status=new_status,
                        )

                    # Update scores
                    if sg.home_score is not None:
                        game.home_score = sg.home_score
                    if sg.away_score is not None:
                        game.away_score = sg.away_score
                    break
    except Exception as exc:
        if "429" in str(exc):
            raise _RateLimitError() from exc
        logger.warning("poll_nba_scoreboard_error", game_id=game.id, error=str(exc))

    # Fetch PBP if game is live or pregame (not for games that just went final)
    if game.status in (db_models.GameStatus.live.value, db_models.GameStatus.pregame.value):
        try:
            payload = client.fetch_play_by_play(nba_game_id)
            result["api_calls"] += 1

            if payload.plays:
                inserted = upsert_plays(session, game.id, payload.plays, source="nba_api")
                result["pbp_events"] = inserted
                game.last_pbp_at = now_utc()
        except Exception as exc:
            if "429" in str(exc):
                raise _RateLimitError() from exc
            logger.warning("poll_nba_pbp_error", game_id=game.id, error=str(exc))

    return result


def _poll_nhl_game(session, game) -> dict:
    """Poll a single NHL game via the NHL live API."""
    from ..live.nhl import NHLLiveFeedClient
    from ..db import db_models
    from ..persistence.plays import upsert_plays
    from ..persistence.games import resolve_status_transition
    from ..utils.datetime_utils import now_utc

    nhl_game_pk = (game.external_ids or {}).get("nhl_game_pk")
    if not nhl_game_pk:
        logger.debug("poll_nhl_skip_no_game_pk", game_id=game.id)
        return {"api_calls": 0}

    try:
        nhl_game_id = int(nhl_game_pk)
    except (ValueError, TypeError):
        logger.warning("poll_nhl_invalid_game_pk", game_id=game.id, nhl_game_pk=nhl_game_pk)
        return {"api_calls": 0}

    client = NHLLiveFeedClient()
    result: dict = {"api_calls": 0}

    # Fetch schedule for status check
    try:
        game_day = game.game_date.date() if game.game_date else None
        if game_day:
            schedule_games = client.fetch_schedule(game_day, game_day)
            result["api_calls"] += 1

            for sg in schedule_games:
                if sg.game_id == nhl_game_id:
                    new_status = resolve_status_transition(game.status, sg.status)
                    if new_status != game.status:
                        old_status = game.status
                        game.status = new_status
                        game.updated_at = now_utc()

                        if new_status == db_models.GameStatus.final.value and game.end_time is None:
                            game.end_time = now_utc()

                        result["transition"] = {
                            "game_id": game.id,
                            "from": old_status,
                            "to": new_status,
                        }
                        logger.info(
                            "poll_pbp_status_transition",
                            game_id=game.id,
                            league="NHL",
                            from_status=old_status,
                            to_status=new_status,
                        )

                    if sg.home_score is not None:
                        game.home_score = sg.home_score
                    if sg.away_score is not None:
                        game.away_score = sg.away_score
                    break
    except Exception as exc:
        if "429" in str(exc):
            raise _RateLimitError() from exc
        logger.warning("poll_nhl_schedule_error", game_id=game.id, error=str(exc))

    # Fetch PBP if game is live or pregame
    if game.status in (db_models.GameStatus.live.value, db_models.GameStatus.pregame.value):
        try:
            payload = client.fetch_play_by_play(nhl_game_id)
            result["api_calls"] += 1

            if payload.plays:
                inserted = upsert_plays(session, game.id, payload.plays, source="nhl_api")
                result["pbp_events"] = inserted
                game.last_pbp_at = now_utc()
        except Exception as exc:
            if "429" in str(exc):
                raise _RateLimitError() from exc
            logger.warning("poll_nhl_pbp_error", game_id=game.id, error=str(exc))

    return result


@shared_task(name="poll_active_odds")
def poll_active_odds_task() -> dict:
    """Sync odds for active games only (replaces broad 30-min sweep).

    Only fetches for:
    - pregame games (live games excluded to preserve closing lines)
    - recently-final games within 2h (closing line capture)
    """
    from ..services.active_games import ActiveGamesResolver
    from ..odds.synchronizer import OddsSynchronizer
    from ..models import IngestionConfig

    if not _acquire_redis_lock("lock:poll_active_odds", timeout=LOCK_TIMEOUT_10MIN):
        logger.debug("poll_active_odds_skipped_locked")
        return {"skipped": True, "reason": "locked"}

    try:
        resolver = ActiveGamesResolver()

        from ..db import db_models as _db_models

        # Extract needed fields inside the session to avoid DetachedInstanceError
        league_date_ranges: dict[int, tuple[str, list]] = {}
        game_count = 0

        with get_session() as session:
            games = resolver.get_games_needing_odds(session)

            if not games:
                logger.debug("poll_active_odds_no_games")
                return {"games": 0, "odds_count": 0}

            game_count = len(games)

            # Group games by league and collect date ranges while session is open
            league_games: dict[int, list] = {}
            for game in games:
                league_games.setdefault(game.league_id, []).append(game)

            for league_id, lg_games in league_games.items():
                league = session.query(_db_models.SportsLeague).get(league_id)
                if not league:
                    continue

                dates = [g.game_date.date() for g in lg_games if g.game_date]
                if not dates:
                    continue

                league_date_ranges[league_id] = (league.code, dates)

        logger.info(
            "poll_active_odds_start",
            total_games=game_count,
            leagues=len(league_date_ranges),
        )

        # Use existing OddsSynchronizer per league
        sync = OddsSynchronizer()
        total_odds = 0
        results: dict[str, dict] = {}

        for league_id, (league_code, dates) in league_date_ranges.items():
            start = min(dates)
            end = max(dates)

            try:
                config = IngestionConfig(
                    league_code=league_code,
                    start_date=start,
                    end_date=end,
                    odds=True,
                    boxscores=False,
                    social=False,
                    pbp=False,
                )
                count = sync.sync(config)
                results[league_code] = {"odds_count": count, "status": "success"}
                total_odds += count
            except Exception as exc:
                results[league_code] = {"odds_count": 0, "status": "error", "error": str(exc)}
                logger.warning(
                    "poll_active_odds_league_error",
                    league=league_code,
                    error=str(exc),
                )

        logger.info("poll_active_odds_complete", total_odds=total_odds, results=results)
        return {"games": game_count, "odds_count": total_odds, "results": results}

    finally:
        _release_redis_lock("lock:poll_active_odds")

