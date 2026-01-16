"""Admin endpoints for timeline generation jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, select

from ... import db_models
from ...db import AsyncSession, get_db
from ...services.timeline_generator import TimelineGenerationError, generate_timeline_artifact

router = APIRouter()


class TimelineGenerationRequest(BaseModel):
    """Request to generate timeline for a specific game."""
    timeline_version: str = Field(default="v1", description="Timeline version identifier")


class TimelineGenerationResponse(BaseModel):
    """Response after generating a timeline."""
    game_id: int
    timeline_version: str
    success: bool
    message: str


class MissingTimelineGame(BaseModel):
    """Game missing timeline artifact."""
    game_id: int
    game_date: str
    league: str
    home_team: str
    away_team: str
    status: str
    has_pbp: bool


class MissingTimelinesResponse(BaseModel):
    """List of games missing timeline artifacts."""
    games: list[MissingTimelineGame]
    total_count: int


class BatchGenerationRequest(BaseModel):
    """Request to generate timelines for multiple games."""
    league_code: str = Field(default="NBA", description="League to process")
    days_back: int = Field(default=7, ge=1, le=30, description="Days back to check")
    max_games: int | None = Field(default=None, description="Max games to process")


class BatchGenerationResponse(BaseModel):
    """Response after batch timeline generation."""
    job_id: str
    message: str
    games_found: int


@router.post("/timelines/generate/{game_id}", response_model=TimelineGenerationResponse)
async def generate_timeline_for_game(
    game_id: int,
    request: TimelineGenerationRequest,
    session: AsyncSession = Depends(get_db),
) -> TimelineGenerationResponse:
    """
    Generate timeline artifact for a specific game.
    
    This endpoint triggers timeline generation for a single game. The game must:
    - Exist in the database
    - Be in final/completed status
    - Have play-by-play data available
    """
    # Check if game exists
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found"
        )
    
    # Check if game is completed
    if game.status not in [db_models.GameStatus.final.value, db_models.GameStatus.completed.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Game {game_id} is not completed (status: {game.status})"
        )
    
    # Check if PBP data exists
    pbp_exists = await session.scalar(
        select(exists().where(db_models.SportsGamePlay.game_id == game_id))
    )
    if not pbp_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Game {game_id} has no play-by-play data"
        )
    
    # Generate timeline
    try:
        await generate_timeline_artifact(
            session,
            game_id,
            timeline_version=request.timeline_version,
        )
        
        return TimelineGenerationResponse(
            game_id=game_id,
            timeline_version=request.timeline_version,
            success=True,
            message="Timeline generated successfully",
        )
        
    except TimelineGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Timeline generation failed: {str(exc)}"
        ) from exc


@router.get("/timelines/missing", response_model=MissingTimelinesResponse)
async def list_missing_timelines(
    league_code: str = Query("NBA", description="League code to filter by"),
    days_back: int = Query(7, ge=1, le=90, description="Days back to check"),
    session: AsyncSession = Depends(get_db),
) -> MissingTimelinesResponse:
    """
    List games that have PBP data but are missing timeline artifacts.
    
    Returns completed games from the specified time range that need
    timeline generation.
    """
    from datetime import timedelta
    from sqlalchemy.orm import aliased
    from ...utils.datetime_utils import now_utc
    
    # Get league
    league_result = await session.execute(
        select(db_models.SportsLeague).where(db_models.SportsLeague.code == league_code)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"League {league_code} not found"
        )
    
    cutoff_date = now_utc() - timedelta(days=days_back)
    
    # Create aliases for home and away teams
    HomeTeam = aliased(db_models.SportsTeam)
    AwayTeam = aliased(db_models.SportsTeam)
    
    # Find games missing timelines
    query = (
        select(
            db_models.SportsGame.id,
            db_models.SportsGame.game_date,
            db_models.SportsGame.status,
            db_models.SportsLeague.code.label("league_code"),
            HomeTeam.name.label("home_team"),
            AwayTeam.name.label("away_team"),
        )
        .join(db_models.SportsLeague, db_models.SportsGame.league_id == db_models.SportsLeague.id)
        .join(
            HomeTeam,
            db_models.SportsGame.home_team_id == HomeTeam.id,
        )
        .join(
            AwayTeam,
            db_models.SportsGame.away_team_id == AwayTeam.id,
        )
        .where(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.status.in_([
                db_models.GameStatus.final.value,
                db_models.GameStatus.completed.value,
            ]),
            db_models.SportsGame.game_date >= cutoff_date,
        )
        .where(
            # Has PBP data
            exists().where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id)
        )
        .where(
            # Missing timeline artifact
            ~exists().where(
                db_models.SportsGameTimelineArtifact.game_id == db_models.SportsGame.id
            )
        )
        .order_by(db_models.SportsGame.game_date.desc())
    )
    
    result = await session.execute(query)
    rows = result.all()
    
    games = [
        MissingTimelineGame(
            game_id=row.id,
            game_date=row.game_date.isoformat(),
            league=row.league_code,
            home_team=row.home_team,
            away_team=row.away_team,
            status=row.status,
            has_pbp=True,
        )
        for row in rows
    ]
    
    return MissingTimelinesResponse(
        games=games,
        total_count=len(games),
    )


class SyncBatchGenerationResponse(BaseModel):
    """Response after synchronous batch timeline generation."""
    games_processed: int
    games_successful: int
    games_failed: int
    failed_game_ids: list[int]
    message: str


class RegenerateBatchRequest(BaseModel):
    """Request to regenerate timelines for specific games or all games with existing timelines."""
    game_ids: list[int] | None = Field(default=None, description="Specific game IDs to regenerate (None = all)")
    league_code: str = Field(default="NBA", description="League to filter by")
    days_back: int = Field(default=7, ge=1, le=90, description="Days back to check")
    only_stale: bool = Field(default=False, description="Only regenerate if social posts are newer than timeline")


class ExistingTimelineGame(BaseModel):
    """Game with an existing timeline artifact."""
    game_id: int
    game_date: str
    league: str
    home_team: str
    away_team: str
    status: str
    timeline_generated_at: str
    last_social_at: str | None
    is_stale: bool  # True if last_social_at > timeline_generated_at


class ExistingTimelinesResponse(BaseModel):
    """List of games with existing timeline artifacts."""
    games: list[ExistingTimelineGame]
    total_count: int
    stale_count: int


@router.post("/timelines/generate-batch", response_model=SyncBatchGenerationResponse)
async def generate_timelines_batch(
    request: BatchGenerationRequest,
    session: AsyncSession = Depends(get_db),
) -> SyncBatchGenerationResponse:
    """
    Generate timelines for all games missing them (synchronous).
    
    This endpoint generates timelines directly in the API. It processes
    games one by one and returns results when complete.
    
    Note: For large batches, this may take several minutes.
    """
    from datetime import timedelta
    from ...utils.datetime_utils import now_utc
    
    # Verify league exists
    league_result = await session.execute(
        select(db_models.SportsLeague).where(db_models.SportsLeague.code == request.league_code)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"League {request.league_code} not found"
        )
    
    cutoff_date = now_utc() - timedelta(days=request.days_back)
    
    # Find games needing timelines
    query = (
        select(db_models.SportsGame.id)
        .where(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.status.in_([
                db_models.GameStatus.final.value,
                db_models.GameStatus.completed.value,
            ]),
            db_models.SportsGame.game_date >= cutoff_date,
        )
        .where(
            exists().where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id)
        )
        .where(
            ~exists().where(
                db_models.SportsGameTimelineArtifact.game_id == db_models.SportsGame.id
            )
        )
        .order_by(db_models.SportsGame.game_date.desc())
    )
    
    if request.max_games:
        query = query.limit(request.max_games)
    
    result = await session.execute(query)
    game_ids = [row[0] for row in result.all()]
    
    if not game_ids:
        return SyncBatchGenerationResponse(
            games_processed=0,
            games_successful=0,
            games_failed=0,
            failed_game_ids=[],
            message="No games found needing timeline generation",
        )
    
    # Generate timelines for each game
    import logging
    logger = logging.getLogger(__name__)
    
    successful = 0
    failed = 0
    failed_ids: list[int] = []
    
    for game_id in game_ids:
        try:
            await generate_timeline_artifact(
                session,
                game_id,
                timeline_version="v1",
            )
            await session.commit()
            successful += 1
            logger.info(f"Generated timeline for game {game_id}")
        except Exception as exc:
            await session.rollback()
            failed += 1
            failed_ids.append(game_id)
            logger.error(f"Failed to generate timeline for game {game_id}: {exc}")
    
    return SyncBatchGenerationResponse(
        games_processed=len(game_ids),
        games_successful=successful,
        games_failed=failed,
        failed_game_ids=failed_ids,
        message=f"Generated {successful}/{len(game_ids)} timelines",
    )


@router.get("/timelines/existing", response_model=ExistingTimelinesResponse)
async def list_existing_timelines(
    league_code: str = Query("NBA", description="League code to filter by"),
    days_back: int = Query(7, ge=1, le=90, description="Days back to check"),
    only_stale: bool = Query(False, description="Only show stale timelines"),
    session: AsyncSession = Depends(get_db),
) -> ExistingTimelinesResponse:
    """
    List games that have existing timeline artifacts.
    
    Returns games with timeline artifacts, including staleness indicator
    based on whether social posts were added after timeline generation.
    """
    from datetime import timedelta
    from sqlalchemy.orm import aliased
    from ...utils.datetime_utils import now_utc
    
    # Get league
    league_result = await session.execute(
        select(db_models.SportsLeague).where(db_models.SportsLeague.code == league_code)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"League {league_code} not found"
        )
    
    cutoff_date = now_utc() - timedelta(days=days_back)
    
    # Create aliases for home and away teams
    HomeTeam = aliased(db_models.SportsTeam)
    AwayTeam = aliased(db_models.SportsTeam)
    
    # Find games with existing timelines
    query = (
        select(
            db_models.SportsGame.id,
            db_models.SportsGame.game_date,
            db_models.SportsGame.status,
            db_models.SportsGame.last_social_at,
            db_models.SportsLeague.code.label("league_code"),
            HomeTeam.name.label("home_team"),
            AwayTeam.name.label("away_team"),
            db_models.SportsGameTimelineArtifact.generated_at.label("timeline_generated_at"),
        )
        .join(db_models.SportsLeague, db_models.SportsGame.league_id == db_models.SportsLeague.id)
        .join(HomeTeam, db_models.SportsGame.home_team_id == HomeTeam.id)
        .join(AwayTeam, db_models.SportsGame.away_team_id == AwayTeam.id)
        .join(
            db_models.SportsGameTimelineArtifact,
            db_models.SportsGameTimelineArtifact.game_id == db_models.SportsGame.id,
        )
        .where(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= cutoff_date,
        )
        .order_by(db_models.SportsGame.game_date.desc())
    )
    
    result = await session.execute(query)
    rows = result.all()
    
    games = []
    stale_count = 0
    for row in rows:
        # Determine staleness: last_social_at > timeline_generated_at
        is_stale = False
        if row.last_social_at and row.timeline_generated_at:
            is_stale = row.last_social_at > row.timeline_generated_at
        
        if only_stale and not is_stale:
            continue
        
        if is_stale:
            stale_count += 1
        
        games.append(
            ExistingTimelineGame(
                game_id=row.id,
                game_date=row.game_date.isoformat(),
                league=row.league_code,
                home_team=row.home_team,
                away_team=row.away_team,
                status=row.status,
                timeline_generated_at=row.timeline_generated_at.isoformat(),
                last_social_at=row.last_social_at.isoformat() if row.last_social_at else None,
                is_stale=is_stale,
            )
        )
    
    return ExistingTimelinesResponse(
        games=games,
        total_count=len(games),
        stale_count=stale_count,
    )


@router.post("/timelines/regenerate-batch", response_model=SyncBatchGenerationResponse)
async def regenerate_timelines_batch(
    request: RegenerateBatchRequest,
    session: AsyncSession = Depends(get_db),
) -> SyncBatchGenerationResponse:
    """
    Regenerate timelines for games that already have timeline artifacts.
    
    Use this to refresh timelines after social posts have been backfilled
    or when timeline logic has been updated.
    
    If game_ids is provided, only those games are regenerated.
    Otherwise, all games with existing timelines in the date range are regenerated.
    """
    from datetime import timedelta
    import logging
    from ...utils.datetime_utils import now_utc
    
    logger = logging.getLogger(__name__)
    
    # Verify league exists
    league_result = await session.execute(
        select(db_models.SportsLeague).where(db_models.SportsLeague.code == request.league_code)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"League {request.league_code} not found"
        )
    
    if request.game_ids:
        # Regenerate specific games
        game_ids = request.game_ids
    else:
        # Find all games with existing timelines in date range
        cutoff_date = now_utc() - timedelta(days=request.days_back)
        
        query = (
            select(db_models.SportsGame.id, db_models.SportsGame.last_social_at)
            .join(
                db_models.SportsGameTimelineArtifact,
                db_models.SportsGameTimelineArtifact.game_id == db_models.SportsGame.id,
            )
            .where(
                db_models.SportsGame.league_id == league.id,
                db_models.SportsGame.game_date >= cutoff_date,
            )
        )
        
        if request.only_stale:
            # Only include games where last_social_at > timeline generated_at
            query = query.where(
                db_models.SportsGame.last_social_at > db_models.SportsGameTimelineArtifact.generated_at
            )
        
        result = await session.execute(query)
        game_ids = [row[0] for row in result.all()]
    
    if not game_ids:
        return SyncBatchGenerationResponse(
            games_processed=0,
            games_successful=0,
            games_failed=0,
            failed_game_ids=[],
            message="No games found for regeneration",
        )
    
    # Regenerate timelines for each game
    successful = 0
    failed = 0
    failed_ids: list[int] = []
    
    for game_id in game_ids:
        try:
            await generate_timeline_artifact(
                session,
                game_id,
                timeline_version="v1",
                generated_by="admin_regenerate",
                generation_reason="manual_regeneration",
            )
            await session.commit()
            successful += 1
            logger.info(f"Regenerated timeline for game {game_id}")
        except Exception as exc:
            await session.rollback()
            failed += 1
            failed_ids.append(game_id)
            logger.error(f"Failed to regenerate timeline for game {game_id}: {exc}")
    
    return SyncBatchGenerationResponse(
        games_processed=len(game_ids),
        games_successful=successful,
        games_failed=failed,
        failed_game_ids=failed_ids,
        message=f"Regenerated {successful}/{len(game_ids)} timelines",
    )
