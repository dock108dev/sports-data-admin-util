"""NCAAB boxscore ingestion via College Basketball Data API.

This module handles boxscore data ingestion for NCAAB games using
the College Basketball Data API (api.collegebasketballdata.com).

Benefits:
- Single data source (schedule, PBP, and boxscores)
- Faster ingestion - REST API vs web scraping
- More reliable - official API less likely to break than HTML scraping
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..logging import logger
from ..models import (
    GameIdentification,
    NormalizedGame,
)
from ..persistence import persist_game_payload
from ..utils.date_utils import season_ending_year
from .ncaab_game_ids import (
    populate_ncaab_game_ids,
    select_games_for_boxscores_ncaab_api,
)


def ingest_boxscores_via_ncaab_api(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> tuple[int, int, int]:
    """Ingest NCAAB boxscores using the College Basketball Data API.

    Uses batch fetching to minimize API calls.

    Flow:
    1. Populate cbb_game_id for games missing it (via CBB schedule API)
    2. Select games with cbb_game_id that need boxscore data
    3. Batch fetch all boxscores with 2 API calls (teams + players)
    4. Filter and persist boxscores for requested games

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
    from ..live.ncaab import NCAABLiveFeedClient

    logger.info(
        "ncaab_boxscore_ingestion_start",
        run_id=run_id,
        start_date=str(start_date),
        end_date=str(end_date),
        only_missing=only_missing,
    )

    # Step 1: Populate missing CBB game IDs
    populate_ncaab_game_ids(
        session,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Step 2: Select games for boxscore ingestion
    games = select_games_for_boxscores_ncaab_api(
        session,
        start_date=start_date,
        end_date=end_date,
        only_missing=only_missing,
        updated_before=updated_before,
    )

    if not games:
        logger.info(
            "ncaab_boxscore_no_games_selected",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
            only_missing=only_missing,
        )
        return (0, 0, 0)

    logger.info(
        "ncaab_boxscore_games_selected",
        run_id=run_id,
        games=len(games),
        only_missing=only_missing,
        updated_before=str(updated_before) if updated_before else None,
    )

    # Step 3: Batch fetch boxscores
    client = NCAABLiveFeedClient()
    season = season_ending_year(start_date)

    cbb_game_ids = [cbb_game_id for _, cbb_game_id, _, _, _ in games]
    team_names_by_game = {
        cbb_game_id: (home_team_name, away_team_name)
        for _, cbb_game_id, _, home_team_name, away_team_name in games
    }

    boxscores = client.fetch_boxscores_batch(
        game_ids=cbb_game_ids,
        start_date=start_date,
        end_date=end_date,
        season=season,
        team_names_by_game=team_names_by_game,
    )

    logger.info(
        "ncaab_boxscore_batch_fetched",
        run_id=run_id,
        requested_games=len(games),
        boxscores_received=len(boxscores),
    )

    # Step 4: Persist boxscores
    games_processed = 0
    games_enriched = 0
    games_with_stats = 0

    for game_id, cbb_game_id, game_date, home_team_name, away_team_name in games:
        boxscore = boxscores.get(cbb_game_id)

        if not boxscore:
            logger.warning(
                "ncaab_boxscore_not_in_batch",
                run_id=run_id,
                game_id=game_id,
                cbb_game_id=cbb_game_id,
            )
            continue

        try:
            game_datetime = datetime.combine(game_date, datetime.min.time(), tzinfo=timezone.utc)
            boxscore.game_date = game_datetime

            normalized_game = convert_ncaab_boxscore_to_normalized_game(boxscore)

            result = persist_game_payload(session, normalized_game)

            if result.game_id is not None:
                games_processed += 1
                if result.enriched:
                    games_enriched += 1
                if result.has_player_stats:
                    games_with_stats += 1

                logger.info(
                    "ncaab_boxscore_ingested",
                    run_id=run_id,
                    game_id=game_id,
                    cbb_game_id=cbb_game_id,
                    enriched=result.enriched,
                    player_stats_inserted=result.player_stats.inserted if result.player_stats else 0,
                )

        except Exception as exc:
            logger.warning(
                "ncaab_boxscore_persist_failed",
                run_id=run_id,
                game_id=game_id,
                cbb_game_id=cbb_game_id,
                error=str(exc),
            )
            continue

    logger.info(
        "ncaab_boxscore_ingestion_complete",
        run_id=run_id,
        games_processed=games_processed,
        games_enriched=games_enriched,
        games_with_stats=games_with_stats,
    )

    return (games_processed, games_enriched, games_with_stats)


def convert_ncaab_boxscore_to_normalized_game(
    boxscore,  # NCAABBoxscore from live.ncaab
) -> NormalizedGame:
    """Convert NCAABBoxscore to NormalizedGame for persistence."""
    identity = GameIdentification(
        league_code="NCAAB",
        season=boxscore.season,
        season_type="regular",
        game_date=boxscore.game_date,
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
