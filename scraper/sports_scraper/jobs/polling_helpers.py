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

                # Infer live if PBP has plays but game is still pregame
                if game.status == db_models.GameStatus.pregame.value:
                    game.status = db_models.GameStatus.live.value
                    game.updated_at = now_utc()
                    result["transition"] = {
                        "game_id": game.id,
                        "from": "pregame",
                        "to": "live",
                    }
                    logger.info(
                        "poll_pbp_inferred_live",
                        game_id=game.id,
                        league="NBA",
                        reason="pbp_plays_found",
                        play_count=len(payload.plays),
                    )
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

                # Infer live if PBP has plays but game is still pregame
                if game.status == db_models.GameStatus.pregame.value:
                    game.status = db_models.GameStatus.live.value
                    game.updated_at = now_utc()
                    result["transition"] = {
                        "game_id": game.id,
                        "from": "pregame",
                        "to": "live",
                    }
                    logger.info(
                        "poll_pbp_inferred_live",
                        game_id=game.id,
                        league="NHL",
                        reason="pbp_plays_found",
                        play_count=len(payload.plays),
                    )
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


def _match_ncaa_scoreboard_to_games(
    session, games: list, scoreboard_games: list,
) -> dict:
    """Match NCAA scoreboard entries to DB games by team name normalization.

    For each DB game, tries to find a matching NCAA scoreboard game by
    normalizing both home and away team names and comparing.

    Returns dict mapping DB game.id -> NCAAScoreboardGame.
    """
    from ..db import db_models
    from ..normalization import normalize_team_name

    # Build lookup: (home_canonical, away_canonical) -> scoreboard game
    scoreboard_by_teams: dict[tuple[str, str], object] = {}
    for sg in scoreboard_games:
        home_canonical, _ = normalize_team_name("NCAAB", sg.home_team_short)
        away_canonical, _ = normalize_team_name("NCAAB", sg.away_team_short)
        scoreboard_by_teams[(home_canonical, away_canonical)] = sg

    matches: dict = {}
    for game in games:
        # Skip if already has ncaa_game_id
        if (game.external_ids or {}).get("ncaa_game_id"):
            continue

        home_team = session.query(db_models.SportsTeam).get(game.home_team_id)
        away_team = session.query(db_models.SportsTeam).get(game.away_team_id)
        if not home_team or not away_team:
            continue

        home_canonical, _ = normalize_team_name("NCAAB", home_team.name)
        away_canonical, _ = normalize_team_name("NCAAB", away_team.name)

        # Try normal match
        sg = scoreboard_by_teams.get((home_canonical, away_canonical))

        # Try reversed (neutral site games may swap home/away)
        if sg is None:
            sg = scoreboard_by_teams.get((away_canonical, home_canonical))

        if sg is not None:
            matches[game.id] = sg

    return matches


def _update_ncaab_statuses(session, games: list, client) -> list[dict]:
    """Check NCAA API scoreboard for game statuses and apply transitions.

    Primary: NCAA API scoreboard (1 API call for all games).
    Fallback: CBB API fetch_games if NCAA scoreboard fails.

    Also stores ncaa_game_id in external_ids for matched games.

    Returns list of transition dicts for logging.
    """
    from ..db import db_models
    from ..persistence.games import resolve_status_transition
    from ..utils.datetime_utils import now_utc

    transitions: list[dict] = []
    now = now_utc()

    # --- Primary: NCAA API scoreboard ---
    ncaa_success = False
    try:
        scoreboard_games = client.fetch_ncaa_scoreboard()
        if scoreboard_games:
            ncaa_success = True
            logger.info(
                "ncaab_status_using_ncaa_scoreboard",
                scoreboard_count=len(scoreboard_games),
                db_games=len(games),
            )

            # Match scoreboard games to DB games
            matches = _match_ncaa_scoreboard_to_games(session, games, scoreboard_games)

            # Build ncaa_game_id -> status map for all scoreboard games
            ncaa_id_status: dict[str, str] = {
                sg.ncaa_game_id: sg.game_state for sg in scoreboard_games
            }
            ncaa_id_scores: dict[str, tuple] = {
                sg.ncaa_game_id: (sg.home_score, sg.away_score) for sg in scoreboard_games
            }

            for game in games:
                # Store ncaa_game_id for newly matched games
                if game.id in matches:
                    sg = matches[game.id]
                    ext = dict(game.external_ids or {})
                    ext["ncaa_game_id"] = sg.ncaa_game_id
                    game.external_ids = ext
                    logger.info(
                        "ncaab_ncaa_game_id_stored",
                        game_id=game.id,
                        ncaa_game_id=sg.ncaa_game_id,
                    )

                ncaa_game_id = (game.external_ids or {}).get("ncaa_game_id")
                if not ncaa_game_id:
                    continue

                api_status = ncaa_id_status.get(ncaa_game_id)
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
                        ncaa_game_id=ncaa_game_id,
                        source="ncaa_api",
                    )

                # Update scores from scoreboard
                scores = ncaa_id_scores.get(ncaa_game_id)
                if scores:
                    home_score, away_score = scores
                    if home_score is not None:
                        game.home_score = home_score
                    if away_score is not None:
                        game.away_score = away_score

    except Exception as exc:
        logger.warning("ncaa_scoreboard_error", error=str(exc))

    if ncaa_success:
        return transitions

    # --- Fallback: CBB API ---
    logger.info("ncaab_status_falling_back_to_cbb")

    game_dates = [g.game_date.date() for g in games if g.game_date]
    if not game_dates:
        return transitions

    start_date = min(game_dates)
    end_date = max(game_dates)

    try:
        cbb_games = client.fetch_games(start_date, end_date)
    except Exception as exc:
        logger.warning("ncaab_status_fetch_error", error=str(exc))
        return transitions

    # Build cbb_game_id -> status map
    cbb_status_map: dict[int, str] = {}
    for cg in cbb_games:
        cbb_status_map[cg.game_id] = cg.status

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
                source="cbb_api",
            )

    return transitions


def _poll_ncaab_games_batch(session, games: list) -> dict:
    """Poll PBP and boxscores for NCAAB games in batch.

    Primary: NCAA API for PBP and boxscores (per-game calls).
    Fallback: CBB API for games without an ncaa_game_id.
    """
    from ..db import db_models
    from ..live.ncaab import NCAABLiveFeedClient
    from ..persistence.boxscores import upsert_player_boxscores, upsert_team_boxscores
    from ..persistence.plays import upsert_plays
    from ..utils.date_utils import season_ending_year
    from ..utils.datetime_utils import now_utc

    client = NCAABLiveFeedClient()

    # Check for status transitions before polling (uses NCAA scoreboard as primary)
    ncaab_transitions = _update_ncaab_statuses(session, games, client)
    api_calls = 1 if games else 0  # count the scoreboard call
    pbp_updated = 0
    boxscores_updated = 0

    # Categorize games by available IDs
    ncaa_games: list = []     # Have ncaa_game_id -> use NCAA API
    cbb_only_games: list = [] # Only have cbb_game_id -> use CBB API fallback
    game_dates: list = []
    team_names_by_game_id: dict[int, tuple[str, str]] = {}  # DB game.id -> (home, away)

    for game in games:
        # Resolve team names (needed for both NCAA and CBB boxscores)
        home_team = session.query(db_models.SportsTeam).get(game.home_team_id)
        away_team = session.query(db_models.SportsTeam).get(game.away_team_id)
        home_name = home_team.name if home_team else "Unknown"
        away_name = away_team.name if away_team else "Unknown"
        team_names_by_game_id[game.id] = (home_name, away_name)

        if game.game_date:
            game_dates.append(game.game_date.date())

        ncaa_game_id = (game.external_ids or {}).get("ncaa_game_id")
        cbb_game_id = (game.external_ids or {}).get("cbb_game_id")

        if ncaa_game_id:
            ncaa_games.append(game)
        elif cbb_game_id:
            cbb_only_games.append(game)
        else:
            logger.debug("poll_ncaab_skip_no_id", game_id=game.id)

    if not ncaa_games and not cbb_only_games:
        return {"api_calls": 0, "pbp_updated": 0, "boxscores_updated": 0}

    logger.info(
        "poll_ncaab_batch_start",
        ncaa_games=len(ncaa_games),
        cbb_only_games=len(cbb_only_games),
    )

    # --- PBP: NCAA API (primary) ---
    for game in ncaa_games:
        ncaa_game_id = game.external_ids["ncaa_game_id"]

        if api_calls > 0:
            time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

        try:
            payload = client.fetch_ncaa_play_by_play(ncaa_game_id, game_status=game.status)
            api_calls += 1

            if payload.plays:
                inserted = upsert_plays(session, game.id, payload.plays, source="ncaa_api")
                if inserted:
                    pbp_updated += 1
                game.last_pbp_at = now_utc()

                if game.status == db_models.GameStatus.pregame.value:
                    game.status = db_models.GameStatus.live.value
                    game.updated_at = now_utc()
                    ncaab_transitions.append({
                        "game_id": game.id,
                        "from": "pregame",
                        "to": "live",
                    })
                    logger.info(
                        "poll_pbp_inferred_live",
                        game_id=game.id,
                        league="NCAAB",
                        reason="pbp_plays_found",
                        play_count=len(payload.plays),
                        ncaa_game_id=ncaa_game_id,
                    )

        except Exception as exc:
            if "429" in str(exc):
                raise _RateLimitError() from exc
            logger.warning(
                "poll_ncaab_pbp_error",
                game_id=game.id,
                ncaa_game_id=ncaa_game_id,
                source="ncaa_api",
                error=str(exc),
            )

    # --- PBP: CBB API (fallback for games without ncaa_game_id) ---
    for game in cbb_only_games:
        cbb_game_id = game.external_ids.get("cbb_game_id")
        try:
            cbb_id = int(cbb_game_id)
        except (ValueError, TypeError):
            continue

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

                if game.status == db_models.GameStatus.pregame.value:
                    game.status = db_models.GameStatus.live.value
                    game.updated_at = now_utc()
                    ncaab_transitions.append({
                        "game_id": game.id,
                        "from": "pregame",
                        "to": "live",
                    })
                    logger.info(
                        "poll_pbp_inferred_live",
                        game_id=game.id,
                        league="NCAAB",
                        reason="pbp_plays_found",
                        play_count=len(payload.plays),
                        cbb_id=cbb_id,
                    )

        except Exception as exc:
            if "429" in str(exc):
                raise _RateLimitError() from exc
            logger.warning("poll_ncaab_pbp_error", game_id=game.id, cbb_id=cbb_id, error=str(exc))

    # --- Boxscores: NCAA API (per-game for NCAA-capable games) ---
    ncaa_live_or_final = [
        g for g in ncaa_games
        if g.status in (db_models.GameStatus.live.value, db_models.GameStatus.final.value)
    ]

    for game in ncaa_live_or_final:
        ncaa_game_id = game.external_ids["ncaa_game_id"]
        home_name, away_name = team_names_by_game_id[game.id]

        if api_calls > 0:
            time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

        try:
            boxscore = client.fetch_ncaa_boxscore(
                ncaa_game_id, home_name, away_name, game_status=game.status,
            )
            api_calls += 1

            if boxscore:
                if boxscore.team_boxscores:
                    upsert_team_boxscores(
                        session, game.id, boxscore.team_boxscores, source="ncaa_api",
                    )
                if boxscore.player_boxscores:
                    upsert_player_boxscores(
                        session, game.id, boxscore.player_boxscores, source="ncaa_api",
                    )
                game.last_boxscore_at = now_utc()
                boxscores_updated += 1

        except Exception as exc:
            if "429" in str(exc):
                raise _RateLimitError() from exc
            logger.warning(
                "poll_ncaab_boxscore_error",
                game_id=game.id,
                ncaa_game_id=ncaa_game_id,
                error=str(exc),
            )

    # --- Boxscores: CBB API batch (fallback for CBB-only games) ---
    cbb_live_or_final = [
        g for g in cbb_only_games
        if g.status in (db_models.GameStatus.live.value, db_models.GameStatus.final.value)
    ]

    if cbb_live_or_final and game_dates:
        cbb_ids_for_batch: list[int] = []
        game_by_cbb_id: dict[int, object] = {}
        cbb_team_names: dict[int, tuple[str, str]] = {}

        for game in cbb_live_or_final:
            cbb_game_id = game.external_ids.get("cbb_game_id")
            try:
                cbb_id = int(cbb_game_id)
            except (ValueError, TypeError):
                continue
            cbb_ids_for_batch.append(cbb_id)
            game_by_cbb_id[cbb_id] = game
            cbb_team_names[cbb_id] = team_names_by_game_id[game.id]

        if cbb_ids_for_batch:
            start_date = min(game_dates)
            end_date = max(game_dates)
            season = season_ending_year(start_date)

            time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

            try:
                boxscores = client.fetch_boxscores_batch(
                    game_ids=cbb_ids_for_batch,
                    start_date=start_date,
                    end_date=end_date,
                    season=season,
                    team_names_by_game=cbb_team_names,
                )
                api_calls += 2  # batch endpoint makes 2 calls (teams + players)

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
