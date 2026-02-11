"""NBA boxscore ingestion via official NBA CDN API.

This module handles boxscore data ingestion for NBA games using
the NBA CDN API (cdn.nba.com).

Benefits:
- Data available immediately after games end (unlike Basketball Reference)
- Single data source (scoreboard, PBP, and boxscores from same API)
- More reliable — official API less likely to break than HTML scraping
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import exists, not_
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..models import (
    GameIdentification,
    NormalizedGame,
)
from ..persistence import persist_game_payload
from ..utils.date_utils import season_ending_year
from ..utils.datetime_utils import date_to_utc_datetime
from .pbp_nba import populate_nba_game_ids


def select_games_for_boxscores_nba_api(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> list[tuple[int, str, date]]:
    """Return game ids and NBA game IDs for NBA API boxscore ingestion.

    NBA boxscores are fetched via the NBA CDN API using the NBA game ID
    (like "0022400123") stored in external_ids['nba_game_id'].

    Args:
        session: Database session
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have boxscore data
        updated_before: Only include games with stale boxscore data

    Returns:
        List of (game_id, nba_game_id, game_date) tuples for games needing boxscores
    """
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NBA"
    ).first()
    if not league:
        return []

    # NBA game ID is stored in external_ids JSONB field under 'nba_game_id' key
    nba_game_id_expr = db_models.SportsGame.external_ids["nba_game_id"].astext

    query = session.query(
        db_models.SportsGame.id,
        nba_game_id_expr.label("nba_game_id"),
        db_models.SportsGame.game_date,
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
    )

    if only_missing:
        has_boxscores = exists().where(
            db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id
        )
        query = query.filter(not_(has_boxscores))

    if updated_before:
        has_fresh = exists().where(
            db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id,
            db_models.SportsTeamBoxscore.updated_at >= updated_before,
        )
        query = query.filter(not_(has_fresh))

    rows = query.all()
    results = []
    for game_id, nba_game_id, game_date in rows:
        if nba_game_id:
            game_day = game_date.date() if game_date else None
            if game_day:
                results.append((game_id, nba_game_id, game_day))
    return results


def ingest_boxscores_via_nba_api(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> tuple[int, int, int]:
    """Ingest NBA boxscores using the NBA CDN API.

    Flow:
    1. Populate nba_game_id for games missing it (via NBA scoreboard API)
    2. Select games with nba_game_id that need boxscore data
    3. Fetch boxscore from NBA CDN API for each game
    4. Convert to NormalizedGame with team/player boxscores
    5. Persist via existing persist_game_payload()

    Args:
        session: Database session
        run_id: Scrape run ID for logging
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have boxscore data
        updated_before: Only include games with stale boxscore data

    Returns:
        Tuple of (games_processed, games_enriched, games_with_stats)
    """
    from ..live.nba import NBALiveFeedClient

    # Step 1: Populate missing NBA game IDs
    populate_nba_game_ids(
        session,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Step 2: Select games for boxscore ingestion
    games = select_games_for_boxscores_nba_api(
        session,
        start_date=start_date,
        end_date=end_date,
        only_missing=only_missing,
        updated_before=updated_before,
    )

    if not games:
        logger.info(
            "nba_boxscore_no_games_selected",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
            only_missing=only_missing,
        )
        return (0, 0, 0)

    logger.info(
        "nba_boxscore_games_selected",
        run_id=run_id,
        games=len(games),
        only_missing=only_missing,
        updated_before=str(updated_before) if updated_before else None,
    )

    # Step 3: Fetch and persist boxscores
    client = NBALiveFeedClient()
    games_processed = 0
    games_enriched = 0
    games_with_stats = 0

    for game_id, nba_game_id, game_date in games:
        try:
            boxscore = client.fetch_boxscore(nba_game_id)

            if not boxscore:
                logger.warning(
                    "nba_boxscore_empty_response",
                    run_id=run_id,
                    game_id=game_id,
                    nba_game_id=nba_game_id,
                )
                continue

            normalized_game = convert_nba_boxscore_to_normalized_game(
                boxscore, game_date
            )

            result = persist_game_payload(session, normalized_game)

            if result.game_id is not None:
                games_processed += 1
                if result.enriched:
                    games_enriched += 1
                if result.has_player_stats:
                    games_with_stats += 1

                logger.info(
                    "nba_boxscore_ingested",
                    run_id=run_id,
                    game_id=game_id,
                    nba_game_id=nba_game_id,
                    enriched=result.enriched,
                    player_stats_inserted=result.player_stats.inserted if result.player_stats else 0,
                )

        except Exception as exc:
            logger.warning(
                "nba_boxscore_fetch_failed",
                run_id=run_id,
                game_id=game_id,
                nba_game_id=nba_game_id,
                error=str(exc),
            )
            continue

    logger.info(
        "nba_boxscore_ingestion_complete",
        run_id=run_id,
        games_processed=games_processed,
        games_enriched=games_enriched,
        games_with_stats=games_with_stats,
    )

    return (games_processed, games_enriched, games_with_stats)


def convert_nba_boxscore_to_normalized_game(
    boxscore,  # NBABoxscore from live.nba_boxscore
    game_date: date,
) -> NormalizedGame:
    """Convert NBABoxscore to NormalizedGame for persistence.

    This bridges the NBA CDN API boxscore format to our normalized persistence layer.
    """
    identity = GameIdentification(
        league_code="NBA",
        season=season_ending_year(game_date),
        season_type="regular",
        game_date=date_to_utc_datetime(game_date),
        home_team=boxscore.home_team,
        away_team=boxscore.away_team,
        source_game_key=str(boxscore.game_id),
    )

    return NormalizedGame(
        identity=identity,
        status="completed" if boxscore.status == "final" else boxscore.status,
        home_score=boxscore.home_score,
        away_score=boxscore.away_score,
        team_boxscores=boxscore.team_boxscores,
        player_boxscores=boxscore.player_boxscores,
    )
