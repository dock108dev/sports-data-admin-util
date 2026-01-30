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
from zoneinfo import ZoneInfo

from sqlalchemy import exists, not_, or_
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..models import (
    GameIdentification,
    NormalizedGame,
)
from ..persistence import persist_game_payload
from ..utils.date_utils import ncaab_season_for_cbb_api
from ..utils.datetime_utils import date_to_utc_datetime
from .pbp_ingestion import _populate_nhl_game_ids

# US sports use Eastern Time for game dates
US_EASTERN = ZoneInfo("America/New_York")


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


def _normalize_team_name(name: str) -> str:
    """Normalize team name for fuzzy matching.

    Handles common variations between database and CBB API names:
    - Punctuation (apostrophes, periods, hyphens)
    - Common abbreviations (St. -> Saint, Int'l -> International)
    - Parenthetical location indicators (Loyola (MD) -> Loyola Maryland)
    """
    import re

    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower()

    # Replace parenthetical locations with space-separated
    # e.g., "Loyola (MD)" -> "Loyola MD"
    normalized = re.sub(r"\s*\(([^)]+)\)\s*", r" \1 ", normalized)

    # Common abbreviations
    replacements = [
        (r"\bst\.\s*", "saint "),
        (r"\bmt\.\s*", "mount "),
        (r"\bint'l\b", "international"),
        (r"\bgw\b", "george washington"),
        (r"\buconn\b", "connecticut"),
        (r"\bsmu\b", "southern methodist"),
        (r"\btcu\b", "texas christian"),
        (r"\bucla\b", "ucla"),  # Keep as is
        (r"\busc\b", "southern california"),
        (r"\blsu\b", "louisiana state"),
        (r"\bole miss\b", "mississippi"),
        (r"\bumkc\b", "missouri kansas city"),
        (r"\butsa\b", "texas san antonio"),
        (r"\butep\b", "texas el paso"),
        (r"\buab\b", "alabama birmingham"),
        (r"\biupui\b", "indiana purdue indianapolis"),
        (r"\bliu\b", "long island"),
        (r"\bunc\b", "north carolina"),
        (r"\bvcu\b", "virginia commonwealth"),
        (r"\bucf\b", "central florida"),
        (r"\bfiu\b", "florida international"),
        (r"\bcsu\b", "colorado state"),
        (r"\bfau\b", "florida atlantic"),
    ]

    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)

    # Remove remaining punctuation and extra whitespace
    normalized = re.sub(r"['\.\-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip()

    return normalized


def _populate_ncaab_game_ids(
    session: Session,
    *,
    run_id: int,
    start_date: date,
    end_date: date,
) -> int:
    """Populate cbb_game_id for NCAAB games that don't have it.

    Matches games by cbb_team_id + tip_time (UTC) to CBB API startDate (UTC).
    Both are actual start times in UTC - direct match.

    Returns:
        Number of games updated with CBB game IDs
    """
    from ..live.ncaab import NCAABLiveFeedClient

    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NCAAB"
    ).first()
    if not league:
        return 0

    # Find games without cbb_game_id that have tip_time
    cbb_game_id_expr = db_models.SportsGame.external_ids["cbb_game_id"].astext

    games_missing_id = (
        session.query(
            db_models.SportsGame.id,
            db_models.SportsGame.tip_time,
            db_models.SportsGame.home_team_id,
            db_models.SportsGame.away_team_id,
        )
        .filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
            db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
            db_models.SportsGame.tip_time.isnot(None),  # Must have tip_time
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

    # Build team_id -> cbb_team_id mapping from external_codes
    teams = session.query(
        db_models.SportsTeam.id,
        db_models.SportsTeam.external_codes,
    ).filter(
        db_models.SportsTeam.league_id == league.id
    ).all()

    team_to_cbb_id: dict[int, int] = {}
    for team_id, ext_codes in teams:
        if ext_codes and ext_codes.get("cbb_team_id"):
            team_to_cbb_id[team_id] = int(ext_codes["cbb_team_id"])

    logger.info(
        "ncaab_team_mappings_loaded",
        run_id=run_id,
        teams_with_cbb_id=len(team_to_cbb_id),
    )

    # Fetch CBB schedule
    client = NCAABLiveFeedClient()
    season = ncaab_season_for_cbb_api(start_date)
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

    # Build lookup by team IDs (no date - teams don't play each other on consecutive days)
    # Key: (cbb_home_id, cbb_away_id) -> (game_date, cbb_game_id)
    cbb_by_teams: dict[tuple[int, int], tuple[date, int]] = {}
    cbb_by_names: dict[tuple[str, str], tuple[date, int]] = {}

    for cg in cbb_games:
        if cg.status != "final":
            continue

        game_day = cg.game_date.date()

        # Index by team IDs (both orderings)
        cbb_by_teams[(cg.home_team_id, cg.away_team_id)] = (game_day, cg.game_id)
        cbb_by_teams[(cg.away_team_id, cg.home_team_id)] = (game_day, cg.game_id)

        # Index by normalized team names (both orderings)
        home_norm = _normalize_team_name(cg.home_team_name)
        away_norm = _normalize_team_name(cg.away_team_name)
        cbb_by_names[(home_norm, away_norm)] = (game_day, cg.game_id)
        cbb_by_names[(away_norm, home_norm)] = (game_day, cg.game_id)

    # Log sample of API team IDs for debugging
    sample_teams = set()
    for cg in cbb_games[:10]:
        sample_teams.add((cg.home_team_id, cg.home_team_name))
        sample_teams.add((cg.away_team_id, cg.away_team_name))

    logger.info(
        "ncaab_game_ids_api_games",
        run_id=run_id,
        total_api_games=len(cbb_games),
        final_games=sum(1 for cg in cbb_games if cg.status == "final"),
        sample_api_teams=list(sample_teams)[:10],
    )

    # Build team_id -> normalized team name mapping for fallback
    team_id_to_name: dict[int, str] = {}
    all_teams = session.query(
        db_models.SportsTeam.id,
        db_models.SportsTeam.name,
    ).filter(
        db_models.SportsTeam.league_id == league.id
    ).all()
    for team_id, team_name in all_teams:
        if team_name:
            team_id_to_name[team_id] = _normalize_team_name(team_name)

    # Match by team IDs + date, fallback to normalized names + date
    updated = 0
    unmatched = 0
    unmatched_reasons: dict[str, int] = {"no_team_mapping": 0, "no_api_match": 0, "time_mismatch": 0}

    for game_id, tip_time, home_team_id, away_team_id in games_missing_id:
        cbb_home_id = team_to_cbb_id.get(home_team_id)
        cbb_away_id = team_to_cbb_id.get(away_team_id)

        if not tip_time:
            unmatched += 1
            continue

        game_day = tip_time.date()
        cbb_game_id = None

        # Try matching by team IDs first
        if cbb_home_id and cbb_away_id:
            match = cbb_by_teams.get((cbb_home_id, cbb_away_id))
            if match:
                api_date, api_game_id = match
                # Allow +/- 1 day tolerance (timezone differences)
                if abs((api_date - game_day).days) <= 1:
                    cbb_game_id = api_game_id

        # Fallback: try matching by normalized team names
        if not cbb_game_id:
            home_name = team_id_to_name.get(home_team_id, "")
            away_name = team_id_to_name.get(away_team_id, "")

            if home_name and away_name:
                match = cbb_by_names.get((home_name, away_name))
                if match:
                    api_date, api_game_id = match
                    if abs((api_date - game_day).days) <= 1:
                        cbb_game_id = api_game_id

        if cbb_game_id:
            game = session.query(db_models.SportsGame).get(game_id)
            if game:
                new_external_ids = dict(game.external_ids) if game.external_ids else {}
                new_external_ids["cbb_game_id"] = cbb_game_id
                game.external_ids = new_external_ids
                updated += 1
        else:
            unmatched += 1
            # Track reason for debugging
            if not cbb_home_id or not cbb_away_id:
                unmatched_reasons["no_team_mapping"] += 1
            else:
                unmatched_reasons["no_api_match"] += 1

            # Log details for first few unmatched games to help debug
            if unmatched <= 5:
                db_home_name = team_id_to_name.get(home_team_id, "")
                db_away_name = team_id_to_name.get(away_team_id, "")
                # Check if team pair exists in API data at all
                match = cbb_by_teams.get((cbb_home_id, cbb_away_id)) if cbb_home_id and cbb_away_id else None
                logger.info(
                    "ncaab_game_unmatched_detail",
                    game_id=game_id,
                    db_game_day=str(game_day),
                    cbb_home_id=cbb_home_id,
                    cbb_away_id=cbb_away_id,
                    home_name=db_home_name,
                    away_name=db_away_name,
                    api_match_found=match is not None,
                    api_date=str(match[0]) if match else None,
                    date_diff=abs((match[0] - game_day).days) if match else None,
                )
                logger.debug(
                    "ncaab_game_unmatched_detail",
                    game_id=game_id,
                    game_day=str(game_day),
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    cbb_home_id=cbb_home_id,
                    cbb_away_id=cbb_away_id,
                    home_name_normalized=db_home_name if db_home_name else None,
                    away_name_normalized=db_away_name if db_away_name else None,
                )

    session.flush()
    logger.info(
        "ncaab_game_ids_populated",
        run_id=run_id,
        updated=updated,
        unmatched=unmatched,
        unmatched_reasons=unmatched_reasons,
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
) -> list[tuple[int, int, date, str, str]]:
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
        List of (game_id, cbb_game_id, game_date, home_team_name, away_team_name) tuples
    """
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == "NCAAB"
    ).first()
    if not league:
        return []

    # CBB game ID is stored in external_ids JSONB field under 'cbb_game_id' key
    cbb_game_id_expr = db_models.SportsGame.external_ids["cbb_game_id"].astext

    # Join with teams to get team names
    home_team = db_models.SportsTeam.__table__.alias("home_team")
    away_team = db_models.SportsTeam.__table__.alias("away_team")

    query = session.query(
        db_models.SportsGame.id,
        cbb_game_id_expr.label("cbb_game_id"),
        db_models.SportsGame.game_date,
        home_team.c.name.label("home_team_name"),
        away_team.c.name.label("away_team_name"),
    ).join(
        home_team,
        db_models.SportsGame.home_team_id == home_team.c.id,
    ).join(
        away_team,
        db_models.SportsGame.away_team_id == away_team.c.id,
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
    for game_id, cbb_game_id, game_date, home_team_name, away_team_name in rows:
        if cbb_game_id:
            try:
                cbb_id = int(cbb_game_id)
                game_day = game_date.date() if game_date else None
                if game_day and home_team_name and away_team_name:
                    results.append((game_id, cbb_id, game_day, home_team_name, away_team_name))
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

    Uses batch fetching to minimize API calls. The CBB API ignores the gameId
    parameter on /games/teams and /games/players endpoints, returning all games.
    Instead of making 2 API calls per game, we make just 2 API calls total for
    the entire date range and filter results in code.

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

    # Step 1: Populate missing CBB game IDs
    _populate_ncaab_game_ids(
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
        return (0, 0)

    logger.info(
        "ncaab_boxscore_games_selected",
        run_id=run_id,
        games=len(games),
        only_missing=only_missing,
        updated_before=str(updated_before) if updated_before else None,
    )

    # Step 3: Batch fetch boxscores (2 API calls total instead of 2 per game)
    client = NCAABLiveFeedClient()
    season = ncaab_season_for_cbb_api(start_date)

    # Build lookup structures for batch fetch
    cbb_game_ids = [cbb_game_id for _, cbb_game_id, _, _, _ in games]
    team_names_by_game = {
        cbb_game_id: (home_team_name, away_team_name)
        for _, cbb_game_id, _, home_team_name, away_team_name in games
    }

    # Batch fetch: 2 API calls total for teams + players
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
            # Update boxscore with correct game_date
            game_datetime = datetime.combine(game_date, datetime.min.time(), tzinfo=timezone.utc)
            boxscore.game_date = game_datetime

            # Convert to NormalizedGame for persistence
            normalized_game = _convert_ncaab_boxscore_to_normalized_game(boxscore)

            # Persist via existing infrastructure
            result = persist_game_payload(session, normalized_game)

            if result.game_id is not None:
                games_processed += 1
                if result.enriched:
                    games_enriched += 1

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
    )

    return (games_processed, games_enriched)


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
