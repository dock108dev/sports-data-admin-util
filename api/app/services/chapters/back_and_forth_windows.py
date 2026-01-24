"""
Back-and-Forth Window Detection: Detect periods of lead volatility.

A back-and-forth window captures periods where the lead changes frequently
or the game is tied multiple times, indicating competitive balance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .beat_types import (
    BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD,
    BACK_AND_FORTH_TIES_THRESHOLD,
)


@dataclass
class BackAndForthWindow:
    """Represents a detected back-and-forth window with lead volatility.

    A BACK_AND_FORTH window captures periods of high lead volatility where
    the lead changes frequently or the game is tied multiple times.
    """

    start_play_index: int  # Index where window starts
    end_play_index: int  # Index where window ends
    lead_change_count: int  # Number of lead changes in window
    tie_count: int  # Number of times score became tied
    start_home_score: int  # Home score at window start
    start_away_score: int  # Away score at window start
    end_home_score: int  # Home score at window end
    end_away_score: int  # Away score at window end

    def is_qualifying(self) -> bool:
        """Check if this window qualifies as a BACK_AND_FORTH beat.

        A window qualifies if:
        - lead_change_count >= 2, OR
        - tie_count >= 3
        """
        return (
            self.lead_change_count >= BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD
            or self.tie_count >= BACK_AND_FORTH_TIES_THRESHOLD
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        return {
            "start_play_index": self.start_play_index,
            "end_play_index": self.end_play_index,
            "lead_change_count": self.lead_change_count,
            "tie_count": self.tie_count,
            "start_score": f"{self.start_home_score}-{self.start_away_score}",
            "end_score": f"{self.end_home_score}-{self.end_away_score}",
            "is_qualifying": self.is_qualifying(),
        }


def detect_back_and_forth_window(
    plays: list[dict[str, Any]],
) -> BackAndForthWindow | None:
    """Detect back-and-forth window within a chapter's plays.

    Tracks lead changes and ties throughout the chapter:
    - Lead change: positive margin -> negative margin or vice versa
    - Tie: margin becomes exactly 0

    Args:
        plays: List of play raw_data dicts from a chapter

    Returns:
        BackAndForthWindow if any lead changes or ties detected, None if empty
    """
    if not plays:
        return None

    lead_change_count = 0
    tie_count = 0

    # Track previous state
    prev_home_score: int | None = None
    prev_away_score: int | None = None
    prev_leader: str | None = None  # "home", "away", or None (tied)

    start_home = 0
    start_away = 0
    end_home = 0
    end_away = 0
    first_score_seen = False

    for i, play in enumerate(plays):
        home_score = play.get("home_score", 0) or 0
        away_score = play.get("away_score", 0) or 0

        # Initialize start scores from first play
        if not first_score_seen:
            start_home = home_score
            start_away = away_score
            first_score_seen = True

        # Update end scores
        end_home = home_score
        end_away = away_score

        # Determine current leader
        if home_score > away_score:
            current_leader = "home"
        elif away_score > home_score:
            current_leader = "away"
        else:
            current_leader = None  # Tied

        # Check for lead change or tie
        if prev_leader is not None:
            # Lead change: leader switched from one team to the other
            if current_leader is not None and prev_leader != current_leader:
                lead_change_count += 1

            # Tie created: was not tied, now tied
            if prev_leader is not None and current_leader is None:
                tie_count += 1

        elif prev_home_score is not None and prev_away_score is not None:
            # Previous was tied, check dynamics
            if current_leader is None and (
                home_score != prev_home_score or away_score != prev_away_score
            ):
                # Still tied but scores changed - count as tie occurrence
                if home_score != prev_home_score or away_score != prev_away_score:
                    tie_count += 1

        prev_home_score = home_score
        prev_away_score = away_score
        prev_leader = current_leader

    if not first_score_seen:
        return None

    return BackAndForthWindow(
        start_play_index=0,
        end_play_index=len(plays) - 1,
        lead_change_count=lead_change_count,
        tie_count=tie_count,
        start_home_score=start_home,
        start_away_score=start_away,
        end_home_score=end_home,
        end_away_score=end_away,
    )


def get_qualifying_back_and_forth_window(
    plays: list[dict[str, Any]],
) -> BackAndForthWindow | None:
    """Get back-and-forth window if it qualifies.

    Args:
        plays: List of play raw_data dicts

    Returns:
        BackAndForthWindow if qualifying (>=2 lead changes OR >=3 ties), None otherwise
    """
    window = detect_back_and_forth_window(plays)
    if window and window.is_qualifying():
        return window
    return None
