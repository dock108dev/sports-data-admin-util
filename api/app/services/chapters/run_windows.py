"""
Run Window Detection: Detect scoring runs within chapters.

A run window captures periods where one team scores unanswered points,
potentially causing momentum shifts through lead changes or margin expansion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .beat_types import RUN_WINDOW_THRESHOLD, RUN_MARGIN_EXPANSION_THRESHOLD


@dataclass
class RunWindow:
    """Represents a detected scoring run window.

    A run window starts when one team scores >= RUN_WINDOW_THRESHOLD unanswered
    points and ends when the opposing team scores or the chapter ends.
    """

    team: str  # "home" or "away"
    start_play_index: int  # Index within chapter where run started
    end_play_index: int  # Index within chapter where run ended
    points_scored: int  # Total points in the run
    start_home_score: int  # Home score when run started
    start_away_score: int  # Away score when run started
    end_home_score: int  # Home score when run ended
    end_away_score: int  # Away score when run ended
    caused_lead_change: bool  # Did this run flip the lead?
    margin_expansion: int  # How much did margin change in running team's favor?

    def is_qualifying(self) -> bool:
        """Check if this run qualifies as a RUN beat.

        A run qualifies if it:
        - Caused a lead change, OR
        - Expanded the margin by >= RUN_MARGIN_EXPANSION_THRESHOLD points
        """
        return (
            self.caused_lead_change
            or self.margin_expansion >= RUN_MARGIN_EXPANSION_THRESHOLD
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        return {
            "team": self.team,
            "start_play_index": self.start_play_index,
            "end_play_index": self.end_play_index,
            "points_scored": self.points_scored,
            "start_score": f"{self.start_home_score}-{self.start_away_score}",
            "end_score": f"{self.end_home_score}-{self.end_away_score}",
            "caused_lead_change": self.caused_lead_change,
            "margin_expansion": self.margin_expansion,
            "is_qualifying": self.is_qualifying(),
        }


def _get_leader(home_score: int, away_score: int) -> str | None:
    """Determine which team is leading.

    Returns:
        "home", "away", or None if tied
    """
    if home_score > away_score:
        return "home"
    elif away_score > home_score:
        return "away"
    return None


def detect_run_windows(plays: list[dict[str, Any]]) -> list[RunWindow]:
    """Detect run windows within a chapter's plays.

    A run window:
    - Starts when a team scores >= RUN_WINDOW_THRESHOLD unanswered points
    - Ends when the opposing team scores OR the chapter ends

    Args:
        plays: List of play raw_data dicts from a chapter

    Returns:
        List of RunWindow objects detected in the plays
    """
    if not plays:
        return []

    run_windows: list[RunWindow] = []

    # Track run state
    current_run_team: str | None = None
    current_run_start_idx: int = 0
    current_run_points: int = 0
    run_start_home_score: int = 0
    run_start_away_score: int = 0
    run_start_leader: str | None = None

    # Track previous scores - initialize to None to detect first scoring play
    prev_home_score: int | None = None
    prev_away_score: int | None = None

    for i, play in enumerate(plays):
        description = (play.get("description") or "").lower()

        # Skip non-scoring plays
        if "makes" not in description:
            continue

        # Get current scores
        home_score = play.get("home_score", 0) or 0
        away_score = play.get("away_score", 0) or 0

        # Initialize prev scores on first scoring play
        if prev_home_score is None or prev_away_score is None:
            # Heuristic: if total score is low, assume game start (0-0 baseline)
            # If score is high, this is a mid-game chapter - use current as baseline
            total_score = home_score + away_score
            if total_score <= RUN_WINDOW_THRESHOLD:
                # Likely start of game, assume 0-0 baseline
                prev_home_score = 0
                prev_away_score = 0
            else:
                # Mid-game chapter, can't determine delta for first play
                prev_home_score = home_score
                prev_away_score = away_score
                continue

        # Calculate deltas from previous play within this chapter
        home_delta = home_score - prev_home_score
        away_delta = away_score - prev_away_score

        # Determine which team scored
        scoring_team: str | None = None
        points_scored: int = 0

        if home_delta > 0 and away_delta == 0:
            scoring_team = "home"
            points_scored = home_delta
        elif away_delta > 0 and home_delta == 0:
            scoring_team = "away"
            points_scored = away_delta
        elif home_delta > 0 and away_delta > 0:
            # Both changed (unusual) - ends any run
            if current_run_team and current_run_points >= RUN_WINDOW_THRESHOLD:
                run_windows.append(
                    _finalize_run_window(
                        team=current_run_team,
                        start_idx=current_run_start_idx,
                        end_idx=i - 1,
                        points=current_run_points,
                        start_home=run_start_home_score,
                        start_away=run_start_away_score,
                        end_home=prev_home_score,
                        end_away=prev_away_score,
                        start_leader=run_start_leader,
                    )
                )
            current_run_team = None
            current_run_points = 0
            prev_home_score = home_score
            prev_away_score = away_score
            continue

        if scoring_team:
            if current_run_team == scoring_team:
                # Same team scoring - extend the run
                current_run_points += points_scored
            else:
                # Different team scored
                if current_run_team and current_run_points >= RUN_WINDOW_THRESHOLD:
                    # Finalize previous run window
                    run_windows.append(
                        _finalize_run_window(
                            team=current_run_team,
                            start_idx=current_run_start_idx,
                            end_idx=i - 1,
                            points=current_run_points,
                            start_home=run_start_home_score,
                            start_away=run_start_away_score,
                            end_home=prev_home_score,
                            end_away=prev_away_score,
                            start_leader=run_start_leader,
                        )
                    )

                # Start new potential run
                current_run_team = scoring_team
                current_run_start_idx = i
                current_run_points = points_scored
                run_start_home_score = prev_home_score
                run_start_away_score = prev_away_score
                run_start_leader = _get_leader(prev_home_score, prev_away_score)

        # Update previous scores
        prev_home_score = home_score
        prev_away_score = away_score

    # Check for run at chapter end
    if current_run_team and current_run_points >= RUN_WINDOW_THRESHOLD:
        run_windows.append(
            _finalize_run_window(
                team=current_run_team,
                start_idx=current_run_start_idx,
                end_idx=len(plays) - 1,
                points=current_run_points,
                start_home=run_start_home_score,
                start_away=run_start_away_score,
                end_home=prev_home_score,
                end_away=prev_away_score,
                start_leader=run_start_leader,
            )
        )

    return run_windows


def _finalize_run_window(
    team: str,
    start_idx: int,
    end_idx: int,
    points: int,
    start_home: int,
    start_away: int,
    end_home: int,
    end_away: int,
    start_leader: str | None,
) -> RunWindow:
    """Create a finalized RunWindow with lead change and margin calculations."""
    end_leader = _get_leader(end_home, end_away)

    # Lead change: leader switched to the running team
    caused_lead_change = start_leader != team and end_leader == team

    # Margin expansion: how much did margin increase in favor of running team?
    if team == "home":
        start_margin = start_home - start_away
        end_margin = end_home - end_away
    else:
        start_margin = start_away - start_home
        end_margin = end_away - end_home

    margin_expansion = end_margin - start_margin

    return RunWindow(
        team=team,
        start_play_index=start_idx,
        end_play_index=end_idx,
        points_scored=points,
        start_home_score=start_home,
        start_away_score=start_away,
        end_home_score=end_home,
        end_away_score=end_away,
        caused_lead_change=caused_lead_change,
        margin_expansion=margin_expansion,
    )


def get_qualifying_run_windows(plays: list[dict[str, Any]]) -> list[RunWindow]:
    """Get only the run windows that qualify as a RUN beat.

    Args:
        plays: List of play raw_data dicts

    Returns:
        List of RunWindow objects that caused lead change or margin expansion >=8
    """
    all_windows = detect_run_windows(plays)
    return [w for w in all_windows if w.is_qualifying()]
