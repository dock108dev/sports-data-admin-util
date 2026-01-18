"""Frontend Payload Version Service.

Manages immutable, versioned frontend payloads. Each time a pipeline run
completes, a NEW payload version is created - payloads are NEVER mutated.

DESIGN PRINCIPLES
=================

1. IMMUTABILITY
   - Once created, a FrontendPayloadVersion is never modified
   - No UPDATE operations - only INSERTs
   - Historical versions preserved forever

2. VERSIONING
   - Each game has a version_number sequence (1, 2, 3, ...)
   - Exactly one version is "active" at any time
   - Creating a new version deactivates the previous

3. CHANGE DETECTION
   - payload_hash enables quick duplicate detection
   - If content hasn't changed, no new version is created
   - diff_from_previous shows what changed

4. TRACEABILITY
   - Every payload links to its pipeline_run_id
   - generation_source and generation_notes for audit

FRONTEND CONTRACT
=================

The frontend receives exactly this structure:
{
    "timeline": [...],     // Array of timeline events
    "moments": [...],      // Array of moment objects
    "summary": {...},      // Game summary object
    "version": {
        "version_number": 3,
        "generated_at": "2026-02-18T12:00:00Z",
        "pipeline_run_id": 456
    }
}
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import func, select, update

from .. import db_models
from ..db import AsyncSession

logger = logging.getLogger(__name__)


def compute_payload_hash(
    timeline: list[dict[str, Any]],
    moments: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    """Compute SHA-256 hash of payload content.
    
    This enables quick duplicate detection without comparing full payloads.
    """
    content = json.dumps({
        "timeline": timeline,
        "moments": moments,
        "summary": summary,
    }, sort_keys=True, default=str)
    
    return hashlib.sha256(content.encode()).hexdigest()


def compute_diff(
    prev_timeline: list[dict[str, Any]] | None,
    prev_moments: list[dict[str, Any]] | None,
    new_timeline: list[dict[str, Any]],
    new_moments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute a summary of changes between versions.
    
    Returns a diff summary (not a full diff) suitable for quick review.
    """
    diff: dict[str, Any] = {}
    
    # Timeline changes
    prev_timeline_count = len(prev_timeline) if prev_timeline else 0
    new_timeline_count = len(new_timeline)
    
    if prev_timeline_count != new_timeline_count:
        diff["timeline_count_change"] = new_timeline_count - prev_timeline_count
    
    # Moment changes
    prev_moment_count = len(prev_moments) if prev_moments else 0
    new_moment_count = len(new_moments)
    
    if prev_moment_count != new_moment_count:
        diff["moment_count_change"] = new_moment_count - prev_moment_count
    
    # Compare moment IDs
    if prev_moments:
        prev_moment_ids = {m.get("id") for m in prev_moments}
        new_moment_ids = {m.get("id") for m in new_moments}
        
        added_moments = new_moment_ids - prev_moment_ids
        removed_moments = prev_moment_ids - new_moment_ids
        
        if added_moments:
            diff["moments_added"] = list(added_moments)
        if removed_moments:
            diff["moments_removed"] = list(removed_moments)
    
    # Compare moment types distribution
    if new_moments:
        new_type_counts: dict[str, int] = {}
        for m in new_moments:
            mtype = m.get("type", "unknown")
            new_type_counts[mtype] = new_type_counts.get(mtype, 0) + 1
        diff["moment_types"] = new_type_counts
    
    if not diff:
        diff["no_changes"] = True
    
    return diff


async def get_next_version_number(
    session: AsyncSession,
    game_id: int,
) -> int:
    """Get the next version number for a game."""
    result = await session.execute(
        select(func.coalesce(func.max(db_models.FrontendPayloadVersion.version_number), 0))
        .where(db_models.FrontendPayloadVersion.game_id == game_id)
    )
    max_version = result.scalar() or 0
    return max_version + 1


async def get_active_version(
    session: AsyncSession,
    game_id: int,
) -> db_models.FrontendPayloadVersion | None:
    """Get the currently active payload version for a game."""
    result = await session.execute(
        select(db_models.FrontendPayloadVersion)
        .where(
            db_models.FrontendPayloadVersion.game_id == game_id,
            db_models.FrontendPayloadVersion.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_version_by_number(
    session: AsyncSession,
    game_id: int,
    version_number: int,
) -> db_models.FrontendPayloadVersion | None:
    """Get a specific version by number."""
    result = await session.execute(
        select(db_models.FrontendPayloadVersion)
        .where(
            db_models.FrontendPayloadVersion.game_id == game_id,
            db_models.FrontendPayloadVersion.version_number == version_number,
        )
    )
    return result.scalar_one_or_none()


async def list_versions(
    session: AsyncSession,
    game_id: int,
    limit: int = 50,
) -> list[db_models.FrontendPayloadVersion]:
    """List all payload versions for a game, newest first."""
    result = await session.execute(
        select(db_models.FrontendPayloadVersion)
        .where(db_models.FrontendPayloadVersion.game_id == game_id)
        .order_by(db_models.FrontendPayloadVersion.version_number.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_payload_version(
    session: AsyncSession,
    game_id: int,
    timeline: list[dict[str, Any]],
    moments: list[dict[str, Any]],
    summary: dict[str, Any],
    pipeline_run_id: int | None = None,
    source: str = "pipeline",
    notes: str | None = None,
    skip_if_unchanged: bool = True,
) -> db_models.FrontendPayloadVersion | None:
    """Create a new immutable payload version.
    
    This function:
    1. Computes the payload hash
    2. Optionally skips if unchanged from active version
    3. Gets the next version number
    4. Deactivates the current active version
    5. Creates the new version as active
    6. Computes the diff from the previous version
    
    Args:
        session: Database session
        game_id: Game ID
        timeline: Timeline events array
        moments: Moments array
        summary: Summary object
        pipeline_run_id: Optional pipeline run that created this
        source: Generation source (pipeline, manual, backfill)
        notes: Optional generation notes
        skip_if_unchanged: If True, skip creating if content unchanged
        
    Returns:
        The new FrontendPayloadVersion, or None if skipped
    """
    # Compute hash
    payload_hash = compute_payload_hash(timeline, moments, summary)
    
    # Get current active version
    current_active = await get_active_version(session, game_id)
    
    # Skip if unchanged
    if skip_if_unchanged and current_active:
        if current_active.payload_hash == payload_hash:
            logger.info(
                "frontend_payload_unchanged",
                extra={
                    "game_id": game_id,
                    "current_version": current_active.version_number,
                    "hash": payload_hash[:16],
                },
            )
            return None
    
    # Get next version number
    next_version = await get_next_version_number(session, game_id)
    
    # Compute diff from previous
    diff = None
    if current_active:
        diff = compute_diff(
            current_active.timeline_json,
            current_active.moments_json,
            timeline,
            moments,
        )
    
    # Deactivate current active version
    if current_active:
        await session.execute(
            update(db_models.FrontendPayloadVersion)
            .where(
                db_models.FrontendPayloadVersion.game_id == game_id,
                db_models.FrontendPayloadVersion.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )
    
    # Create new version
    new_version = db_models.FrontendPayloadVersion(
        game_id=game_id,
        pipeline_run_id=pipeline_run_id,
        version_number=next_version,
        is_active=True,
        payload_hash=payload_hash,
        timeline_json=timeline,
        moments_json=moments,
        summary_json=summary,
        event_count=len(timeline),
        moment_count=len(moments),
        generation_source=source,
        generation_notes=notes,
        diff_from_previous=diff,
    )
    
    session.add(new_version)
    await session.flush()
    
    logger.info(
        "frontend_payload_version_created",
        extra={
            "game_id": game_id,
            "version_number": next_version,
            "pipeline_run_id": pipeline_run_id,
            "event_count": len(timeline),
            "moment_count": len(moments),
            "hash": payload_hash[:16],
        },
    )
    
    return new_version


async def get_frontend_payload(
    session: AsyncSession,
    game_id: int,
    version_number: int | None = None,
) -> dict[str, Any] | None:
    """Get the frontend payload for a game.
    
    Args:
        session: Database session
        game_id: Game ID
        version_number: Specific version, or None for active version
        
    Returns:
        The full frontend payload with metadata, or None if not found
    """
    if version_number is not None:
        version = await get_version_by_number(session, game_id, version_number)
    else:
        version = await get_active_version(session, game_id)
    
    if not version:
        return None
    
    return {
        "timeline": version.timeline_json,
        "moments": version.moments_json,
        "summary": version.summary_json,
        "version": {
            "version_number": version.version_number,
            "is_active": version.is_active,
            "generated_at": version.created_at.isoformat(),
            "pipeline_run_id": version.pipeline_run_id,
            "generation_source": version.generation_source,
            "payload_hash": version.payload_hash,
        },
    }


async def compare_versions(
    session: AsyncSession,
    game_id: int,
    version_a: int,
    version_b: int,
) -> dict[str, Any]:
    """Compare two payload versions.
    
    Returns a summary of differences between the versions.
    """
    v_a = await get_version_by_number(session, game_id, version_a)
    v_b = await get_version_by_number(session, game_id, version_b)
    
    if not v_a or not v_b:
        return {
            "error": "One or both versions not found",
            "version_a_found": v_a is not None,
            "version_b_found": v_b is not None,
        }
    
    # Compute diff
    diff = compute_diff(
        v_a.timeline_json,
        v_a.moments_json,
        v_b.timeline_json,
        v_b.moments_json,
    )
    
    return {
        "version_a": {
            "version_number": v_a.version_number,
            "event_count": v_a.event_count,
            "moment_count": v_a.moment_count,
            "created_at": v_a.created_at.isoformat(),
        },
        "version_b": {
            "version_number": v_b.version_number,
            "event_count": v_b.event_count,
            "moment_count": v_b.moment_count,
            "created_at": v_b.created_at.isoformat(),
        },
        "hashes_match": v_a.payload_hash == v_b.payload_hash,
        "diff": diff,
    }
