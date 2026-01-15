"""
Timeline artifact storage and versioning.

Handles persisting and retrieving timeline artifacts from the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ... import db_models
from ...db import AsyncSession
from ...utils.datetime_utils import now_utc

logger = logging.getLogger(__name__)

DEFAULT_TIMELINE_VERSION = "v1"


@dataclass
class TimelineArtifactPayload:
    """Payload for a generated timeline artifact."""
    game_id: int
    sport: str
    timeline_version: str
    generated_at: datetime
    timeline: list[dict[str, Any]]
    summary: dict[str, Any]
    game_analysis: dict[str, Any]


class TimelineGenerationError(Exception):
    """Raised when timeline generation fails."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


async def get_stored_artifact(
    session: AsyncSession,
    game_id: int,
    sport: str = "NBA",
    timeline_version: str = DEFAULT_TIMELINE_VERSION,
) -> db_models.SportsGameTimelineArtifact | None:
    """Retrieve a stored timeline artifact."""
    result = await session.execute(
        select(db_models.SportsGameTimelineArtifact).where(
            db_models.SportsGameTimelineArtifact.game_id == game_id,
            db_models.SportsGameTimelineArtifact.sport == sport,
            db_models.SportsGameTimelineArtifact.timeline_version == timeline_version,
        )
    )
    return result.scalar_one_or_none()


async def store_artifact(
    session: AsyncSession,
    game_id: int,
    sport: str,
    timeline_version: str,
    timeline: list[dict[str, Any]],
    game_analysis: dict[str, Any],
    summary: dict[str, Any],
    generated_by: str = "api",
    generation_reason: str | None = None,
) -> TimelineArtifactPayload:
    """
    Store or update a timeline artifact in the database.

    Returns the artifact payload.
    """
    generated_at = now_utc()

    artifact = await get_stored_artifact(session, game_id, sport, timeline_version)

    if artifact is None:
        artifact = db_models.SportsGameTimelineArtifact(
            game_id=game_id,
            sport=sport,
            timeline_version=timeline_version,
            generated_at=generated_at,
            timeline_json=timeline,
            game_analysis_json=game_analysis,
            summary_json=summary,
            generated_by=generated_by,
            generation_reason=generation_reason,
        )
        session.add(artifact)
        logger.info(
            "timeline_artifact_created",
            extra={"game_id": game_id, "timeline_version": timeline_version},
        )
    else:
        artifact.generated_at = generated_at
        artifact.timeline_json = timeline
        artifact.game_analysis_json = game_analysis
        artifact.summary_json = summary
        artifact.generated_by = generated_by
        artifact.generation_reason = generation_reason
        logger.info(
            "timeline_artifact_updated",
            extra={"game_id": game_id, "timeline_version": timeline_version},
        )

    await session.flush()

    return TimelineArtifactPayload(
        game_id=game_id,
        sport=sport,
        timeline_version=timeline_version,
        generated_at=generated_at,
        timeline=timeline,
        summary=summary,
        game_analysis=game_analysis,
    )
