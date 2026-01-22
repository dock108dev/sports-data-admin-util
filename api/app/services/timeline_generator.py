"""
Timeline artifact generation for finalized games.

Builds PBP and social events for game timelines:
1. PBP events from game plays (with phase assignment)
2. Social events from posts (with phase and role assignment)
3. Merge events using phase-first ordering
4. Validate timeline structure

Related modules:
- social_events.py: Social post processing and role assignment
- timeline_validation.py: Validation and sanity checks

See docs/TIMELINE_ASSEMBLY.md for the assembly contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import db_models
from ..db import AsyncSession
from ..utils.datetime_utils import now_utc, parse_clock_to_seconds
from .timeline_validation import validate_and_log, TimelineValidationError
from .social_events import build_social_events, build_social_events_async

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_PREGAME_REAL_SECONDS = 10 * 60
NBA_OVERTIME_PADDING_SECONDS = 30 * 60
DEFAULT_TIMELINE_VERSION = "v1"

# Social post time windows (configurable)
# These define how far before/after the game we include social posts
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60   # 2 hours before game start
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60  # 2 hours after game end

# Canonical phase ordering - this is the source of truth for timeline order
PHASE_ORDER: dict[str, int] = {
    "pregame": 0,
    "q1": 1,
    "q2": 2,
    "halftime": 3,
    "q3": 4,
    "q4": 5,
    "ot1": 6,
    "ot2": 7,
    "ot3": 8,
    "ot4": 9,
    "postgame": 99,
}


def _phase_sort_order(phase: str | None) -> int:
    """Get sort order for a phase. Unknown phases sort after postgame."""
    if phase is None:
        return 100
    return PHASE_ORDER.get(phase, 100)


# =============================================================================
# DATA CLASSES
# =============================================================================


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


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


# Clock parsing moved to utils/datetime_utils.py


def _progress_from_index(index: int, total: int) -> float:
    """
    Calculate progress through the game based on play index.

    Returns 0.0 at start, 1.0 at end.
    """
    if total <= 1:
        return 0.0
    return index / (total - 1)


# =============================================================================
# PHASE UTILITIES
# =============================================================================


def _nba_phase_for_quarter(quarter: int | None) -> str:
    """Map quarter number to narrative phase."""
    if quarter is None:
        return "unknown"
    if quarter == 1:
        return "q1"
    if quarter == 2:
        return "q2"
    if quarter == 3:
        return "q3"
    if quarter == 4:
        return "q4"
    if quarter == 5:
        return "ot1"
    if quarter == 6:
        return "ot2"
    if quarter == 7:
        return "ot3"
    if quarter == 8:
        return "ot4"
    return f"ot{quarter - 4}" if quarter > 4 else "unknown"


def _nba_block_for_quarter(quarter: int | None) -> str:
    """Map quarter to game block (first_half, second_half, overtime)."""
    if quarter is None:
        return "unknown"
    if quarter <= 2:
        return "first_half"
    if quarter <= 4:
        return "second_half"
    return "overtime"


def _nba_quarter_start(game_start: datetime, quarter: int) -> datetime:
    """Calculate when a quarter starts in real time."""
    if quarter == 1:
        return game_start
    if quarter == 2:
        return game_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    if quarter == 3:
        return game_start + timedelta(
            seconds=2 * NBA_QUARTER_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS
        )
    if quarter == 4:
        return game_start + timedelta(
            seconds=3 * NBA_QUARTER_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS
        )
    # Overtime quarters
    ot_num = quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_num * 15 * 60
    )


def _nba_regulation_end(game_start: datetime) -> datetime:
    """Calculate when regulation ends."""
    return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)


def _nba_game_end(
    game_start: datetime, plays: Sequence[db_models.SportsGamePlay]
) -> datetime:
    """Calculate actual game end time based on plays."""
    max_quarter = 4
    for play in plays:
        if play.quarter and play.quarter > max_quarter:
            max_quarter = play.quarter

    if max_quarter <= 4:
        return _nba_regulation_end(game_start)

    # Has overtime
    ot_count = max_quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_count * 15 * 60
    )


def _compute_phase_boundaries(
    game_start: datetime, has_overtime: bool = False
) -> dict[str, tuple[datetime, datetime]]:
    """
    Compute start/end times for each narrative phase.

    These boundaries are used to assign social posts to phases.
    The pregame and postgame phases extend beyond the game itself.
    """
    boundaries: dict[str, tuple[datetime, datetime]] = {}

    # Pregame: 2 hours before to game start
    pregame_start = game_start - timedelta(seconds=SOCIAL_PREGAME_WINDOW_SECONDS)
    boundaries["pregame"] = (pregame_start, game_start)

    # Q1
    q1_start = game_start
    q1_end = game_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q1"] = (q1_start, q1_end)

    # Q2
    q2_start = q1_end
    q2_end = q2_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q2"] = (q2_start, q2_end)

    # Halftime
    halftime_start = q2_end
    halftime_end = halftime_start + timedelta(seconds=NBA_HALFTIME_REAL_SECONDS)
    boundaries["halftime"] = (halftime_start, halftime_end)

    # Q3
    q3_start = halftime_end
    q3_end = q3_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q3"] = (q3_start, q3_end)

    # Q4
    q4_start = q3_end
    q4_end = q4_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q4"] = (q4_start, q4_end)

    # Overtime periods (if applicable)
    if has_overtime:
        ot_start = q4_end
        for i in range(1, 5):  # Up to 4 OT periods
            ot_end = ot_start + timedelta(seconds=15 * 60)
            boundaries[f"ot{i}"] = (ot_start, ot_end)
            ot_start = ot_end
        boundaries["postgame"] = (ot_start, ot_start + timedelta(hours=2))
    else:
        boundaries["postgame"] = (q4_end, q4_end + timedelta(hours=2))

    return boundaries


# =============================================================================
# PBP EVENT BUILDING
# =============================================================================


def _build_pbp_events(
    plays: Sequence[db_models.SportsGamePlay],
    game_start: datetime,
) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Build PBP events with phase assignment and synthetic timestamps.

    Each event includes:
    - phase: Narrative phase (q1, q2, etc.)
    - intra_phase_order: Sort key within phase (clock-based)
    - synthetic_timestamp: Computed wall-clock time for display
    - team_abbreviation: Team abbreviation (if team_id is present)
    - player_name: Player name (if available)
    """
    events: list[tuple[datetime, dict[str, Any]]] = []
    total_plays = len(plays)

    for play in plays:
        quarter = play.quarter or 1
        phase = _nba_phase_for_quarter(quarter)
        block = _nba_block_for_quarter(quarter)

        # Parse game clock
        clock_seconds = parse_clock_to_seconds(play.game_clock)
        if clock_seconds is None:
            # Fallback: use play index for ordering
            intra_phase_order = play.play_index
            progress = _progress_from_index(play.play_index, total_plays)
        else:
            # Invert clock: 12:00 (720s) -> 0, 0:00 -> 720
            # So earlier in quarter has lower order (comes first)
            intra_phase_order = NBA_QUARTER_GAME_SECONDS - clock_seconds
            progress = (quarter - 1 + (1 - clock_seconds / 720)) / 4

        # Compute synthetic timestamp
        quarter_start = _nba_quarter_start(game_start, quarter)
        elapsed_in_quarter = NBA_QUARTER_GAME_SECONDS - (clock_seconds or 0)
        # Scale game time to real time (roughly 1.5x)
        real_elapsed = elapsed_in_quarter * (NBA_QUARTER_REAL_SECONDS / NBA_QUARTER_GAME_SECONDS)
        synthetic_ts = quarter_start + timedelta(seconds=real_elapsed)

        # Extract team abbreviation from relationship
        team_abbrev = None
        if hasattr(play, 'team') and play.team:
            team_abbrev = play.team.abbreviation

        event_payload = {
            "event_type": "pbp",
            "phase": phase,
            "intra_phase_order": intra_phase_order,
            "play_index": play.play_index,
            "quarter": quarter,
            "block": block,
            "game_clock": play.game_clock,
            "description": play.description,
            "play_type": play.play_type,
            "team_abbreviation": team_abbrev,
            "player_name": play.player_name,
            "home_score": play.home_score,
            "away_score": play.away_score,
            "synthetic_timestamp": synthetic_ts.isoformat(),
            "game_progress": round(progress, 3),
        }
        events.append((synthetic_ts, event_payload))

    return events


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
    game_end = _nba_game_end(game_start, plays)
    has_overtime = any((play.quarter or 0) > 4 for play in plays)

    # Compute phase boundaries for social event assignment
    phase_boundaries = _compute_phase_boundaries(game_start, has_overtime)

    pbp_events = _build_pbp_events(plays, game_start)
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

    synthetic_timestamp is NOT used for ordering. It is retained for
    display/debugging purposes only.

    See docs/TIMELINE_ASSEMBLY.md for the canonical assembly recipe.
    """
    merged = list(pbp_events) + list(social_events)

    def sort_key(
        item: tuple[datetime, dict[str, Any]]
    ) -> tuple[int, float, int, int]:
        _, payload = item

        # Primary: phase order
        phase = payload.get("phase", "unknown")
        phase_order = _phase_sort_order(phase)

        # Secondary: intra-phase order
        intra_order = payload.get("intra_phase_order", 0)

        # Tertiary: event type (pbp=0, tweet=1) so PBP comes first at ties
        event_type_order = 0 if payload.get("event_type") == "pbp" else 1

        # Quaternary: play_index for PBP stability
        play_index = payload.get("play_index", 0)

        return (phase_order, intra_order, event_type_order, play_index)

    sorted_events = sorted(merged, key=sort_key)

    # Extract payloads, keeping intra_phase_order for compact mode
    result = []
    for _, payload in sorted_events:
        result.append(payload)

    return result


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

        # Fetch plays with team relationship for team_abbreviation
        plays_result = await session.execute(
            select(db_models.SportsGamePlay)
            .options(selectinload(db_models.SportsGamePlay.team))
            .where(db_models.SportsGamePlay.game_id == game_id)
            .order_by(db_models.SportsGamePlay.play_index)
        )
        plays = plays_result.scalars().all()
        if not plays:
            raise TimelineGenerationError(
                "Missing play-by-play data", status_code=422
            )

        game_start = game.start_time
        game_end = _nba_game_end(game_start, plays)
        has_overtime = any((play.quarter or 0) > 4 for play in plays)

        # Compute phase boundaries for social event assignment
        phase_boundaries = _compute_phase_boundaries(game_start, has_overtime)

        # Only include social posts if we have a reliable tip_time
        # Without tip_time, social post windows would be based on midnight UTC
        # which produces incorrect/meaningless results
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
                    "reason": "No reliable tip_time available, social posts excluded from timeline",
                },
            )

        # Build PBP events
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "build_pbp_events"},
        )
        pbp_events = _build_pbp_events(plays, game_start)
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
        
        # Build game context for team name resolution
        game_context = {
            "home_team_name": game.home_team.name if game.home_team else "Home",
            "away_team_name": game.away_team.name if game.away_team else "Away",
            "home_team_abbrev": game.home_team.abbreviation if game.home_team else "HOME",
            "away_team_abbrev": game.away_team.abbreviation if game.away_team else "AWAY",
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
                db_models.SportsGameTimelineArtifact.sport == "NBA",
                db_models.SportsGameTimelineArtifact.timeline_version == timeline_version,
            )
        )
        artifact = artifact_result.scalar_one_or_none()

        if artifact is None:
            artifact = db_models.SportsGameTimelineArtifact(
                game_id=game_id,
                sport="NBA",
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
            sport="NBA",
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
