"""Odds persistence helpers.

Handles odds matching to games and persistence, including NCAAB-specific name matching.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import alias, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..models import NormalizedOddsSnapshot
from ..utils.db_queries import get_league_id
from ..utils.datetime_utils import now_utc
from .odds_matching import (
    cache_get,
    cache_set,
    canonicalize_team_names,
    match_game_by_names_ncaab,
    match_game_by_names_non_ncaab,
    match_game_by_team_ids,
    should_log,
)
from .teams import _find_team_by_name, _upsert_team


def upsert_odds(session: Session, snapshot: NormalizedOddsSnapshot) -> bool:
    """Upsert odds snapshot, matching to existing game.

    Tries multiple matching strategies:
    1. Match by team IDs (exact and swapped)
    2. Match by team names (NCAAB uses normalized matching, others use exact)

    Returns False if no matching game is found, True if odds were persisted.
    """
    league_id = get_league_id(session, snapshot.league_code)

    home_team_id = _find_team_by_name(session, league_id, snapshot.home_team.name, snapshot.home_team.abbreviation)
    if home_team_id is None:
        logger.debug(
            "odds_team_not_found_creating",
            team_name=snapshot.home_team.name,
            abbreviation=snapshot.home_team.abbreviation,
            league=snapshot.league_code,
        )
        home_team_id = _upsert_team(session, league_id, snapshot.home_team)
    else:
        if should_log(f"odds_team_found:{home_team_id}", sample=200):
            logger.debug(
                "odds_team_found",
                team_name=snapshot.home_team.name,
                team_id=home_team_id,
                league=snapshot.league_code,
            )

    away_team_id = _find_team_by_name(session, league_id, snapshot.away_team.name, snapshot.away_team.abbreviation)
    if away_team_id is None:
        logger.debug(
            "odds_team_not_found_creating",
            team_name=snapshot.away_team.name,
            abbreviation=snapshot.away_team.abbreviation,
            league=snapshot.league_code,
        )
        away_team_id = _upsert_team(session, league_id, snapshot.away_team)
    else:
        if should_log(f"odds_team_found:{away_team_id}", sample=200):
            logger.debug(
                "odds_team_found",
                team_name=snapshot.away_team.name,
                team_id=away_team_id,
                league=snapshot.league_code,
            )

    game_day = snapshot.game_date.date()
    cache_key = (
        snapshot.league_code,
        game_day,
        min(home_team_id, away_team_id),
        max(home_team_id, away_team_id),
    )
    cached = cache_get(cache_key)
    if cached is not False:
        game_id = cached  # type: ignore[assignment]
        if game_id is None:
            return False
        side_value = snapshot.side if snapshot.side else None
        stmt = (
            insert(db_models.SportsGameOdds)
            .values(
                game_id=game_id,
                book=snapshot.book,
                market_type=snapshot.market_type,
                side=side_value,
                line=snapshot.line,
                price=snapshot.price,
                is_closing_line=snapshot.is_closing_line,
                observed_at=snapshot.observed_at,
                source_key=snapshot.source_key,
                raw_payload=snapshot.raw_payload,
            )
            .on_conflict_do_update(
                index_elements=["game_id", "book", "market_type", "side", "is_closing_line"],
                set_={
                    "line": snapshot.line,
                    "price": snapshot.price,
                    "observed_at": snapshot.observed_at,
                    "source_key": snapshot.source_key,
                    "raw_payload": snapshot.raw_payload,
                    "updated_at": now_utc(),
                },
            )
        )
        session.execute(stmt)
        return True
    day_start = datetime.combine(game_day - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    day_end = datetime.combine(game_day + timedelta(days=1), datetime.max.time(), tzinfo=timezone.utc)

    if should_log("odds_matching_start"):
        logger.debug(
            "odds_matching_start",
            league=snapshot.league_code,
            home_team_name=snapshot.home_team.name,
            home_team_id=home_team_id,
            away_team_name=snapshot.away_team.name,
            away_team_id=away_team_id,
            game_date=str(game_day),
            game_datetime=str(snapshot.game_date),
            day_start=str(day_start),
            day_end=str(day_end),
        )

    home_canonical, away_canonical = canonicalize_team_names(snapshot)

    all_games_check = (
        select(
            db_models.SportsGame.id,
            db_models.SportsGame.game_date,
            db_models.SportsGame.home_team_id,
            db_models.SportsGame.away_team_id,
        )
        .where(db_models.SportsGame.league_id == league_id)
        .where(db_models.SportsGame.game_date >= day_start)
        .where(db_models.SportsGame.game_date <= day_end)
        .limit(10)
    )
    all_games = session.execute(all_games_check).all()

    diagnostic_games = []
    if all_games:
        team_ids = set()
        for game in all_games:
            team_ids.add(game[2])
            team_ids.add(game[3])

        teams_stmt = select(db_models.SportsTeam.id, db_models.SportsTeam.name).where(
            db_models.SportsTeam.id.in_(team_ids)
        )
        teams_map = {row[0]: row[1] for row in session.execute(teams_stmt).all()}

        diagnostic_games = [
            {
                "id": game[0],
                "date": str(game[1]),
                "home_id": game[2],
                "away_id": game[3],
                "home_name": teams_map.get(game[2], "unknown"),
                "away_name": teams_map.get(game[3], "unknown"),
            }
            for game in all_games
        ]

    if should_log("odds_diagnostic_all_games"):
        logger.debug(
            "odds_diagnostic_all_games",
            league=snapshot.league_code,
            game_date=str(game_day),
            day_start=str(day_start),
            day_end=str(day_end),
            total_games_count=len(all_games),
            diagnostic_games=diagnostic_games[:3],
            searching_for_home=snapshot.home_team.name,
            searching_for_away=snapshot.away_team.name,
        )

    home_team_alias = alias(db_models.SportsTeam)
    away_team_alias = alias(db_models.SportsTeam)

    games_check = (
        select(
            db_models.SportsGame.id,
            db_models.SportsGame.game_date,
            db_models.SportsGame.home_team_id,
            db_models.SportsGame.away_team_id,
        )
        .join(home_team_alias, db_models.SportsGame.home_team_id == home_team_alias.c.id)
        .join(away_team_alias, db_models.SportsGame.away_team_id == away_team_alias.c.id)
        .where(db_models.SportsGame.league_id == league_id)
        .where(db_models.SportsGame.game_date >= day_start)
        .where(db_models.SportsGame.game_date <= day_end)
        .where(
            or_(
                db_models.SportsGame.home_team_id == home_team_id,
                db_models.SportsGame.away_team_id == home_team_id,
                db_models.SportsGame.home_team_id == away_team_id,
                db_models.SportsGame.away_team_id == away_team_id,
                func.lower(home_team_alias.c.name) == func.lower(snapshot.home_team.name),
                func.lower(home_team_alias.c.name) == func.lower(home_canonical),
                func.lower(away_team_alias.c.name) == func.lower(snapshot.away_team.name),
                func.lower(away_team_alias.c.name) == func.lower(away_canonical),
                func.lower(home_team_alias.c.name) == func.lower(snapshot.away_team.name),
                func.lower(home_team_alias.c.name) == func.lower(away_canonical),
                func.lower(away_team_alias.c.name) == func.lower(snapshot.home_team.name),
                func.lower(away_team_alias.c.name) == func.lower(home_canonical),
            )
        )
        .limit(20)
    )
    potential_games = session.execute(games_check).all()

    if should_log("odds_potential_games_found"):
        logger.debug(
            "odds_potential_games_found",
            league=snapshot.league_code,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            potential_games_count=len(potential_games),
            potential_games=[
                {
                    "id": game[0],
                    "date": str(game[1]),
                    "home_id": game[2],
                    "away_id": game[3],
                }
                for game in potential_games[:5]
            ],
        )

    game_id = match_game_by_team_ids(session, league_id, home_team_id, away_team_id, day_start, day_end)

    logger.debug(
        "odds_exact_match_attempt",
        league=snapshot.league_code,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        game_id=game_id,
        matched=game_id is not None,
    )

    if game_id is None:
        if snapshot.league_code == "NCAAB":
            game_id = match_game_by_names_ncaab(
                session, league_id, snapshot, home_canonical, away_canonical, day_start, day_end
            )
        else:
            game_id = match_game_by_names_non_ncaab(
                session, league_id, snapshot, home_canonical, away_canonical, day_start, day_end
            )

    if game_id is None:
        home_team = session.execute(
            select(db_models.SportsTeam.name, db_models.SportsTeam.abbreviation).where(
                db_models.SportsTeam.id == home_team_id
            )
        ).first()
        away_team = session.execute(
            select(db_models.SportsTeam.name, db_models.SportsTeam.abbreviation).where(
                db_models.SportsTeam.id == away_team_id
            )
        ).first()

        if should_log("odds_game_missing"):
            logger.warning(
                "odds_game_missing",
                league=snapshot.league_code,
                home_team_name=snapshot.home_team.name,
                home_team_abbr=snapshot.home_team.abbreviation,
                home_team_id=home_team_id,
                home_team_db_name=home_team[0] if home_team else None,
                home_team_db_abbr=home_team[1] if home_team else None,
                away_team_name=snapshot.away_team.name,
                away_team_abbr=snapshot.away_team.abbreviation,
                away_team_id=away_team_id,
                away_team_db_name=away_team[0] if away_team else None,
                away_team_db_abbr=away_team[1] if away_team else None,
                game_date=str(snapshot.game_date.date()),
                game_datetime=str(snapshot.game_date),
                day_start=str(day_start),
                day_end=str(day_end),
                potential_games_count=len(potential_games),
                potential_games=[
                    {"id": game[0], "date": str(game[1]), "home_id": game[2], "away_id": game[3]}
                    for game in potential_games[:3]
                ],
            )
        cache_set(cache_key, None)
        return False

    side_value = snapshot.side if snapshot.side else None

    stmt = (
        insert(db_models.SportsGameOdds)
        .values(
            game_id=game_id,
            book=snapshot.book,
            market_type=snapshot.market_type,
            side=side_value,
            line=snapshot.line,
            price=snapshot.price,
            is_closing_line=snapshot.is_closing_line,
            observed_at=snapshot.observed_at,
            source_key=snapshot.source_key,
            raw_payload=snapshot.raw_payload,
        )
        .on_conflict_do_update(
            index_elements=["game_id", "book", "market_type", "side", "is_closing_line"],
            set_={
                "line": snapshot.line,
                "price": snapshot.price,
                "observed_at": snapshot.observed_at,
                "source_key": snapshot.source_key,
                "raw_payload": snapshot.raw_payload,
                "updated_at": now_utc(),
            },
        )
    )
    session.execute(stmt)
    cache_set(cache_key, game_id)
    return True
