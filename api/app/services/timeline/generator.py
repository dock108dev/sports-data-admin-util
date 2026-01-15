"""
Timeline artifact generation orchestrator.

This is the main entry point for timeline generation. It coordinates:
1. Fetching game data from the database
2. Building PBP events with phases
3. Building social events with roles
4. Merging into unified timeline
5. Running game analysis and summary generation
6. Validating and persisting the artifact

Related modules:
- pbp_events.py: PBP → timeline events
- phase_utils.py: Phase/time calculations
- artifact.py: Storage/versioning
- social_events.py: Social post processing
- summary_builder.py: Reading guide generation
- game_analysis.py: Segment detection
- ai_client.py: OpenAI integration

AI Usage Principle:
    OpenAI is used ONLY for interpretation and narration - never for
    ordering, filtering, or correctness. See docs/TECHNICAL_FLOW.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession
from ..timeline_validation import validate_and_log, TimelineValidationError
from ..game_analysis import build_nba_game_analysis_async
from ..social_events import build_social_events, build_social_events_async
from ..summary_builder import build_nba_summary, build_summary_from_timeline_async

from .phase_utils import (
    SOCIAL_PREGAME_WINDOW_SECONDS,
    SOCIAL_POSTGAME_WINDOW_SECONDS,
    phase_sort_order,
    compute_phase_boundaries,
)
from .pbp_events import build_pbp_events, nba_game_end
from .artifact import (
    DEFAULT_TIMELINE_VERSION,
    TimelineArtifactPayload,
    TimelineGenerationError,
    store_artifact,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TIMELINE ASSEMBLY
# =============================================================================


def build_nba_timeline(
    game: db_models.SportsGame,
    plays: Sequence[db_models.SportsGamePlay],
    social_posts: Sequence[db_models.GameSocialPost],
) -> tuple[list[dict[str, Any]], dict[str, Any], datetime]:
    """
    Build a complete timeline for an NBA game.

    This is the main entry point for timeline construction. It:
    1. Builds PBP events with phases
    2. Builds social events with phases and roles
    3. Merges them using phase-first ordering
    4. Returns timeline, summary metadata, and computed game end time
    """
    game_start = game.start_time
    game_end = nba_game_end(game_start, plays)
    has_overtime = any((play.quarter or 0) > 4 for play in plays)

    # Compute phase boundaries for social event assignment
    phase_boundaries = compute_phase_boundaries(game_start, has_overtime)

    pbp_events = build_pbp_events(plays, game_start)
    social_events = build_social_events(social_posts, phase_boundaries)
    timeline = _merge_timeline_events(pbp_events, social_events)
    summary = build_nba_summary(game)
    return timeline, summary, game_end


def _merge_timeline_events(
    pbp_events: Sequence[tuple[datetime, dict[str, Any]]],
    social_events: Sequence[tuple[datetime, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Merge PBP and social events using PHASE-FIRST ordering.

    Ordering is determined by:
    1. phase_order (from PHASE_ORDER constant) - PRIMARY
    2. intra_phase_order (clock progress for PBP, seconds for social) - SECONDARY
    3. event_type tiebreaker (pbp before tweet at same position) - TERTIARY

    synthetic_timestamp is NOT used for ordering.
    """
    merged = list(pbp_events) + list(social_events)

    def sort_key(
        item: tuple[datetime, dict[str, Any]]
    ) -> tuple[int, float, int, int]:
        _, payload = item

        # Primary: phase order
        phase = payload.get("phase", "unknown")
        phase_order_val = phase_sort_order(phase)

        # Secondary: intra-phase order
        intra_order = payload.get("intra_phase_order", 0)

        # Tertiary: event type (pbp=0, tweet=1) so PBP comes first at ties
        event_type_order = 0 if payload.get("event_type") == "pbp" else 1

        # Quaternary: play_index for PBP stability
        play_index = payload.get("play_index", 0)

        return (phase_order_val, intra_order, event_type_order, play_index)

    sorted_events = sorted(merged, key=sort_key)

    # Extract payloads
    return [payload for _, payload in sorted_events]


# =============================================================================
# ARTIFACT GENERATION
# =============================================================================


async def generate_timeline_artifact(
    session: AsyncSession,
    game_id: int,
    timeline_version: str = DEFAULT_TIMELINE_VERSION,
    generated_by: str = "api",
    generation_reason: str | None = None,
) -> TimelineArtifactPayload:
    """
    Generate and persist a complete timeline artifact for a game.

    This is the main async entry point. It:
    1. Fetches game, plays, and social posts from DB
    2. Builds PBP and social events with phases
    3. Merges into unified timeline
    4. Runs game analysis and summary generation
    5. Validates and persists the artifact
    """
    logger.info(
        "timeline_artifact_generation_started",
        extra={"game_id": game_id, "timeline_version": timeline_version},
    )
    try:
        # Fetch game with relations
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
            raise TimelineGenerationError("Game not found", status_code=404)

        if not game.is_final:
            raise TimelineGenerationError("Game is not final", status_code=409)

        league_code = game.league.code if game.league else ""
        if league_code != "NBA":
            raise TimelineGenerationError(
                "Timeline generation only supported for NBA", status_code=422
            )

        # Fetch plays
        plays_result = await session.execute(
            select(db_models.SportsGamePlay)
            .where(db_models.SportsGamePlay.game_id == game_id)
            .order_by(db_models.SportsGamePlay.play_index)
        )
        plays = plays_result.scalars().all()
        if not plays:
            raise TimelineGenerationError(
                "Missing play-by-play data", status_code=422
            )

        game_start = game.start_time
        game_end = nba_game_end(game_start, plays)
        has_overtime = any((play.quarter or 0) > 4 for play in plays)

        # Compute phase boundaries for social event assignment
        phase_boundaries = compute_phase_boundaries(game_start, has_overtime)

        # Expanded social post window
        social_window_start = game_start - timedelta(
            seconds=SOCIAL_PREGAME_WINDOW_SECONDS
        )
        social_window_end = game_end + timedelta(
            seconds=SOCIAL_POSTGAME_WINDOW_SECONDS
        )

        posts_result = await session.execute(
            select(db_models.GameSocialPost)
            .where(
                db_models.GameSocialPost.game_id == game_id,
                db_models.GameSocialPost.posted_at >= social_window_start,
                db_models.GameSocialPost.posted_at <= social_window_end,
            )
            .order_by(db_models.GameSocialPost.posted_at)
        )
        posts = posts_result.scalars().all()

        logger.info(
            "social_posts_window",
            extra={
                "game_id": game_id,
                "window_start": social_window_start.isoformat(),
                "window_end": social_window_end.isoformat(),
                "posts_found": len(posts),
            },
        )

        # Build PBP events
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "build_pbp_events"},
        )
        pbp_events = build_pbp_events(plays, game_start)
        if not pbp_events:
            raise TimelineGenerationError(
                "Missing play-by-play data", status_code=422
            )
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "build_pbp_events",
                "events": len(pbp_events),
            },
        )

        # Build social events with AI-enhanced roles
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "build_social_events"},
        )
        social_events = await build_social_events_async(
            posts, phase_boundaries, league_code
        )
        timeline = _merge_timeline_events(pbp_events, social_events)
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "build_social_events",
                "timeline_events": len(timeline),
                "social_posts": len(posts),
            },
        )

        # Game analysis
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "game_analysis"},
        )
        base_summary = build_nba_summary(game)
        game_analysis = await build_nba_game_analysis_async(
            timeline=timeline,
            summary=base_summary,
            game_id=game_id,
            sport=league_code,
        )
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "game_analysis",
                "segments": len(game_analysis.get("segments", [])),
                "highlights": len(game_analysis.get("highlights", [])),
            },
        )

        # Summary generation
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "summary_generation"},
        )
        game_analysis_with_summary = {**game_analysis, "summary": base_summary}
        summary_json = await build_summary_from_timeline_async(
            timeline=timeline,
            game_analysis=game_analysis_with_summary,
            game_id=game_id,
            timeline_version=timeline_version,
            sport=league_code,
        )
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "summary_generation",
                "ai_generated": summary_json.get("ai_generated", False),
            },
        )

        # Validation
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "validation"},
        )
        try:
            validation_report = validate_and_log(timeline, summary_json, game_id)
            logger.info(
                "timeline_artifact_phase_completed",
                extra={
                    "game_id": game_id,
                    "phase": "validation",
                    "verdict": validation_report.verdict,
                    "critical_passed": validation_report.critical_passed,
                    "warnings": validation_report.warnings_count,
                },
            )
        except TimelineValidationError as exc:
            logger.error(
                "timeline_artifact_validation_blocked",
                extra={
                    "game_id": game_id,
                    "phase": "validation",
                    "report": exc.report.to_dict(),
                },
            )
            raise TimelineGenerationError(
                f"Timeline validation failed: {exc}",
                status_code=422,
            ) from exc

        # Persist artifact
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "persist_artifact"},
        )
        payload = await store_artifact(
            session=session,
            game_id=game_id,
            sport="NBA",
            timeline_version=timeline_version,
            timeline=timeline,
            game_analysis=game_analysis,
            summary=summary_json,
            generated_by=generated_by,
            generation_reason=generation_reason,
        )
        logger.info(
            "timeline_artifact_phase_completed",
            extra={"game_id": game_id, "phase": "persist_artifact"},
        )

        logger.info(
            "timeline_artifact_generated",
            extra={
                "game_id": game_id,
                "timeline_version": timeline_version,
                "timeline_events": len(timeline),
                "social_posts": len(posts),
                "plays": len(plays),
            },
        )

        return payload
    except Exception:
        logger.exception(
            "timeline_artifact_generation_failed",
            extra={"game_id": game_id, "timeline_version": timeline_version},
        )
        raise
