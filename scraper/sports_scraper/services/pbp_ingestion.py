"""Play-by-play ingestion helpers.

Handles PBP fetching and persistence for different sources:
- Sports Reference (NBA)
- NHL API (NHL)
- College Basketball Data API (NCAAB)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import exists, not_, or_
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..persistence.plays import upsert_plays
from ..utils.date_utils import ncaab_season_for_cbb_api
from .game_selection import select_games_for_pbp_sportsref


def ingest_pbp_via_sportsref(
    session: Session,
    *,
    run_id: int,
    league_code: str,
    scraper,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> tuple[int, int]:
    """Ingest PBP using Sports Reference scraper implementations (non-live mode)."""
    if not scraper:
        logger.info(
            "pbp_sportsref_not_supported",
            run_id=run_id,
            league=league_code,
            reason="no_sportsref_scraper",
        )
        return (0, 0)

    games = select_games_for_pbp_sportsref(
        session,
        league_code=league_code,
        start_date=start_date,
        end_date=end_date,
        only_missing=only_missing,
        updated_before=updated_before,
    )
    logger.info(
        "pbp_sportsref_games_selected",
        run_id=run_id,
        league=league_code,
        games=len(games),
        only_missing=only_missing,
        updated_before=str(updated_before) if updated_before else None,
    )

    pbp_games = 0
    pbp_events = 0
    for game_id, source_game_key, game_date in games:
        try:
            payload = scraper.fetch_play_by_play(source_game_key, game_date)
        except NotImplementedError:
            logger.warning("pbp_unavailable_sportsref", run_id=run_id, league=league_code, reason="source_unavailable")
            return (0, 0)
        except Exception as exc:
            logger.warning(
                "pbp_sportsref_fetch_failed",
                run_id=run_id,
                league=league_code,
                game_id=game_id,
                source_game_key=source_game_key,
                error=str(exc),
            )
            continue

        inserted = upsert_plays(session, game_id, payload.plays, source="sportsref")
        if inserted:
            pbp_games += 1
            pbp_events += inserted

    return (pbp_games, pbp_events)


def select_games_for_pbp_nhl_api(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> list[tuple[int, int]]:
    """Return game ids and NHL game IDs for NHL API play-by-play ingestion.

    NHL PBP must be fetched via the official NHL API using the NHL game ID
    (like 2025020767) stored in external_ids['nhl_game_pk'].
    Sports Reference does not provide NHL PBP.

    Args:
        session: Database session
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have PBP data
        updated_before: Only include games with stale PBP data

    Returns:
        List of (game_id, nhl_game_id) tuples for games needing PBP
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
        db_models.SportsGame.status,
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
        # nhl_game_pk is required for NHL API PBP fetch
        nhl_game_pk_expr.isnot(None),
    )

    # No status filter - like NBA's select_games_for_pbp_sportsref, we use date range
    # (run_manager limits to yesterday and earlier) to determine which games should
    # have PBP. The NHL API will tell us if data is available.

    if only_missing:
        has_pbp = exists().where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id)
        query = query.filter(not_(has_pbp))

    if updated_before:
        has_fresh = exists().where(
            db_models.SportsGamePlay.game_id == db_models.SportsGame.id,
            db_models.SportsGamePlay.updated_at >= updated_before,
        )
        query = query.filter(not_(has_fresh))

    rows = query.all()
    results = []
    for game_id, nhl_game_pk, status in rows:
        if nhl_game_pk:
            try:
                nhl_game_id = int(nhl_game_pk)
                results.append((game_id, nhl_game_id))
            except (ValueError, TypeError):
                logger.warning(
                    "nhl_pbp_invalid_game_pk",
                    game_id=game_id,
                    nhl_game_pk=nhl_game_pk,
                )
    return results


def _populate_nhl_game_ids(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
) -> int:
    """Populate nhl_game_pk for NHL games that don't have it.

    Fetches the NHL schedule and matches games by team + date to populate
    the external_ids['nhl_game_pk'] field needed for PBP fetching.

    Returns:
        Number of games updated with NHL game IDs
    """
    from ..live.nhl import NHLLiveFeedClient

    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NHL"
    ).first()
    if not league:
        return 0

    # Find games without nhl_game_pk
    nhl_game_pk_expr = db_models.SportsGame.external_ids["nhl_game_pk"].astext

    # No status filter - we populate nhl_game_pk for all games in date range.
    # Like NBA, we use date range (yesterday and earlier) to determine which games
    # should be complete. The NHL API will confirm actual status.
    games_missing_pk = (
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
                nhl_game_pk_expr.is_(None),
                nhl_game_pk_expr == "",
            ),
        )
        .all()
    )

    if not games_missing_pk:
        logger.info(
            "nhl_game_ids_all_present",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
        )
        return 0

    logger.info(
        "nhl_game_ids_missing",
        run_id=run_id,
        count=len(games_missing_pk),
        start_date=str(start_date),
        end_date=str(end_date),
    )

    # Build team ID to abbreviation mapping
    teams = session.query(db_models.SportsTeam).filter(
        db_models.SportsTeam.league_id == league.id
    ).all()
    team_id_to_abbr = {t.id: t.abbreviation for t in teams}

    # Fetch NHL schedule
    client = NHLLiveFeedClient()
    nhl_games = client.fetch_schedule(start_date, end_date)

    # Build lookup: (home_abbr, away_abbr, date) -> nhl_game_id
    nhl_lookup: dict[tuple[str, str, date], int] = {}
    for ng in nhl_games:
        key = (
            ng.home_team.abbreviation.upper(),
            ng.away_team.abbreviation.upper(),
            ng.game_date.date(),
        )
        nhl_lookup[key] = ng.game_id

    # Match and update
    updated = 0
    for game_id, game_date, home_team_id, away_team_id in games_missing_pk:
        home_abbr = team_id_to_abbr.get(home_team_id, "").upper()
        away_abbr = team_id_to_abbr.get(away_team_id, "").upper()
        game_day = game_date.date() if game_date else None

        if not home_abbr or not away_abbr or not game_day:
            continue

        key = (home_abbr, away_abbr, game_day)
        nhl_game_id = nhl_lookup.get(key)

        if nhl_game_id:
            game = session.query(db_models.SportsGame).get(game_id)
            if game:
                # Update external_ids with nhl_game_pk
                new_external_ids = dict(game.external_ids) if game.external_ids else {}
                new_external_ids["nhl_game_pk"] = nhl_game_id
                game.external_ids = new_external_ids
                updated += 1
                logger.info(
                    "nhl_game_id_populated",
                    run_id=run_id,
                    game_id=game_id,
                    nhl_game_pk=nhl_game_id,
                    home=home_abbr,
                    away=away_abbr,
                )

    session.flush()
    logger.info(
        "nhl_game_ids_populated",
        run_id=run_id,
        updated=updated,
        total_missing=len(games_missing_pk),
    )
    return updated


def ingest_pbp_via_nhl_api(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> tuple[int, int]:
    """Ingest PBP using the official NHL API (api-web.nhle.com).

    This is the only way to get NHL play-by-play data - Sports Reference
    does not provide it.

    Flow:
    1. Populate nhl_game_pk for games missing it (via NHL schedule API)
    2. Select games with nhl_game_pk that need PBP
    3. Fetch and persist PBP for each game

    Args:
        session: Database session
        run_id: Scrape run ID for logging
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have PBP data
        updated_before: Only include games with stale PBP data

    Returns:
        Tuple of (games_with_pbp, total_events_inserted)
    """
    from ..live.nhl import NHLLiveFeedClient
    from ..live.nhl_constants import NHL_MIN_EXPECTED_PLAYS

    # Step 1: Populate missing NHL game IDs
    _populate_nhl_game_ids(
        session,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Step 2: Select games for PBP ingestion
    games = select_games_for_pbp_nhl_api(
        session,
        start_date=start_date,
        end_date=end_date,
        only_missing=only_missing,
        updated_before=updated_before,
    )

    if not games:
        logger.info(
            "nhl_pbp_no_games_selected",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
            only_missing=only_missing,
        )
        return (0, 0)

    logger.info(
        "nhl_pbp_games_selected",
        run_id=run_id,
        games=len(games),
        only_missing=only_missing,
        updated_before=str(updated_before) if updated_before else None,
    )

    # Step 3: Fetch and persist PBP
    client = NHLLiveFeedClient()
    pbp_games = 0
    pbp_events = 0

    for game_id, nhl_game_id in games:
        try:
            # Fetch PBP from NHL API
            payload = client.fetch_play_by_play(nhl_game_id)

            if not payload.plays:
                logger.warning(
                    "nhl_pbp_empty_response",
                    run_id=run_id,
                    game_id=game_id,
                    nhl_game_id=nhl_game_id,
                )
                continue

            # Validation: Check if game is final and event count is suspiciously low
            game = session.query(db_models.SportsGame).get(game_id)
            if game and game.status == db_models.GameStatus.final.value:
                if len(payload.plays) < NHL_MIN_EXPECTED_PLAYS:
                    logger.warning(
                        "nhl_pbp_insufficient_events",
                        run_id=run_id,
                        game_id=game_id,
                        nhl_game_id=nhl_game_id,
                        play_count=len(payload.plays),
                        expected_min=NHL_MIN_EXPECTED_PLAYS,
                    )

            # Persist plays
            inserted = upsert_plays(session, game_id, payload.plays, source="nhl_api")

            if inserted:
                pbp_games += 1
                pbp_events += inserted

                logger.info(
                    "nhl_pbp_ingested",
                    run_id=run_id,
                    game_id=game_id,
                    nhl_game_id=nhl_game_id,
                    events_inserted=inserted,
                )

        except Exception as exc:
            logger.warning(
                "nhl_pbp_fetch_failed",
                run_id=run_id,
                game_id=game_id,
                nhl_game_id=nhl_game_id,
                error=str(exc),
            )
            continue

    logger.info(
        "nhl_pbp_ingestion_complete",
        run_id=run_id,
        games_processed=pbp_games,
        total_events=pbp_events,
    )

    return (pbp_games, pbp_events)


# -----------------------------------------------------------------------------
# NCAAB PBP ingestion via College Basketball Data API
# -----------------------------------------------------------------------------


def select_games_for_pbp_ncaab_api(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> list[tuple[int, int]]:
    """Return game ids and CBB game IDs for NCAAB API play-by-play ingestion.

    NCAAB PBP is fetched via the College Basketball Data API using the CBB game ID
    stored in external_ids['cbb_game_id'].

    Args:
        session: Database session
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have PBP data
        updated_before: Only include games with stale PBP data

    Returns:
        List of (game_id, cbb_game_id) tuples for games needing PBP
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
        db_models.SportsGame.status,
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
        # cbb_game_id is required for CBB API PBP fetch
        cbb_game_id_expr.isnot(None),
    )

    if only_missing:
        has_pbp = exists().where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id)
        query = query.filter(not_(has_pbp))

    if updated_before:
        has_fresh = exists().where(
            db_models.SportsGamePlay.game_id == db_models.SportsGame.id,
            db_models.SportsGamePlay.updated_at >= updated_before,
        )
        query = query.filter(not_(has_fresh))

    rows = query.all()
    results = []
    for game_id, cbb_game_id, status in rows:
        if cbb_game_id:
            try:
                cbb_id = int(cbb_game_id)
                results.append((game_id, cbb_id))
            except (ValueError, TypeError):
                logger.warning(
                    "ncaab_pbp_invalid_game_id",
                    game_id=game_id,
                    cbb_game_id=cbb_game_id,
                )
    return results


def ingest_pbp_via_ncaab_api(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> tuple[int, int]:
    """Ingest PBP using the College Basketball Data API.

    Flow (follows NHL pattern):
    1. Populate cbb_game_id for games missing it (via CBB schedule API)
    2. Select games with cbb_game_id that need PBP
    3. Fetch and persist PBP for each game

    Args:
        session: Database session
        run_id: Scrape run ID for logging
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have PBP data
        updated_before: Only include games with stale PBP data

    Returns:
        Tuple of (games_with_pbp, total_events_inserted)
    """
    from ..live.ncaab import NCAABLiveFeedClient
    from ..live.ncaab_constants import NCAAB_MIN_EXPECTED_PLAYS
    from .boxscore_ingestion import _populate_ncaab_game_ids

    logger.info(
        "ncaab_pbp_ingestion_start",
        run_id=run_id,
        start_date=str(start_date),
        end_date=str(end_date),
        only_missing=only_missing,
    )

    # Step 1: Populate missing CBB game IDs
    _populate_ncaab_game_ids(
        session,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Step 2: Select games for PBP ingestion
    games = select_games_for_pbp_ncaab_api(
        session,
        start_date=start_date,
        end_date=end_date,
        only_missing=only_missing,
        updated_before=updated_before,
    )

    if not games:
        logger.info(
            "ncaab_pbp_no_games_selected",
            run_id=run_id,
            start_date=str(start_date),
            end_date=str(end_date),
            only_missing=only_missing,
        )
        return (0, 0)

    logger.info(
        "ncaab_pbp_games_selected",
        run_id=run_id,
        games=len(games),
        only_missing=only_missing,
        updated_before=str(updated_before) if updated_before else None,
    )

    # Fetch and persist PBP
    client = NCAABLiveFeedClient()
    pbp_games = 0
    pbp_events = 0

    for game_id, cbb_game_id in games:
        try:
            # Fetch PBP from CBB API
            payload = client.fetch_play_by_play(cbb_game_id)

            if not payload.plays:
                logger.warning(
                    "ncaab_pbp_empty_response",
                    run_id=run_id,
                    game_id=game_id,
                    cbb_game_id=cbb_game_id,
                )
                continue

            # Validation: Check if game is final and event count is suspiciously low
            game = session.query(db_models.SportsGame).get(game_id)
            if game and game.status == db_models.GameStatus.final.value:
                if len(payload.plays) < NCAAB_MIN_EXPECTED_PLAYS:
                    logger.warning(
                        "ncaab_pbp_insufficient_events",
                        run_id=run_id,
                        game_id=game_id,
                        cbb_game_id=cbb_game_id,
                        play_count=len(payload.plays),
                        expected_min=NCAAB_MIN_EXPECTED_PLAYS,
                    )

            # Persist plays
            inserted = upsert_plays(session, game_id, payload.plays, source="cbb_api")

            if inserted:
                pbp_games += 1
                pbp_events += inserted

                logger.info(
                    "ncaab_pbp_ingested",
                    run_id=run_id,
                    game_id=game_id,
                    cbb_game_id=cbb_game_id,
                    events_inserted=inserted,
                )

        except Exception as exc:
            logger.warning(
                "ncaab_pbp_fetch_failed",
                run_id=run_id,
                game_id=game_id,
                cbb_game_id=cbb_game_id,
                error=str(exc),
            )
            continue

    logger.info(
        "ncaab_pbp_ingestion_complete",
        run_id=run_id,
        games_processed=pbp_games,
        total_events=pbp_events,
    )

    return (pbp_games, pbp_events)
