"""Helper queries and ingestion utilities for scrape runs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from sqlalchemy import and_, exists, func, not_, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..db import db_models
from ..logging import logger
from ..persistence.plays import upsert_plays
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
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time()),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time()),
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
        db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time()),
        db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time()),
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

    live_status = db_models.GameStatus.live.value
    final_statuses = [db_models.GameStatus.final.value, db_models.GameStatus.completed.value]
    
    if is_backfill:
        # Backfill mode: include all completed/final games regardless of when they ended
        query = query.filter(
            or_(
                db_models.SportsGame.status == live_status,
                db_models.SportsGame.status.in_(final_statuses),
            )
        )
    else:
        # Real-time mode: only include live games or games that ended recently
        query = query.filter(
            or_(
                db_models.SportsGame.status == live_status,
                and_(
                    db_models.SportsGame.status.in_(final_statuses),
                    db_models.SportsGame.end_time.isnot(None),
                    db_models.SportsGame.end_time >= recent_cutoff,
                ),
            )
        )

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
            logger.info(
                "pbp_sportsref_not_supported",
                run_id=run_id,
                league=league_code,
                reason="fetch_play_by_play_not_implemented",
            )
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

        inserted = upsert_plays(session, game_id, payload.plays)
        if inserted:
            pbp_games += 1
            pbp_events += inserted

    return (pbp_games, pbp_events)
