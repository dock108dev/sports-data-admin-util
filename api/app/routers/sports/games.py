"""Game endpoints for sports admin."""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, exists, func, select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession, get_db
from ...game_metadata.nuggets import generate_nugget
from ...game_metadata.scoring import excitement_score, quality_score
from ...game_metadata.services import RatingsService, StandingsService
from ...services.derived_metrics import compute_derived_metrics
from .common import (
    serialize_play_entry,
    serialize_player_stat,
    serialize_team_stat,
)
from .game_helpers import (
    apply_game_filters,
    build_preview_context,
    enqueue_single_game_run,
    normalize_score,
    preview_tags,
    resolve_team_key,
    select_preview_entry,
    serialize_social_posts,
    summarize_game,
)
from .schemas import (
    GameDetailResponse,
    GameListResponse,
    GameMeta,
    GamePreviewScoreResponse,
    JobResponse,
    OddsEntry,
)

router = APIRouter()
logger = logging.getLogger(__name__)


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

    base_stmt = apply_game_filters(
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
    count_stmt = apply_game_filters(
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
    summaries = [summarize_game(game) for game in games]

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


@router.get("/games/{game_id}/preview-score", response_model=GamePreviewScoreResponse)
async def get_game_preview_score(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GamePreviewScoreResponse:
    result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.league),
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    if not game.home_team or not game.away_team:
        logger.error("Preview score missing team data", extra={"game_id": game_id})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Game missing team data",
        )

    league_code = game.league.code if game.league else "UNKNOWN"
    ratings_service = RatingsService()
    standings_service = StandingsService()

    try:
        ratings = ratings_service.get_ratings(league_code)
        standings = standings_service.get_standings(league_code)
        home_key = resolve_team_key(game.home_team)
        away_key = resolve_team_key(game.away_team)
        home_rating = select_preview_entry(ratings, home_key, 0, "ratings")
        away_rating = select_preview_entry(ratings, away_key, 1, "ratings")
        home_standing = select_preview_entry(standings, home_key, 0, "standings")
        away_standing = select_preview_entry(standings, away_key, 1, "standings")
    except Exception as exc:
        logger.exception("Failed to build preview score", extra={"game_id": game_id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preview score unavailable",
        ) from exc

    context = build_preview_context(game, home_rating, away_rating)
    tags = preview_tags(home_rating, away_rating, home_standing, away_standing)
    preview = GamePreviewScoreResponse(
        game_id=str(game.id),
        excitement_score=normalize_score(excitement_score(context)),
        quality_score=normalize_score(
            quality_score(home_rating, away_rating, home_standing, away_standing)
        ),
        tags=tags,
        nugget=generate_nugget(context, tags),
    )
    return preview


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
        last_ingested_at=game.last_ingested_at,
        last_pbp_at=game.last_pbp_at,
        last_social_at=game.last_social_at,
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

    social_posts_entries = serialize_social_posts(game, game.social_posts or [])

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
    return await enqueue_single_game_run(
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
    return await enqueue_single_game_run(
        session,
        game,
        include_boxscores=False,
        include_odds=True,
        scraper_type="odds_resync",
    )
