"""Helper functions for the NORMALIZE_PBP stage.

Contains game-end calculations, phase boundary computations,
PBP event building, and resolution statistics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from ....db.sports import SportsGamePlay
from ....utils.datetime_utils import parse_clock_to_seconds
from ....services.timeline_types import (
    # NBA Constants
    NBA_REGULATION_REAL_SECONDS,
    NBA_HALFTIME_REAL_SECONDS,
    NBA_QUARTER_REAL_SECONDS,
    NBA_QUARTER_GAME_SECONDS,
    NBA_OT_GAME_SECONDS,
    NBA_OT_REAL_SECONDS,
    # NCAAB Constants
    NCAAB_REGULATION_REAL_SECONDS,
    NCAAB_HALFTIME_REAL_SECONDS,
    NCAAB_HALF_REAL_SECONDS,
    NCAAB_HALF_GAME_SECONDS,
    NCAAB_OT_GAME_SECONDS,
    NCAAB_OT_REAL_SECONDS,
    # NHL Constants
    NHL_REGULATION_REAL_SECONDS,
    NHL_INTERMISSION_REAL_SECONDS,
    NHL_PERIOD_REAL_SECONDS,
    NHL_PERIOD_GAME_SECONDS,
    NHL_OT_GAME_SECONDS,
    NHL_OT_REAL_SECONDS,
    NHL_PLAYOFF_OT_GAME_SECONDS,
    # Social windows
    SOCIAL_PREGAME_WINDOW_SECONDS,
)
from ....services.timeline_phases import (
    # Phase mapping
    nba_phase_for_quarter,
    nba_block_for_quarter,
    ncaab_phase_for_period,
    ncaab_block_for_period,
    nhl_phase_for_period,
    nhl_block_for_period,
    # Period timing
    nba_quarter_start,
    ncaab_period_start,
    nhl_period_start,
)


def nba_game_end(
    game_start: datetime, plays: Sequence[SportsGamePlay]
) -> datetime:
    """Calculate actual game end time based on plays."""
    max_quarter = 4
    for play in plays:
        if play.quarter and play.quarter > max_quarter:
            max_quarter = play.quarter

    if max_quarter <= 4:
        return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)

    ot_count = max_quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_count * 15 * 60
    )


def ncaab_game_end(
    game_start: datetime, plays: Sequence[SportsGamePlay]
) -> datetime:
    """Calculate NCAAB game end time based on plays."""
    max_period = 2
    for play in plays:
        if play.quarter and play.quarter > max_period:
            max_period = play.quarter

    if max_period <= 2:
        return game_start + timedelta(seconds=NCAAB_REGULATION_REAL_SECONDS)

    ot_count = max_period - 2
    return game_start + timedelta(
        seconds=NCAAB_REGULATION_REAL_SECONDS + ot_count * 10 * 60
    )


def nhl_game_end(
    game_start: datetime, plays: Sequence[SportsGamePlay]
) -> datetime:
    """Calculate NHL game end time based on plays."""
    max_period = 3
    for play in plays:
        if play.quarter and play.quarter > max_period:
            max_period = play.quarter

    if max_period <= 3:
        return game_start + timedelta(seconds=NHL_REGULATION_REAL_SECONDS)

    ot_count = max_period - 3
    return game_start + timedelta(
        seconds=NHL_REGULATION_REAL_SECONDS + ot_count * 10 * 60
    )


def compute_phase_boundaries(
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


def compute_ncaab_phase_boundaries(
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


def compute_nhl_phase_boundaries(
    game_start: datetime,
    has_overtime: bool = False,
    has_shootout: bool = False,
) -> dict[str, tuple[datetime, datetime]]:
    """Compute start/end times for each NHL narrative phase.

    NHL has 3 periods with 2 intermissions, plus optional OT and shootout.
    """
    boundaries: dict[str, tuple[datetime, datetime]] = {}

    # Pregame: 2 hours before to game start
    pregame_start = game_start - timedelta(seconds=SOCIAL_PREGAME_WINDOW_SECONDS)
    boundaries["pregame"] = (pregame_start, game_start)

    # P1 (first period)
    p1_start = game_start
    p1_end = game_start + timedelta(seconds=NHL_PERIOD_REAL_SECONDS)
    boundaries["p1"] = (p1_start, p1_end)

    # First intermission
    int1_start = p1_end
    int1_end = int1_start + timedelta(seconds=NHL_INTERMISSION_REAL_SECONDS)
    boundaries["int1"] = (int1_start, int1_end)

    # P2 (second period)
    p2_start = int1_end
    p2_end = p2_start + timedelta(seconds=NHL_PERIOD_REAL_SECONDS)
    boundaries["p2"] = (p2_start, p2_end)

    # Second intermission
    int2_start = p2_end
    int2_end = int2_start + timedelta(seconds=NHL_INTERMISSION_REAL_SECONDS)
    boundaries["int2"] = (int2_start, int2_end)

    # P3 (third period)
    p3_start = int2_end
    p3_end = p3_start + timedelta(seconds=NHL_PERIOD_REAL_SECONDS)
    boundaries["p3"] = (p3_start, p3_end)

    # Overtime (if applicable)
    if has_overtime:
        ot_start = p3_end
        ot_end = ot_start + timedelta(seconds=10 * 60)  # ~10 min real for OT
        boundaries["ot"] = (ot_start, ot_end)
        last_end = ot_end
    else:
        last_end = p3_end

    # Shootout (if applicable)
    if has_shootout:
        so_start = last_end
        so_end = so_start + timedelta(seconds=10 * 60)  # ~10 min for shootout
        boundaries["shootout"] = (so_start, so_end)
        last_end = so_end

    boundaries["postgame"] = (last_end, last_end + timedelta(hours=2))

    return boundaries


def progress_from_index(index: int, total: int) -> float:
    """Calculate progress through the game based on play index."""
    if total <= 1:
        return 0.0
    return index / (total - 1)


def build_pbp_events(
    plays: Sequence[SportsGamePlay],
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
    is_nhl = league_code == "NHL"

    if is_nhl:
        num_regulation_periods = 3
    elif is_ncaab:
        num_regulation_periods = 2
    else:
        num_regulation_periods = 4

    # Track last known valid scores (cumulative, never reset)
    last_valid_home_score = 0
    last_valid_away_score = 0

    for idx, play in enumerate(plays):
        period = play.quarter or 1

        # League-specific phase/block mapping
        if is_nhl:
            phase = nhl_phase_for_period(period)
            block = nhl_block_for_period(period)
        elif is_ncaab:
            phase = ncaab_phase_for_period(period)
            block = ncaab_block_for_period(period)
        else:
            phase = nba_phase_for_quarter(period)
            block = nba_block_for_quarter(period)

        # Determine period-specific timing (regulation vs OT)
        is_overtime = period > num_regulation_periods
        is_shootout = is_nhl and period == 5

        if is_shootout:
            # NHL shootout has no game clock - use play index for ordering
            period_game_seconds = 0
            period_real_seconds = NHL_OT_REAL_SECONDS
        elif is_nhl:
            if is_overtime:
                # NHL regular season OT is 5 min; playoff OT is 20 min
                # Period 4 = OT1 (5 min regular season), periods 6+ = playoff OT (20 min)
                if period == 4:
                    period_game_seconds = NHL_OT_GAME_SECONDS
                    period_real_seconds = NHL_OT_REAL_SECONDS
                else:
                    # Playoff extended OT (20-minute periods)
                    period_game_seconds = NHL_PLAYOFF_OT_GAME_SECONDS
                    period_real_seconds = NHL_PERIOD_REAL_SECONDS
            else:
                period_game_seconds = NHL_PERIOD_GAME_SECONDS
                period_real_seconds = NHL_PERIOD_REAL_SECONDS
        elif is_ncaab:
            if is_overtime:
                period_game_seconds = NCAAB_OT_GAME_SECONDS
                period_real_seconds = NCAAB_OT_REAL_SECONDS
            else:
                period_game_seconds = NCAAB_HALF_GAME_SECONDS
                period_real_seconds = NCAAB_HALF_REAL_SECONDS
        else:
            # NBA
            if is_overtime:
                period_game_seconds = NBA_OT_GAME_SECONDS
                period_real_seconds = NBA_OT_REAL_SECONDS
            else:
                period_game_seconds = NBA_QUARTER_GAME_SECONDS
                period_real_seconds = NBA_QUARTER_REAL_SECONDS

        # Parse game clock
        clock_seconds = parse_clock_to_seconds(play.game_clock)
        if clock_seconds is None or is_shootout:
            # No clock (or shootout) - use play index for ordering
            intra_phase_order = play.play_index
            progress = progress_from_index(play.play_index, total_plays)
        else:
            # Invert clock: period_game_seconds -> 0, 0:00 -> period_game_seconds
            intra_phase_order = period_game_seconds - clock_seconds
            progress = (period - 1 + (1 - clock_seconds / period_game_seconds)) / num_regulation_periods

        # Compute synthetic timestamp
        if is_nhl:
            period_start = nhl_period_start(game_start, period)
        elif is_ncaab:
            period_start = ncaab_period_start(game_start, period)
        else:
            period_start = nba_quarter_start(game_start, period)

        if is_shootout or period_game_seconds == 0:
            # Shootout has no clock - distribute plays evenly across the period
            real_elapsed = period_real_seconds * (play.play_index / max(total_plays, 1))
        else:
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
            "quarter": period,  # Unified key name across sports (stores period number for NHL)
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


def compute_resolution_stats(plays: list) -> dict[str, Any]:
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
