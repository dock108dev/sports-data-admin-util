"""Entity Resolution Tracking Service.

Tracks how teams and players are resolved from source identifiers to internal
IDs. This enables full auditability of the resolution process.

RESOLUTION FLOW
===============

1. TEAM RESOLUTION (during PBP ingestion):
   - Source: team_abbreviation (e.g., "LAL", "BOS", "PHX")
   - Target: team_id in sports_teams table
   - Methods:
     - exact_match: Abbreviation matches team.abbreviation exactly
     - game_context: Using game's home_team/away_team mapping
     - fuzzy_match: Normalized name matching (NCAAB)
   - Result: EntityResolution record with status and details

2. PLAYER RESOLUTION (during PBP ingestion):
   - Source: player_name (e.g., "LeBron James", "J. Brown")
   - Target: Currently just name normalization (no players table)
   - Methods:
     - passthrough: Name used as-is
     - normalized: Name cleaned and standardized
   - Note: Players are tracked by name, not internal ID

EDGE CASES
==========

1. UNRESOLVED TEAMS:
   - Cause: Unknown abbreviation, typo, or data source variation
   - Example: "PHX" vs "PHO" for Phoenix Suns
   - Action: Log as failed, show in admin UI for manual review

2. AMBIGUOUS TEAMS:
   - Cause: Same abbreviation in different contexts
   - Example: "LA" could be Lakers or Clippers
   - Action: Pick most likely, log as ambiguous with candidates

3. MISSING PLAYERS:
   - Cause: Some plays don't have player names (timeouts, etc.)
   - Action: Skip player resolution for these plays
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from .. import db_models
from ..db import AsyncSession

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class ResolutionAttempt:
    """Single resolution attempt for tracking."""

    entity_type: str  # "team" or "player"
    source_identifier: str
    source_context: dict[str, Any] | None = None
    resolved_id: int | None = None
    resolved_name: str | None = None
    status: str = "pending"  # success, failed, ambiguous, partial
    method: str | None = None
    confidence: float | None = None
    failure_reason: str | None = None
    candidates: list[dict[str, Any]] | None = None
    play_index: int | None = None


@dataclass
class ResolutionSummary:
    """Summary of all resolutions for a game or run."""

    game_id: int
    pipeline_run_id: int | None = None

    # Team resolution stats
    teams_total: int = 0
    teams_resolved: int = 0
    teams_failed: int = 0
    teams_ambiguous: int = 0

    # Player resolution stats
    players_total: int = 0
    players_resolved: int = 0
    players_failed: int = 0

    # Detailed results
    team_resolutions: list[dict[str, Any]] = field(default_factory=list)
    player_resolutions: list[dict[str, Any]] = field(default_factory=list)

    # Issues for review
    unresolved_teams: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_teams: list[dict[str, Any]] = field(default_factory=list)
    unresolved_players: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "pipeline_run_id": self.pipeline_run_id,
            "teams": {
                "total": self.teams_total,
                "resolved": self.teams_resolved,
                "failed": self.teams_failed,
                "ambiguous": self.teams_ambiguous,
                "resolution_rate": round(
                    self.teams_resolved / self.teams_total * 100, 1
                )
                if self.teams_total > 0
                else 0,
            },
            "players": {
                "total": self.players_total,
                "resolved": self.players_resolved,
                "failed": self.players_failed,
                "resolution_rate": round(
                    self.players_resolved / self.players_total * 100, 1
                )
                if self.players_total > 0
                else 0,
            },
            "issues": {
                "unresolved_teams": self.unresolved_teams,
                "ambiguous_teams": self.ambiguous_teams,
                "unresolved_players": self.unresolved_players,
            },
        }


# =============================================================================
# RESOLUTION TRACKER
# =============================================================================


class ResolutionTracker:
    """Tracks entity resolutions during PBP processing.

    Usage:
        tracker = ResolutionTracker(game_id, pipeline_run_id)

        # Track team resolution
        tracker.track_team(
            source_abbrev="LAL",
            resolved_id=123,
            resolved_name="Los Angeles Lakers",
            method="game_context",
            play_index=45,
        )

        # Track failed resolution
        tracker.track_team_failure(
            source_abbrev="XYZ",
            reason="Unknown abbreviation",
            play_index=67,
        )

        # Persist all resolutions
        await tracker.persist(session)
    """

    def __init__(
        self,
        game_id: int,
        pipeline_run_id: int | None = None,
    ):
        self.game_id = game_id
        self.pipeline_run_id = pipeline_run_id
        self.attempts: list[ResolutionAttempt] = []
        self._seen_teams: dict[str, int] = {}  # source_id -> first index in attempts
        self._seen_players: dict[
            str, int
        ] = {}  # source_name -> first index in attempts

    def track_team(
        self,
        source_abbrev: str,
        resolved_id: int | None = None,
        resolved_name: str | None = None,
        method: str = "exact_match",
        confidence: float | None = None,
        play_index: int | None = None,
        source_context: dict[str, Any] | None = None,
    ) -> None:
        """Track a successful or partially successful team resolution."""
        key = source_abbrev.upper() if source_abbrev else ""

        if key in self._seen_teams:
            # Update occurrence count for existing resolution
            idx = self._seen_teams[key]
            self.attempts[idx].source_context = self.attempts[idx].source_context or {}
            self.attempts[idx].source_context["occurrence_count"] = (
                self.attempts[idx].source_context.get("occurrence_count", 1) + 1
            )
            if play_index is not None:
                self.attempts[idx].source_context["last_play_index"] = play_index
            return

        status = "success" if resolved_id else "partial"
        attempt = ResolutionAttempt(
            entity_type="team",
            source_identifier=source_abbrev,
            source_context=source_context
            or {"occurrence_count": 1, "first_play_index": play_index},
            resolved_id=resolved_id,
            resolved_name=resolved_name,
            status=status,
            method=method,
            confidence=confidence,
            play_index=play_index,
        )

        self._seen_teams[key] = len(self.attempts)
        self.attempts.append(attempt)

    def track_team_failure(
        self,
        source_abbrev: str,
        reason: str,
        candidates: list[dict[str, Any]] | None = None,
        play_index: int | None = None,
        source_context: dict[str, Any] | None = None,
    ) -> None:
        """Track a failed team resolution."""
        key = source_abbrev.upper() if source_abbrev else ""

        if key in self._seen_teams:
            idx = self._seen_teams[key]
            self.attempts[idx].source_context = self.attempts[idx].source_context or {}
            self.attempts[idx].source_context["occurrence_count"] = (
                self.attempts[idx].source_context.get("occurrence_count", 1) + 1
            )
            return

        status = "ambiguous" if candidates and len(candidates) > 1 else "failed"
        attempt = ResolutionAttempt(
            entity_type="team",
            source_identifier=source_abbrev,
            source_context=source_context
            or {"occurrence_count": 1, "first_play_index": play_index},
            status=status,
            failure_reason=reason,
            candidates=candidates,
            play_index=play_index,
        )

        self._seen_teams[key] = len(self.attempts)
        self.attempts.append(attempt)

    def track_player(
        self,
        source_name: str,
        resolved_name: str | None = None,
        method: str = "passthrough",
        play_index: int | None = None,
        source_context: dict[str, Any] | None = None,
    ) -> None:
        """Track a player resolution (currently name normalization only)."""
        if not source_name:
            return

        key = source_name.lower().strip()

        if key in self._seen_players:
            idx = self._seen_players[key]
            self.attempts[idx].source_context = self.attempts[idx].source_context or {}
            self.attempts[idx].source_context["occurrence_count"] = (
                self.attempts[idx].source_context.get("occurrence_count", 1) + 1
            )
            if play_index is not None:
                self.attempts[idx].source_context["last_play_index"] = play_index
            return

        attempt = ResolutionAttempt(
            entity_type="player",
            source_identifier=source_name,
            source_context=source_context
            or {"occurrence_count": 1, "first_play_index": play_index},
            resolved_name=resolved_name or source_name,
            status="success",
            method=method,
            play_index=play_index,
        )

        self._seen_players[key] = len(self.attempts)
        self.attempts.append(attempt)

    def track_player_failure(
        self,
        source_name: str,
        reason: str,
        play_index: int | None = None,
    ) -> None:
        """Track a failed player resolution."""
        if not source_name:
            return

        key = source_name.lower().strip()

        if key in self._seen_players:
            return  # Already tracked

        attempt = ResolutionAttempt(
            entity_type="player",
            source_identifier=source_name,
            source_context={"occurrence_count": 1, "first_play_index": play_index},
            status="failed",
            failure_reason=reason,
            play_index=play_index,
        )

        self._seen_players[key] = len(self.attempts)
        self.attempts.append(attempt)

    def get_summary(self) -> ResolutionSummary:
        """Build a summary of all tracked resolutions."""
        summary = ResolutionSummary(
            game_id=self.game_id,
            pipeline_run_id=self.pipeline_run_id,
        )

        for attempt in self.attempts:
            if attempt.entity_type == "team":
                summary.teams_total += 1
                if attempt.status == "success":
                    summary.teams_resolved += 1
                elif attempt.status == "failed":
                    summary.teams_failed += 1
                    summary.unresolved_teams.append(
                        {
                            "source": attempt.source_identifier,
                            "reason": attempt.failure_reason,
                            "occurrences": attempt.source_context.get(
                                "occurrence_count", 1
                            )
                            if attempt.source_context
                            else 1,
                        }
                    )
                elif attempt.status == "ambiguous":
                    summary.teams_ambiguous += 1
                    summary.ambiguous_teams.append(
                        {
                            "source": attempt.source_identifier,
                            "candidates": attempt.candidates,
                            "resolved_to": attempt.resolved_name,
                        }
                    )

                summary.team_resolutions.append(
                    {
                        "source": attempt.source_identifier,
                        "resolved_id": attempt.resolved_id,
                        "resolved_name": attempt.resolved_name,
                        "status": attempt.status,
                        "method": attempt.method,
                    }
                )

            elif attempt.entity_type == "player":
                summary.players_total += 1
                if attempt.status == "success":
                    summary.players_resolved += 1
                elif attempt.status == "failed":
                    summary.players_failed += 1
                    summary.unresolved_players.append(
                        {
                            "source": attempt.source_identifier,
                            "reason": attempt.failure_reason,
                        }
                    )

                summary.player_resolutions.append(
                    {
                        "source": attempt.source_identifier,
                        "resolved_name": attempt.resolved_name,
                        "status": attempt.status,
                        "method": attempt.method,
                    }
                )

        return summary

    async def persist(self, session: AsyncSession) -> int:
        """Persist all tracked resolutions to the database.

        Returns:
            Number of resolution records created
        """
        if not self.attempts:
            return 0

        count = 0
        for attempt in self.attempts:
            ctx = attempt.source_context or {}
            record = db_models.EntityResolution(
                game_id=self.game_id,
                pipeline_run_id=self.pipeline_run_id,
                entity_type=attempt.entity_type,
                source_identifier=attempt.source_identifier,
                source_context=attempt.source_context,
                resolved_id=attempt.resolved_id,
                resolved_name=attempt.resolved_name,
                resolution_status=attempt.status,
                resolution_method=attempt.method,
                confidence=attempt.confidence,
                failure_reason=attempt.failure_reason,
                candidates=attempt.candidates,
                occurrence_count=ctx.get("occurrence_count", 1),
                first_play_index=ctx.get("first_play_index"),
                last_play_index=ctx.get("last_play_index"),
            )
            session.add(record)
            count += 1

        await session.flush()

        logger.info(
            "entity_resolutions_persisted",
            extra={
                "game_id": self.game_id,
                "pipeline_run_id": self.pipeline_run_id,
                "resolution_count": count,
            },
        )

        return count


# =============================================================================
# QUERY UTILITIES
# =============================================================================


async def get_resolution_summary_for_game(
    session: AsyncSession,
    game_id: int,
) -> ResolutionSummary:
    """Get resolution summary for a game from persisted records."""
    result = await session.execute(
        select(db_models.EntityResolution)
        .where(db_models.EntityResolution.game_id == game_id)
        .order_by(db_models.EntityResolution.created_at.desc())
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
        select(db_models.GamePipelineRun).where(db_models.GamePipelineRun.id == run_id)
    )
    run = run_result.scalar_one_or_none()

    if not run:
        return None

    result = await session.execute(
        select(db_models.EntityResolution).where(
            db_models.EntityResolution.pipeline_run_id == run_id
        )
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
