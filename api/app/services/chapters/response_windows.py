"""
Response Window Detection: Detect response sequences following scoring runs.

A response window captures the trailing team's counter-scoring after a RUN,
indicating competitive resilience.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .run_windows import RunWindow


@dataclass
class ResponseWindow:
    """Represents a detected RESPONSE window following a RUN.

    A RESPONSE window begins immediately after a qualifying RUN window ends
    and captures the trailing team's counter-scoring.
    """

    responding_team: str  # "home" or "away" - team that was trailing
    run_team: str  # "home" or "away" - team that had the RUN
    start_play_index: int  # Index where response starts (after RUN ends)
    end_play_index: int  # Index where response ends
    responding_team_points: int  # Points scored by responding team
    run_team_points: int  # Points scored by team that had the RUN
    run_end_home_score: int  # Home score when RUN ended
    run_end_away_score: int  # Away score when RUN ended
    response_end_home_score: int  # Home score when response ends
    response_end_away_score: int  # Away score when response ends

    def is_qualifying(self) -> bool:
        """Check if this response qualifies as a RESPONSE beat.

        A RESPONSE qualifies if the trailing team outscores the leading team
        in the response window. No requirement for lead change or both teams
        to score.
        """
        return self.responding_team_points > self.run_team_points

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        return {
            "responding_team": self.responding_team,
            "run_team": self.run_team,
            "start_play_index": self.start_play_index,
            "end_play_index": self.end_play_index,
            "responding_team_points": self.responding_team_points,
            "run_team_points": self.run_team_points,
            "run_end_score": f"{self.run_end_home_score}-{self.run_end_away_score}",
            "response_end_score": f"{self.response_end_home_score}-{self.response_end_away_score}",
            "is_qualifying": self.is_qualifying(),
        }


def detect_response_windows(
    plays: list[dict[str, Any]],
    qualifying_runs: list[RunWindow],
) -> list[ResponseWindow]:
    """Detect RESPONSE windows following qualifying RUN windows.

    A RESPONSE window:
    - Begins immediately after a qualifying RUN window ends
    - Continues until the end of the plays list (chapter end)

    Args:
        plays: List of play raw_data dicts from a chapter
        qualifying_runs: List of qualifying RunWindow objects in this chapter

    Returns:
        List of ResponseWindow objects detected after RUN windows
    """
    if not plays or not qualifying_runs:
        return []

    response_windows: list[ResponseWindow] = []

    for run in qualifying_runs:
        # Response starts after the RUN ends
        response_start_idx = run.end_play_index + 1

        # If RUN ended at last play, no response window possible
        if response_start_idx >= len(plays):
            continue

        # The responding team is the one that was NOT running
        responding_team = "away" if run.team == "home" else "home"

        # Track scoring in the response window
        responding_points = 0
        run_team_points = 0

        # Track scores
        prev_home = run.end_home_score
        prev_away = run.end_away_score
        end_home = run.end_home_score
        end_away = run.end_away_score
        end_idx = response_start_idx

        for i in range(response_start_idx, len(plays)):
            play = plays[i]
            description = (play.get("description") or "").lower()

            # Skip non-scoring plays
            if "makes" not in description:
                continue

            home_score = play.get("home_score", 0) or 0
            away_score = play.get("away_score", 0) or 0

            home_delta = home_score - prev_home
            away_delta = away_score - prev_away

            # Update running totals
            if responding_team == "home":
                responding_points += home_delta
                run_team_points += away_delta
            else:
                responding_points += away_delta
                run_team_points += home_delta

            prev_home = home_score
            prev_away = away_score
            end_home = home_score
            end_away = away_score
            end_idx = i

        # Create response window if there was any activity
        if responding_points > 0 or run_team_points > 0:
            response_windows.append(
                ResponseWindow(
                    responding_team=responding_team,
                    run_team=run.team,
                    start_play_index=response_start_idx,
                    end_play_index=end_idx,
                    responding_team_points=responding_points,
                    run_team_points=run_team_points,
                    run_end_home_score=run.end_home_score,
                    run_end_away_score=run.end_away_score,
                    response_end_home_score=end_home,
                    response_end_away_score=end_away,
                )
            )

    return response_windows


def get_qualifying_response_windows(
    plays: list[dict[str, Any]],
    qualifying_runs: list[RunWindow],
) -> list[ResponseWindow]:
    """Get only the response windows that qualify as a RESPONSE beat.

    Args:
        plays: List of play raw_data dicts
        qualifying_runs: List of qualifying RunWindow objects

    Returns:
        List of ResponseWindow objects where trailing team outscored leading team
    """
    all_responses = detect_response_windows(plays, qualifying_runs)
    return [r for r in all_responses if r.is_qualifying()]
