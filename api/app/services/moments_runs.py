"""
Run Detection for Moments.

Detects scoring runs in game timelines. Runs are sequences of unanswered scoring
by one team. They do NOT create moment boundaries - they become metadata attached
to moments.

Key principle: Runs are detected independently and then matched to moments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

# Minimum points for a run to be considered significant
# This is sport-agnostic - the caller should provide appropriate threshold
DEFAULT_RUN_THRESHOLD = 6


@dataclass
class DetectedRun:
    """
    A detected scoring run (before assignment to a moment).

    Runs are sequences of unanswered scoring by one team.
    They do NOT create moment boundaries by themselves.
    """
    team: str  # "home" or "away"
    points: int
    start_idx: int  # Timeline index where run started
    end_idx: int    # Timeline index where run ended
    play_ids: list[int] = field(default_factory=list)  # All scoring play indices


@dataclass
class RunInfo:
    """
    Run information attached to a Moment.

    This is the final form of run metadata after assignment to a moment.
    """
    team: str
    points: int
    unanswered: bool
    play_ids: list[int] = field(default_factory=list)
    start_idx: int | None = None
    end_idx: int | None = None


def detect_runs(
    events: Sequence[dict[str, Any]],
    min_points: int = DEFAULT_RUN_THRESHOLD,
) -> list[DetectedRun]:
    """
    Detect scoring runs in the timeline.

    A run is a sequence of unanswered scoring by one team.
    Runs are detected but do NOT create moment boundaries.
    They become metadata attached to the owning moment.

    Args:
        events: Timeline events
        min_points: Minimum points to qualify as a run

    Returns:
        List of detected runs (not yet assigned to moments)
    """
    runs: list[DetectedRun] = []

    # Track current run state
    current_run_team: str | None = None
    current_run_points = 0
    current_run_start = 0
    current_run_plays: list[int] = []

    prev_home = 0
    prev_away = 0

    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue

        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0

        # Calculate score deltas
        home_delta = home_score - prev_home
        away_delta = away_score - prev_away

        # Determine which team scored
        if home_delta > 0 and away_delta == 0:
            scoring_team = "home"
            points_scored = home_delta
        elif away_delta > 0 and home_delta == 0:
            scoring_team = "away"
            points_scored = away_delta
        elif home_delta > 0 or away_delta > 0:
            # Both teams scored - end any current run
            if current_run_points >= min_points:
                runs.append(DetectedRun(
                    team=current_run_team or "home",
                    points=current_run_points,
                    start_idx=current_run_start,
                    end_idx=i - 1,
                    play_ids=current_run_plays.copy(),
                ))
            current_run_team = None
            current_run_points = 0
            current_run_plays = []
            prev_home = home_score
            prev_away = away_score
            continue
        else:
            # No scoring - continue current run
            prev_home = home_score
            prev_away = away_score
            continue

        # Handle scoring by one team
        if scoring_team == current_run_team:
            # Extend current run
            current_run_points += points_scored
            current_run_plays.append(i)
        else:
            # New team scored - close previous run if significant
            if current_run_points >= min_points:
                runs.append(DetectedRun(
                    team=current_run_team or "home",
                    points=current_run_points,
                    start_idx=current_run_start,
                    end_idx=i - 1,
                    play_ids=current_run_plays.copy(),
                ))
            # Start new run
            current_run_team = scoring_team
            current_run_points = points_scored
            current_run_start = i
            current_run_plays = [i]

        prev_home = home_score
        prev_away = away_score

    # Close any open run
    if current_run_points >= min_points and current_run_plays:
        runs.append(DetectedRun(
            team=current_run_team or "home",
            points=current_run_points,
            start_idx=current_run_start,
            end_idx=current_run_plays[-1],
            play_ids=current_run_plays.copy(),
        ))

    return runs


def find_run_for_moment(
    runs: list[DetectedRun],
    moment_start: int,
    moment_end: int,
) -> DetectedRun | None:
    """
    Find the best run that contributed to a moment.

    A run "contributed" to a moment if:
    - The run overlaps with the moment's play range
    - The run ended at or before the moment boundary

    Returns the largest run that fits, or None.
    """
    best_run: DetectedRun | None = None
    best_points = 0

    for run in runs:
        # Check if run overlaps with moment
        if run.end_idx < moment_start or run.start_idx > moment_end:
            continue

        # This run contributed to the moment - take the largest
        if run.points > best_points:
            best_run = run
            best_points = run.points

    return best_run


def run_to_info(run: DetectedRun) -> RunInfo:
    """Convert a DetectedRun to RunInfo for attachment to a Moment."""
    return RunInfo(
        team=run.team,
        points=run.points,
        unanswered=True,  # By definition, runs are unanswered
        play_ids=run.play_ids.copy(),
        start_idx=run.start_idx,
        end_idx=run.end_idx,
    )
