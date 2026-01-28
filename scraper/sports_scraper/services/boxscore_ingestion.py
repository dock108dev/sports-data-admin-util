"""Boxscore ingestion via official APIs.

This module handles boxscore data ingestion for NHL and NCAAB games using
their respective official APIs instead of web scraping.

NHL: api-web.nhle.com
NCAAB: api.collegebasketballdata.com

Benefits:
- Single data source per league (schedule, PBP, and boxscores)
- Faster ingestion - REST API vs web scraping
- More reliable - official API less likely to break than HTML scraping
- No Sports Reference rate limiting
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import exists, not_, or_
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..models import (
    GameIdentification,
    NormalizedGame,
)
from ..persistence import persist_game_payload
from ..utils.datetime_utils import date_to_utc_datetime
from .pbp_ingestion import _populate_nhl_game_ids


def select_games_for_boxscores_nhl_api(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> list[tuple[int, int, date]]:
    """Return game ids and NHL game IDs for NHL API boxscore ingestion.

    NHL boxscores are fetched via the official NHL API using the NHL game ID
    (like 2025020767) stored in external_ids['nhl_game_pk'].

    Args:
        session: Database session
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have boxscore data
        updated_before: Only include games with stale boxscore data

    Returns:
        List of (game_id, nhl_game_id, game_date) tuples for games needing boxscores
    """
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NHL"
    ).first()
    if not league:
        return []

    # NHL game ID is stored in external_ids JSONB field under 'nhl_game_pk' key
    nhl_game_pk_expr = db_models.SportsGame.external_ids["nhl_game_pk"].astext

    query = session.query(
        db_models.SportsGame.id,
        nhl_game_pk_expr.label("nhl_game_pk"),
        db_models.SportsGame.game_date,
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
    )

    # No status filter - like NBA, we use date range (yesterday and earlier) to determine
    # which games should have boxscores. The NHL API will tell us if the game is complete,
    # and persist_game_payload will update the status to "final".

    if only_missing:
        has_boxscores = exists().where(
            db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id
        )
        query = query.filter(not_(has_boxscores))

    if updated_before:
        # Filter games with stale boxscore data
        has_fresh = exists().where(
            db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id,
            db_models.SportsTeamBoxscore.updated_at >= updated_before,
        )
        query = query.filter(not_(has_fresh))

    rows = query.all()
    results = []
    for game_id, nhl_game_pk, game_date in rows:
        if nhl_game_pk:
            try:
                nhl_game_id = int(nhl_game_pk)
                game_day = game_date.date() if game_date else None
                if game_day:
                    results.append((game_id, nhl_game_id, game_day))
            except (ValueError, TypeError):
                logger.warning(
                    "nhl_boxscore_invalid_game_pk",
                    game_id=game_id,
                    nhl_game_pk=nhl_game_pk,
                )
    return results


def _season_from_date(game_date: date) -> int:
    """Calculate NHL season year from a game date.

    NHL season runs from October to June. Games in January-June belong to
    the previous calendar year's season (e.g., January 2025 = 2024-25 season = 2025).
    """
    if game_date.month >= 10:
        # October-December: season starts this year
        return game_date.year + 1
    else:
        # January-June: season started last year
        return game_date.year


def ingest_boxscores_via_nhl_api(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> tuple[int, int]:
    """Ingest NHL boxscores using the official NHL API.

    This replaces Hockey Reference scraping for NHL boxscores. The NHL API
    provides all the same data through a faster and more reliable REST API.

    Flow:
    1. Populate nhl_game_pk for games missing it (via NHL schedule API)
    2. Select games with nhl_game_pk that need boxscore data
    3. Fetch boxscore from NHL API for each game
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
        Tuple of (games_processed, games_enriched)
    """
    from ..live.nhl import NHLLiveFeedClient

    # Step 1: Populate missing NHL game IDs
    _populate_nhl_game_ids(
        session,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Step 2: Select games for boxscore ingestion
    games = select_games_for_boxscores_nhl_api(
        session,
        start_date=start_date,
        end_date=end_date,
        only_missing=only_missing,
        updated_before=updated_before,
    )

    if not games:
        logger.info(
            "nhl_boxscore_no_games_selected",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
            only_missing=only_missing,
        )
        return (0, 0)

    logger.info(
        "nhl_boxscore_games_selected",
        run_id=run_id,
        games=len(games),
        only_missing=only_missing,
        updated_before=str(updated_before) if updated_before else None,
    )

    # Step 3: Fetch and persist boxscores
    client = NHLLiveFeedClient()
    games_processed = 0
    games_enriched = 0

    for game_id, nhl_game_id, game_date in games:
        try:
            # Fetch boxscore from NHL API
            boxscore = client.fetch_boxscore(nhl_game_id)

            if not boxscore:
                logger.warning(
                    "nhl_boxscore_empty_response",
                    run_id=run_id,
                    game_id=game_id,
                    nhl_game_id=nhl_game_id,
                )
                continue

            # Convert NHLBoxscore to NormalizedGame for persistence
            normalized_game = _convert_boxscore_to_normalized_game(
                boxscore, game_date
            )

            # Persist via existing infrastructure
            result = persist_game_payload(session, normalized_game)

            if result.game_id is not None:
                games_processed += 1
                if result.enriched:
                    games_enriched += 1

                logger.info(
                    "nhl_boxscore_ingested",
                    run_id=run_id,
                    game_id=game_id,
                    nhl_game_id=nhl_game_id,
                    enriched=result.enriched,
                    player_stats_inserted=result.player_stats.inserted if result.player_stats else 0,
                )

        except Exception as exc:
            logger.warning(
                "nhl_boxscore_fetch_failed",
                run_id=run_id,
                game_id=game_id,
                nhl_game_id=nhl_game_id,
                error=str(exc),
            )
            continue

    logger.info(
        "nhl_boxscore_ingestion_complete",
        run_id=run_id,
        games_processed=games_processed,
        games_enriched=games_enriched,
    )

    return (games_processed, games_enriched)


def _convert_boxscore_to_normalized_game(
    boxscore,  # NHLBoxscore from live.nhl
    game_date: date,
) -> NormalizedGame:
    """Convert NHLBoxscore to NormalizedGame for persistence.

    This bridges the NHL API boxscore format to our normalized persistence layer.
    """
    identity = GameIdentification(
        league_code="NHL",
        season=_season_from_date(game_date),
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


# -----------------------------------------------------------------------------
# NCAAB boxscore ingestion via College Basketball Data API
# -----------------------------------------------------------------------------


def _ncaab_season_from_date(game_date: date) -> int:
    """Calculate NCAAB season year from a game date.

    The CBB API uses the ending year of the season (e.g., 2026 for 2025-2026 season).
    NCAAB season runs from November to April:
    - November-December games: season = next year (Nov 2025 -> season 2026)
    - January-April games: season = current year (Jan 2026 -> season 2026)
    """
    if game_date.month >= 11:
        # November-December: season ends next year
        return game_date.year + 1
    else:
        # January-April: season ends this year
        return game_date.year


def _populate_ncaab_game_ids(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
) -> int:
    """Populate cbb_game_id for NCAAB games that don't have it.

    Fetches the CBB schedule and matches games by normalized team name + date
    to populate the external_ids['cbb_game_id'] field needed for boxscore/PBP fetching.

    This follows the same pattern as NHL's _populate_nhl_game_ids().

    Returns:
        Number of games updated with CBB game IDs
    """
    from ..live.ncaab import NCAABLiveFeedClient

    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NCAAB"
    ).first()
    if not league:
        return 0

    # Find games without cbb_game_id
    cbb_game_id_expr = db_models.SportsGame.external_ids["cbb_game_id"].astext

    games_missing_id = (
        session.query(
            db_models.SportsGame.id,
            db_models.SportsGame.game_date,
            db_models.SportsGame.home_team_id,
            db_models.SportsGame.away_team_id,
        )
        .filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
            db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
            or_(
                cbb_game_id_expr.is_(None),
                cbb_game_id_expr == "",
            ),
        )
        .all()
    )

    if not games_missing_id:
        logger.info(
            "ncaab_game_ids_all_present",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
        )
        return 0

    logger.info(
        "ncaab_game_ids_missing",
        run_id=run_id,
        count=len(games_missing_id),
        start_date=str(start_date),
        end_date=str(end_date),
    )

    # Build team ID to name mapping
    teams = session.query(db_models.SportsTeam).filter(
        db_models.SportsTeam.league_id == league.id
    ).all()
    team_id_to_name = {t.id: t.name for t in teams}

    # Fetch CBB schedule
    client = NCAABLiveFeedClient()
    season = _ncaab_season_from_date(start_date)
    cbb_games = client.fetch_games(start_date, end_date, season=season)

    if not cbb_games:
        logger.info(
            "ncaab_game_ids_no_api_games",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
            season=season,
        )
        return 0

    # Build lookup: (normalized_home_name, normalized_away_name, date) -> (cbb_game_id, api_game)
    cbb_lookup: dict[str, tuple[int, object]] = {}
    for cg in cbb_games:
        # Only include completed games
        if cg.status != "final":
            continue
        key = _make_ncaab_lookup_key(
            cg.home_team_name,
            cg.away_team_name,
            cg.game_date.date(),
        )
        cbb_lookup[key] = (cg.game_id, cg)
        # Also add reverse key since home/away might be swapped
        reverse_key = _make_ncaab_lookup_key(
            cg.away_team_name,
            cg.home_team_name,
            cg.game_date.date(),
        )
        cbb_lookup[reverse_key] = (cg.game_id, cg)

    # Match and update
    updated = 0
    for game_id, game_date, home_team_id, away_team_id in games_missing_id:
        home_name = team_id_to_name.get(home_team_id, "")
        away_name = team_id_to_name.get(away_team_id, "")
        game_day = game_date.date() if game_date else None

        if not home_name or not away_name or not game_day:
            continue

        key = _make_ncaab_lookup_key(home_name, away_name, game_day)
        match = cbb_lookup.get(key)

        if match:
            cbb_game_id, _ = match
            game = session.query(db_models.SportsGame).get(game_id)
            if game:
                # Update external_ids with cbb_game_id
                new_external_ids = dict(game.external_ids) if game.external_ids else {}
                new_external_ids["cbb_game_id"] = cbb_game_id
                game.external_ids = new_external_ids
                updated += 1
                logger.info(
                    "ncaab_game_id_populated",
                    run_id=run_id,
                    game_id=game_id,
                    cbb_game_id=cbb_game_id,
                    home=home_name,
                    away=away_name,
                )

    session.flush()
    logger.info(
        "ncaab_game_ids_populated",
        run_id=run_id,
        updated=updated,
        total_missing=len(games_missing_id),
    )
    return updated


def select_games_for_boxscores_ncaab_api(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> list[tuple[int, int, date]]:
    """Return game ids and CBB game IDs for NCAAB API boxscore ingestion.

    NCAAB boxscores are fetched via the CBB API using the CBB game ID
    stored in external_ids['cbb_game_id'].

    Args:
        session: Database session
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have boxscore data
        updated_before: Only include games with stale boxscore data

    Returns:
        List of (game_id, cbb_game_id, game_date) tuples for games needing boxscores
    """
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NCAAB"
    ).first()
    if not league:
        return []

    # CBB game ID is stored in external_ids JSONB field under 'cbb_game_id' key
    cbb_game_id_expr = db_models.SportsGame.external_ids["cbb_game_id"].astext

    query = session.query(
        db_models.SportsGame.id,
        cbb_game_id_expr.label("cbb_game_id"),
        db_models.SportsGame.game_date,
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
        # cbb_game_id is required for CBB API boxscore fetch
        cbb_game_id_expr.isnot(None),
    )

    if only_missing:
        has_boxscores = exists().where(
            db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id
        )
        query = query.filter(not_(has_boxscores))

    if updated_before:
        # Filter games with stale boxscore data
        has_fresh = exists().where(
            db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id,
            db_models.SportsTeamBoxscore.updated_at >= updated_before,
        )
        query = query.filter(not_(has_fresh))

    rows = query.all()
    results = []
    for game_id, cbb_game_id, game_date in rows:
        if cbb_game_id:
            try:
                cbb_id = int(cbb_game_id)
                game_day = game_date.date() if game_date else None
                if game_day:
                    results.append((game_id, cbb_id, game_day))
            except (ValueError, TypeError):
                logger.warning(
                    "ncaab_boxscore_invalid_game_id",
                    game_id=game_id,
                    cbb_game_id=cbb_game_id,
                )
    return results


def ingest_boxscores_via_ncaab_api(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> tuple[int, int]:
    """Ingest NCAAB boxscores using the College Basketball Data API.

    Flow:
    1. Fetch games from CBB API for date range
    2. For each game, fetch team and player boxscores
    3. Match to existing games in DB (created by Odds API)
    4. Persist via existing persist_game_payload()

    Args:
        session: Database session
        run_id: Scrape run ID for logging
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have boxscore data
        updated_before: Only include games with stale boxscore data

    Returns:
        Tuple of (games_processed, games_enriched)
    """
    from ..live.ncaab import NCAABLiveFeedClient

    logger.info(
        "ncaab_boxscore_ingestion_start",
        run_id=run_id,
        start_date=str(start_date),
        end_date=str(end_date),
        only_missing=only_missing,
    )

    client = NCAABLiveFeedClient()

    # Fetch games from CBB API
    season = _ncaab_season_from_date(start_date)
    api_games = client.fetch_games(start_date, end_date, season=season)

    if not api_games:
        logger.info(
            "ncaab_boxscore_no_games_from_api",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
            season=season,
        )
        return (0, 0)

    logger.info(
        "ncaab_boxscore_games_from_api",
        run_id=run_id,
        games=len(api_games),
        season=season,
    )

    # Get league ID
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NCAAB"
    ).first()
    if not league:
        logger.warning("ncaab_boxscore_no_league", run_id=run_id)
        return (0, 0)

    # Build lookup of existing games by team names + date
    # NCAAB games are matched by home_team_name + away_team_name + game_date
    existing_games = _build_ncaab_game_lookup(
        session,
        league_id=league.id,
        start_date=start_date,
        end_date=end_date,
        only_missing=only_missing,
        updated_before=updated_before,
    )

    games_processed = 0
    games_enriched = 0

    for api_game in api_games:
        # Only process completed games
        if api_game.status != "final":
            continue

        # Try to match to existing game in DB
        game_day = api_game.game_date.date()
        lookup_key = _make_ncaab_lookup_key(
            api_game.home_team_name,
            api_game.away_team_name,
            game_day,
        )

        db_game_id = existing_games.get(lookup_key)
        if db_game_id is None:
            # Try reverse order (away @ home)
            reverse_key = _make_ncaab_lookup_key(
                api_game.away_team_name,
                api_game.home_team_name,
                game_day,
            )
            db_game_id = existing_games.get(reverse_key)

        if db_game_id is None:
            # Game not found in DB - this is normal, Odds API may not have it
            logger.debug(
                "ncaab_boxscore_game_not_in_db",
                run_id=run_id,
                cbb_game_id=api_game.game_id,
                home=api_game.home_team_name,
                away=api_game.away_team_name,
                game_date=str(game_day),
            )
            continue

        try:
            # Fetch full boxscore
            boxscore = client.fetch_boxscore(api_game)

            if not boxscore:
                logger.warning(
                    "ncaab_boxscore_empty_response",
                    run_id=run_id,
                    db_game_id=db_game_id,
                    cbb_game_id=api_game.game_id,
                )
                continue

            # Convert to NormalizedGame for persistence
            normalized_game = _convert_ncaab_boxscore_to_normalized_game(boxscore)

            # Persist via existing infrastructure
            result = persist_game_payload(session, normalized_game)

            if result.game_id is not None:
                games_processed += 1
                if result.enriched:
                    games_enriched += 1

                # Store CBB game ID in external_ids for future reference
                _store_cbb_game_id(session, result.game_id, api_game.game_id)

                logger.info(
                    "ncaab_boxscore_ingested",
                    run_id=run_id,
                    db_game_id=result.game_id,
                    cbb_game_id=api_game.game_id,
                    enriched=result.enriched,
                    player_stats_inserted=result.player_stats.inserted if result.player_stats else 0,
                )

        except Exception as exc:
            logger.warning(
                "ncaab_boxscore_fetch_failed",
                run_id=run_id,
                cbb_game_id=api_game.game_id,
                error=str(exc),
            )
            continue

    logger.info(
        "ncaab_boxscore_ingestion_complete",
        run_id=run_id,
        games_processed=games_processed,
        games_enriched=games_enriched,
    )

    return (games_processed, games_enriched)


def _build_ncaab_game_lookup(
    session: Session,
    *,
    league_id: int,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> dict[str, int]:
    """Build lookup of NCAAB games by (home_team, away_team, date) -> game_id.

    Since NCAAB teams don't have stable abbreviations, we match by team name.
    """
    query = session.query(
        db_models.SportsGame.id,
        db_models.SportsGame.game_date,
        db_models.SportsTeam.name.label("home_team_name"),
    ).join(
        db_models.SportsTeam,
        db_models.SportsGame.home_team_id == db_models.SportsTeam.id,
    ).filter(
        db_models.SportsGame.league_id == league_id,
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

    # We need away team name too - do a separate join
    away_team = db_models.SportsTeam.__table__.alias("away_team")
    query = query.add_columns(away_team.c.name.label("away_team_name"))
    query = query.join(
        away_team,
        db_models.SportsGame.away_team_id == away_team.c.id,
    )

    lookup: dict[str, int] = {}
    for row in query.all():
        game_id = row[0]
        game_date = row[1]
        home_name = row[2]
        away_name = row[3]
        game_day = game_date.date() if game_date else None
        if game_day and home_name and away_name:
            key = _make_ncaab_lookup_key(home_name, away_name, game_day)
            lookup[key] = game_id

    return lookup


def _normalize_ncaab_team_name(name: str) -> str:
    """Normalize NCAAB team name for matching.

    Removes punctuation and normalizes whitespace for fuzzy matching.
    Does NOT expand abbreviations (St. stays as st, not state) to avoid
    false positives like "St. Louis" -> "State Louis".
    """
    normalized = name.lower().strip()
    # Remove punctuation but keep letters, numbers, spaces
    normalized = normalized.replace("'", "").replace(".", "").replace("-", " ").replace("&", "and")
    # Collapse multiple spaces
    normalized = " ".join(normalized.split())
    return normalized


def _make_ncaab_lookup_key(home_team: str, away_team: str, game_date: date) -> str:
    """Create a lookup key for NCAAB game matching.

    Normalizes team names for fuzzy matching.
    """
    home_norm = _normalize_ncaab_team_name(home_team)
    away_norm = _normalize_ncaab_team_name(away_team)
    return f"{home_norm}|{away_norm}|{game_date.isoformat()}"


def _store_cbb_game_id(session: Session, game_id: int, cbb_game_id: int) -> None:
    """Store CBB game ID in external_ids for future reference."""
    game = session.query(db_models.SportsGame).get(game_id)
    if game:
        new_external_ids = dict(game.external_ids) if game.external_ids else {}
        if "cbb_game_id" not in new_external_ids:
            new_external_ids["cbb_game_id"] = cbb_game_id
            game.external_ids = new_external_ids


def _convert_ncaab_boxscore_to_normalized_game(
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
