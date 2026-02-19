"""Admin endpoints for Entity Resolution inspection.

ENTITY RESOLUTION API
=====================

These endpoints expose how teams and players are resolved from source
identifiers (abbreviations, names) to internal IDs.

RESOLUTION PROCESS
==================

1. TEAM RESOLUTION
   - Source: team_abbreviation from PBP data (e.g., "LAL", "BOS")
   - Target: team_id in sports_teams table
   - Methods:
     * exact_match: Abbreviation matches exactly
     * game_context: Using game's home/away team mapping
     * fuzzy_match: Normalized name matching (NCAAB)
     * abbreviation_lookup: Lookup by abbreviation column

2. PLAYER RESOLUTION
   - Source: player_name from PBP data
   - Target: Currently just name normalization (no players table)
   - Methods:
     * passthrough: Name used as-is
     * normalized: Name cleaned and standardized

EDGE CASES & ISSUES
===================

1. UNRESOLVED TEAMS (resolution_status = 'failed')
   Symptom: team_id is null in PBP data
   Cause: Unknown abbreviation, typo, or source variation
   Example: "PHX" vs "PHO" for Phoenix Suns
   Resolution: Check source_identifier and compare with sports_teams
   Action: May need to add alias or fix source data

2. AMBIGUOUS TEAMS (resolution_status = 'ambiguous')
   Symptom: Multiple teams matched, one was picked
   Cause: Same abbreviation in different contexts
   Example: "LA" could be Lakers or Clippers
   Resolution: Check candidates field for alternatives
   Action: May need more specific abbreviation

3. UNRESOLVED PLAYERS (resolution_status = 'failed')
   Symptom: player_name couldn't be normalized
   Cause: Malformed name in source data
   Note: We don't have a players table, so this is rare
   Action: Check source data quality

4. PARTIAL RESOLUTION (resolution_status = 'partial')
   Symptom: Some information resolved but not all
   Example: Team name found but team_id missing
   Action: Check if team exists in sports_teams
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ...db import AsyncSession, get_db
from ...db.resolution import EntityResolution
from ...db.sports import SportsGame, SportsGamePlay
from ...services.resolution_queries import (
    get_resolution_summary_for_game,
    get_resolution_summary_for_run,
)
from .resolution_models import (
    PlayerResolutionResult,
    ResolutionDetailResponse,
    ResolutionStats,
    ResolutionSummaryResponse,
    TeamResolutionResult,
)

router = APIRouter()


# =============================================================================
# ENDPOINTS - Game Resolution Summary
# =============================================================================


@router.get(
    "/resolution/game/{game_id}",
    response_model=ResolutionSummaryResponse,
    summary="Get resolution summary for game",
    description="Get entity resolution summary for a game from persisted records.",
)
async def get_game_resolution_summary(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> ResolutionSummaryResponse:
    """Get the entity resolution summary for a game.

    Returns all team and player resolutions with success/failure status.
    Also includes issues that may require manual review.
    """
    # Fetch game info
    game_result = await session.execute(
        select(SportsGame)
        .options(
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
            selectinload(SportsGame.league),
        )
        .where(SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()

    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found",
        )

    # Get resolution summary
    summary = await get_resolution_summary_for_game(session, game_id)

    # Build game info
    game_info = {
        "game_date": game.game_date.isoformat() if game.game_date else None,
        "home_team": game.home_team.name if game.home_team else None,
        "home_team_abbrev": game.home_team.abbreviation if game.home_team else None,
        "away_team": game.away_team.name if game.away_team else None,
        "away_team_abbrev": game.away_team.abbreviation if game.away_team else None,
        "league": game.league.code if game.league else None,
        "status": game.status,
    }

    return ResolutionSummaryResponse(
        game_id=game_id,
        pipeline_run_id=summary.pipeline_run_id,
        game_info=game_info,
        teams=ResolutionStats(
            total=summary.teams_total,
            resolved=summary.teams_resolved,
            failed=summary.teams_failed,
            resolution_rate=round(summary.teams_resolved / summary.teams_total * 100, 1)
            if summary.teams_total > 0
            else 0,
        ),
        players=ResolutionStats(
            total=summary.players_total,
            resolved=summary.players_resolved,
            failed=summary.players_failed,
            resolution_rate=round(
                summary.players_resolved / summary.players_total * 100, 1
            )
            if summary.players_total > 0
            else 0,
        ),
        team_resolutions=[TeamResolutionResult(**r) for r in summary.team_resolutions],
        player_resolutions=[
            PlayerResolutionResult(**r) for r in summary.player_resolutions
        ],
        issues={
            "unresolved_teams": summary.unresolved_teams,
            "ambiguous_teams": summary.ambiguous_teams,
            "unresolved_players": summary.unresolved_players,
        },
    )


@router.get(
    "/resolution/game/{game_id}/live",
    summary="Get live resolution analysis for game",
    description="Analyze current PBP data for resolution issues without persisted records.",
)
async def get_live_resolution_analysis(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Analyze current PBP data for resolution issues.

    This is a live analysis that doesn't require persisted resolution records.
    Useful for debugging resolution issues in existing games.
    """
    # Fetch game with team info
    game_result = await session.execute(
        select(SportsGame)
        .options(
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
        )
        .where(SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()

    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found",
        )

    # Fetch plays
    plays_result = await session.execute(
        select(SportsGamePlay)
        .options(selectinload(SportsGamePlay.team))
        .where(SportsGamePlay.game_id == game_id)
        .order_by(SportsGamePlay.play_index)
    )
    plays = list(plays_result.scalars().all())

    if not plays:
        return {
            "game_id": game_id,
            "status": "no_pbp_data",
            "message": "No play-by-play data found for this game",
        }

    # Analyze resolutions
    team_abbrevs_seen: dict[str, dict[str, Any]] = {}
    player_names_seen: dict[str, dict[str, Any]] = {}

    for play in plays:
        # Team analysis
        raw_team = play.raw_data.get("teamTricode") or play.raw_data.get("team")
        if raw_team:
            if raw_team not in team_abbrevs_seen:
                team_abbrevs_seen[raw_team] = {
                    "source": raw_team,
                    "resolved_id": play.team_id,
                    "resolved_name": play.team.name if play.team else None,
                    "resolved_abbrev": play.team.abbreviation if play.team else None,
                    "status": "success" if play.team_id else "failed",
                    "first_play": play.play_index,
                    "occurrences": 1,
                }
            else:
                team_abbrevs_seen[raw_team]["occurrences"] += 1
                team_abbrevs_seen[raw_team]["last_play"] = play.play_index

        # Player analysis
        if play.player_name:
            name = play.player_name.strip()
            if name not in player_names_seen:
                player_names_seen[name] = {
                    "source": name,
                    "status": "success",
                    "first_play": play.play_index,
                    "occurrences": 1,
                }
            else:
                player_names_seen[name]["occurrences"] += 1

    # Find issues
    unresolved_teams = [
        t for t in team_abbrevs_seen.values() if t["status"] == "failed"
    ]

    # Expected teams from game context
    expected_teams = []
    if game.home_team:
        expected_teams.append(
            {
                "abbrev": game.home_team.abbreviation,
                "name": game.home_team.name,
                "team_id": game.home_team.id,
                "role": "home",
            }
        )
    if game.away_team:
        expected_teams.append(
            {
                "abbrev": game.away_team.abbreviation,
                "name": game.away_team.name,
                "team_id": game.away_team.id,
                "role": "away",
            }
        )

    # Check for unexpected teams
    expected_abbrevs = {t["abbrev"].upper() for t in expected_teams}
    unexpected_teams = [
        t
        for t in team_abbrevs_seen.values()
        if t["source"].upper() not in expected_abbrevs
    ]

    return {
        "game_id": game_id,
        "total_plays": len(plays),
        "expected_teams": expected_teams,
        "analysis": {
            "teams": {
                "unique_abbreviations": len(team_abbrevs_seen),
                "resolved": sum(
                    1 for t in team_abbrevs_seen.values() if t["status"] == "success"
                ),
                "unresolved": len(unresolved_teams),
                "details": list(team_abbrevs_seen.values()),
            },
            "players": {
                "unique_names": len(player_names_seen),
                "top_by_occurrences": sorted(
                    player_names_seen.values(),
                    key=lambda x: x["occurrences"],
                    reverse=True,
                )[:10],
            },
        },
        "issues": {
            "unresolved_teams": unresolved_teams,
            "unexpected_teams": unexpected_teams,
        },
    }


# =============================================================================
# ENDPOINTS - Pipeline Run Resolution
# =============================================================================


@router.get(
    "/resolution/pipeline-run/{run_id}",
    response_model=ResolutionSummaryResponse,
    summary="Get resolution summary for pipeline run",
    description="Get entity resolution summary for a specific pipeline run.",
)
async def get_run_resolution_summary(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> ResolutionSummaryResponse:
    """Get the entity resolution summary for a pipeline run.

    Returns resolutions that were tracked during this specific run.
    """
    summary = await get_resolution_summary_for_run(session, run_id)

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No resolution data found for pipeline run {run_id}",
        )

    # Fetch game info
    game_result = await session.execute(
        select(SportsGame)
        .options(
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
        )
        .where(SportsGame.id == summary.game_id)
    )
    game = game_result.scalar_one_or_none()

    game_info = None
    if game:
        game_info = {
            "game_date": game.game_date.isoformat() if game.game_date else None,
            "home_team": game.home_team.name if game.home_team else None,
            "away_team": game.away_team.name if game.away_team else None,
        }

    return ResolutionSummaryResponse(
        game_id=summary.game_id,
        pipeline_run_id=run_id,
        game_info=game_info,
        teams=ResolutionStats(
            total=summary.teams_total,
            resolved=summary.teams_resolved,
            failed=summary.teams_failed,
            resolution_rate=round(summary.teams_resolved / summary.teams_total * 100, 1)
            if summary.teams_total > 0
            else 0,
        ),
        players=ResolutionStats(
            total=summary.players_total,
            resolved=summary.players_resolved,
            failed=summary.players_failed,
            resolution_rate=round(
                summary.players_resolved / summary.players_total * 100, 1
            )
            if summary.players_total > 0
            else 0,
        ),
        team_resolutions=[TeamResolutionResult(**r) for r in summary.team_resolutions],
        player_resolutions=[
            PlayerResolutionResult(**r) for r in summary.player_resolutions
        ],
        issues={
            "unresolved_teams": summary.unresolved_teams,
            "ambiguous_teams": summary.ambiguous_teams,
            "unresolved_players": summary.unresolved_players,
        },
    )


# =============================================================================
# ENDPOINTS - Detailed Resolution Lookup
# =============================================================================


@router.get(
    "/resolution/game/{game_id}/entity/{entity_type}/{source_identifier}",
    response_model=ResolutionDetailResponse,
    summary="Get detailed resolution for entity",
    description="Get full resolution details for a specific entity.",
)
async def get_entity_resolution_detail(
    game_id: int,
    entity_type: str,
    source_identifier: str,
    session: AsyncSession = Depends(get_db),
) -> ResolutionDetailResponse:
    """Get detailed resolution information for a specific entity.

    Useful for debugging why a particular team or player failed to resolve.
    """
    if entity_type not in ("team", "player"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_type must be 'team' or 'player'",
        )

    result = await session.execute(
        select(EntityResolution)
        .where(
            EntityResolution.game_id == game_id,
            EntityResolution.entity_type == entity_type,
            EntityResolution.source_identifier == source_identifier,
        )
        .order_by(EntityResolution.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No resolution found for {entity_type} '{source_identifier}' in game {game_id}",
        )

    return ResolutionDetailResponse(
        entity_type=record.entity_type,
        source_identifier=record.source_identifier,
        resolved_id=record.resolved_id,
        resolved_name=record.resolved_name,
        status=record.resolution_status,
        method=record.resolution_method,
        confidence=record.confidence,
        failure_reason=record.failure_reason,
        candidates=record.candidates,
        occurrence_count=record.occurrence_count,
        first_play_index=record.first_play_index,
        last_play_index=record.last_play_index,
        source_context=record.source_context,
    )


# =============================================================================
# ENDPOINTS - Resolution Issues Overview
# =============================================================================


@router.get(
    "/resolution/issues",
    summary="List games with resolution issues",
    description="Find games that have unresolved or ambiguous entities.",
)
async def list_games_with_resolution_issues(
    entity_type: str | None = Query(
        default=None,
        description="Filter by entity type: team or player",
    ),
    status_filter: str = Query(
        default="failed",
        description="Filter by status: failed, ambiguous, or all",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List games that have resolution issues.

    Useful for finding games that need attention or data fixes.
    """
    query = select(
        EntityResolution.game_id,
        func.count(EntityResolution.id).label("issue_count"),
    ).group_by(EntityResolution.game_id)

    if entity_type:
        query = query.where(EntityResolution.entity_type == entity_type)

    if status_filter == "failed":
        query = query.where(EntityResolution.resolution_status == "failed")
    elif status_filter == "ambiguous":
        query = query.where(EntityResolution.resolution_status == "ambiguous")
    elif status_filter != "all":
        query = query.where(
            EntityResolution.resolution_status.in_(["failed", "ambiguous"])
        )

    query = query.order_by(func.count(EntityResolution.id).desc()).limit(limit)

    result = await session.execute(query)
    rows = result.all()

    # Fetch game details for the results
    game_issues = []
    for game_id, issue_count in rows:
        game_result = await session.execute(
            select(SportsGame)
            .options(
                selectinload(SportsGame.home_team),
                selectinload(SportsGame.away_team),
            )
            .where(SportsGame.id == game_id)
        )
        game = game_result.scalar_one_or_none()

        if game:
            game_issues.append(
                {
                    "game_id": game_id,
                    "game_date": game.game_date.isoformat() if game.game_date else None,
                    "home_team": game.home_team.name if game.home_team else None,
                    "away_team": game.away_team.name if game.away_team else None,
                    "issue_count": issue_count,
                }
            )

    return {
        "filter": {
            "entity_type": entity_type,
            "status": status_filter,
        },
        "total_games_with_issues": len(game_issues),
        "games": game_issues,
    }
