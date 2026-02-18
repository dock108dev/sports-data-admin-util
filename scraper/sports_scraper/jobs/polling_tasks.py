"""Polling tasks for game-state-machine architecture.

These tasks run at high frequency (3-5 min) and only touch games that
need attention right now, unlike the old batch sweeps that processed
everything for the last 96 hours.

The poll_live_pbp task handles:
- PBP polling for NBA/NHL (per-game)
- Boxscore polling for NBA/NHL live games (per-game)
- NCAAB PBP + boxscore polling (batch via CBB API)

Rate limit safeguards:
- Redis lock per task (prevents overlap from slow execution)
- 1-2s random jitter between API calls
- Max 30 API calls per PBP cycle, 20 per boxscore cycle
- 429 response → back off 60s, skip remaining games
"""

from __future__ import annotations

import random
import time

from celery import shared_task

from ..db import get_session
from ..logging import logger

# Maximum API calls per polling cycle to stay within rate limits
_MAX_PBP_CALLS_PER_CYCLE = 30
_MAX_BOXSCORE_CALLS_PER_CYCLE = 20

# Jitter between API calls (seconds)
_JITTER_MIN = 1.0
_JITTER_MAX = 2.0

# Backoff on 429 responses
_RATE_LIMIT_BACKOFF_SECONDS = 60


from ..utils.redis_lock import acquire_redis_lock as _acquire_redis_lock  # noqa: E402
from ..utils.redis_lock import release_redis_lock as _release_redis_lock  # noqa: E402
from ..utils.redis_lock import LOCK_TIMEOUT_5MIN, LOCK_TIMEOUT_10MIN  # noqa: E402


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
    """Poll PBP, boxscores, and status for pregame/live games (runs every 5 min).

    Phases:
    1. NBA/NHL PBP polling (existing — per-game scoreboard + PBP fetch)
    2. NBA/NHL boxscore polling for live games (per-game fetch)
    3. NCAAB batch polling (PBP per-game + boxscores via batch endpoint)
    """
    from ..services.active_games import ActiveGamesResolver

    if not _acquire_redis_lock("lock:poll_live_pbp", timeout=LOCK_TIMEOUT_5MIN):
        logger.debug("poll_live_pbp_skipped_locked")
        return {"skipped": True, "reason": "locked"}

    try:
        resolver = ActiveGamesResolver()

        with get_session() as session:
            # --- Phase 1: NBA/NHL PBP polling (existing) ---
            pbp_games = resolver.get_games_needing_pbp(session)

            api_calls = 0
            games_polled = 0
            transitions: list[dict] = []
            pbp_updated = 0
            rate_limited = False

            # Build league lookup and separate NCAAB from NBA/NHL
            from ..db import db_models
            league_map: dict[int, str] = {}
            nba_nhl_pbp_games: list = []
            ncaab_pbp_games: list = []
            if pbp_games:
                league_ids = {g.league_id for g in pbp_games}
                leagues = (
                    session.query(db_models.SportsLeague)
                    .filter(db_models.SportsLeague.id.in_(league_ids))
                    .all()
                )
                league_map = {lg.id: lg.code for lg in leagues}

            for game in pbp_games:
                code = league_map.get(game.league_id, "")
                if code == "NCAAB":
                    ncaab_pbp_games.append(game)
                else:
                    nba_nhl_pbp_games.append(game)

            if not nba_nhl_pbp_games and not ncaab_pbp_games:
                logger.debug("poll_live_pbp_no_pbp_games")
            else:
                logger.info(
                    "poll_live_data_start",
                    nba_nhl_pbp=len(nba_nhl_pbp_games),
                    ncaab_pbp=len(ncaab_pbp_games),
                )

            # NBA/NHL PBP loop (unchanged logic)
            for game in nba_nhl_pbp_games:
                if api_calls >= _MAX_PBP_CALLS_PER_CYCLE:
                    logger.info("poll_live_pbp_max_calls_reached", api_calls=api_calls)
                    break

                if rate_limited:
                    break

                if api_calls > 0:
                    time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

                try:
                    result = _poll_single_game_pbp(session, game)
                    api_calls += result.get("api_calls", 1)
                    games_polled += 1

                    if result.get("transition"):
                        transitions.append(result["transition"])
                        tr = result["transition"]
                        if tr["to"] == "final":
                            try:
                                from .final_whistle_tasks import run_final_whistle_social
                                run_final_whistle_social.apply_async(
                                    args=[tr["game_id"]],
                                    countdown=300,
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

            # --- Phase 2: NBA/NHL boxscore polling for live games ---
            boxscore_calls = 0
            boxscores_updated = 0

            if not rate_limited:
                boxscore_games = resolver.get_games_needing_boxscore(session)
                # Filter to NBA/NHL only (NCAAB boxscores handled in batch phase)
                nba_nhl_box_games = [
                    g for g in boxscore_games
                    if league_map.get(g.league_id, "") in ("NBA", "NHL")
                ]
                # Ensure league_map covers boxscore games too
                if boxscore_games:
                    new_league_ids = {g.league_id for g in boxscore_games} - set(league_map.keys())
                    if new_league_ids:
                        extra = (
                            session.query(db_models.SportsLeague)
                            .filter(db_models.SportsLeague.id.in_(new_league_ids))
                            .all()
                        )
                        league_map.update({lg.id: lg.code for lg in extra})
                    nba_nhl_box_games = [
                        g for g in boxscore_games
                        if league_map.get(g.league_id, "") in ("NBA", "NHL")
                    ]

                for game in nba_nhl_box_games:
                    if boxscore_calls >= _MAX_BOXSCORE_CALLS_PER_CYCLE:
                        logger.info("poll_boxscore_max_calls_reached", calls=boxscore_calls)
                        break
                    if rate_limited:
                        break

                    if boxscore_calls > 0 or api_calls > 0:
                        time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

                    try:
                        code = league_map.get(game.league_id, "")
                        if code == "NBA":
                            bc_result = _poll_nba_game_boxscore(session, game)
                        elif code == "NHL":
                            bc_result = _poll_nhl_game_boxscore(session, game)
                        else:
                            continue

                        boxscore_calls += bc_result.get("api_calls", 0)
                        if bc_result.get("boxscore_updated"):
                            boxscores_updated += 1

                    except _RateLimitError:
                        logger.warning(
                            "poll_boxscore_rate_limited",
                            game_id=game.id,
                            calls_so_far=boxscore_calls,
                        )
                        rate_limited = True
                        time.sleep(_RATE_LIMIT_BACKOFF_SECONDS)

                    except Exception as exc:
                        logger.warning(
                            "poll_boxscore_game_error",
                            game_id=game.id,
                            error=str(exc),
                        )
                        continue

            # --- Phase 3: NCAAB batch polling (PBP + boxscores) ---
            ncaab_stats: dict = {}
            if ncaab_pbp_games and not rate_limited:
                try:
                    ncaab_stats = _poll_ncaab_games_batch(session, ncaab_pbp_games)
                    api_calls += ncaab_stats.get("api_calls", 0)
                    pbp_updated += ncaab_stats.get("pbp_updated", 0)
                    boxscores_updated += ncaab_stats.get("boxscores_updated", 0)
                except _RateLimitError:
                    logger.warning("poll_ncaab_rate_limited")
                    rate_limited = True
                except Exception as exc:
                    logger.warning("poll_ncaab_batch_error", error=str(exc))

            total_api_calls = api_calls + boxscore_calls

            logger.info(
                "poll_live_data_complete",
                games_polled=games_polled,
                api_calls=total_api_calls,
                transitions=len(transitions),
                pbp_updated=pbp_updated,
                boxscores_updated=boxscores_updated,
                ncaab_games=len(ncaab_pbp_games),
                rate_limited=rate_limited,
            )

            return {
                "games_polled": games_polled,
                "api_calls": total_api_calls,
                "transitions": transitions,
                "pbp_updated": pbp_updated,
                "boxscores_updated": boxscores_updated,
                "rate_limited": rate_limited,
            }

    finally:
        _release_redis_lock("lock:poll_live_pbp")


class _RateLimitError(Exception):
    """Raised when an API returns 429."""


def _poll_single_game_pbp(session, game) -> dict:
    """Poll a single game for status + PBP updates.

    Returns dict with api_calls count, transition info, and pbp_events.
    NCAAB games are handled by _poll_ncaab_games_batch and skipped here.
    """
    from ..db import db_models

    league = session.query(db_models.SportsLeague).get(game.league_id)
    if not league:
        return {"api_calls": 0}

    league_code = league.code
    result: dict = {"api_calls": 0}

    if league_code == "NBA":
        result = _poll_nba_game(session, game)
    elif league_code == "NHL":
        result = _poll_nhl_game(session, game)
    elif league_code == "NCAAB":
        pass  # Handled by _poll_ncaab_games_batch

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


# ---------------------------------------------------------------------------
# Boxscore polling helpers (NBA / NHL)
# ---------------------------------------------------------------------------


def _poll_nba_game_boxscore(session, game) -> dict:
    """Fetch and persist boxscore for a single live NBA game."""
    from ..live.nba import NBALiveFeedClient
    from ..persistence.boxscores import upsert_team_boxscores, upsert_player_boxscores
    from ..utils.datetime_utils import now_utc

    nba_game_id = (game.external_ids or {}).get("nba_game_id")
    if not nba_game_id:
        return {"api_calls": 0}

    client = NBALiveFeedClient()
    result: dict = {"api_calls": 0, "boxscore_updated": False}

    try:
        boxscore = client.fetch_boxscore(nba_game_id)
        result["api_calls"] = 1

        if boxscore:
            if boxscore.team_boxscores:
                upsert_team_boxscores(
                    session, game.id, boxscore.team_boxscores, source="nba_api",
                )
            if boxscore.player_boxscores:
                upsert_player_boxscores(
                    session, game.id, boxscore.player_boxscores, source="nba_api",
                )
            game.last_boxscore_at = now_utc()
            result["boxscore_updated"] = True

            logger.info(
                "poll_nba_boxscore_ok",
                game_id=game.id,
                teams=len(boxscore.team_boxscores),
                players=len(boxscore.player_boxscores),
            )
    except Exception as exc:
        if "429" in str(exc):
            raise _RateLimitError() from exc
        logger.warning("poll_nba_boxscore_error", game_id=game.id, error=str(exc))

    return result


def _poll_nhl_game_boxscore(session, game) -> dict:
    """Fetch and persist boxscore for a single live NHL game."""
    from ..live.nhl import NHLLiveFeedClient
    from ..persistence.boxscores import upsert_team_boxscores, upsert_player_boxscores
    from ..utils.datetime_utils import now_utc

    nhl_game_pk = (game.external_ids or {}).get("nhl_game_pk")
    if not nhl_game_pk:
        return {"api_calls": 0}

    try:
        nhl_game_id = int(nhl_game_pk)
    except (ValueError, TypeError):
        return {"api_calls": 0}

    client = NHLLiveFeedClient()
    result: dict = {"api_calls": 0, "boxscore_updated": False}

    try:
        boxscore = client.fetch_boxscore(nhl_game_id)
        result["api_calls"] = 1

        if boxscore:
            if boxscore.team_boxscores:
                upsert_team_boxscores(
                    session, game.id, boxscore.team_boxscores, source="nhl_api",
                )
            if boxscore.player_boxscores:
                upsert_player_boxscores(
                    session, game.id, boxscore.player_boxscores, source="nhl_api",
                )
            game.last_boxscore_at = now_utc()
            result["boxscore_updated"] = True

            logger.info(
                "poll_nhl_boxscore_ok",
                game_id=game.id,
                teams=len(boxscore.team_boxscores),
                players=len(boxscore.player_boxscores),
            )
    except Exception as exc:
        if "429" in str(exc):
            raise _RateLimitError() from exc
        logger.warning("poll_nhl_boxscore_error", game_id=game.id, error=str(exc))

    return result


# ---------------------------------------------------------------------------
# NCAAB batch polling (PBP per-game + boxscores via batch endpoint)
# ---------------------------------------------------------------------------


def _poll_ncaab_games_batch(session, games: list) -> dict:
    """Poll PBP and boxscores for NCAAB games in batch.

    PBP: per-game calls to the CBB plays endpoint.
    Boxscores: 2 batch API calls per unique date range (team + player endpoints).
    """
    from ..live.ncaab import NCAABLiveFeedClient
    from ..db import db_models
    from ..persistence.plays import upsert_plays
    from ..persistence.boxscores import upsert_team_boxscores, upsert_player_boxscores
    from ..utils.datetime_utils import now_utc
    from ..utils.date_utils import season_ending_year

    client = NCAABLiveFeedClient()
    api_calls = 0
    pbp_updated = 0
    boxscores_updated = 0

    # Collect game metadata for batch boxscore fetch
    cbb_game_ids: list[int] = []
    game_by_cbb_id: dict[int, object] = {}
    team_names_by_game: dict[int, tuple[str, str]] = {}
    game_dates: list = []

    for game in games:
        cbb_game_id = (game.external_ids or {}).get("cbb_game_id")
        if not cbb_game_id:
            logger.debug("poll_ncaab_skip_no_cbb_id", game_id=game.id)
            continue

        try:
            cbb_id = int(cbb_game_id)
        except (ValueError, TypeError):
            logger.warning("poll_ncaab_invalid_cbb_id", game_id=game.id, cbb_game_id=cbb_game_id)
            continue

        cbb_game_ids.append(cbb_id)
        game_by_cbb_id[cbb_id] = game

        # Resolve team names for batch boxscore endpoint
        home_team = session.query(db_models.SportsTeam).get(game.home_team_id)
        away_team = session.query(db_models.SportsTeam).get(game.away_team_id)
        home_name = home_team.name if home_team else "Unknown"
        away_name = away_team.name if away_team else "Unknown"
        team_names_by_game[cbb_id] = (home_name, away_name)

        if game.game_date:
            game_dates.append(game.game_date.date())

    if not cbb_game_ids:
        return {"api_calls": 0, "pbp_updated": 0, "boxscores_updated": 0}

    logger.info("poll_ncaab_batch_start", games=len(cbb_game_ids))

    # --- PBP: per-game calls ---
    for cbb_id in cbb_game_ids:
        game = game_by_cbb_id[cbb_id]

        if api_calls > 0:
            time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

        try:
            payload = client.fetch_play_by_play(cbb_id, game_status=game.status)
            api_calls += 1

            if payload.plays:
                inserted = upsert_plays(session, game.id, payload.plays, source="ncaab_api")
                if inserted:
                    pbp_updated += 1
                game.last_pbp_at = now_utc()

        except Exception as exc:
            if "429" in str(exc):
                raise _RateLimitError() from exc
            logger.warning("poll_ncaab_pbp_error", game_id=game.id, cbb_id=cbb_id, error=str(exc))

    # --- Boxscores: batch fetch (2 API calls for all games in date range) ---
    # Only fetch boxscores for live games (boxscores have no data before tip)
    live_cbb_ids = [
        cbb_id for cbb_id in cbb_game_ids
        if game_by_cbb_id[cbb_id].status == db_models.GameStatus.live.value
    ]

    if live_cbb_ids and game_dates:
        start_date = min(game_dates)
        end_date = max(game_dates)
        season = season_ending_year(start_date)

        time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

        try:
            boxscores = client.fetch_boxscores_batch(
                game_ids=live_cbb_ids,
                start_date=start_date,
                end_date=end_date,
                season=season,
                team_names_by_game={
                    cbb_id: team_names_by_game[cbb_id]
                    for cbb_id in live_cbb_ids
                    if cbb_id in team_names_by_game
                },
            )
            api_calls += 2  # batch endpoint always makes 2 calls (teams + players)

            for cbb_id, boxscore in boxscores.items():
                game = game_by_cbb_id.get(cbb_id)
                if not game:
                    continue

                if boxscore.team_boxscores:
                    upsert_team_boxscores(
                        session, game.id, boxscore.team_boxscores, source="ncaab_api",
                    )
                if boxscore.player_boxscores:
                    upsert_player_boxscores(
                        session, game.id, boxscore.player_boxscores, source="ncaab_api",
                    )
                game.last_boxscore_at = now_utc()
                boxscores_updated += 1

        except Exception as exc:
            if "429" in str(exc):
                raise _RateLimitError() from exc
            logger.warning("poll_ncaab_boxscore_batch_error", error=str(exc))

    logger.info(
        "poll_ncaab_batch_complete",
        api_calls=api_calls,
        pbp_updated=pbp_updated,
        boxscores_updated=boxscores_updated,
    )

    return {
        "api_calls": api_calls,
        "pbp_updated": pbp_updated,
        "boxscores_updated": boxscores_updated,
    }


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
