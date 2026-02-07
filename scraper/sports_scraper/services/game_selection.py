"""Game selection queries for scrape runs.

These functions select games that need scraping based on various filters.
Used by run_manager to determine which games to process.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from sqlalchemy import exists, func, not_, or_, and_
from sqlalchemy.orm import Session

from ..config import settings
from ..db import db_models
from ..utils.datetime_utils import now_utc


def select_games_for_boxscores(
    session: Session,
    league_code: str,
    start_date: date,
    end_date: date,
    *,
    only_missing: bool = False,
    updated_before: datetime | None = None,
) -> list[tuple[int, str, date | None]]:
    """Return game ids/keys for boxscore scraping with filters."""
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == league_code
    ).first()
    if not league:
        return []

    query = session.query(
        db_models.SportsGame.id,
        db_models.SportsGame.source_game_key,
        db_models.SportsGame.game_date,
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
        db_models.SportsGame.source_game_key.isnot(None),
    )

    if only_missing:
        has_boxscores = exists().where(
            db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id
        )
        query = query.filter(not_(has_boxscores))

    if updated_before:
        query = query.filter(db_models.SportsGame.updated_at < updated_before)

    results = query.all()
    return [(r.id, r.source_game_key, r.game_date.date() if r.game_date else None) for r in results]


def select_games_for_odds(
    session: Session,
    league_code: str,
    start_date: date,
    end_date: date,
    *,
    only_missing: bool = False,
) -> list[date]:
    """Return unique dates needing odds fetch."""
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == league_code
    ).first()
    if not league:
        return []

    query = session.query(
        func.date(db_models.SportsGame.game_date).label("game_day")
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
    ).distinct()

    if only_missing:
        has_odds = exists().where(
            db_models.SportsGameOdds.game_id == db_models.SportsGame.id
        )
        query = query.filter(not_(has_odds))

    results = query.all()
    return [r.game_day for r in results if r.game_day]


def select_games_for_social(
    session: Session,
    league_code: str,
    start_date: date,
    end_date: date,
    *,
    only_missing: bool = False,
    updated_before: datetime | None = None,
    is_backfill: bool = False,
    include_pregame: bool = True,
) -> list[int]:
    """Return game IDs for social scraping with filters.

    Args:
        session: Database session
        league_code: League to query (e.g., "NBA", "NHL")
        start_date: Start of date range
        end_date: End of date range
        only_missing: Skip games that already have social posts
        updated_before: Only include games with stale social data
        is_backfill: If True, skip the recent game window filter. Use this
                     for historical backfills where we want to scrape social
                     for games that ended more than `recent_game_window_hours` ago.
        include_pregame: If True, include scheduled (pregame) games for social collection.
                        This enables pregame social content without requiring boxscore data.
    """
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == league_code
    ).first()
    if not league:
        return []

    now = now_utc()
    recent_cutoff = now - timedelta(hours=settings.social_config.recent_game_window_hours)
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    query = session.query(db_models.SportsGame.id).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= start_dt,
        db_models.SportsGame.game_date <= end_dt,
    )

    scheduled_status = db_models.GameStatus.scheduled.value
    live_status = db_models.GameStatus.live.value
    final_statuses = [db_models.GameStatus.final.value]

    if is_backfill:
        # Backfill mode: include scheduled, live, and final games
        if include_pregame:
            query = query.filter(
                or_(
                    db_models.SportsGame.status == scheduled_status,
                    db_models.SportsGame.status == live_status,
                    db_models.SportsGame.status.in_(final_statuses),
                )
            )
        else:
            query = query.filter(
                or_(
                    db_models.SportsGame.status == live_status,
                    db_models.SportsGame.status.in_(final_statuses),
                )
            )
    else:
        # Real-time mode: include pregame, live, or recently ended final games
        status_conditions = [db_models.SportsGame.status == live_status]

        if include_pregame:
            # Include scheduled games with upcoming tip_time (within 48 hours)
            upcoming_cutoff = now + timedelta(hours=48)
            status_conditions.append(
                and_(
                    db_models.SportsGame.status == scheduled_status,
                    db_models.SportsGame.game_date <= upcoming_cutoff,
                )
            )

        # Include final games that ended recently
        status_conditions.append(
            and_(
                db_models.SportsGame.status.in_(final_statuses),
                db_models.SportsGame.end_time.isnot(None),
                db_models.SportsGame.end_time >= recent_cutoff,
            )
        )

        query = query.filter(or_(*status_conditions))

    if only_missing:
        has_posts = exists().where(
            db_models.GameSocialPost.game_id == db_models.SportsGame.id
        )
        query = query.filter(not_(has_posts))

    if updated_before:
        has_fresh = exists().where(
            db_models.GameSocialPost.game_id == db_models.SportsGame.id,
            db_models.GameSocialPost.updated_at >= updated_before,
        )
        query = query.filter(not_(has_fresh))

    return [r[0] for r in query.all()]


def select_games_for_pbp_sportsref(
    session: Session,
    *,
    league_code: str,
    start_date: date,
    end_date: date,
    only_missing: bool,
    updated_before: datetime | None,
) -> list[tuple[int, str, date]]:
    """Return game ids/keys for Sports Reference play-by-play ingestion."""
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == league_code
    ).first()
    if not league:
        return []

    query = session.query(
        db_models.SportsGame.id,
        db_models.SportsGame.source_game_key,
        db_models.SportsGame.game_date,
    ).filter(
        db_models.SportsGame.league_id == league.id,
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
        db_models.SportsGame.source_game_key.isnot(None),
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
    return [(gid, str(source_key), game_dt.date()) for gid, source_key, game_dt in rows if source_key]
