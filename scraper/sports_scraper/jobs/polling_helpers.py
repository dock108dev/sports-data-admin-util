"""Polling helper functions for live game data.

League-specific polling implementations for NBA, NHL, and NCAAB.
These are called by the @shared_task entry points in polling_tasks.py.
"""

from __future__ import annotations

import random
import time

from ..logging import logger

# Shared constants (also defined in polling_tasks.py for task-level use)
_JITTER_MIN = 1.0
_JITTER_MAX = 2.0


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
    from ..db import db_models
    from ..live.nba import NBALiveFeedClient
    from ..persistence.games import resolve_status_transition
    from ..persistence.plays import upsert_plays
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
    from ..db import db_models
    from ..live.nhl import NHLLiveFeedClient
    from ..persistence.games import resolve_status_transition
    from ..persistence.plays import upsert_plays
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
    from ..persistence.boxscores import upsert_player_boxscores, upsert_team_boxscores
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
    from ..persistence.boxscores import upsert_player_boxscores, upsert_team_boxscores
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


def _update_ncaab_statuses(session, games: list, client) -> list[dict]:
    """Check CBB API for current game statuses and apply transitions.

    Returns list of transition dicts for logging.
    """
    from ..db import db_models
    from ..persistence.games import resolve_status_transition
    from ..utils.datetime_utils import now_utc

    game_dates = [g.game_date.date() for g in games if g.game_date]
    if not game_dates:
        return []

    start_date = min(game_dates)
    end_date = max(game_dates)

    try:
        cbb_games = client.fetch_games(start_date, end_date)
    except Exception as exc:
        logger.warning("ncaab_status_fetch_error", error=str(exc))
        return []

    # Build cbb_game_id -> status map
    cbb_status_map: dict[int, str] = {}
    for cg in cbb_games:
        cbb_status_map[cg.game_id] = cg.status

    transitions: list[dict] = []
    now = now_utc()

    for game in games:
        cbb_game_id = (game.external_ids or {}).get("cbb_game_id")
        if not cbb_game_id:
            continue

        try:
            cbb_id = int(cbb_game_id)
        except (ValueError, TypeError):
            continue

        api_status = cbb_status_map.get(cbb_id)
        if not api_status:
            continue

        new_status = resolve_status_transition(game.status, api_status)
        if new_status != game.status:
            old_status = game.status
            game.status = new_status
            game.updated_at = now

            if new_status == db_models.GameStatus.final.value and game.end_time is None:
                game.end_time = now

            transitions.append({
                "game_id": game.id,
                "from": old_status,
                "to": new_status,
            })
            logger.info(
                "poll_ncaab_status_transition",
                game_id=game.id,
                from_status=old_status,
                to_status=new_status,
                cbb_game_id=cbb_id,
            )

    return transitions


def _poll_ncaab_games_batch(session, games: list) -> dict:
    """Poll PBP and boxscores for NCAAB games in batch.

    PBP: per-game calls to the CBB plays endpoint.
    Boxscores: 2 batch API calls per unique date range (team + player endpoints).
    """
    from ..db import db_models
    from ..live.ncaab import NCAABLiveFeedClient
    from ..persistence.boxscores import upsert_player_boxscores, upsert_team_boxscores
    from ..persistence.plays import upsert_plays
    from ..utils.date_utils import season_ending_year
    from ..utils.datetime_utils import now_utc

    client = NCAABLiveFeedClient()

    # Check for status transitions before polling
    ncaab_transitions = _update_ncaab_statuses(session, games, client)
    api_calls = 1 if games else 0  # count the fetch_games call
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
        "transitions": ncaab_transitions,
    }
