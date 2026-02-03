"""
Timeline artifact generation for finalized games.

SOCIAL DECOUPLING CONTRACT (Phase 2)
====================================
Timeline generation treats social data as OPTIONAL:
- Works identically with or without social posts
- No league-specific branching for social data availability
- Social posts gracefully degrade to empty list for all leagues

The timeline MUST render completely when:
- Social posts are present
- Social posts are partially present
- Social posts are completely absent

Current social scraping status:
- NBA: Social scraping configured (posts may exist)
- NHL: No social scraping (posts will be empty)
- NCAAB: No social scraping (posts will be empty)

This is acceptable and requires NO special handling.

Builds PBP and social events for game timelines:
1. PBP events from game plays (with phase assignment)
2. Social events from posts (with phase and role assignment) - OPTIONAL
3. Merge events using phase-first ordering
4. Validate timeline structure

Related modules:
- timeline_types.py: Constants, data classes, exceptions
- timeline_phases.py: Phase utilities and timing calculations
- timeline_events.py: PBP event building and timeline merging
- social_events.py: Social post processing and role assignment
- timeline_validation.py: Validation and sanity checks

See docs/TIMELINE_ASSEMBLY.md for the assembly contract.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import db_models
from ..db import AsyncSession
from ..utils.datetime_utils import now_utc
from .timeline_types import (
    DEFAULT_TIMELINE_VERSION,
    SOCIAL_POSTGAME_WINDOW_SECONDS,
    SOCIAL_PREGAME_WINDOW_SECONDS,
    TimelineArtifactPayload,
    TimelineGenerationError,
)
from .timeline_phases import compute_phase_boundaries, nba_game_end
from .timeline_events import build_pbp_events, merge_timeline_events
from .timeline_validation import validate_and_log, TimelineValidationError
from .social_events import build_social_events, build_social_events_async

logger = logging.getLogger(__name__)


# =============================================================================
# STUB FUNCTIONS (Not Yet Implemented)
# These are placeholders for future AI-powered analysis features
# =============================================================================


def build_game_summary(game: db_models.SportsGame) -> dict[str, Any]:
    """Build basic summary dict from game data.

    Returns minimal game metadata for timeline context.
    League-agnostic - works for NBA, NHL, NCAAB.
    """
    league_code = game.league.code if game.league else "UNK"
    return {
        "game_id": game.id,
        "league": league_code,
        "home_team": game.home_team.name if game.home_team else None,
        "away_team": game.away_team.name if game.away_team else None,
        "home_score": game.home_score,
        "away_score": game.away_score,
        "status": game.status,
    }


async def build_game_analysis_async(
    timeline: list[dict[str, Any]],
    summary: dict[str, Any],
    game_id: int,
    sport: str,
    timeline_version: str,
    game_context: dict[str, Any],
) -> dict[str, Any]:
    """Build game analysis from timeline data.

    NOT YET IMPLEMENTED - placeholder for future AI analysis.
    Returns minimal structure with empty chapters.
    """
    return {
        "chapters": [],
        "key_moments": [],
        "game_flow": {},
    }


async def build_summary_from_timeline_async(
    timeline: list[dict[str, Any]],
    game_analysis: dict[str, Any],
    game_id: int | None = None,
    timeline_version: str | None = None,
    sport: str | None = None,
) -> dict[str, Any]:
    """Generate AI summary from timeline and analysis.

    NOT YET IMPLEMENTED - placeholder for future AI summary generation.
    Returns empty summary structure.
    """
    return {
        "ai_generated": False,
        "summary_text": "",
        "highlights": [],
    }


# =============================================================================
# TIMELINE ASSEMBLY
# =============================================================================


def build_nba_timeline(
    game: db_models.SportsGame,
    plays: Sequence[db_models.SportsGamePlay],
    social_posts: Sequence[db_models.GameSocialPost],
) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
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
    timeline = merge_timeline_events(pbp_events, social_events)
    summary = build_game_summary(game)
    return timeline, summary, game_end


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

        # Phase 2: Timeline generation is league-agnostic
        # Social data is optional and gracefully degrades to empty for all leagues
        league_code = game.league.code if game.league else "UNK"

        # Fetch plays with team relationship for team_abbreviation
        plays_result = await session.execute(
            select(db_models.SportsGamePlay)
            .options(selectinload(db_models.SportsGamePlay.team))
            .where(db_models.SportsGamePlay.game_id == game_id)
            .order_by(db_models.SportsGamePlay.play_index)
        )
        plays = plays_result.scalars().all()
        if not plays:
            raise TimelineGenerationError("Missing play-by-play data", status_code=422)

        game_start = game.start_time
        game_end = nba_game_end(game_start, plays)
        has_overtime = any((play.quarter or 0) > 4 for play in plays)

        # Compute phase boundaries for social event assignment
        phase_boundaries = compute_phase_boundaries(game_start, has_overtime)

        # Only include social posts if we have a reliable tip_time
        posts: list[db_models.GameSocialPost] = []
        if game.has_reliable_start_time:
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
            posts = list(posts_result.scalars().all())

            logger.info(
                "social_posts_window",
                extra={
                    "game_id": game_id,
                    "window_start": social_window_start.isoformat(),
                    "window_end": social_window_end.isoformat(),
                    "posts_found": len(posts),
                },
            )
        else:
            logger.warning(
                "social_posts_skipped_no_tip_time",
                extra={
                    "game_id": game_id,
                    "reason": "No reliable tip_time available",
                },
            )

        # Build PBP events
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "build_pbp_events"},
        )
        pbp_events = build_pbp_events(plays, game_start)
        if not pbp_events:
            raise TimelineGenerationError("Missing play-by-play data", status_code=422)
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
        timeline = merge_timeline_events(pbp_events, social_events)
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
        base_summary = build_game_summary(game)

        # Build game context for team name resolution
        game_context = {
            "home_team_name": game.home_team.name if game.home_team else "Home",
            "away_team_name": game.away_team.name if game.away_team else "Away",
            "home_team_abbrev": game.home_team.abbreviation
            if game.home_team
            else "HOME",
            "away_team_abbrev": game.away_team.abbreviation
            if game.away_team
            else "AWAY",
        }

        game_analysis = await build_game_analysis_async(
            timeline=timeline,
            summary=base_summary,
            game_id=game_id,
            sport=league_code,
            timeline_version=timeline_version,
            game_context=game_context,
        )
        chapter_count = len(game_analysis.get("chapters", []))
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "game_analysis",
                "chapter_count": chapter_count,
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
        generated_at = now_utc()
        artifact_result = await session.execute(
            select(db_models.SportsGameTimelineArtifact).where(
                db_models.SportsGameTimelineArtifact.game_id == game_id,
                db_models.SportsGameTimelineArtifact.sport == league_code,
                db_models.SportsGameTimelineArtifact.timeline_version
                == timeline_version,
            )
        )
        artifact = artifact_result.scalar_one_or_none()

        if artifact is None:
            artifact = db_models.SportsGameTimelineArtifact(
                game_id=game_id,
                sport=league_code,
                timeline_version=timeline_version,
                generated_at=generated_at,
                timeline_json=timeline,
                game_analysis_json=game_analysis,
                summary_json=summary_json,
                generated_by=generated_by,
                generation_reason=generation_reason,
            )
            session.add(artifact)
        else:
            artifact.generated_at = generated_at
            artifact.timeline_json = timeline
            artifact.game_analysis_json = game_analysis
            artifact.summary_json = summary_json
            artifact.generated_by = generated_by
            artifact.generation_reason = generation_reason

        await session.flush()
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

        return TimelineArtifactPayload(
            game_id=game_id,
            sport=league_code,
            timeline_version=timeline_version,
            generated_at=generated_at,
            timeline=timeline,
            summary=summary_json,
            game_analysis=game_analysis,
        )
    except Exception:
        logger.exception(
            "timeline_artifact_generation_failed",
            extra={"game_id": game_id, "timeline_version": timeline_version},
        )
        raise
