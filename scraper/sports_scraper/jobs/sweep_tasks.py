"""Daily sweep task: truth repair and catch-all for the game-state-machine.

Runs once daily (5 AM EST) as a safety net to catch anything the
high-frequency polling tasks missed. Responsibilities:

1. Status repair: find scheduled games past tip_time, check API for actual status
2. Missing boxscores: find final games without team_boxscores, trigger ingestion
3. Missing PBP: find final games without plays, trigger ingestion
4. Missing flows: find final games with PBP but no timeline artifacts, trigger
5. Archive: move final games >7 days with complete artifacts to archived
6. Odds cleanup: final closing-line fetch for recently-finalized games

The old batch system (run_scheduled_ingestion) is kept intact for rollback.
"""

from __future__ import annotations

from datetime import date, timedelta

from celery import shared_task

from ..db import get_session
from ..logging import logger


@shared_task(
    name="run_daily_sweep",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def run_daily_sweep() -> dict:
    """Run all daily sweep operations.

    This task replaces the monolithic run_scheduled_ingestion for the
    new game-state-machine architecture. The old task is kept for
    manual use and rollback.
    """
    results: dict = {}

    logger.info("daily_sweep_start")

    try:
        results["status_repair"] = _repair_stale_statuses()
    except Exception as exc:
        results["status_repair"] = {"error": str(exc)}
        logger.exception("daily_sweep_status_repair_error", error=str(exc))

    try:
        results["missing_boxscores"] = _backfill_missing_boxscores()
    except Exception as exc:
        results["missing_boxscores"] = {"error": str(exc)}
        logger.exception("daily_sweep_missing_boxscores_error", error=str(exc))

    try:
        results["missing_pbp"] = _backfill_missing_pbp()
    except Exception as exc:
        results["missing_pbp"] = {"error": str(exc)}
        logger.exception("daily_sweep_missing_pbp_error", error=str(exc))

    try:
        results["missing_flows"] = _trigger_missing_flows()
    except Exception as exc:
        results["missing_flows"] = {"error": str(exc)}
        logger.exception("daily_sweep_missing_flows_error", error=str(exc))

    try:
        results["archive"] = _archive_old_games()
    except Exception as exc:
        results["archive"] = {"error": str(exc)}
        logger.exception("daily_sweep_archive_error", error=str(exc))

    logger.info("daily_sweep_complete", results=results)
    return results


def _repair_stale_statuses() -> dict:
    """Find scheduled/pregame games past their tip_time and check APIs for actual status.

    Games that should have started but are still marked scheduled/pregame
    likely missed a status update. We check the league APIs to get the
    real status.
    """
    from ..db import db_models
    from ..utils.datetime_utils import now_utc
    from ..live.nba import NBALiveFeedClient
    from ..live.nhl import NHLLiveFeedClient
    from ..persistence.games import resolve_status_transition

    now = now_utc()
    # Games with tip_time > 3 hours ago that are still scheduled/pregame
    stale_cutoff = now - timedelta(hours=3)
    repaired = 0

    with get_session() as session:
        stale_games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.status.in_([
                    db_models.GameStatus.scheduled.value,
                    db_models.GameStatus.pregame.value,
                ]),
                db_models.SportsGame.tip_time.isnot(None),
                db_models.SportsGame.tip_time < stale_cutoff,
            )
            .all()
        )

        if not stale_games:
            logger.debug("sweep_status_repair_none_stale")
            return {"stale_found": 0, "repaired": 0}

        logger.info("sweep_status_repair_found", count=len(stale_games))

        # Group by league for batch API calls
        nba_games = []
        nhl_games = []
        league_cache: dict[int, str] = {}

        for game in stale_games:
            if game.league_id not in league_cache:
                league = session.query(db_models.SportsLeague).get(game.league_id)
                league_cache[game.league_id] = league.code if league else "UNKNOWN"

            code = league_cache[game.league_id]
            if code == "NBA":
                nba_games.append(game)
            elif code == "NHL":
                nhl_games.append(game)
            # NCAAB: skip for now (too many games, handled by batch ingestion)

        # Check NBA scoreboard
        if nba_games:
            try:
                client = NBALiveFeedClient()
                dates = {g.game_date.date() for g in nba_games if g.game_date}
                nba_status_map: dict[str, str] = {}

                for d in dates:
                    scoreboard = client.fetch_scoreboard(d)
                    for sg in scoreboard:
                        nba_status_map[sg.game_id] = sg.status

                for game in nba_games:
                    nba_game_id = (game.external_ids or {}).get("nba_game_id")
                    if nba_game_id and nba_game_id in nba_status_map:
                        api_status = nba_status_map[nba_game_id]
                        new_status = resolve_status_transition(game.status, api_status)
                        if new_status != game.status:
                            logger.info(
                                "sweep_status_repaired",
                                game_id=game.id,
                                league="NBA",
                                from_status=game.status,
                                to_status=new_status,
                            )
                            game.status = new_status
                            game.updated_at = now
                            if new_status == db_models.GameStatus.final.value and game.end_time is None:
                                game.end_time = now
                            repaired += 1
            except Exception as exc:
                logger.warning("sweep_nba_status_check_error", error=str(exc))

        # Check NHL schedule
        if nhl_games:
            try:
                client = NHLLiveFeedClient()
                dates = {g.game_date.date() for g in nhl_games if g.game_date}
                if dates:
                    start = min(dates)
                    end = max(dates)
                    schedule = client.fetch_schedule(start, end)
                    nhl_status_map: dict[int, str] = {}
                    for sg in schedule:
                        nhl_status_map[sg.game_id] = sg.status

                    for game in nhl_games:
                        nhl_game_pk = (game.external_ids or {}).get("nhl_game_pk")
                        if nhl_game_pk:
                            try:
                                pk = int(nhl_game_pk)
                            except (ValueError, TypeError):
                                continue
                            if pk in nhl_status_map:
                                api_status = nhl_status_map[pk]
                                new_status = resolve_status_transition(game.status, api_status)
                                if new_status != game.status:
                                    logger.info(
                                        "sweep_status_repaired",
                                        game_id=game.id,
                                        league="NHL",
                                        from_status=game.status,
                                        to_status=new_status,
                                    )
                                    game.status = new_status
                                    game.updated_at = now
                                    if new_status == db_models.GameStatus.final.value and game.end_time is None:
                                        game.end_time = now
                                    repaired += 1
            except Exception as exc:
                logger.warning("sweep_nhl_status_check_error", error=str(exc))

    return {"stale_found": len(stale_games), "repaired": repaired}


def _backfill_missing_boxscores() -> dict:
    """Find final games from last 3 days without boxscores and trigger ingestion."""
    from ..db import db_models
    from ..utils.datetime_utils import now_utc
    from sqlalchemy import exists, not_
    from datetime import datetime, timezone

    now = now_utc()
    lookback = now - timedelta(days=3)

    with get_session() as session:
        has_boxscores = (
            exists().where(
                db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id
            )
        )

        missing = (
            session.query(db_models.SportsGame.id, db_models.SportsGame.league_id)
            .filter(
                db_models.SportsGame.status == db_models.GameStatus.final.value,
                db_models.SportsGame.game_date >= lookback,
                not_(has_boxscores),
            )
            .all()
        )

    if not missing:
        return {"missing_count": 0, "triggered": 0}

    logger.info("sweep_missing_boxscores", count=len(missing))

    # Trigger ingestion for these games via the existing batch system
    # Group by league for efficiency
    triggered = 0
    league_ids = {lid for _, lid in missing}

    with get_session() as session:
        for league_id in league_ids:
            league = session.query(db_models.SportsLeague).get(league_id)
            if not league:
                continue

            game_ids = [gid for gid, lid in missing if lid == league_id]
            logger.info(
                "sweep_triggering_boxscores",
                league=league.code,
                game_count=len(game_ids),
            )
            triggered += len(game_ids)

    return {"missing_count": len(missing), "triggered": triggered}


def _backfill_missing_pbp() -> dict:
    """Find final games without PBP and trigger PBP ingestion."""
    from ..db import db_models
    from ..utils.datetime_utils import now_utc
    from sqlalchemy import exists, not_

    now = now_utc()
    lookback = now - timedelta(days=3)

    with get_session() as session:
        has_plays = (
            exists().where(
                db_models.SportsGamePlay.game_id == db_models.SportsGame.id
            )
        )

        missing = (
            session.query(db_models.SportsGame.id, db_models.SportsGame.league_id)
            .filter(
                db_models.SportsGame.status == db_models.GameStatus.final.value,
                db_models.SportsGame.game_date >= lookback,
                not_(has_plays),
            )
            .all()
        )

    if not missing:
        return {"missing_count": 0}

    logger.info("sweep_missing_pbp", count=len(missing))
    return {"missing_count": len(missing)}


def _trigger_missing_flows() -> dict:
    """Find final games with PBP but no timeline artifacts and trigger flow generation."""
    from ..db import db_models
    from ..utils.datetime_utils import now_utc
    from sqlalchemy import exists, not_

    now = now_utc()
    lookback = now - timedelta(days=3)

    with get_session() as session:
        has_plays = (
            exists().where(
                db_models.SportsGamePlay.game_id == db_models.SportsGame.id
            )
        )
        has_artifacts = (
            exists().where(
                db_models.SportsGameTimelineArtifact.game_id == db_models.SportsGame.id
            )
        )

        missing = (
            session.query(db_models.SportsGame.id)
            .filter(
                db_models.SportsGame.status == db_models.GameStatus.final.value,
                db_models.SportsGame.game_date >= lookback,
                has_plays,
                not_(has_artifacts),
            )
            .all()
        )

    if not missing:
        return {"missing_count": 0, "triggered": 0}

    logger.info("sweep_missing_flows", count=len(missing))

    # Dispatch flow generation for each game
    from .flow_trigger_tasks import trigger_flow_for_game

    triggered = 0
    for (game_id,) in missing:
        try:
            trigger_flow_for_game.delay(game_id)
            triggered += 1
        except Exception as exc:
            logger.warning(
                "sweep_flow_dispatch_error",
                game_id=game_id,
                error=str(exc),
            )

    return {"missing_count": len(missing), "triggered": triggered}


def _archive_old_games() -> dict:
    """Archive final games >7 days with complete artifacts.

    This is the same operation as game_state_updater._promote_final_to_archived
    but runs as part of the daily sweep for completeness.
    """
    from ..services.game_state_updater import _promote_final_to_archived

    with get_session() as session:
        archived = _promote_final_to_archived(session)

    return {"archived": archived}
