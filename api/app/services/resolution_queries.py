"""Read-path query utilities for entity resolution data.

These functions query persisted EntityResolution records and build
ResolutionSummary objects for the admin resolution API.
"""

from __future__ import annotations

from sqlalchemy import select

from ..db import AsyncSession
from ..db.pipeline import GamePipelineRun
from ..db.resolution import EntityResolution
from .resolution_tracker import ResolutionSummary


async def get_resolution_summary_for_game(
    session: AsyncSession,
    game_id: int,
) -> ResolutionSummary:
    """Get resolution summary for a game from persisted records."""
    result = await session.execute(
        select(EntityResolution)
        .where(EntityResolution.game_id == game_id)
        .order_by(EntityResolution.created_at.desc())
    )
    records = result.scalars().all()

    summary = ResolutionSummary(game_id=game_id)

    for record in records:
        if record.entity_type == "team":
            summary.teams_total += 1
            if record.resolution_status == "success":
                summary.teams_resolved += 1
            elif record.resolution_status == "failed":
                summary.teams_failed += 1
                summary.unresolved_teams.append(
                    {
                        "source": record.source_identifier,
                        "reason": record.failure_reason,
                        "occurrences": record.occurrence_count,
                    }
                )
            elif record.resolution_status == "ambiguous":
                summary.teams_ambiguous += 1
                summary.ambiguous_teams.append(
                    {
                        "source": record.source_identifier,
                        "candidates": record.candidates,
                        "resolved_to": record.resolved_name,
                    }
                )

            summary.team_resolutions.append(
                {
                    "source": record.source_identifier,
                    "resolved_id": record.resolved_id,
                    "resolved_name": record.resolved_name,
                    "status": record.resolution_status,
                    "method": record.resolution_method,
                    "occurrences": record.occurrence_count,
                }
            )

        elif record.entity_type == "player":
            summary.players_total += 1
            if record.resolution_status == "success":
                summary.players_resolved += 1
            elif record.resolution_status == "failed":
                summary.players_failed += 1
                summary.unresolved_players.append(
                    {
                        "source": record.source_identifier,
                        "reason": record.failure_reason,
                    }
                )

            summary.player_resolutions.append(
                {
                    "source": record.source_identifier,
                    "resolved_name": record.resolved_name,
                    "status": record.resolution_status,
                    "method": record.resolution_method,
                    "occurrences": record.occurrence_count,
                }
            )

    return summary


async def get_resolution_summary_for_run(
    session: AsyncSession,
    run_id: int,
) -> ResolutionSummary | None:
    """Get resolution summary for a specific pipeline run."""
    # Get the run to find game_id
    run_result = await session.execute(
        select(GamePipelineRun).where(GamePipelineRun.id == run_id)
    )
    run = run_result.scalar_one_or_none()

    if not run:
        return None

    result = await session.execute(
        select(EntityResolution).where(EntityResolution.pipeline_run_id == run_id)
    )
    records = result.scalars().all()

    summary = ResolutionSummary(game_id=run.game_id, pipeline_run_id=run_id)

    for record in records:
        if record.entity_type == "team":
            summary.teams_total += 1
            if record.resolution_status == "success":
                summary.teams_resolved += 1
            elif record.resolution_status == "failed":
                summary.teams_failed += 1
                summary.unresolved_teams.append(
                    {
                        "source": record.source_identifier,
                        "reason": record.failure_reason,
                        "occurrences": record.occurrence_count,
                    }
                )
            elif record.resolution_status == "ambiguous":
                summary.teams_ambiguous += 1
                summary.ambiguous_teams.append(
                    {
                        "source": record.source_identifier,
                        "candidates": record.candidates,
                    }
                )

            summary.team_resolutions.append(
                {
                    "source": record.source_identifier,
                    "resolved_id": record.resolved_id,
                    "resolved_name": record.resolved_name,
                    "status": record.resolution_status,
                    "method": record.resolution_method,
                }
            )

        elif record.entity_type == "player":
            summary.players_total += 1
            if record.resolution_status == "success":
                summary.players_resolved += 1
            elif record.resolution_status == "failed":
                summary.players_failed += 1

            summary.player_resolutions.append(
                {
                    "source": record.source_identifier,
                    "resolved_name": record.resolved_name,
                    "status": record.resolution_status,
                }
            )

    return summary
