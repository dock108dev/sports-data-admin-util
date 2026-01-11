"""Snapshot API endpoints for app consumption."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import selectinload

from .. import db_models
from ..config import settings
from ..db import AsyncSession, get_db
from ..services.recap_generator import build_recap
from ..services.reveal_levels import parse_reveal_level
from ..utils.datetime_utils import now_utc
from .game_snapshot_models import (
    GameSnapshot,
    GameSnapshotResponse,
    PbpResponse,
    RecapResponse,
    SocialPostSnapshot,
    SocialResponse,
    chunk_plays_by_period,
    post_reveal_level,
    team_snapshot,
)

router = APIRouter(tags=["game-snapshots"])
logger = logging.getLogger(__name__)

_VALID_RANGES = {"last2", "current", "next24"}


def _validate_range(range_value: str) -> None:
    if range_value not in _VALID_RANGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid range value",
        )


async def _record_snapshot_job_run(
    session: AsyncSession,
    *,
    started_at: datetime,
    status_value: str,
    leagues: list[str],
    error_summary: str | None = None,
) -> None:
    finished_at = now_utc()
    duration = (finished_at - started_at).total_seconds()
    session.add(
        db_models.SportsJobRun(
            phase="snapshot",
            leagues=leagues,
            status=status_value,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
            error_summary=error_summary,
        )
    )


@router.get("/games", response_model=GameSnapshotResponse)
async def list_games(
    range: str = Query("current"),
    league: str | None = Query(None),
    assume_now: datetime | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> GameSnapshotResponse:
    """
    List games by time window.

    Example request:
        GET /games?range=current
    Example request (single league):
        GET /games?range=current&league=NBA
    Example response:
        {
          "range": "current",
          "games": [
            {
              "id": 123,
              "league": "NBA",
              "status": "live",
              "start_time": "2026-01-15T02:00:00Z",
              "home_team": {"id": 1, "name": "Warriors", "abbreviation": "GSW"},
              "away_team": {"id": 2, "name": "Lakers", "abbreviation": "LAL"},
              "has_pbp": true,
              "has_social": false,
              "last_updated_at": "2026-01-15T03:00:00Z"
            }
          ]
        }
    """
    _validate_range(range)
    started_at = now_utc()
    league_filter: str | None = league.strip().upper() if league else None
    if league_filter == "":
        league_filter = None
    if assume_now is not None and settings.environment != "development":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="assume_now is only available in development",
        )
    if assume_now is not None:
        # If a naive datetime is provided, treat it as UTC for local testing.
        if assume_now.tzinfo is None or assume_now.tzinfo.utcoffset(assume_now) is None:
            assume_now = assume_now.replace(tzinfo=timezone.utc)
        now = assume_now.astimezone(timezone.utc)
    else:
        now = now_utc()
    window_start: datetime
    window_end: datetime

    if range == "last2":
        window_start = now - timedelta(hours=48)
        window_end = now
        filters = and_(
            db_models.SportsGame.game_date >= window_start,
            db_models.SportsGame.game_date <= window_end,
        )
    elif range == "next24":
        window_start = now
        window_end = now + timedelta(hours=24)
        filters = and_(
            db_models.SportsGame.game_date >= window_start,
            db_models.SportsGame.game_date <= window_end,
        )
    else:
        start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)
        filters = or_(
            and_(
                db_models.SportsGame.game_date >= start_of_day,
                db_models.SportsGame.game_date < end_of_day,
            ),
            db_models.SportsGame.status == db_models.GameStatus.live.value,
        )

    has_pbp = exists(select(1).where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id))
    has_social = exists(select(1).where(db_models.GameSocialPost.game_id == db_models.SportsGame.id))

    conflict_exists = exists(
        select(1)
        .where(db_models.SportsGameConflict.resolved_at.is_(None))
        .where(
            or_(
                db_models.SportsGameConflict.game_id == db_models.SportsGame.id,
                db_models.SportsGameConflict.conflict_game_id == db_models.SportsGame.id,
            )
        )
    )

    try:
        league_clause = (
            db_models.SportsGame.league.has(db_models.SportsLeague.code == league_filter)
            if league_filter
            else None
        )
        stmt = (
            select(
                db_models.SportsGame,
                has_pbp.label("has_pbp"),
                has_social.label("has_social"),
                conflict_exists.label("has_conflict"),
            )
            .options(
                selectinload(db_models.SportsGame.league),
                selectinload(db_models.SportsGame.home_team),
                selectinload(db_models.SportsGame.away_team),
            )
            .where(filters)
            .where(league_clause if league_clause is not None else True)
            .order_by(db_models.SportsGame.game_date.asc())
        )
        results = await session.execute(stmt)
        rows = results.all()
    except Exception as exc:
        await _record_snapshot_job_run(
            session,
            started_at=started_at,
            status_value="error",
            leagues=[],
            error_summary=str(exc),
        )
        await session.commit()
        raise

    games: list[GameSnapshot] = []
    excluded = 0
    league_codes: set[str] = set()
    for game, has_pbp_value, has_social_value, has_conflict in rows:
        league_code = game.league.code if game.league else "UNK"
        if league_filter and league_code != league_filter:
            # Safety guard: if the DB layer ever returns mixed leagues, do not serve them.
            excluded += 1
            logger.warning(
                "snapshot_game_excluded",
                extra={
                    "league": league_code,
                    "game_id": game.id,
                    "external_id": getattr(game, "source_game_key", None),
                    "reason": "league_filter_mismatch",
                    "requested_league": league_filter,
                },
            )
            continue
        league_codes.add(league_code)
        unsafe_reason: str | None = None
        if has_conflict:
            unsafe_reason = "conflict"
        elif not game.home_team or not game.away_team:
            # Safety exclusion: missing team mappings means we cannot guarantee identity.
            unsafe_reason = "team_mapping_missing"
        # Derived safety flag: exclude unsafe games from snapshot responses.
        safe_to_serve = unsafe_reason is None
        if not safe_to_serve:
            excluded += 1
            logger.warning(
                "snapshot_game_excluded",
                extra={
                    "league": league_code,
                    "game_id": game.id,
                    "external_id": getattr(game, "source_game_key", None),
                    "reason": unsafe_reason,
                },
            )
            continue
        timestamps = [
            game.last_ingested_at,
            game.last_pbp_at,
            game.last_social_at,
            game.last_scraped_at,
            game.updated_at,
        ]
        last_updated = max([dt for dt in timestamps if dt is not None], default=game.game_date)
        games.append(
            GameSnapshot(
                id=game.id,
                league=league_code,
                status=game.status,
                start_time=game.game_date,
                home_team=team_snapshot(game.home_team, fallback_id=game.home_team_id),
                away_team=team_snapshot(game.away_team, fallback_id=game.away_team_id),
                has_pbp=bool(has_pbp_value),
                has_social=bool(has_social_value),
                last_updated_at=last_updated,
            )
        )

    if excluded:
        logger.info("snapshot_games_excluded", extra={"range": range, "excluded": excluded})

    await _record_snapshot_job_run(
        session,
        started_at=started_at,
        status_value="success",
        leagues=sorted(league_codes),
    )
    return GameSnapshotResponse(range=range, games=games)


@router.get("/games/{game_id}/pbp", response_model=PbpResponse)
async def get_game_pbp(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> PbpResponse:
    """
    Fetch play-by-play grouped by period.

    Example request:
        GET /games/123/pbp
    Example response:
        {
          "periods": [
            {
              "period": 1,
              "events": [
                {"index": 1, "clock": "12:00", "description": "Tipoff", "play_type": "tip"}
              ]
            }
          ]
        }
    """
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = plays_result.scalars().all()
    if not plays:
        return PbpResponse(periods=[])

    return PbpResponse(periods=chunk_plays_by_period(plays))


@router.get("/games/{game_id}/social", response_model=SocialResponse)
async def get_game_social(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> SocialResponse:
    """
    Fetch social posts ordered by posted time.

    Example request:
        GET /games/123/social
    Example response:
        {
          "posts": [
            {
              "id": 99,
              "team": {"id": 1, "name": "Warriors", "abbreviation": "GSW"},
              "content": "Game day.",
              "posted_at": "2026-01-15T02:00:00Z",
              "reveal_level": "pre"
            }
          ]
        }
    """
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    posts_result = await session.execute(
        select(db_models.GameSocialPost)
        .options(selectinload(db_models.GameSocialPost.team))
        .where(db_models.GameSocialPost.game_id == game_id)
        .order_by(db_models.GameSocialPost.posted_at.asc())
    )
    posts = posts_result.scalars().all()
    return SocialResponse(
        posts=[
            SocialPostSnapshot(
                id=post.id,
                team=team_snapshot(post.team, fallback_id=post.team_id),
                content=post.tweet_text,
                posted_at=post.posted_at,
                reveal_level=post_reveal_level(post),
            )
            for post in posts
        ]
    )


@router.get("/games/{game_id}/recap", response_model=RecapResponse)
async def get_game_recap(
    game_id: int,
    reveal: str = Query("pre"),
    session: AsyncSession = Depends(get_db),
) -> RecapResponse:
    """
    Generate a recap for a game at the requested reveal level.

    Example request:
        GET /games/123/recap?reveal=pre
    Example response:
        {
          "game_id": 123,
          "reveal": "pre",
          "available": true,
          "summary": "The game featured momentum swings and key stretches.",
          "reason": null
        }
    """
    reveal_level = parse_reveal_level(reveal)
    if reveal_level is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reveal value")

    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = plays_result.scalars().all()

    posts_result = await session.execute(
        select(db_models.GameSocialPost)
        .options(selectinload(db_models.GameSocialPost.team))
        .where(db_models.GameSocialPost.game_id == game_id)
        .order_by(db_models.GameSocialPost.posted_at.asc())
    )
    posts = posts_result.scalars().all()

    recap = build_recap(
        game=game,
        plays=plays,
        social_posts=posts,
        reveal_level=reveal_level,
    )
    return RecapResponse(
        game_id=game_id,
        reveal=recap.reveal_level,
        available=recap.available,
        summary=recap.summary,
        reason=recap.reason,
    )
