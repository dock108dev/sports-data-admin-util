"""Game endpoints for sports admin."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, exists, func, not_, or_, select
from sqlalchemy.orm import selectinload

from ...db import AsyncSession, get_db
from ...db.sports import (
    SportsGame,
    SportsTeamBoxscore,
    SportsPlayerBoxscore,
    SportsGamePlay,
)
from ...db.odds import SportsGameOdds
from ...db.social import TeamSocialPost
from ...db.scraper import SportsGameConflict
from ...db.story import SportsGameFlow
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
    GameFlowBlock,
    GameFlowContent,
    GameFlowMoment,
    GameFlowPlay,
    GameFlowResponse,
    GameListResponse,
    GameMeta,
    GamePreviewScoreResponse,
    JobResponse,
    NHLGoalieStat,
    NHLSkaterStat,
    OddsEntry,
    TimelineArtifactResponse,
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
    hasPbp: bool = Query(
        False,
        alias="hasPbp",
        description="Only return games with play-by-play data",
    ),
    safe: bool = Query(
        False,
        description="Exclude games with conflicts or missing team mappings (app-safe mode)",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> GameListResponse:
    base_stmt = select(SportsGame).options(
        selectinload(SportsGame.league),
        selectinload(SportsGame.home_team),
        selectinload(SportsGame.away_team),
        selectinload(SportsGame.team_boxscores),
        selectinload(SportsGame.player_boxscores),
        selectinload(SportsGame.odds),
        selectinload(SportsGame.social_posts),
        selectinload(SportsGame.plays),
        selectinload(SportsGame.timeline_artifacts),
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

    # Filter to games with play-by-play data
    if hasPbp:
        pbp_exists = exists(
            select(1).where(
                SportsGamePlay.game_id == SportsGame.id
            )
        )
        base_stmt = base_stmt.where(pbp_exists)

    # Safety filtering: exclude games with conflicts or missing team mappings
    if safe:
        # Exclude games with unresolved conflicts
        conflict_exists = exists(
            select(1)
            .where(SportsGameConflict.resolved_at.is_(None))
            .where(
                or_(
                    SportsGameConflict.game_id == SportsGame.id,
                    SportsGameConflict.conflict_game_id
                    == SportsGame.id,
                )
            )
        )
        base_stmt = base_stmt.where(not_(conflict_exists))
        # Exclude games with missing team mappings
        base_stmt = base_stmt.where(
            SportsGame.home_team_id.isnot(None),
            SportsGame.away_team_id.isnot(None),
        )

    stmt = (
        base_stmt.order_by(desc(SportsGame.game_date))
        .offset(offset)
        .limit(limit)
    )
    results = await session.execute(stmt)
    games = results.scalars().unique().all()

    count_stmt = select(func.count(SportsGame.id))
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

    # Apply hasPbp filter to count query
    if hasPbp:
        pbp_exists_count = exists(
            select(1).where(
                SportsGamePlay.game_id == SportsGame.id
            )
        )
        count_stmt = count_stmt.where(pbp_exists_count)

    # Apply same safety filtering to count query
    if safe:
        conflict_exists_count = exists(
            select(1)
            .where(SportsGameConflict.resolved_at.is_(None))
            .where(
                or_(
                    SportsGameConflict.game_id == SportsGame.id,
                    SportsGameConflict.conflict_game_id
                    == SportsGame.id,
                )
            )
        )
        count_stmt = count_stmt.where(not_(conflict_exists_count))
        count_stmt = count_stmt.where(
            SportsGame.home_team_id.isnot(None),
            SportsGame.away_team_id.isnot(None),
        )

    total = (await session.execute(count_stmt)).scalar_one()

    with_boxscore_count_stmt = count_stmt.where(
        exists(
            select(1).where(
                SportsTeamBoxscore.game_id == SportsGame.id
            )
        )
    )
    with_player_stats_count_stmt = count_stmt.where(
        exists(
            select(1).where(
                SportsPlayerBoxscore.game_id == SportsGame.id
            )
        )
    )
    with_odds_count_stmt = count_stmt.where(
        exists(
            select(1).where(SportsGameOdds.game_id == SportsGame.id)
        )
    )
    with_social_count_stmt = count_stmt.where(
        exists(
            select(1).where(
                TeamSocialPost.game_id == SportsGame.id,
                TeamSocialPost.mapping_status == "mapped",
            )
        )
    )
    with_pbp_count_stmt = count_stmt.where(
        exists(
            select(1).where(SportsGamePlay.game_id == SportsGame.id)
        )
    )
    with_flow_count_stmt = count_stmt.where(
        exists(
            select(1).where(
                SportsGameFlow.game_id == SportsGame.id,
                SportsGameFlow.moments_json.isnot(None),
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
    with_flow_count = (await session.execute(with_flow_count_stmt)).scalar_one()

    # Query which games have flows in SportsGameFlow table
    game_ids = [game.id for game in games]
    if game_ids:
        flow_check_stmt = select(SportsGameFlow.game_id).where(
            SportsGameFlow.game_id.in_(game_ids),
            SportsGameFlow.moments_json.isnot(None),
        )
        flow_result = await session.execute(flow_check_stmt)
        games_with_flow = set(flow_result.scalars().all())
    else:
        games_with_flow = set()

    next_offset = offset + limit if offset + limit < total else None
    summaries = [
        summarize_game(game, has_flow=game.id in games_with_flow)
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
        with_flow_count=with_flow_count,
    )


@router.get("/games/{game_id}/preview-score", response_model=GamePreviewScoreResponse)
async def get_game_preview_score(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GamePreviewScoreResponse:
    result = await session.execute(
        select(SportsGame)
        .options(
            selectinload(SportsGame.league),
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
        )
        .where(SportsGame.id == game_id)
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
        select(SportsGame)
        .options(
            selectinload(SportsGame.league),
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
            selectinload(SportsGame.team_boxscores).selectinload(
                SportsTeamBoxscore.team
            ),
            selectinload(SportsGame.player_boxscores).selectinload(
                SportsPlayerBoxscore.team
            ),
            selectinload(SportsGame.odds),
            selectinload(SportsGame.social_posts).selectinload(
                TeamSocialPost.team
            ),
            selectinload(SportsGame.plays).selectinload(
                SportsGamePlay.team
            ),
            selectinload(SportsGame.timeline_artifacts),
        )
        .where(SportsGame.id == game_id)
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

    # Check if game has a flow in SportsGameFlow table
    flow_check = await session.execute(
        select(SportsGameFlow.id).where(
            SportsGameFlow.game_id == game_id,
            SportsGameFlow.moments_json.isnot(None),
        ).limit(1)
    )
    has_flow = flow_check.scalar() is not None

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
        has_flow=has_flow,
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
    game = await session.get(SportsGame, game_id)
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
    game = await session.get(SportsGame, game_id)
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
    """Generate and store a finalized timeline artifact for any league.

    Social data is optional and gracefully degrades to empty for leagues
    without social scraping configured (NHL, NCAAB).
    """
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
# Game Flow API
# =============================================================================

# Story version identifier (DB filter value — "v2-moments")
STORY_VERSION = "v2-moments"


@router.get("/games/{game_id}/flow", response_model=GameFlowResponse)
async def get_game_flow(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GameFlowResponse:
    """Get the persisted Game Flow for a game.

    Returns the Game Flow exactly as persisted - no transformation, no aggregation.

    Game Flow Contract:
    - moments: Ordered list of condensed moments with narratives
    - plays: Only plays referenced by moments
    - validation_passed: Whether validation passed
    - validation_errors: Any validation errors (empty if passed)
    - blocks: 4-7 narrative blocks (Phase 1, consumer-facing output)
    - total_words: Total word count across all block narratives

    Returns:
        GameFlowResponse with moments, plays, blocks, and validation status

    Raises:
        HTTPException 404: If no Game Flow exists for this game
    """
    flow_result = await session.execute(
        select(SportsGameFlow).where(
            SportsGameFlow.game_id == game_id,
            SportsGameFlow.story_version == STORY_VERSION,
            SportsGameFlow.moments_json.isnot(None),
        )
    )
    flow_record = flow_result.scalar_one_or_none()

    if not flow_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Game Flow found for game {game_id}",
        )

    # Get moments from persisted data (no transformation)
    moments_data = flow_record.moments_json or []

    # Collect all play_ids referenced by moments
    all_play_ids: set[int] = set()
    for moment in moments_data:
        all_play_ids.update(moment.get("play_ids", []))

    # Load plays by play_ids
    plays_result = await session.execute(
        select(SportsGamePlay).where(
            SportsGamePlay.game_id == game_id,
            SportsGamePlay.play_index.in_(all_play_ids),
        )
    )
    plays_records = plays_result.scalars().all()

    # Build play lookup for ordering
    play_lookup = {p.play_index: p for p in plays_records}

    # Build response moments (exact data, no transformation)
    response_moments = [
        GameFlowMoment(
            playIds=moment["play_ids"],
            explicitlyNarratedPlayIds=moment["explicitly_narrated_play_ids"],
            period=moment["period"],
            startClock=moment.get("start_clock"),
            endClock=moment.get("end_clock"),
            # Internal format is [home, away], API contract is [away, home]
            scoreBefore=[moment["score_before"][1], moment["score_before"][0]],
            scoreAfter=[moment["score_after"][1], moment["score_after"][0]],
            narrative=moment.get("narrative"),
            cumulativeBoxScore=moment.get("cumulative_box_score"),
        )
        for moment in moments_data
    ]

    # Build response plays (only those referenced by moments, ordered by play_index)
    # NOTE: playId uses play_index (not DB id) to match moment.playIds contract
    response_plays = [
        GameFlowPlay(
            playId=play.play_index,
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

    # Build response blocks if present (Phase 1)
    response_blocks: list[GameFlowBlock] | None = None
    total_words: int | None = None

    blocks_data = flow_record.blocks_json
    if blocks_data:
        response_blocks = [
            GameFlowBlock(
                blockIndex=block["block_index"],
                role=block["role"],
                momentIndices=block["moment_indices"],
                periodStart=block["period_start"],
                periodEnd=block["period_end"],
                # Internal format is [home, away], API contract is [away, home]
                scoreBefore=[block["score_before"][1], block["score_before"][0]],
                scoreAfter=[block["score_after"][1], block["score_after"][0]],
                playIds=block["play_ids"],
                keyPlayIds=block["key_play_ids"],
                narrative=block.get("narrative"),
                miniBox=block.get("mini_box"),
                embeddedSocialPostId=block.get("embedded_social_post_id"),
            )
            for block in blocks_data
        ]
        # Calculate total words from block narratives
        total_words = sum(
            len((block.get("narrative") or "").split())
            for block in blocks_data
        )

    # Validation status from persisted data
    validation_passed = flow_record.validated_at is not None

    return GameFlowResponse(
        gameId=game_id,
        flow=GameFlowContent(moments=response_moments),
        plays=response_plays,
        validationPassed=validation_passed,
        validationErrors=[],
        blocks=response_blocks,
        totalWords=total_words,
    )
