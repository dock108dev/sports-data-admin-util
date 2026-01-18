"""FINALIZE_MOMENTS Stage Implementation.

This stage takes validated moments and persists the final timeline artifact.
It merges PBP events with social posts and generates the summary.

Input: ValidationOutput from VALIDATE_MOMENTS stage (plus accumulated context)
Output: FinalizedOutput with artifact reference
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .... import db_models
from ....db import AsyncSession
from ....utils.datetime_utils import now_utc
from ...social_events import build_social_events_async
from ...summary_builder import build_nba_summary, build_summary_from_timeline_async
from ...frontend_payload import create_payload_version
from ..models import FinalizedOutput, StageInput, StageOutput

logger = logging.getLogger(__name__)

# Social post time windows
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60

# Canonical phase ordering
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
    """Get sort order for a phase."""
    if phase is None:
        return 100
    return PHASE_ORDER.get(phase, 100)


def _merge_timeline_events(
    pbp_events: Sequence[dict[str, Any]],
    social_events: Sequence[tuple[datetime, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Merge PBP and social events using PHASE-FIRST ordering."""
    # Convert PBP events to tuple format for sorting
    pbp_tuples = []
    for event in pbp_events:
        # Use synthetic timestamp for display
        ts_str = event.get("synthetic_timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else datetime.min
        except ValueError:
            ts = datetime.min
        pbp_tuples.append((ts, event))
    
    merged = list(pbp_tuples) + list(social_events)
    
    def sort_key(
        item: tuple[datetime, dict[str, Any]]
    ) -> tuple[int, float, int, int]:
        _, payload = item
        phase = payload.get("phase", "unknown")
        phase_order = _phase_sort_order(phase)
        intra_order = payload.get("intra_phase_order", 0)
        event_type_order = 0 if payload.get("event_type") == "pbp" else 1
        play_index = payload.get("play_index", 0)
        return (phase_order, intra_order, event_type_order, play_index)
    
    sorted_events = sorted(merged, key=sort_key)
    return [payload for _, payload in sorted_events]


async def execute_finalize_moments(
    session: AsyncSession,
    stage_input: StageInput,
    run_uuid: str,
) -> StageOutput:
    """Execute the FINALIZE_MOMENTS stage.
    
    Merges PBP events with social posts, generates summary, and persists
    the final timeline artifact.
    
    Args:
        session: Database session
        stage_input: Input containing accumulated outputs from previous stages
        run_uuid: UUID of the pipeline run for audit trail
        
    Returns:
        StageOutput with FinalizedOutput data
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id
    
    output.add_log(f"Starting FINALIZE_MOMENTS for game {game_id}")
    
    # Get accumulated outputs from previous stages
    prev_output = stage_input.previous_output
    if prev_output is None:
        raise ValueError("FINALIZE_MOMENTS requires accumulated output from previous stages")
    
    # Check validation passed
    if not prev_output.get("passed", False):
        raise ValueError("Cannot finalize - validation did not pass")
    
    # Get data from earlier stages
    pbp_events = prev_output.get("pbp_events", [])
    moments = prev_output.get("moments", [])
    game_start_str = prev_output.get("game_start", "")
    game_end_str = prev_output.get("game_end", "")
    phase_boundaries_str = prev_output.get("phase_boundaries", {})
    
    if not pbp_events:
        raise ValueError("No PBP events in accumulated output")
    if not moments:
        raise ValueError("No moments in accumulated output")
    
    output.add_log(f"Finalizing {len(moments)} moments with {len(pbp_events)} PBP events")
    
    # Fetch game for summary generation
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
        raise ValueError(f"Game {game_id} not found")
    
    # Parse timestamps
    try:
        game_start = datetime.fromisoformat(game_start_str) if game_start_str else game.start_time
        game_end = datetime.fromisoformat(game_end_str) if game_end_str else game_start + timedelta(hours=3)
    except ValueError:
        game_start = game.start_time
        game_end = game_start + timedelta(hours=3)
    
    # Convert phase boundaries from string to datetime
    phase_boundaries: dict[str, tuple[datetime, datetime]] = {}
    for phase, (start_str, end_str) in phase_boundaries_str.items():
        try:
            phase_boundaries[phase] = (
                datetime.fromisoformat(start_str),
                datetime.fromisoformat(end_str),
            )
        except (ValueError, TypeError):
            pass
    
    # Fetch and process social posts
    social_events: list[tuple[datetime, dict[str, Any]]] = []
    
    if game.has_reliable_start_time and phase_boundaries:
        output.add_log("Fetching social posts...")
        
        social_window_start = game_start - timedelta(seconds=SOCIAL_PREGAME_WINDOW_SECONDS)
        social_window_end = game_end + timedelta(seconds=SOCIAL_POSTGAME_WINDOW_SECONDS)
        
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
        
        output.add_log(f"Found {len(posts)} social posts")
        
        if posts:
            league_code = game.league.code if game.league else "NBA"
            social_events = await build_social_events_async(
                posts, phase_boundaries, league_code
            )
            output.add_log(f"Built {len(social_events)} social events")
    else:
        output.add_log("Skipping social posts (no reliable tip_time)", "warning")
    
    # Merge timeline
    timeline = _merge_timeline_events(pbp_events, social_events)
    output.add_log(f"Merged timeline: {len(timeline)} total events")
    
    # Build game analysis
    game_analysis = {
        "moments": moments,
        "notable_moments": prev_output.get("notable_moments", []),
        "moment_count": len(moments),
    }
    
    # Build summary
    output.add_log("Generating summary...")
    base_summary = build_nba_summary(game)
    game_analysis_with_summary = {**game_analysis, "summary": base_summary}
    
    league_code = game.league.code if game.league else "NBA"
    summary_json = await build_summary_from_timeline_async(
        timeline=timeline,
        game_analysis=game_analysis_with_summary,
        game_id=game_id,
        timeline_version="v1",
        sport=league_code,
    )
    
    output.add_log("Summary generated")
    
    # Persist artifact
    output.add_log("Persisting timeline artifact...")
    generated_at = now_utc()
    
    artifact_result = await session.execute(
        select(db_models.SportsGameTimelineArtifact).where(
            db_models.SportsGameTimelineArtifact.game_id == game_id,
            db_models.SportsGameTimelineArtifact.sport == league_code,
            db_models.SportsGameTimelineArtifact.timeline_version == "v1",
        )
    )
    artifact = artifact_result.scalar_one_or_none()
    
    if artifact is None:
        artifact = db_models.SportsGameTimelineArtifact(
            game_id=game_id,
            sport=league_code,
            timeline_version="v1",
            generated_at=generated_at,
            timeline_json=timeline,
            game_analysis_json=game_analysis,
            summary_json=summary_json,
            generated_by="pipeline",
            generation_reason=f"pipeline_run:{run_uuid}",
        )
        session.add(artifact)
    else:
        artifact.generated_at = generated_at
        artifact.timeline_json = timeline
        artifact.game_analysis_json = game_analysis
        artifact.summary_json = summary_json
        artifact.generated_by = "pipeline"
        artifact.generation_reason = f"pipeline_run:{run_uuid}"
    
    await session.flush()
    artifact_id = artifact.id
    
    output.add_log(f"Artifact persisted with id={artifact_id}")
    
    # Create immutable frontend payload version
    # This ensures we never mutate what the frontend receives
    output.add_log("Creating frontend payload version...")
    
    # Get pipeline run ID from input
    pipeline_run_id = stage_input.run_id
    
    try:
        payload_version = await create_payload_version(
            session=session,
            game_id=game_id,
            timeline=timeline,
            moments=moments,
            summary=summary_json,
            pipeline_run_id=pipeline_run_id,
            source="pipeline",
            notes=f"pipeline_run:{run_uuid}",
            skip_if_unchanged=True,
        )
        
        if payload_version:
            output.add_log(
                f"Frontend payload version {payload_version.version_number} created "
                f"(hash: {payload_version.payload_hash[:16]}...)"
            )
        else:
            output.add_log("Frontend payload unchanged - no new version created")
    except Exception as e:
        output.add_log(f"Warning: Failed to create frontend payload version: {e}", "warning")
    
    # Build output
    finalized_output = FinalizedOutput(
        artifact_id=artifact_id,
        timeline_events=len(timeline),
        moment_count=len(moments),
        generated_at=generated_at.isoformat(),
    )
    
    output.data = finalized_output.to_dict()
    output.add_log("FINALIZE_MOMENTS completed successfully")
    
    return output
