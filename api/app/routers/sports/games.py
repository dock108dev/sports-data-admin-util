"""Game endpoints for sports admin."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, desc, exists, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import or_

from ... import db_models
from ...celery_client import get_celery_app
from ...db import AsyncSession, get_db
from ...services.derived_metrics import compute_derived_metrics
from ...services.moment_summaries import summarize_moment
from .common import (
    build_compact_hint,
    build_score_chips,
    dedupe_social_posts,
    find_compact_moment_bounds,
    get_compact_cache,
    post_contains_score,
    serialize_play_entry,
    serialize_player_stat,
    serialize_team_stat,
    store_compact_cache,
)
from .schemas import (
    CompactMoment,
    CompactMomentSummaryResponse,
    CompactMomentsResponse,
    CompactPbpResponse,
    CompactPostEntry,
    CompactPostsResponse,
    GameDetailResponse,
    GameListResponse,
    GameMeta,
    GameSummary,
    JobResponse,
    OddsEntry,
    ScrapeRunConfig,
    SocialPostEntry,
)

router = APIRouter()


def _apply_game_filters(
    stmt: Select[tuple[db_models.SportsGame]],
    leagues: Sequence[str] | None,
    season: int | None,
    team: str | None,
    start_date: date | None,
    end_date: date | None,
    missing_boxscore: bool,
    missing_player_stats: bool,
    missing_odds: bool,
    missing_social: bool,
    missing_any: bool,
) -> Select[tuple[db_models.SportsGame]]:
    if leagues:
        league_codes = [code.upper() for code in leagues]
        stmt = stmt.where(db_models.SportsGame.league.has(db_models.SportsLeague.code.in_(league_codes)))

    if season is not None:
        stmt = stmt.where(db_models.SportsGame.season == season)

    if team:
        pattern = f"%{team}%"
        stmt = stmt.where(
            or_(
                db_models.SportsGame.home_team.has(db_models.SportsTeam.name.ilike(pattern)),
                db_models.SportsGame.away_team.has(db_models.SportsTeam.name.ilike(pattern)),
                db_models.SportsGame.home_team.has(db_models.SportsTeam.short_name.ilike(pattern)),
                db_models.SportsGame.away_team.has(db_models.SportsTeam.short_name.ilike(pattern)),
                db_models.SportsGame.home_team.has(db_models.SportsTeam.abbreviation.ilike(pattern)),
                db_models.SportsGame.away_team.has(db_models.SportsTeam.abbreviation.ilike(pattern)),
            )
        )

    if start_date:
        start_dt = datetime.combine(start_date, datetime.min.time())
        stmt = stmt.where(db_models.SportsGame.game_date >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, datetime.max.time())
        stmt = stmt.where(db_models.SportsGame.game_date <= end_dt)

    if missing_boxscore:
        stmt = stmt.where(~db_models.SportsGame.team_boxscores.any())
    if missing_player_stats:
        stmt = stmt.where(~db_models.SportsGame.player_boxscores.any())
    if missing_odds:
        stmt = stmt.where(~db_models.SportsGame.odds.any())
    if missing_social:
        stmt = stmt.where(~db_models.SportsGame.social_posts.any())
    if missing_any:
        stmt = stmt.where(
            or_(
                ~db_models.SportsGame.team_boxscores.any(),
                ~db_models.SportsGame.player_boxscores.any(),
                ~db_models.SportsGame.odds.any(),
            )
        )
    return stmt


def _summarize_game(game: db_models.SportsGame) -> GameSummary:
    has_boxscore = bool(game.team_boxscores)
    has_player_stats = bool(game.player_boxscores)
    has_odds = bool(game.odds)
    social_posts = getattr(game, "social_posts", []) or []
    has_social = bool(social_posts)
    social_post_count = len(social_posts)
    plays = getattr(game, "plays", []) or []
    has_pbp = bool(plays)
    play_count = len(plays)
    return GameSummary(
        id=game.id,
        league_code=game.league.code if game.league else "UNKNOWN",
        game_date=game.game_date,
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        home_score=game.home_score,
        away_score=game.away_score,
        has_boxscore=has_boxscore,
        has_player_stats=has_player_stats,
        has_odds=has_odds,
        has_social=has_social,
        has_pbp=has_pbp,
        play_count=play_count,
        social_post_count=social_post_count,
        has_required_data=has_boxscore and has_odds,
        scrape_version=getattr(game, "scrape_version", None),
        last_scraped_at=game.last_scraped_at,
    )


def _resolve_team_abbreviation(
    game: db_models.SportsGame,
    post: db_models.GameSocialPost,
) -> str:
    if hasattr(post, "team") and post.team and post.team.abbreviation:
        return post.team.abbreviation
    if hasattr(post, "team_id"):
        if game.home_team and game.home_team.id == post.team_id:
            return game.home_team.abbreviation
        if game.away_team and game.away_team.id == post.team_id:
            return game.away_team.abbreviation
    return "UNK"


def _serialize_social_posts(
    game: db_models.SportsGame,
    posts: Sequence[db_models.GameSocialPost],
) -> list[SocialPostEntry]:
    entries: list[SocialPostEntry] = []
    for post in posts:
        entries.append(
            SocialPostEntry(
                id=post.id,
                post_url=post.post_url,
                posted_at=post.posted_at,
                has_video=post.has_video,
                team_abbreviation=_resolve_team_abbreviation(game, post),
                tweet_text=post.tweet_text,
                video_url=post.video_url,
                image_url=post.image_url,
                source_handle=post.source_handle,
                media_type=post.media_type,
            )
        )
    return entries


@router.get("/games", response_model=GameListResponse)
async def list_games(
    session: AsyncSession = Depends(get_db),
    league: list[str] | None = Query(None),
    season: int | None = Query(None),
    team: str | None = Query(None),
    startDate: date | None = Query(None, alias="startDate"),
    endDate: date | None = Query(None, alias="endDate"),
    missingBoxscore: bool = Query(False, alias="missingBoxscore"),
    missingPlayerStats: bool = Query(False, alias="missingPlayerStats"),
    missingOdds: bool = Query(False, alias="missingOdds"),
    missingSocial: bool = Query(False, alias="missingSocial"),
    missingAny: bool = Query(False, alias="missingAny"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> GameListResponse:
    base_stmt = select(db_models.SportsGame).options(
        selectinload(db_models.SportsGame.league),
        selectinload(db_models.SportsGame.home_team),
        selectinload(db_models.SportsGame.away_team),
        selectinload(db_models.SportsGame.team_boxscores),
        selectinload(db_models.SportsGame.player_boxscores),
        selectinload(db_models.SportsGame.odds),
        selectinload(db_models.SportsGame.social_posts),
        selectinload(db_models.SportsGame.plays),
    )

    base_stmt = _apply_game_filters(
        base_stmt,
        leagues=league,
        season=season,
        team=team,
        start_date=startDate,
        end_date=endDate,
        missing_boxscore=missingBoxscore,
        missing_player_stats=missingPlayerStats,
        missing_odds=missingOdds,
        missing_social=missingSocial,
        missing_any=missingAny,
    )

    stmt = base_stmt.order_by(desc(db_models.SportsGame.game_date)).offset(offset).limit(limit)
    results = await session.execute(stmt)
    games = results.scalars().unique().all()

    count_stmt = select(func.count(db_models.SportsGame.id))
    count_stmt = _apply_game_filters(
        count_stmt,
        leagues=league,
        season=season,
        team=team,
        start_date=startDate,
        end_date=endDate,
        missing_boxscore=missingBoxscore,
        missing_player_stats=missingPlayerStats,
        missing_odds=missingOdds,
        missing_social=missingSocial,
        missing_any=missingAny,
    )
    total = (await session.execute(count_stmt)).scalar_one()

    with_boxscore_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id))
    )
    with_player_stats_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsPlayerBoxscore.game_id == db_models.SportsGame.id))
    )
    with_odds_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsGameOdds.game_id == db_models.SportsGame.id))
    )
    with_social_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.GameSocialPost.game_id == db_models.SportsGame.id))
    )
    with_pbp_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id))
    )

    with_boxscore_count = (await session.execute(with_boxscore_count_stmt)).scalar_one()
    with_player_stats_count = (await session.execute(with_player_stats_count_stmt)).scalar_one()
    with_odds_count = (await session.execute(with_odds_count_stmt)).scalar_one()
    with_social_count = (await session.execute(with_social_count_stmt)).scalar_one()
    with_pbp_count = (await session.execute(with_pbp_count_stmt)).scalar_one()

    next_offset = offset + limit if offset + limit < total else None
    summaries = [_summarize_game(game) for game in games]

    return GameListResponse(
        games=summaries,
        total=total,
        next_offset=next_offset,
        with_boxscore_count=with_boxscore_count,
        with_player_stats_count=with_player_stats_count,
        with_odds_count=with_odds_count,
        with_social_count=with_social_count,
        with_pbp_count=with_pbp_count,
    )


@router.get("/games/{game_id}/compact", response_model=CompactMomentsResponse)
async def get_game_compact(game_id: int, session: AsyncSession = Depends(get_db)) -> CompactMomentsResponse:
    cached = get_compact_cache(game_id)
    if cached:
        return cached

    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = plays_result.scalars().all()

    moments: list[CompactMoment] = []
    moment_types: list[str] = []

    for play in plays:
        moment_type = play.play_type or "unknown"
        if moment_type not in moment_types:
            moment_types.append(moment_type)
        moments.append(
            CompactMoment(
                playIndex=play.play_index,
                quarter=play.quarter,
                gameClock=play.game_clock,
                momentType=moment_type,
                hint=build_compact_hint(play, moment_type),
            )
        )

    score_chips = build_score_chips(plays)
    response = CompactMomentsResponse(moments=moments, momentTypes=moment_types, scoreChips=score_chips)
    store_compact_cache(game_id, response)
    return response


@router.get("/games/{game_id}/compact/{moment_id}/pbp", response_model=CompactPbpResponse)
async def get_game_compact_pbp(
    game_id: int,
    moment_id: int,
    session: AsyncSession = Depends(get_db),
) -> CompactPbpResponse:
    compact_response = get_compact_cache(game_id)
    if compact_response is None:
        compact_response = await get_game_compact(game_id, session)

    try:
        start_index, end_index = find_compact_moment_bounds(compact_response.moments, moment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if end_index is None:
        max_index_stmt = select(func.max(db_models.SportsGamePlay.play_index)).where(
            db_models.SportsGamePlay.game_id == game_id
        )
        end_index = (await session.execute(max_index_stmt)).scalar_one_or_none()

    if end_index is None or end_index < start_index:
        return CompactPbpResponse(plays=[])

    plays_stmt = (
        select(db_models.SportsGamePlay)
        .where(
            db_models.SportsGamePlay.game_id == game_id,
            db_models.SportsGamePlay.play_index >= start_index,
            db_models.SportsGamePlay.play_index <= end_index,
        )
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays_result = await session.execute(plays_stmt)
    plays = plays_result.scalars().all()
    plays_entries = [serialize_play_entry(play) for play in plays]
    return CompactPbpResponse(plays=plays_entries)


@router.get("/games/{game_id}/compact/{moment_id}/posts", response_model=CompactPostsResponse)
async def get_game_compact_posts(
    game_id: int,
    moment_id: int,
    session: AsyncSession = Depends(get_db),
) -> CompactPostsResponse:
    compact_response = get_compact_cache(game_id)
    if compact_response is None:
        compact_response = await get_game_compact(game_id, session)

    try:
        start_index, end_index = find_compact_moment_bounds(compact_response.moments, moment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if end_index is None:
        max_index_stmt = select(func.max(db_models.SportsGamePlay.play_index)).where(
            db_models.SportsGamePlay.game_id == game_id
        )
        end_index = (await session.execute(max_index_stmt)).scalar_one_or_none()

    if end_index is None or end_index < start_index:
        return CompactPostsResponse(posts=[])

    bounds_stmt = select(
        func.min(db_models.SportsGamePlay.created_at),
        func.max(db_models.SportsGamePlay.created_at),
    ).where(
        db_models.SportsGamePlay.game_id == game_id,
        db_models.SportsGamePlay.play_index >= start_index,
        db_models.SportsGamePlay.play_index <= end_index,
    )
    bounds_result = await session.execute(bounds_stmt)
    bounds = bounds_result.one_or_none()
    if not bounds or bounds[0] is None or bounds[1] is None:
        return CompactPostsResponse(posts=[])

    start_time, end_time = bounds
    if end_time < start_time:
        start_time, end_time = end_time, start_time

    if end_time - start_time < timedelta(seconds=30):
        padding = timedelta(minutes=5)
        start_time -= padding
        end_time += padding

    posts_stmt = (
        select(db_models.GameSocialPost)
        .options(selectinload(db_models.GameSocialPost.team))
        .where(
            db_models.GameSocialPost.game_id == game_id,
            db_models.GameSocialPost.posted_at >= start_time,
            db_models.GameSocialPost.posted_at <= end_time,
        )
        .order_by(db_models.GameSocialPost.posted_at)
    )
    posts_result = await session.execute(posts_stmt)
    posts = posts_result.scalars().all()
    deduped_posts = dedupe_social_posts(posts)

    entries: list[CompactPostEntry] = []
    for post in deduped_posts:
        team_abbr = post.team.abbreviation if post.team and post.team.abbreviation else "UNK"
        entries.append(
            CompactPostEntry(
                id=post.id,
                post_url=post.post_url,
                posted_at=post.posted_at,
                has_video=post.has_video,
                team_abbreviation=team_abbr,
                tweet_text=post.tweet_text,
                video_url=post.video_url,
                image_url=post.image_url,
                source_handle=post.source_handle,
                media_type=post.media_type,
                containsScore=post_contains_score(post.tweet_text),
            )
        )

    return CompactPostsResponse(posts=entries)


@router.get("/games/{game_id}/compact/{moment_id}/summary", response_model=CompactMomentSummaryResponse)
async def get_game_compact_summary(
    game_id: int,
    moment_id: int,
    session: AsyncSession = Depends(get_db),
) -> CompactMomentSummaryResponse:
    try:
        summary = await summarize_moment(game_id, moment_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CompactMomentSummaryResponse(summary=summary)


@router.get("/games/{game_id}", response_model=GameDetailResponse)
async def get_game(game_id: int, session: AsyncSession = Depends(get_db)) -> GameDetailResponse:
    result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.league),
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
            selectinload(db_models.SportsGame.team_boxscores).selectinload(db_models.SportsTeamBoxscore.team),
            selectinload(db_models.SportsGame.player_boxscores).selectinload(db_models.SportsPlayerBoxscore.team),
            selectinload(db_models.SportsGame.odds),
            selectinload(db_models.SportsGame.social_posts),
            selectinload(db_models.SportsGame.plays),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    team_stats = [serialize_team_stat(box) for box in game.team_boxscores]
    player_stats = [serialize_player_stat(player) for player in game.player_boxscores]
    odds_entries = [
        OddsEntry(
            book=odd.book,
            market_type=odd.market_type,
            side=odd.side,
            line=odd.line,
            price=odd.price,
            is_closing_line=odd.is_closing_line,
            observed_at=odd.observed_at,
        )
        for odd in game.odds
    ]

    plays_entries = [serialize_play_entry(play) for play in sorted(game.plays, key=lambda p: p.play_index)]

    meta = GameMeta(
        id=game.id,
        league_code=game.league.code if game.league else "UNKNOWN",
        season=game.season,
        season_type=getattr(game, "season_type", None),
        game_date=game.game_date,
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        home_score=game.home_score,
        away_score=game.away_score,
        status=game.status,
        scrape_version=getattr(game, "scrape_version", None),
        last_scraped_at=game.last_scraped_at,
        has_boxscore=bool(game.team_boxscores),
        has_player_stats=bool(game.player_boxscores),
        has_odds=bool(game.odds),
        has_social=bool(game.social_posts),
        has_pbp=bool(game.plays),
        play_count=len(game.plays) if game.plays else 0,
        social_post_count=len(game.social_posts) if game.social_posts else 0,
        home_team_x_handle=game.home_team.x_handle if game.home_team else None,
        away_team_x_handle=game.away_team.x_handle if game.away_team else None,
    )

    social_posts_entries = _serialize_social_posts(game, game.social_posts or [])

    derived = compute_derived_metrics(game, game.odds)
    raw_payloads = {
        "team_boxscores": [
            {
                "team": box.team.name if box.team else "Unknown",
                "stats": box.stats,
                "source": box.source,
            }
            for box in game.team_boxscores
            if box.stats
        ],
        "player_boxscores": [
            {
                "team": player.team.name if player.team else "Unknown",
                "player": player.player_name,
                "stats": player.stats,
            }
            for player in game.player_boxscores
            if player.stats
        ],
        "odds": [
            {
                "book": odd.book,
                "market_type": odd.market_type,
                "raw": odd.raw_payload,
            }
            for odd in game.odds
            if odd.raw_payload
        ],
    }

    return GameDetailResponse(
        game=meta,
        team_stats=team_stats,
        player_stats=player_stats,
        odds=odds_entries,
        social_posts=social_posts_entries,
        plays=plays_entries,
        derived_metrics=derived,
        raw_payloads=raw_payloads,
    )


async def _enqueue_single_game_run(
    session: AsyncSession,
    game: db_models.SportsGame,
    *,
    include_boxscores: bool,
    include_odds: bool,
    scraper_type: str,
) -> JobResponse:
    """Create a scrape run and enqueue it for a single game."""
    await session.refresh(game, attribute_names=["league"])
    if not game.league:
        raise HTTPException(status_code=400, detail="League missing for game")

    config = ScrapeRunConfig(
        league_code=game.league.code,
        season=game.season,
        season_type=getattr(game, "season_type", "regular"),
        start_date=game.game_date.date(),
        end_date=game.game_date.date(),
        boxscores=include_boxscores,
        odds=include_odds,
        social=False,
        pbp=False,
        only_missing=False,
        updated_before=None,
        include_books=None,
    )

    run = db_models.SportsScrapeRun(
        scraper_type=scraper_type,
        league_id=game.league_id,
        season=game.season,
        season_type=getattr(game, "season_type", "regular"),
        start_date=datetime.combine(game.game_date.date(), datetime.min.time()),
        end_date=datetime.combine(game.game_date.date(), datetime.min.time()),
        status="pending",
        requested_by="admin_boxscore_viewer",
        config=config.model_dump(by_alias=False),
    )
    session.add(run)
    await session.flush()

    worker_payload = config.to_worker_payload()
    celery_app = get_celery_app()
    async_result = celery_app.send_task(
        "run_scrape_job",
        args=[run.id, worker_payload],
        queue="bets-scraper",
        routing_key="bets-scraper",
    )
    run.job_id = async_result.id

    return JobResponse(run_id=run.id, job_id=async_result.id, message="Job enqueued")


@router.post("/games/{game_id}/rescrape", response_model=JobResponse)
async def rescrape_game(game_id: int, session: AsyncSession = Depends(get_db)) -> JobResponse:
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return await _enqueue_single_game_run(
        session,
        game,
        include_boxscores=True,
        include_odds=False,
        scraper_type="game_rescrape",
    )


@router.post("/games/{game_id}/resync-odds", response_model=JobResponse)
async def resync_game_odds(game_id: int, session: AsyncSession = Depends(get_db)) -> JobResponse:
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return await _enqueue_single_game_run(
        session,
        game,
        include_boxscores=False,
        include_odds=True,
        scraper_type="odds_resync",
    )
