"""Admin endpoints for Play-by-Play data inspection.

PBP INSPECTION API
==================

These endpoints provide full visibility into play-by-play data at every
stage of processing:

1. RAW PBP: Original data as received from data sources
2. CURRENT PBP: Live data from the sports_game_plays table
3. NORMALIZED PBP: After phase assignment and timestamp computation
4. RESOLVED PBP: After team/player ID resolution

EDGE CASES
==========

When inspecting PBP data, watch for these common issues:

1. MISSING TEAM RESOLUTION
   - Symptom: team_id is null but team_abbreviation has a value
   - Cause: Abbreviation mismatch between source and database
   - Example: "PHX" vs "PHO" for Phoenix Suns
   - Resolution: Check resolution_stats.teams_unresolved

2. MISSING PLAYER INFO
   - Symptom: player_id is null or player_name is missing
   - Cause: Player not in source data or name parsing failed
   - Note: We don't maintain a players table; player_id is external ref
   - Resolution: Check resolution_stats.players_unresolved

3. SCORE GAPS
   - Symptom: home_score/away_score jumps unexpectedly
   - Cause: Missing plays in source data or parsing errors
   - Resolution: Check resolution_stats.score_anomalies

4. CLOCK PARSING FAILURES
   - Symptom: game_clock is malformed or null
   - Cause: Non-standard clock format in source
   - Resolution: Check resolution_stats.clock_parse_failures

DATA FLOW
=========

```
Source (NBA/NHL API)
    → Raw PBP (sports_pbp_snapshots, type=raw)
    → sports_game_plays (persisted)
    → NORMALIZE_PBP stage (pipeline)
    → Normalized PBP (pipeline stage output + snapshot)
    → DERIVE_SIGNALS stage
    → Timeline generation
```
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from typing import Any

from ... import db_models
from ...db import AsyncSession, get_db

router = APIRouter()


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class PlaySummary(BaseModel):
    """Summary of a single play for listing."""
    play_index: int
    quarter: int | None
    game_clock: str | None
    play_type: str | None
    team_abbreviation: str | None
    team_id: int | None
    team_resolved: bool
    player_name: str | None
    player_id: str | None
    description: str | None
    home_score: int | None
    away_score: int | None
    has_raw_data: bool


class PlayDetail(BaseModel):
    """Full detail of a single play."""
    play_index: int
    quarter: int | None
    game_clock: str | None
    play_type: str | None
    team_abbreviation: str | None
    team_id: int | None
    team_name: str | None
    player_name: str | None
    player_id: str | None
    description: str | None
    home_score: int | None
    away_score: int | None
    raw_data: dict[str, Any]
    created_at: str
    updated_at: str


class GamePBPResponse(BaseModel):
    """Current PBP data for a game from sports_game_plays table."""
    game_id: int
    game_date: str
    home_team: str
    away_team: str
    game_status: str
    total_plays: int
    plays: list[PlaySummary]
    resolution_summary: dict[str, Any] = Field(
        description="Summary of team/player resolution status"
    )


class GamePBPDetailResponse(BaseModel):
    """Detailed PBP data with full play information."""
    game_id: int
    game_date: str
    home_team: str
    home_team_id: int
    away_team: str
    away_team_id: int
    game_status: str
    total_plays: int
    plays: list[PlayDetail]
    resolution_summary: dict[str, Any]
    metadata: dict[str, Any] = Field(
        description="Additional metadata about the PBP data"
    )


class PBPSnapshotSummary(BaseModel):
    """Summary of a PBP snapshot."""
    snapshot_id: int
    game_id: int
    snapshot_type: str
    source: str | None
    play_count: int
    pipeline_run_id: int | None
    scrape_run_id: int | None
    created_at: str
    resolution_stats: dict[str, Any] | None


class PBPSnapshotDetail(BaseModel):
    """Full detail of a PBP snapshot."""
    snapshot_id: int
    game_id: int
    snapshot_type: str
    source: str | None
    play_count: int
    pipeline_run_id: int | None
    pipeline_run_uuid: str | None
    scrape_run_id: int | None
    plays: list[dict[str, Any]]
    metadata: dict[str, Any] | None
    resolution_stats: dict[str, Any] | None
    created_at: str


class GamePBPSnapshotsResponse(BaseModel):
    """All PBP snapshots for a game."""
    game_id: int
    game_date: str
    home_team: str
    away_team: str
    snapshots: list[PBPSnapshotSummary]
    total_snapshots: int
    has_raw: bool
    has_normalized: bool
    has_resolved: bool


class PipelineRunPBPResponse(BaseModel):
    """PBP data associated with a specific pipeline run."""
    run_id: int
    run_uuid: str
    game_id: int
    game_date: str
    home_team: str
    away_team: str
    normalized_pbp: dict[str, Any] | None = Field(
        description="Normalized PBP from NORMALIZE_PBP stage output"
    )
    play_count: int
    snapshot: PBPSnapshotSummary | None = Field(
        description="Associated PBP snapshot if one exists"
    )


class PBPComparisonResponse(BaseModel):
    """Compare PBP between current and snapshot."""
    game_id: int
    comparison_type: str
    current_play_count: int
    snapshot_play_count: int
    differences: dict[str, Any] = Field(
        description="Summary of differences between current and snapshot"
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _build_resolution_summary(plays: list[db_models.SportsGamePlay]) -> dict[str, Any]:
    """Build resolution summary from plays."""
    total = len(plays)
    if total == 0:
        return {
            "total_plays": 0,
            "teams_resolved": 0,
            "teams_unresolved": 0,
            "team_resolution_rate": 0,
            "players_with_name": 0,
            "players_without_name": 0,
            "plays_with_score": 0,
            "plays_without_score": 0,
        }
    
    teams_resolved = sum(1 for p in plays if p.team_id is not None)
    teams_unresolved = sum(1 for p in plays if p.team_id is None and (p.description or "").strip())
    players_with_name = sum(1 for p in plays if p.player_name)
    plays_with_score = sum(1 for p in plays if p.home_score is not None)
    
    return {
        "total_plays": total,
        "teams_resolved": teams_resolved,
        "teams_unresolved": teams_unresolved,
        "team_resolution_rate": round(teams_resolved / total * 100, 1) if total > 0 else 0,
        "players_with_name": players_with_name,
        "players_without_name": total - players_with_name,
        "plays_with_score": plays_with_score,
        "plays_without_score": total - plays_with_score,
    }


def _play_to_summary(play: db_models.SportsGamePlay) -> PlaySummary:
    """Convert a play to summary format."""
    return PlaySummary(
        play_index=play.play_index,
        quarter=play.quarter,
        game_clock=play.game_clock,
        play_type=play.play_type,
        team_abbreviation=play.team.abbreviation if play.team else None,
        team_id=play.team_id,
        team_resolved=play.team_id is not None,
        player_name=play.player_name,
        player_id=play.player_id,
        description=play.description,
        home_score=play.home_score,
        away_score=play.away_score,
        has_raw_data=bool(play.raw_data),
    )


def _play_to_detail(play: db_models.SportsGamePlay) -> PlayDetail:
    """Convert a play to detail format."""
    return PlayDetail(
        play_index=play.play_index,
        quarter=play.quarter,
        game_clock=play.game_clock,
        play_type=play.play_type,
        team_abbreviation=play.team.abbreviation if play.team else None,
        team_id=play.team_id,
        team_name=play.team.name if play.team else None,
        player_name=play.player_name,
        player_id=play.player_id,
        description=play.description,
        home_score=play.home_score,
        away_score=play.away_score,
        raw_data=play.raw_data or {},
        created_at=play.created_at.isoformat(),
        updated_at=play.updated_at.isoformat(),
    )


# =============================================================================
# ENDPOINTS - Current PBP (from sports_game_plays)
# =============================================================================


@router.get(
    "/pbp/game/{game_id}",
    response_model=GamePBPResponse,
    summary="Get current PBP for game",
    description="Retrieve the current play-by-play data from sports_game_plays table.",
)
async def get_game_pbp(
    game_id: int,
    limit: int = Query(default=500, ge=1, le=1000, description="Max plays to return"),
    offset: int = Query(default=0, ge=0, description="Starting play index"),
    session: AsyncSession = Depends(get_db),
) -> GamePBPResponse:
    """Get current PBP data for a game.
    
    This returns the live data from sports_game_plays, which is the
    authoritative source for PBP after ingestion.
    """
    # Fetch game
    game_result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()
    
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found",
        )
    
    # Get total count
    count_result = await session.execute(
        select(func.count(db_models.SportsGamePlay.id))
        .where(db_models.SportsGamePlay.game_id == game_id)
    )
    total_plays = count_result.scalar() or 0
    
    # Fetch plays
    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .options(selectinload(db_models.SportsGamePlay.team))
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
        .offset(offset)
        .limit(limit)
    )
    plays = plays_result.scalars().all()
    
    return GamePBPResponse(
        game_id=game_id,
        game_date=game.game_date.isoformat() if game.game_date else "",
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        game_status=game.status,
        total_plays=total_plays,
        plays=[_play_to_summary(p) for p in plays],
        resolution_summary=_build_resolution_summary(list(plays)),
    )


@router.get(
    "/pbp/game/{game_id}/detail",
    response_model=GamePBPDetailResponse,
    summary="Get detailed PBP for game",
    description="Retrieve detailed play-by-play including raw data.",
)
async def get_game_pbp_detail(
    game_id: int,
    limit: int = Query(default=100, ge=1, le=500, description="Max plays to return"),
    offset: int = Query(default=0, ge=0, description="Starting play index"),
    quarter: int | None = Query(default=None, ge=1, le=10, description="Filter by quarter"),
    session: AsyncSession = Depends(get_db),
) -> GamePBPDetailResponse:
    """Get detailed PBP data including raw_data for each play."""
    # Fetch game
    game_result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()
    
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found",
        )
    
    # Build query
    query = (
        select(db_models.SportsGamePlay)
        .options(selectinload(db_models.SportsGamePlay.team))
        .where(db_models.SportsGamePlay.game_id == game_id)
    )
    
    if quarter is not None:
        query = query.where(db_models.SportsGamePlay.quarter == quarter)
    
    # Get total count
    count_query = select(func.count(db_models.SportsGamePlay.id)).where(
        db_models.SportsGamePlay.game_id == game_id
    )
    if quarter is not None:
        count_query = count_query.where(db_models.SportsGamePlay.quarter == quarter)
    count_result = await session.execute(count_query)
    total_plays = count_result.scalar() or 0
    
    # Fetch plays
    plays_result = await session.execute(
        query.order_by(db_models.SportsGamePlay.play_index)
        .offset(offset)
        .limit(limit)
    )
    plays = plays_result.scalars().all()
    
    # Build metadata
    metadata = {
        "offset": offset,
        "limit": limit,
        "quarter_filter": quarter,
        "last_pbp_at": game.last_pbp_at.isoformat() if game.last_pbp_at else None,
        "last_scraped_at": game.last_scraped_at.isoformat() if game.last_scraped_at else None,
    }
    
    return GamePBPDetailResponse(
        game_id=game_id,
        game_date=game.game_date.isoformat() if game.game_date else "",
        home_team=game.home_team.name if game.home_team else "Unknown",
        home_team_id=game.home_team_id,
        away_team=game.away_team.name if game.away_team else "Unknown",
        away_team_id=game.away_team_id,
        game_status=game.status,
        total_plays=total_plays,
        plays=[_play_to_detail(p) for p in plays],
        resolution_summary=_build_resolution_summary(list(plays)),
        metadata=metadata,
    )


@router.get(
    "/pbp/game/{game_id}/play/{play_index}",
    response_model=PlayDetail,
    summary="Get single play",
    description="Retrieve a single play by index with full details.",
)
async def get_single_play(
    game_id: int,
    play_index: int,
    session: AsyncSession = Depends(get_db),
) -> PlayDetail:
    """Get a single play by index."""
    result = await session.execute(
        select(db_models.SportsGamePlay)
        .options(selectinload(db_models.SportsGamePlay.team))
        .where(
            db_models.SportsGamePlay.game_id == game_id,
            db_models.SportsGamePlay.play_index == play_index,
        )
    )
    play = result.scalar_one_or_none()
    
    if not play:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Play {play_index} not found for game {game_id}",
        )
    
    return _play_to_detail(play)


# =============================================================================
# ENDPOINTS - PBP Snapshots
# =============================================================================


@router.get(
    "/pbp/game/{game_id}/snapshots",
    response_model=GamePBPSnapshotsResponse,
    summary="List PBP snapshots for game",
    description="List all PBP snapshots (raw, normalized, resolved) for a game.",
)
async def get_game_pbp_snapshots(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GamePBPSnapshotsResponse:
    """List all PBP snapshots for a game."""
    # Fetch game
    game_result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()
    
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found",
        )
    
    # Fetch snapshots
    snapshots_result = await session.execute(
        select(db_models.PBPSnapshot)
        .where(db_models.PBPSnapshot.game_id == game_id)
        .order_by(db_models.PBPSnapshot.created_at.desc())
    )
    snapshots = snapshots_result.scalars().all()
    
    # Check which types exist
    snapshot_types = {s.snapshot_type for s in snapshots}
    
    return GamePBPSnapshotsResponse(
        game_id=game_id,
        game_date=game.game_date.isoformat() if game.game_date else "",
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        snapshots=[
            PBPSnapshotSummary(
                snapshot_id=s.id,
                game_id=s.game_id,
                snapshot_type=s.snapshot_type,
                source=s.source,
                play_count=s.play_count,
                pipeline_run_id=s.pipeline_run_id,
                scrape_run_id=s.scrape_run_id,
                created_at=s.created_at.isoformat(),
                resolution_stats=s.resolution_stats,
            )
            for s in snapshots
        ],
        total_snapshots=len(snapshots),
        has_raw="raw" in snapshot_types,
        has_normalized="normalized" in snapshot_types,
        has_resolved="resolved" in snapshot_types,
    )


@router.get(
    "/pbp/snapshot/{snapshot_id}",
    response_model=PBPSnapshotDetail,
    summary="Get PBP snapshot detail",
    description="Get full details of a PBP snapshot including all plays.",
)
async def get_pbp_snapshot(
    snapshot_id: int,
    session: AsyncSession = Depends(get_db),
) -> PBPSnapshotDetail:
    """Get full details of a PBP snapshot."""
    result = await session.execute(
        select(db_models.PBPSnapshot)
        .options(selectinload(db_models.PBPSnapshot.pipeline_run))
        .where(db_models.PBPSnapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PBP snapshot {snapshot_id} not found",
        )
    
    return PBPSnapshotDetail(
        snapshot_id=snapshot.id,
        game_id=snapshot.game_id,
        snapshot_type=snapshot.snapshot_type,
        source=snapshot.source,
        play_count=snapshot.play_count,
        pipeline_run_id=snapshot.pipeline_run_id,
        pipeline_run_uuid=str(snapshot.pipeline_run.run_uuid) if snapshot.pipeline_run else None,
        scrape_run_id=snapshot.scrape_run_id,
        plays=snapshot.plays_json or [],
        metadata=snapshot.metadata_json,
        resolution_stats=snapshot.resolution_stats,
        created_at=snapshot.created_at.isoformat(),
    )


# =============================================================================
# ENDPOINTS - Pipeline Run PBP
# =============================================================================


@router.get(
    "/pbp/pipeline-run/{run_id}",
    response_model=PipelineRunPBPResponse,
    summary="Get PBP for pipeline run",
    description="Get PBP data associated with a specific pipeline run.",
)
async def get_pipeline_run_pbp(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> PipelineRunPBPResponse:
    """Get PBP data from a specific pipeline run.
    
    This retrieves the normalized PBP from the NORMALIZE_PBP stage output,
    as well as any associated PBP snapshot.
    """
    # Fetch run with stages
    run_result = await session.execute(
        select(db_models.GamePipelineRun)
        .options(
            selectinload(db_models.GamePipelineRun.stages),
            selectinload(db_models.GamePipelineRun.game).selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.GamePipelineRun.game).selectinload(db_models.SportsGame.away_team),
        )
        .where(db_models.GamePipelineRun.id == run_id)
    )
    run = run_result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run {run_id} not found",
        )
    
    game = run.game
    
    # Get NORMALIZE_PBP stage output
    normalize_stage = next(
        (s for s in run.stages if s.stage == "NORMALIZE_PBP"),
        None,
    )
    
    normalized_pbp = None
    play_count = 0
    
    if normalize_stage and normalize_stage.output_json:
        normalized_pbp = normalize_stage.output_json
        play_count = len(normalized_pbp.get("pbp_events", []))
    
    # Check for associated snapshot
    snapshot_result = await session.execute(
        select(db_models.PBPSnapshot)
        .where(db_models.PBPSnapshot.pipeline_run_id == run_id)
        .order_by(db_models.PBPSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = snapshot_result.scalar_one_or_none()
    
    snapshot_summary = None
    if snapshot:
        snapshot_summary = PBPSnapshotSummary(
            snapshot_id=snapshot.id,
            game_id=snapshot.game_id,
            snapshot_type=snapshot.snapshot_type,
            source=snapshot.source,
            play_count=snapshot.play_count,
            pipeline_run_id=snapshot.pipeline_run_id,
            scrape_run_id=snapshot.scrape_run_id,
            created_at=snapshot.created_at.isoformat(),
            resolution_stats=snapshot.resolution_stats,
        )
    
    return PipelineRunPBPResponse(
        run_id=run.id,
        run_uuid=str(run.run_uuid),
        game_id=run.game_id,
        game_date=game.game_date.isoformat() if game.game_date else "",
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        normalized_pbp=normalized_pbp,
        play_count=play_count,
        snapshot=snapshot_summary,
    )


# =============================================================================
# ENDPOINTS - Comparison
# =============================================================================


@router.get(
    "/pbp/game/{game_id}/compare",
    response_model=PBPComparisonResponse,
    summary="Compare current PBP with snapshot",
    description="Compare current PBP data with a specific snapshot.",
)
async def compare_pbp(
    game_id: int,
    snapshot_id: int = Query(..., description="Snapshot to compare against"),
    session: AsyncSession = Depends(get_db),
) -> PBPComparisonResponse:
    """Compare current PBP with a snapshot.
    
    Useful for debugging differences between raw and processed data.
    """
    # Get current play count
    current_count_result = await session.execute(
        select(func.count(db_models.SportsGamePlay.id))
        .where(db_models.SportsGamePlay.game_id == game_id)
    )
    current_count = current_count_result.scalar() or 0
    
    # Get snapshot
    snapshot_result = await session.execute(
        select(db_models.PBPSnapshot)
        .where(db_models.PBPSnapshot.id == snapshot_id)
    )
    snapshot = snapshot_result.scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PBP snapshot {snapshot_id} not found",
        )
    
    if snapshot.game_id != game_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Snapshot does not belong to this game",
        )
    
    # Calculate differences
    differences = {
        "play_count_delta": current_count - snapshot.play_count,
        "snapshot_type": snapshot.snapshot_type,
        "snapshot_created_at": snapshot.created_at.isoformat(),
    }
    
    # If counts differ, check for missing/extra plays
    if current_count != snapshot.play_count:
        differences["note"] = (
            f"Current has {abs(current_count - snapshot.play_count)} "
            f"{'more' if current_count > snapshot.play_count else 'fewer'} plays"
        )
    
    return PBPComparisonResponse(
        game_id=game_id,
        comparison_type=f"current_vs_{snapshot.snapshot_type}",
        current_play_count=current_count,
        snapshot_play_count=snapshot.play_count,
        differences=differences,
    )


# =============================================================================
# ENDPOINTS - Resolution Issues
# =============================================================================


@router.get(
    "/pbp/game/{game_id}/resolution-issues",
    summary="Get PBP resolution issues",
    description="List plays with resolution issues (missing team, player, etc.).",
)
async def get_resolution_issues(
    game_id: int,
    issue_type: str = Query(
        default="all",
        description="Type of issue: team, player, score, all",
    ),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get plays with resolution issues.
    
    Helps debug data quality problems in PBP ingestion.
    """
    # Fetch all plays
    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .options(selectinload(db_models.SportsGamePlay.team))
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = plays_result.scalars().all()
    
    issues: dict[str, list[dict[str, Any]]] = {
        "team_unresolved": [],
        "player_missing": [],
        "score_missing": [],
        "clock_missing": [],
    }
    
    for play in plays:
        play_info = {
            "play_index": play.play_index,
            "quarter": play.quarter,
            "description": play.description[:100] if play.description else None,
        }
        
        # Team resolution issues
        if issue_type in ("all", "team"):
            if play.team_id is None and play.description:
                # Check if raw_data has team info
                raw_team = play.raw_data.get("teamTricode") or play.raw_data.get("team")
                if raw_team:
                    issues["team_unresolved"].append({
                        **play_info,
                        "raw_team": raw_team,
                        "issue": "Team abbreviation in raw data but not resolved",
                    })
        
        # Player issues
        if issue_type in ("all", "player"):
            if not play.player_name and play.description:
                # Check if play type typically has a player
                if play.play_type and play.play_type not in ("timeout", "substitution", "period_start", "period_end"):
                    issues["player_missing"].append({
                        **play_info,
                        "play_type": play.play_type,
                        "issue": "Expected player name but not found",
                    })
        
        # Score issues
        if issue_type in ("all", "score"):
            if play.home_score is None or play.away_score is None:
                issues["score_missing"].append({
                    **play_info,
                    "issue": "Missing score information",
                })
        
        # Clock issues
        if issue_type in ("all", "clock"):
            if not play.game_clock:
                issues["clock_missing"].append({
                    **play_info,
                    "issue": "Missing game clock",
                })
    
    # Filter by requested type
    if issue_type != "all":
        filtered = {issue_type: issues.get(f"{issue_type}_unresolved", []) or issues.get(f"{issue_type}_missing", [])}
        issues = filtered
    
    return {
        "game_id": game_id,
        "total_plays": len(plays),
        "issue_type_filter": issue_type,
        "issues": issues,
        "summary": {
            "team_unresolved": len(issues.get("team_unresolved", [])),
            "player_missing": len(issues.get("player_missing", [])),
            "score_missing": len(issues.get("score_missing", [])),
            "clock_missing": len(issues.get("clock_missing", [])),
        },
    }
