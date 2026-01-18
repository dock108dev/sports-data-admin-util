"""Admin endpoints for Frontend Payload inspection.

FRONTEND PAYLOAD API
====================

These endpoints expose exactly what the frontend receives and provide
full version history for debugging and auditing.

IMMUTABILITY GUARANTEE
======================

Frontend payloads are NEVER mutated in place:
- Each pipeline run creates a NEW version
- Previous versions are preserved forever
- Only one version is "active" at any time

VERSION LIFECYCLE
=================

1. Pipeline runs FINALIZE_MOMENTS stage
2. New FrontendPayloadVersion is created (if content changed)
3. Previous active version is deactivated
4. New version becomes active
5. Frontend always receives the active version

VERSIONING NOTES
================

- version_number: Auto-incrementing per game (1, 2, 3, ...)
- is_active: True for exactly ONE version per game
- payload_hash: SHA-256 for quick change detection
- diff_from_previous: Summary of changes from previous version

USE CASES
=========

1. DEBUGGING
   "Why did the frontend show wrong moments?"
   → Fetch the active version at that time using version history

2. AUDITING
   "What changed between runs?"
   → Compare two versions using the compare endpoint

3. REGRESSION TESTING
   "Did this pipeline change produce different results?"
   → Check if payload_hash changed
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Any

from ... import db_models
from ...db import AsyncSession, get_db
from ...services.frontend_payload import (
    get_active_version,
    get_version_by_number,
    list_versions,
    compare_versions,
)

router = APIRouter()


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class PayloadVersionSummary(BaseModel):
    """Summary of a payload version (without full content)."""
    version_number: int
    is_active: bool
    payload_hash: str
    event_count: int
    moment_count: int
    pipeline_run_id: int | None
    generation_source: str | None
    created_at: str
    diff_summary: dict[str, Any] | None = Field(
        description="Summary of changes from previous version"
    )


class PayloadVersionDetail(BaseModel):
    """Full detail of a payload version."""
    version_number: int
    is_active: bool
    payload_hash: str
    event_count: int
    moment_count: int
    pipeline_run_id: int | None
    generation_source: str | None
    generation_notes: str | None
    created_at: str
    diff_from_previous: dict[str, Any] | None
    # Full content
    timeline: list[dict[str, Any]]
    moments: list[dict[str, Any]]
    summary: dict[str, Any]


class GamePayloadResponse(BaseModel):
    """Response containing the frontend payload for a game."""
    game_id: int
    game_info: dict[str, Any] | None = Field(description="Game metadata")
    version: PayloadVersionSummary
    timeline: list[dict[str, Any]]
    moments: list[dict[str, Any]]
    summary: dict[str, Any]


class PayloadVersionListResponse(BaseModel):
    """List of payload versions for a game."""
    game_id: int
    total_versions: int
    active_version: int | None
    versions: list[PayloadVersionSummary]


class PayloadComparisonResponse(BaseModel):
    """Comparison between two payload versions."""
    game_id: int
    version_a: dict[str, Any]
    version_b: dict[str, Any]
    hashes_match: bool
    diff: dict[str, Any]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _version_to_summary(version: db_models.FrontendPayloadVersion) -> PayloadVersionSummary:
    """Convert a FrontendPayloadVersion to summary response."""
    return PayloadVersionSummary(
        version_number=version.version_number,
        is_active=version.is_active,
        payload_hash=version.payload_hash,
        event_count=version.event_count,
        moment_count=version.moment_count,
        pipeline_run_id=version.pipeline_run_id,
        generation_source=version.generation_source,
        created_at=version.created_at.isoformat(),
        diff_summary=version.diff_from_previous,
    )


def _version_to_detail(version: db_models.FrontendPayloadVersion) -> PayloadVersionDetail:
    """Convert a FrontendPayloadVersion to detail response."""
    return PayloadVersionDetail(
        version_number=version.version_number,
        is_active=version.is_active,
        payload_hash=version.payload_hash,
        event_count=version.event_count,
        moment_count=version.moment_count,
        pipeline_run_id=version.pipeline_run_id,
        generation_source=version.generation_source,
        generation_notes=version.generation_notes,
        created_at=version.created_at.isoformat(),
        diff_from_previous=version.diff_from_previous,
        timeline=version.timeline_json,
        moments=version.moments_json,
        summary=version.summary_json,
    )


# =============================================================================
# ENDPOINTS - Active Payload
# =============================================================================


@router.get(
    "/frontend-payload/game/{game_id}",
    response_model=GamePayloadResponse,
    summary="Get active frontend payload",
    description="Get the currently active frontend payload for a game.",
)
async def get_active_payload(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GamePayloadResponse:
    """Get the currently active frontend payload.
    
    This is exactly what the frontend would receive for this game.
    """
    # Fetch game info
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
    
    # Get active version
    version = await get_active_version(session, game_id)
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active frontend payload found for game {game_id}. "
                   "Pipeline may not have run yet.",
        )
    
    game_info = {
        "game_date": game.game_date.isoformat() if game.game_date else None,
        "home_team": game.home_team.name if game.home_team else None,
        "away_team": game.away_team.name if game.away_team else None,
        "status": game.status,
    }
    
    return GamePayloadResponse(
        game_id=game_id,
        game_info=game_info,
        version=_version_to_summary(version),
        timeline=version.timeline_json,
        moments=version.moments_json,
        summary=version.summary_json,
    )


# =============================================================================
# ENDPOINTS - Version History
# =============================================================================


@router.get(
    "/frontend-payload/game/{game_id}/versions",
    response_model=PayloadVersionListResponse,
    summary="List payload versions",
    description="List all frontend payload versions for a game.",
)
async def list_payload_versions(
    game_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> PayloadVersionListResponse:
    """List all payload versions for a game.
    
    Useful for viewing version history and finding specific versions
    for debugging.
    """
    versions = await list_versions(session, game_id, limit)
    
    active_version = None
    for v in versions:
        if v.is_active:
            active_version = v.version_number
            break
    
    return PayloadVersionListResponse(
        game_id=game_id,
        total_versions=len(versions),
        active_version=active_version,
        versions=[_version_to_summary(v) for v in versions],
    )


@router.get(
    "/frontend-payload/game/{game_id}/version/{version_number}",
    response_model=PayloadVersionDetail,
    summary="Get specific payload version",
    description="Get a specific frontend payload version by number.",
)
async def get_payload_version(
    game_id: int,
    version_number: int,
    session: AsyncSession = Depends(get_db),
) -> PayloadVersionDetail:
    """Get a specific payload version by number.
    
    Useful for comparing historical versions or debugging past issues.
    """
    version = await get_version_by_number(session, game_id, version_number)
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_number} not found for game {game_id}",
        )
    
    return _version_to_detail(version)


# =============================================================================
# ENDPOINTS - Pipeline Run Payload
# =============================================================================


@router.get(
    "/frontend-payload/pipeline-run/{run_id}",
    response_model=PayloadVersionDetail,
    summary="Get payload from pipeline run",
    description="Get the frontend payload created by a specific pipeline run.",
)
async def get_payload_by_pipeline_run(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> PayloadVersionDetail:
    """Get the frontend payload created by a specific pipeline run.
    
    Useful for tracing exactly what a specific run produced.
    """
    result = await session.execute(
        select(db_models.FrontendPayloadVersion)
        .where(db_models.FrontendPayloadVersion.pipeline_run_id == run_id)
    )
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No frontend payload found for pipeline run {run_id}. "
                   "The run may not have reached FINALIZE_MOMENTS, or content was unchanged.",
        )
    
    return _version_to_detail(version)


# =============================================================================
# ENDPOINTS - Comparison
# =============================================================================


@router.get(
    "/frontend-payload/game/{game_id}/compare",
    response_model=PayloadComparisonResponse,
    summary="Compare payload versions",
    description="Compare two payload versions to see what changed.",
)
async def compare_payload_versions(
    game_id: int,
    version_a: int = Query(..., description="First version to compare"),
    version_b: int = Query(..., description="Second version to compare"),
    session: AsyncSession = Depends(get_db),
) -> PayloadComparisonResponse:
    """Compare two payload versions.
    
    Returns a summary of what changed between the versions.
    """
    result = await compare_versions(session, game_id, version_a, version_b)
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    
    return PayloadComparisonResponse(
        game_id=game_id,
        version_a=result["version_a"],
        version_b=result["version_b"],
        hashes_match=result["hashes_match"],
        diff=result["diff"],
    )


# =============================================================================
# ENDPOINTS - Diagnostics
# =============================================================================


@router.get(
    "/frontend-payload/game/{game_id}/diagnostics",
    summary="Get payload diagnostics",
    description="Get diagnostic information about frontend payloads for a game.",
)
async def get_payload_diagnostics(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get diagnostic information about frontend payloads.
    
    Useful for understanding payload generation history and issues.
    """
    # Get all versions
    versions = await list_versions(session, game_id, limit=100)
    
    if not versions:
        return {
            "game_id": game_id,
            "status": "no_payloads",
            "message": "No frontend payload versions found for this game",
        }
    
    # Find active version
    active = next((v for v in versions if v.is_active), None)
    
    # Analyze version history
    version_summary = []
    prev_hash = None
    for v in reversed(versions):  # Oldest to newest
        changed = prev_hash is None or v.payload_hash != prev_hash
        version_summary.append({
            "version": v.version_number,
            "changed": changed,
            "source": v.generation_source,
            "moment_count": v.moment_count,
            "event_count": v.event_count,
            "created_at": v.created_at.isoformat(),
        })
        prev_hash = v.payload_hash
    
    # Count unique hashes (actual unique payloads)
    unique_hashes = len(set(v.payload_hash for v in versions))
    
    return {
        "game_id": game_id,
        "total_versions": len(versions),
        "unique_payloads": unique_hashes,
        "active_version": active.version_number if active else None,
        "latest_version": versions[0].version_number if versions else None,
        "active_payload_hash": active.payload_hash if active else None,
        "version_history": version_summary,
        "sources": list(set(v.generation_source for v in versions if v.generation_source)),
    }


@router.get(
    "/frontend-payload/game/{game_id}/diff-timeline",
    summary="Get version diff timeline",
    description="Get a timeline of all changes across versions.",
)
async def get_diff_timeline(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a timeline showing what changed in each version.
    
    Useful for understanding the evolution of a game's payload.
    """
    versions = await list_versions(session, game_id, limit=100)
    
    if not versions:
        return {
            "game_id": game_id,
            "changes": [],
        }
    
    changes = []
    for v in reversed(versions):  # Oldest to newest
        change = {
            "version": v.version_number,
            "created_at": v.created_at.isoformat(),
            "source": v.generation_source,
            "pipeline_run_id": v.pipeline_run_id,
            "event_count": v.event_count,
            "moment_count": v.moment_count,
        }
        
        if v.diff_from_previous:
            change["diff"] = v.diff_from_previous
        else:
            change["diff"] = {"initial_version": True}
        
        changes.append(change)
    
    return {
        "game_id": game_id,
        "total_changes": len(changes),
        "changes": changes,
    }
