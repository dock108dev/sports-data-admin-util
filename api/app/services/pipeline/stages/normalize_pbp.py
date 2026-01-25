"""NORMALIZE_PBP Stage Implementation.

This stage reads raw play-by-play data from the database and produces
normalized events with phase assignments and synthetic timestamps.

Input: game_id (reads from sports_game_plays table)
Output: NormalizedPBPOutput with pbp_events, phase_boundaries, etc.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .... import db_models
from ....db import AsyncSession
from ....utils.datetime_utils import parse_clock_to_seconds
from ....services.resolution_tracker import ResolutionTracker
from ..models import NormalizedPBPOutput, StageInput, StageOutput

logger = logging.getLogger(__name__)

# Constants from timeline_generator.py
NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60

# Social post time windows
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60


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


def _nba_game_end(
    game_start: datetime, plays: Sequence[db_models.SportsGamePlay]
) -> datetime:
    """Calculate actual game end time based on plays."""
    max_quarter = 4
    for play in plays:
        if play.quarter and play.quarter > max_quarter:
            max_quarter = play.quarter

    if max_quarter <= 4:
        return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)

    # Has overtime
    ot_count = max_quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_count * 15 * 60
    )


def _compute_phase_boundaries(
    game_start: datetime, has_overtime: bool = False
) -> dict[str, tuple[datetime, datetime]]:
    """Compute start/end times for each narrative phase."""
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


def _progress_from_index(index: int, total: int) -> float:
    """Calculate progress through the game based on play index."""
    if total <= 1:
        return 0.0
    return index / (total - 1)


def _build_pbp_events(
    plays: Sequence[db_models.SportsGamePlay],
    game_start: datetime,
) -> list[dict[str, Any]]:
    """Build normalized PBP events with phase assignment and synthetic timestamps.

    Each event includes:
    - phase: Narrative phase (q1, q2, etc.)
    - intra_phase_order: Sort key within phase (clock-based)
    - synthetic_timestamp: Computed wall-clock time for display
    """
    events: list[dict[str, Any]] = []
    total_plays = len(plays)

    for play in plays:
        quarter = play.quarter or 1
        phase = _nba_phase_for_quarter(quarter)
        block = _nba_block_for_quarter(quarter)

        # Parse game clock
        clock_seconds = parse_clock_to_seconds(play.game_clock)
        if clock_seconds is None:
            intra_phase_order = play.play_index
            progress = _progress_from_index(play.play_index, total_plays)
        else:
            # Invert clock: 12:00 (720s) -> 0, 0:00 -> 720
            intra_phase_order = NBA_QUARTER_GAME_SECONDS - clock_seconds
            progress = (quarter - 1 + (1 - clock_seconds / 720)) / 4

        # Compute synthetic timestamp
        quarter_start = _nba_quarter_start(game_start, quarter)
        elapsed_in_quarter = NBA_QUARTER_GAME_SECONDS - (clock_seconds or 0)
        real_elapsed = elapsed_in_quarter * (
            NBA_QUARTER_REAL_SECONDS / NBA_QUARTER_GAME_SECONDS
        )
        synthetic_ts = quarter_start + timedelta(seconds=real_elapsed)

        # Extract team abbreviation from relationship
        team_abbrev = None
        if hasattr(play, "team") and play.team:
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
        events.append(event_payload)

    return events


def _compute_resolution_stats(plays: list) -> dict[str, Any]:
    """Compute resolution statistics for PBP data.

    Tracks:
    - teams_resolved: Plays with team_id resolved
    - teams_unresolved: Plays with team in raw data but no team_id
    - players_with_name: Plays with player_name
    - plays_with_score: Plays with score information
    - clock_parse_failures: Plays where clock couldn't be parsed
    """
    total = len(plays)
    if total == 0:
        return {
            "total_plays": 0,
            "teams_resolved": 0,
            "teams_unresolved": 0,
            "players_with_name": 0,
            "players_without_name": 0,
            "plays_with_score": 0,
            "plays_without_score": 0,
            "clock_parse_failures": 0,
        }

    teams_resolved = sum(1 for p in plays if p.team_id is not None)
    teams_unresolved = sum(
        1
        for p in plays
        if p.team_id is None
        and (p.raw_data.get("teamTricode") or p.raw_data.get("team"))
    )
    players_with_name = sum(1 for p in plays if p.player_name)
    plays_with_score = sum(1 for p in plays if p.home_score is not None)
    clock_failures = sum(1 for p in plays if not p.game_clock)

    return {
        "total_plays": total,
        "teams_resolved": teams_resolved,
        "teams_unresolved": teams_unresolved,
        "team_resolution_rate": round(teams_resolved / total * 100, 1)
        if total > 0
        else 0,
        "players_with_name": players_with_name,
        "players_without_name": total - players_with_name,
        "plays_with_score": plays_with_score,
        "plays_without_score": total - plays_with_score,
        "clock_parse_failures": clock_failures,
    }


async def execute_normalize_pbp(
    session: AsyncSession,
    stage_input: StageInput,
    pipeline_run_id: int | None = None,
) -> StageOutput:
    """Execute the NORMALIZE_PBP stage.

    Reads play-by-play data from the database and produces normalized
    events with phase assignments and synthetic timestamps.

    Also creates a PBP snapshot for auditability.

    Args:
        session: Database session
        stage_input: Input containing game_id
        pipeline_run_id: Optional pipeline run ID for snapshot association

    Returns:
        StageOutput with NormalizedPBPOutput data
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id
    run_id = pipeline_run_id or stage_input.run_id

    output.add_log(f"Starting NORMALIZE_PBP for game {game_id}")

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
        raise ValueError(f"Game {game_id} not found")

    if not game.is_final:
        raise ValueError(f"Game {game_id} is not final (status: {game.status})")

    output.add_log(f"Game found: {game.away_team.name} @ {game.home_team.name}")

    # Fetch plays with team relationship
    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .options(selectinload(db_models.SportsGamePlay.team))
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = list(plays_result.scalars().all())

    if not plays:
        raise ValueError(f"Game {game_id} has no play-by-play data")

    output.add_log(f"Found {len(plays)} plays")

    # Compute resolution stats BEFORE normalization
    resolution_stats = _compute_resolution_stats(plays)
    output.add_log(f"Team resolution rate: {resolution_stats['team_resolution_rate']}%")

    if resolution_stats["teams_unresolved"] > 0:
        output.add_log(
            f"WARNING: {resolution_stats['teams_unresolved']} plays have unresolved teams",
            "warning",
        )

    # Track entity resolutions for auditability
    resolution_tracker = ResolutionTracker(game_id, run_id)

    # Build team context from game
    home_abbrev = game.home_team.abbreviation if game.home_team else None
    away_abbrev = game.away_team.abbreviation if game.away_team else None

    # Track team and player resolutions
    for play in plays:
        # Track team resolution
        raw_team = play.raw_data.get("teamTricode") or play.raw_data.get("team")
        if raw_team:
            if play.team_id is not None:
                resolution_tracker.track_team(
                    source_abbrev=raw_team,
                    resolved_id=play.team_id,
                    resolved_name=play.team.name if play.team else None,
                    method="game_context"
                    if raw_team.upper() in (home_abbrev, away_abbrev)
                    else "abbreviation_lookup",
                    play_index=play.play_index,
                    source_context={"raw_data": play.raw_data},
                )
            else:
                resolution_tracker.track_team_failure(
                    source_abbrev=raw_team,
                    reason="No matching team found for abbreviation",
                    play_index=play.play_index,
                    source_context={"raw_data": play.raw_data},
                )

        # Track player resolution (name normalization)
        if play.player_name:
            resolution_tracker.track_player(
                source_name=play.player_name,
                resolved_name=play.player_name,  # Currently passthrough
                method="passthrough",
                play_index=play.play_index,
            )

    # Get resolution summary for logging
    res_summary = resolution_tracker.get_summary()
    output.add_log(
        f"Resolution tracking: {res_summary.teams_resolved}/{res_summary.teams_total} teams, "
        f"{res_summary.players_resolved}/{res_summary.players_total} players"
    )

    # Persist entity resolutions
    try:
        resolution_count = await resolution_tracker.persist(session)
        output.add_log(f"Persisted {resolution_count} entity resolutions")
    except Exception as e:
        output.add_log(f"Warning: Failed to persist entity resolutions: {e}", "warning")

    # Compute game timing
    game_start = game.start_time
    game_end = _nba_game_end(game_start, plays)
    has_overtime = any((play.quarter or 0) > 4 for play in plays)

    output.add_log(f"Game timing: {game_start.isoformat()} to {game_end.isoformat()}")
    if has_overtime:
        output.add_log("Game went to overtime")

    # Build normalized PBP events
    pbp_events = _build_pbp_events(plays, game_start)

    output.add_log(f"Normalized {len(pbp_events)} PBP events")

    # Compute phase boundaries for later use
    phase_boundaries = _compute_phase_boundaries(game_start, has_overtime)

    # Convert datetime boundaries to ISO strings for JSON serialization
    phase_boundaries_str = {
        phase: (start.isoformat(), end.isoformat())
        for phase, (start, end) in phase_boundaries.items()
    }

    # Create PBP snapshot for auditability
    try:
        snapshot = db_models.PBPSnapshot(
            game_id=game_id,
            pipeline_run_id=run_id,
            snapshot_type="normalized",
            source="pipeline",
            play_count=len(pbp_events),
            plays_json=pbp_events,
            metadata_json={
                "game_start": game_start.isoformat(),
                "game_end": game_end.isoformat(),
                "has_overtime": has_overtime,
                "phase_boundaries": phase_boundaries_str,
                "home_team": game.home_team.name if game.home_team else None,
                "away_team": game.away_team.name if game.away_team else None,
            },
            resolution_stats=resolution_stats,
        )
        session.add(snapshot)
        await session.flush()
        output.add_log(f"Created PBP snapshot (id={snapshot.id})")
    except Exception as e:
        output.add_log(f"Warning: Failed to create PBP snapshot: {e}", "warning")

    # Build output
    normalized_output = NormalizedPBPOutput(
        pbp_events=pbp_events,
        game_start=game_start.isoformat(),
        game_end=game_end.isoformat(),
        has_overtime=has_overtime,
        total_plays=len(plays),
        phase_boundaries=phase_boundaries_str,
    )

    # Add resolution stats to output for visibility
    output.data = {
        **normalized_output.to_dict(),
        "resolution_stats": resolution_stats,
    }
    output.add_log("NORMALIZE_PBP completed successfully")

    return output
