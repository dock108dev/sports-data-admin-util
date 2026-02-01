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

# NCAAB Constants (20-minute halves)
NCAAB_REGULATION_REAL_SECONDS = 75 * 60  # ~75 min real time (similar to NBA)
NCAAB_HALFTIME_REAL_SECONDS = 20 * 60    # 20-minute halftime
NCAAB_HALF_REAL_SECONDS = NCAAB_REGULATION_REAL_SECONDS // 2
NCAAB_HALF_GAME_SECONDS = 20 * 60        # 20 min per half
NCAAB_OT_GAME_SECONDS = 5 * 60           # 5-minute OT periods

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


def _ncaab_phase_for_period(period: int | None) -> str:
    """Map NCAAB period to narrative phase (h1, h2, ot1, etc.)."""
    if period is None:
        return "unknown"
    if period == 1:
        return "h1"
    if period == 2:
        return "h2"
    return f"ot{period - 2}" if period > 2 else "unknown"


def _ncaab_block_for_period(period: int | None) -> str:
    """Map NCAAB period to game block."""
    if period is None:
        return "unknown"
    if period == 1:
        return "first_half"
    if period == 2:
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


def _ncaab_period_start(game_start: datetime, period: int) -> datetime:
    """Calculate when a NCAAB period starts in real time."""
    if period == 1:
        return game_start
    if period == 2:
        return game_start + timedelta(
            seconds=NCAAB_HALF_REAL_SECONDS + NCAAB_HALFTIME_REAL_SECONDS
        )
    # Overtime periods (~10 min real per OT)
    ot_num = period - 2
    return game_start + timedelta(
        seconds=NCAAB_REGULATION_REAL_SECONDS + ot_num * 10 * 60
    )


def _ncaab_game_end(
    game_start: datetime, plays: Sequence[db_models.SportsGamePlay]
) -> datetime:
    """Calculate NCAAB game end time based on plays."""
    max_period = 2
    for play in plays:
        if play.quarter and play.quarter > max_period:
            max_period = play.quarter

    if max_period <= 2:
        return game_start + timedelta(seconds=NCAAB_REGULATION_REAL_SECONDS)

    # Has overtime
    ot_count = max_period - 2
    return game_start + timedelta(
        seconds=NCAAB_REGULATION_REAL_SECONDS + ot_count * 10 * 60
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


def _compute_ncaab_phase_boundaries(
    game_start: datetime, has_overtime: bool = False
) -> dict[str, tuple[datetime, datetime]]:
    """Compute start/end times for each NCAAB narrative phase."""
    boundaries: dict[str, tuple[datetime, datetime]] = {}

    # Pregame: 2 hours before to game start
    pregame_start = game_start - timedelta(seconds=SOCIAL_PREGAME_WINDOW_SECONDS)
    boundaries["pregame"] = (pregame_start, game_start)

    # H1 (first half)
    h1_start = game_start
    h1_end = game_start + timedelta(seconds=NCAAB_HALF_REAL_SECONDS)
    boundaries["h1"] = (h1_start, h1_end)

    # Halftime
    halftime_start = h1_end
    halftime_end = halftime_start + timedelta(seconds=NCAAB_HALFTIME_REAL_SECONDS)
    boundaries["halftime"] = (halftime_start, halftime_end)

    # H2 (second half)
    h2_start = halftime_end
    h2_end = h2_start + timedelta(seconds=NCAAB_HALF_REAL_SECONDS)
    boundaries["h2"] = (h2_start, h2_end)

    # Overtime periods (if applicable)
    if has_overtime:
        ot_start = h2_end
        for i in range(1, 5):  # Up to 4 OT periods
            ot_end = ot_start + timedelta(seconds=10 * 60)  # ~10 min real per OT
            boundaries[f"ot{i}"] = (ot_start, ot_end)
            ot_start = ot_end
        boundaries["postgame"] = (ot_start, ot_start + timedelta(hours=2))
    else:
        boundaries["postgame"] = (h2_end, h2_end + timedelta(hours=2))

    return boundaries


def _progress_from_index(index: int, total: int) -> float:
    """Calculate progress through the game based on play index."""
    if total <= 1:
        return 0.0
    return index / (total - 1)


def _build_pbp_events(
    plays: Sequence[db_models.SportsGamePlay],
    game_start: datetime,
    game_id: int | None = None,
    league_code: str = "NBA",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build normalized PBP events with phase assignment and synthetic timestamps.

    Each event includes:
    - phase: Narrative phase (q1, q2, h1, h2, etc. depending on league)
    - intra_phase_order: Sort key within phase (clock-based)
    - synthetic_timestamp: Computed wall-clock time for display

    SCORE CONTINUITY ENFORCEMENT:
    Scores are cumulative and NEVER reset except at true game start.
    At period boundaries, the raw PBP data may contain [0, 0] scores which
    are invalid. This function detects and corrects these score resets by
    carrying forward the last known valid score.

    Args:
        plays: Sequence of play records
        game_start: Game start timestamp
        game_id: Optional game ID for logging
        league_code: League code (NBA, NCAAB, etc.)

    Returns:
        Tuple of (events, score_violations) where score_violations is a list
        of detected score reset violations for logging/debugging.
    """
    events: list[dict[str, Any]] = []
    score_violations: list[dict[str, Any]] = []
    total_plays = len(plays)

    # League-specific configuration
    is_ncaab = league_code == "NCAAB"
    period_game_seconds = NCAAB_HALF_GAME_SECONDS if is_ncaab else NBA_QUARTER_GAME_SECONDS
    period_real_seconds = NCAAB_HALF_REAL_SECONDS if is_ncaab else NBA_QUARTER_REAL_SECONDS
    num_regulation_periods = 2 if is_ncaab else 4

    # Track last known valid scores (cumulative, never reset)
    last_valid_home_score = 0
    last_valid_away_score = 0

    for idx, play in enumerate(plays):
        period = play.quarter or 1

        # League-specific phase/block mapping
        if is_ncaab:
            phase = _ncaab_phase_for_period(period)
            block = _ncaab_block_for_period(period)
        else:
            phase = _nba_phase_for_quarter(period)
            block = _nba_block_for_quarter(period)

        # Parse game clock
        clock_seconds = parse_clock_to_seconds(play.game_clock)
        if clock_seconds is None:
            intra_phase_order = play.play_index
            progress = _progress_from_index(play.play_index, total_plays)
        else:
            # Invert clock: period_game_seconds -> 0, 0:00 -> period_game_seconds
            intra_phase_order = period_game_seconds - clock_seconds
            progress = (period - 1 + (1 - clock_seconds / period_game_seconds)) / num_regulation_periods

        # Compute synthetic timestamp
        if is_ncaab:
            period_start = _ncaab_period_start(game_start, period)
        else:
            period_start = _nba_quarter_start(game_start, period)

        elapsed_in_period = period_game_seconds - (clock_seconds or 0)
        real_elapsed = elapsed_in_period * (period_real_seconds / period_game_seconds)
        synthetic_ts = period_start + timedelta(seconds=real_elapsed)

        # Extract team abbreviation from relationship
        team_abbrev = None
        if hasattr(play, "team") and play.team:
            team_abbrev = play.team.abbreviation

        # SCORE CONTINUITY ENFORCEMENT
        # Detect and reject invalid score resets at period boundaries
        raw_home = play.home_score
        raw_away = play.away_score

        # Determine if this is the true game start (first play of period 1)
        is_true_game_start = idx == 0 and period == 1

        # Check for score reset violations
        if raw_home is not None and raw_away is not None:
            # Both scores provided - check for invalid reset
            is_score_reset = (
                raw_home == 0 and raw_away == 0 and
                (last_valid_home_score > 0 or last_valid_away_score > 0)
            )
            is_score_decrease = (
                raw_home < last_valid_home_score or
                raw_away < last_valid_away_score
            )

            if is_score_reset and not is_true_game_start:
                # Invalid score reset detected - log and carry forward
                score_violations.append({
                    "type": "SCORE_RESET",
                    "game_id": game_id,
                    "play_index": play.play_index,
                    "period": period,
                    "game_clock": play.game_clock,
                    "raw_scores": [raw_home, raw_away],
                    "carried_scores": [last_valid_home_score, last_valid_away_score],
                    "message": f"Score reset from [{last_valid_home_score}, {last_valid_away_score}] to [0, 0] at period {period}",
                })
                # Carry forward - do NOT update last_valid scores
            elif is_score_decrease and not is_true_game_start:
                # Score decreased (shouldn't happen) - log and carry forward
                score_violations.append({
                    "type": "SCORE_DECREASE",
                    "game_id": game_id,
                    "play_index": play.play_index,
                    "period": period,
                    "game_clock": play.game_clock,
                    "raw_scores": [raw_home, raw_away],
                    "carried_scores": [last_valid_home_score, last_valid_away_score],
                    "message": f"Score decreased from [{last_valid_home_score}, {last_valid_away_score}] to [{raw_home}, {raw_away}]",
                })
                # Carry forward - do NOT update last_valid scores
            else:
                # Valid score update - accept and update tracking
                last_valid_home_score = raw_home
                last_valid_away_score = raw_away
        elif raw_home is not None:
            # Only home score provided - check for decrease
            if raw_home >= last_valid_home_score:
                last_valid_home_score = raw_home
            else:
                score_violations.append({
                    "type": "SCORE_DECREASE",
                    "game_id": game_id,
                    "play_index": play.play_index,
                    "period": period,
                    "raw_scores": [raw_home, raw_away],
                    "carried_scores": [last_valid_home_score, last_valid_away_score],
                })
        elif raw_away is not None:
            # Only away score provided - check for decrease
            if raw_away >= last_valid_away_score:
                last_valid_away_score = raw_away
            else:
                score_violations.append({
                    "type": "SCORE_DECREASE",
                    "game_id": game_id,
                    "play_index": play.play_index,
                    "period": period,
                    "raw_scores": [raw_home, raw_away],
                    "carried_scores": [last_valid_home_score, last_valid_away_score],
                })
        # else: Neither score provided - carry forward implicitly (no update needed)

        event_payload = {
            "event_type": "pbp",
            "phase": phase,
            "intra_phase_order": intra_phase_order,
            "play_index": play.play_index,
            "quarter": period,  # Keep "quarter" key for compatibility but use period value
            "block": block,
            "game_clock": play.game_clock,
            "description": play.description,
            "play_type": play.play_type,
            "team_abbreviation": team_abbrev,
            "player_name": play.player_name,
            "home_score": last_valid_home_score,
            "away_score": last_valid_away_score,
            "synthetic_timestamp": synthetic_ts.isoformat(),
            "game_progress": round(progress, 3),
        }
        events.append(event_payload)

    return events, score_violations


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

    # Get league code for sport-specific handling
    league_code = game.league.code if game.league else "NBA"
    output.add_log(f"Game found: {game.away_team.name} @ {game.home_team.name} ({league_code})")

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

    # Compute game timing (league-specific)
    game_start = game.start_time
    is_ncaab = league_code == "NCAAB"
    regulation_periods = 2 if is_ncaab else 4

    if is_ncaab:
        game_end = _ncaab_game_end(game_start, plays)
    else:
        game_end = _nba_game_end(game_start, plays)

    has_overtime = any((play.quarter or 0) > regulation_periods for play in plays)

    output.add_log(f"Game timing: {game_start.isoformat()} to {game_end.isoformat()}")
    if has_overtime:
        output.add_log("Game went to overtime")

    # Build normalized PBP events with score continuity enforcement
    pbp_events, score_violations = _build_pbp_events(
        plays, game_start, game_id, league_code=league_code
    )

    output.add_log(f"Normalized {len(pbp_events)} PBP events")

    # Log score violations if any were detected
    if score_violations:
        output.add_log(
            f"SCORE CONTINUITY: Corrected {len(score_violations)} score violations",
            "warning",
        )
        for violation in score_violations[:5]:  # Log first 5 for visibility
            output.add_log(
                f"  {violation['type']}: period {violation.get('period')}, "
                f"play {violation.get('play_index')}: {violation.get('message', '')}",
                "warning",
            )
        if len(score_violations) > 5:
            output.add_log(
                f"  ... and {len(score_violations) - 5} more violations",
                "warning",
            )

    # Compute phase boundaries for later use (league-specific)
    if is_ncaab:
        phase_boundaries = _compute_ncaab_phase_boundaries(game_start, has_overtime)
    else:
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
                "league_code": league_code,
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

    # Add resolution stats and score violations to output for visibility
    output.data = {
        **normalized_output.to_dict(),
        "resolution_stats": resolution_stats,
        "score_violations": score_violations,
        "score_violations_count": len(score_violations),
    }
    output.add_log("NORMALIZE_PBP completed successfully")

    return output
