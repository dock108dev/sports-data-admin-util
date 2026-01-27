"""Game endpoints for sports admin."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, exists, func, or_, select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession, get_db
from ...game_metadata.nuggets import generate_nugget
from ...game_metadata.scoring import excitement_score, quality_score
from ...game_metadata.services import RatingsService, StandingsService
from ...services.derived_metrics import compute_derived_metrics
from ...services.timeline_generator import (
    TimelineGenerationError,
    generate_timeline_artifact,
)
from .common import (
    serialize_nhl_goalie,
    serialize_nhl_skater,
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
from .nhl_helpers import compute_nhl_data_health
from .schemas import (
    GameDetailResponse,
    GameListResponse,
    GameMeta,
    GamePreviewScoreResponse,
    GameStoryResponse,
    JobResponse,
    NHLGoalieStat,
    NHLSkaterStat,
    OddsEntry,
    StoryContent,
    StoryMoment,
    StoryPlay,
)
from ..game_snapshot_models import TimelineArtifactResponse

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
        selectinload(db_models.SportsGame.timeline_artifacts),
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

    stmt = (
        base_stmt.order_by(desc(db_models.SportsGame.game_date))
        .offset(offset)
        .limit(limit)
    )
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
        exists(
            select(1).where(
                db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id
            )
        )
    )
    with_player_stats_count_stmt = count_stmt.where(
        exists(
            select(1).where(
                db_models.SportsPlayerBoxscore.game_id == db_models.SportsGame.id
            )
        )
    )
    with_odds_count_stmt = count_stmt.where(
        exists(
            select(1).where(db_models.SportsGameOdds.game_id == db_models.SportsGame.id)
        )
    )
    with_social_count_stmt = count_stmt.where(
        exists(
            select(1).where(db_models.GameSocialPost.game_id == db_models.SportsGame.id)
        )
    )
    with_pbp_count_stmt = count_stmt.where(
        exists(
            select(1).where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id)
        )
    )
    # has_story: legacy (has_compact_story) OR v2 (moments_json not null)
    with_story_count_stmt = count_stmt.where(
        exists(
            select(1).where(
                db_models.SportsGameStory.game_id == db_models.SportsGame.id,
                or_(
                    db_models.SportsGameStory.has_compact_story.is_(True),
                    db_models.SportsGameStory.moments_json.isnot(None),
                ),
            )
        )
    )

    with_boxscore_count = (await session.execute(with_boxscore_count_stmt)).scalar_one()
    with_player_stats_count = (
        await session.execute(with_player_stats_count_stmt)
    ).scalar_one()
    with_odds_count = (await session.execute(with_odds_count_stmt)).scalar_one()
    with_social_count = (await session.execute(with_social_count_stmt)).scalar_one()
    with_pbp_count = (await session.execute(with_pbp_count_stmt)).scalar_one()
    with_story_count = (await session.execute(with_story_count_stmt)).scalar_one()

    # Query which games have stories in SportsGameStory table
    # has_story: legacy (has_compact_story) OR v2 (moments_json not null)
    game_ids = [game.id for game in games]
    if game_ids:
        story_check_stmt = select(db_models.SportsGameStory.game_id).where(
            db_models.SportsGameStory.game_id.in_(game_ids),
            or_(
                db_models.SportsGameStory.has_compact_story.is_(True),
                db_models.SportsGameStory.moments_json.isnot(None),
            ),
        )
        story_result = await session.execute(story_check_stmt)
        games_with_stories = set(story_result.scalars().all())
    else:
        games_with_stories = set()

    next_offset = offset + limit if offset + limit < total else None
    summaries = [
        summarize_game(game, has_story=game.id in games_with_stories)
        for game in games
    ]

    return GameListResponse(
        games=summaries,
        total=total,
        next_offset=next_offset,
        with_boxscore_count=with_boxscore_count,
        with_player_stats_count=with_player_stats_count,
        with_odds_count=with_odds_count,
        with_social_count=with_social_count,
        with_pbp_count=with_pbp_count,
        with_story_count=with_story_count,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )
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
        home_rating = select_preview_entry(ratings, home_key, "ratings")
        away_rating = select_preview_entry(ratings, away_key, "ratings")
        home_standing = select_preview_entry(standings, home_key, "standings")
        away_standing = select_preview_entry(standings, away_key, "standings")
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
async def get_game(
    game_id: int, session: AsyncSession = Depends(get_db)
) -> GameDetailResponse:
    result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.league),
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
            selectinload(db_models.SportsGame.team_boxscores).selectinload(
                db_models.SportsTeamBoxscore.team
            ),
            selectinload(db_models.SportsGame.player_boxscores).selectinload(
                db_models.SportsPlayerBoxscore.team
            ),
            selectinload(db_models.SportsGame.odds),
            selectinload(db_models.SportsGame.social_posts).selectinload(
                db_models.GameSocialPost.team
            ),
            selectinload(db_models.SportsGame.plays).selectinload(
                db_models.SportsGamePlay.team
            ),
            selectinload(db_models.SportsGame.timeline_artifacts),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )

    team_stats = [serialize_team_stat(box) for box in game.team_boxscores]

    # Determine if this is an NHL game
    league_code = game.league.code if game.league else None
    is_nhl = league_code == "NHL"

    # For NHL, separate skaters and goalies; for other sports use generic player stats
    nhl_skaters: list[NHLSkaterStat] | None = None
    nhl_goalies: list[NHLGoalieStat] | None = None
    player_stats: list = []

    if is_nhl:
        # NHL: populate sport-specific lists, leave player_stats empty
        skaters = []
        goalies = []
        for player in game.player_boxscores:
            stats = player.stats or {}
            player_role = stats.get("player_role")
            if player_role == "goalie":
                goalies.append(serialize_nhl_goalie(player))
            else:
                # Default to skater for NHL players without explicit role
                skaters.append(serialize_nhl_skater(player))
        nhl_skaters = skaters
        nhl_goalies = goalies
    else:
        # Non-NHL: use generic player stats
        player_stats = [
            serialize_player_stat(player) for player in game.player_boxscores
        ]

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

    plays_entries = [
        serialize_play_entry(play)
        for play in sorted(game.plays, key=lambda p: p.play_index)
    ]

    # Check if game has a story in SportsGameStory table
    # has_story: legacy (has_compact_story) OR v2 (moments_json not null)
    story_check = await session.execute(
        select(db_models.SportsGameStory.id).where(
            db_models.SportsGameStory.game_id == game_id,
            or_(
                db_models.SportsGameStory.has_compact_story.is_(True),
                db_models.SportsGameStory.moments_json.isnot(None),
            ),
        ).limit(1)
    )
    has_story = story_check.scalar() is not None

    meta = GameMeta(
        id=game.id,
        league_code=game.league.code if game.league else "UNKNOWN",
        season=game.season,
        season_type=getattr(game, "season_type", None),
        game_date=game.start_time,  # Use start_time which prioritizes tip_time
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
        has_story=has_story,
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

    # Compute NHL-specific data health (None for non-NHL games)
    data_health = compute_nhl_data_health(game, game.player_boxscores)

    return GameDetailResponse(
        game=meta,
        team_stats=team_stats,
        player_stats=player_stats,
        nhl_skaters=nhl_skaters,
        nhl_goalies=nhl_goalies,
        odds=odds_entries,
        social_posts=social_posts_entries,
        plays=plays_entries,
        derived_metrics=derived,
        raw_payloads=raw_payloads,
        data_health=data_health,
    )


@router.post("/games/{game_id}/rescrape", response_model=JobResponse)
async def rescrape_game(
    game_id: int, session: AsyncSession = Depends(get_db)
) -> JobResponse:
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )
    return await enqueue_single_game_run(
        session,
        game,
        include_boxscores=True,
        include_odds=False,
        scraper_type="game_rescrape",
    )


@router.post("/games/{game_id}/resync-odds", response_model=JobResponse)
async def resync_game_odds(
    game_id: int, session: AsyncSession = Depends(get_db)
) -> JobResponse:
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )
    return await enqueue_single_game_run(
        session,
        game,
        include_boxscores=False,
        include_odds=True,
        scraper_type="odds_resync",
    )


@router.post(
    "/games/{game_id}/timeline/generate", response_model=TimelineArtifactResponse
)
async def generate_game_timeline(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> TimelineArtifactResponse:
    """Generate and store a finalized NBA timeline artifact."""
    try:
        artifact = await generate_timeline_artifact(session, game_id)
    except TimelineGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    await session.commit()
    return TimelineArtifactResponse(
        game_id=artifact.game_id,
        sport=artifact.sport,
        timeline_version=artifact.timeline_version,
        generated_at=artifact.generated_at,
        timeline=artifact.timeline,
        summary=artifact.summary,
        game_analysis=artifact.game_analysis,
    )


# =============================================================================
# Story API (Task 6)
# =============================================================================

# Story version identifier for v2 moments format
STORY_VERSION_V2_MOMENTS = "v2-moments"


@router.get("/games/{game_id}/story", response_model=GameStoryResponse)
async def get_game_story(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GameStoryResponse:
    """Get the persisted Story for a game.

    Returns the Story exactly as persisted - no transformation, no aggregation.

    Story Contract:
    - moments: Ordered list of condensed moments with narratives
    - plays: Only plays referenced by moments
    - validation_passed: Whether validation passed
    - validation_errors: Any validation errors (empty if passed)

    Returns:
        GameStoryResponse with moments, plays, and validation status

    Raises:
        HTTPException 404: If no v2-moments Story exists for this game
    """
    # Load Story from SportsGameStory table
    # Only load v2-moments format - no fallback to legacy
    story_result = await session.execute(
        select(db_models.SportsGameStory).where(
            db_models.SportsGameStory.game_id == game_id,
            db_models.SportsGameStory.story_version == STORY_VERSION_V2_MOMENTS,
            db_models.SportsGameStory.moments_json.isnot(None),
        )
    )
    story_record = story_result.scalar_one_or_none()

    if not story_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Story found for game {game_id}",
        )

    # Get moments from persisted data (no transformation)
    moments_data = story_record.moments_json or []

    # Collect all play_ids referenced by moments
    all_play_ids: set[int] = set()
    for moment in moments_data:
        all_play_ids.update(moment.get("play_ids", []))

    # Load plays by play_ids
    plays_result = await session.execute(
        select(db_models.SportsGamePlay).where(
            db_models.SportsGamePlay.game_id == game_id,
            db_models.SportsGamePlay.play_index.in_(all_play_ids),
        )
    )
    plays_records = plays_result.scalars().all()

    # Build play lookup for ordering
    play_lookup = {p.play_index: p for p in plays_records}

    # Build response moments (exact data, no transformation)
    response_moments = [
        StoryMoment(
            playIds=moment["play_ids"],
            explicitlyNarratedPlayIds=moment["explicitly_narrated_play_ids"],
            period=moment["period"],
            startClock=moment.get("start_clock"),
            endClock=moment.get("end_clock"),
            scoreBefore=moment["score_before"],
            scoreAfter=moment["score_after"],
            narrative=moment["narrative"],
        )
        for moment in moments_data
    ]

    # Build response plays (only those referenced by moments, ordered by play_index)
    response_plays = [
        StoryPlay(
            playId=play.id,
            playIndex=play.play_index,
            period=play.quarter or 1,
            clock=play.game_clock,
            playType=play.play_type,
            description=play.description,
            homeScore=play.home_score,
            awayScore=play.away_score,
        )
        for play_index in sorted(all_play_ids)
        if (play := play_lookup.get(play_index))
    ]

    # Validation status from persisted data
    validation_passed = story_record.validated_at is not None

    return GameStoryResponse(
        gameId=game_id,
        story=StoryContent(moments=response_moments),
        plays=response_plays,
        validationPassed=validation_passed,
        validationErrors=[],
    )
