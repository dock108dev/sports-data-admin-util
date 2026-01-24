"""
Beat Classifier: Deterministic beat type assignment for chapters.

This module assigns EXACTLY ONE beat_type to EACH chapter based on:
- score delta
- time remaining
- basic stat deltas

DESIGN PRINCIPLES:
- Deterministic: Same input → same beats every run
- Conservative: When in doubt, use BACK_AND_FORTH
- Explainable: Each rule is documented inline
- Stable: No ML, no tuning, no historical inference beyond previous chapter

This layer exists only to help form story structure later.
It does NOT generate narrative.

LOCKED BEAT TAXONOMY (NBA v1):
- FAST_START
- MISSED_SHOT_FEST
- BACK_AND_FORTH
- EARLY_CONTROL
- RUN
- RESPONSE
- STALL
- CRUNCH_SETUP
- CLOSING_SEQUENCE
- OVERTIME

No new beats. No renaming. No synonyms. No compound beats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .types import Chapter
from .running_stats import SectionDelta


# ============================================================================
# LOCKED BEAT TAXONOMY (NBA v1)
# ============================================================================


class BeatType(str, Enum):
    """Locked beat types for NBA v1.

    These are the ONLY valid beat types. No additions, renaming, or synonyms.

    Note: MISSED_SHOT_FEST is retained in enum for backward compatibility
    but is no longer used as a primary beat (Phase 2.1).
    """

    FAST_START = "FAST_START"
    MISSED_SHOT_FEST = "MISSED_SHOT_FEST"  # Deprecated as primary beat (Phase 2.1)
    BACK_AND_FORTH = "BACK_AND_FORTH"
    EARLY_CONTROL = "EARLY_CONTROL"
    RUN = "RUN"
    RESPONSE = "RESPONSE"
    STALL = "STALL"
    CRUNCH_SETUP = "CRUNCH_SETUP"
    CLOSING_SEQUENCE = "CLOSING_SEQUENCE"
    OVERTIME = "OVERTIME"


class BeatDescriptor(str, Enum):
    """Secondary descriptors that may coexist with any primary beat.

    Descriptors:
    - Do NOT replace primary beats
    - May coexist with any primary beat
    - Are optional (0–N per chapter or section)

    Phase 2.1: MISSED_SHOT_CONTEXT replaces MISSED_SHOT_FEST as primary beat.
    """

    MISSED_SHOT_CONTEXT = "MISSED_SHOT_CONTEXT"


# ============================================================================
# PRIMARY BEATS AND PRIORITY ORDER (Phase 2.1)
# ============================================================================

# Primary beats that can be assigned as the main beat_type
# MISSED_SHOT_FEST is excluded - it's now a descriptor only
PRIMARY_BEATS: set[BeatType] = {
    BeatType.FAST_START,
    BeatType.EARLY_CONTROL,
    BeatType.RUN,
    BeatType.RESPONSE,
    BeatType.BACK_AND_FORTH,
    BeatType.STALL,
    BeatType.CRUNCH_SETUP,
    BeatType.CLOSING_SEQUENCE,
    BeatType.OVERTIME,
}

# Priority order for section beat selection (highest priority first)
# Used when multiple chapters in a section have different beats
BEAT_PRIORITY: list[BeatType] = [
    BeatType.OVERTIME,  # 1. Highest priority
    BeatType.CLOSING_SEQUENCE,  # 2.
    BeatType.CRUNCH_SETUP,  # 3.
    BeatType.RUN,  # 4.
    BeatType.RESPONSE,  # 5.
    BeatType.BACK_AND_FORTH,  # 6.
    BeatType.EARLY_CONTROL,  # 7.
    BeatType.FAST_START,  # 8.
    BeatType.STALL,  # 9. Lowest priority (default)
]

# Threshold for MISSED_SHOT_CONTEXT descriptor (points per play)
MISSED_SHOT_PPP_THRESHOLD = 0.35

# Run detection thresholds
RUN_WINDOW_THRESHOLD = 6  # Minimum unanswered points to start a run window
RUN_MARGIN_EXPANSION_THRESHOLD = (
    8  # Margin increase required to qualify without lead change
)

# Back-and-forth detection thresholds (Phase 2.4)
BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD = 2  # Minimum lead changes to qualify
BACK_AND_FORTH_TIES_THRESHOLD = 3  # Minimum ties to qualify

# Early window detection thresholds (Phase 2.5 - Section-level beats)
EARLY_WINDOW_DURATION_SECONDS = 360  # First 6:00 of Q1 (time > 6:00 remaining)
FAST_START_MIN_COMBINED_POINTS = 30  # Combined points >= 30 for FAST_START
FAST_START_MAX_MARGIN = 6  # Margin <= 6 for FAST_START
EARLY_CONTROL_MIN_LEAD = 8  # Lead >= 8 for EARLY_CONTROL
EARLY_CONTROL_MIN_SHARE_PCT = 0.65  # Leading team scores >= 65% of total

# Late-game beat thresholds (Phase 2.6)
CRUNCH_SETUP_TIME_THRESHOLD = 300  # ≤ 5:00 remaining in Q4
CRUNCH_SETUP_MARGIN_THRESHOLD = 10  # Margin ≤ 10 for CRUNCH_SETUP
CLOSING_SEQUENCE_TIME_THRESHOLD = 120  # ≤ 2:00 remaining in Q4
CLOSING_SEQUENCE_MARGIN_THRESHOLD = 8  # Margin ≤ 8 for CLOSING_SEQUENCE


# ============================================================================
# RUN WINDOW DETECTION
# ============================================================================


@dataclass
class RunWindow:
    """Represents a detected scoring run window.

    A run window starts when one team scores ≥ RUN_WINDOW_THRESHOLD unanswered
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
        - Expanded the margin by ≥ RUN_MARGIN_EXPANSION_THRESHOLD points
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
    - Starts when a team scores ≥ RUN_WINDOW_THRESHOLD unanswered points
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

        # Initialize prev scores on first scoring play if not set
        if prev_home_score is None or prev_away_score is None:
            # First scoring play - calculate from implicit 0-0 start
            # or use the score before this play if available
            prev_home_score = 0
            prev_away_score = 0

        # Calculate deltas
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
                # Finalize current run window
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
    # Positive if running team increased their advantage
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
        List of RunWindow objects that caused lead change or margin expansion ≥8
    """
    all_windows = detect_run_windows(plays)
    return [w for w in all_windows if w.is_qualifying()]


# ============================================================================
# RESPONSE WINDOW DETECTION
# ============================================================================


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

        # The responding team is the one that was NOT running (opposite of run team)
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


# ============================================================================
# BACK_AND_FORTH WINDOW DETECTION (Phase 2.4)
# ============================================================================


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
    - Lead change: positive margin → negative margin or vice versa
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
            # Previous was tied, check if still dynamics
            if current_leader is not None:
                # Went from tied to having a leader - not a lead change
                pass
            elif current_leader is None and (
                home_score != prev_home_score or away_score != prev_away_score
            ):
                # Still tied but scores changed - count as tie occurrence
                # Only count if scores actually changed
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
        BackAndForthWindow if qualifying (≥2 lead changes OR ≥3 ties), None otherwise
    """
    window = detect_back_and_forth_window(plays)
    if window and window.is_qualifying():
        return window
    return None


# ============================================================================
# EARLY WINDOW DETECTION (Phase 2.5 - Section-level beats)
# ============================================================================


@dataclass
class EarlyWindowStats:
    """Statistics from the early-game window (first 6:00 of Q1).

    Used for section-level FAST_START and EARLY_CONTROL detection.
    These beats are not assigned at the chapter level.
    """

    home_points: int  # Points scored by home team in window
    away_points: int  # Points scored by away team in window
    total_points: int  # Combined points in window
    final_home_score: int  # Score at end of window
    final_away_score: int  # Score at end of window
    final_margin: int  # Absolute margin at end of window
    window_end_seconds: int  # Time remaining when window ends (should be >= 360)
    chapter_ids_in_window: list[str]  # Chapters included in window

    @property
    def leading_team(self) -> str | None:
        """Which team is leading at end of window."""
        if self.final_home_score > self.final_away_score:
            return "home"
        elif self.final_away_score > self.final_home_score:
            return "away"
        return None

    @property
    def leading_team_points(self) -> int:
        """Points scored by the leading team in window."""
        if self.final_home_score > self.final_away_score:
            return self.home_points
        elif self.final_away_score > self.final_home_score:
            return self.away_points
        return 0

    @property
    def leading_team_share(self) -> float:
        """Percentage of total points scored by leading team."""
        if self.total_points == 0:
            return 0.0
        return self.leading_team_points / self.total_points

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        return {
            "home_points": self.home_points,
            "away_points": self.away_points,
            "total_points": self.total_points,
            "final_score": f"{self.final_home_score}-{self.final_away_score}",
            "final_margin": self.final_margin,
            "leading_team": self.leading_team,
            "leading_team_share": round(self.leading_team_share, 3),
            "window_end_seconds": self.window_end_seconds,
            "chapter_ids_in_window": self.chapter_ids_in_window,
        }


def compute_early_window_stats(
    chapters: list["Chapter"],
) -> EarlyWindowStats | None:
    """Compute statistics from the early-game window.

    The early window is the first 6:00 of Q1 (plays with time_remaining > 360s).

    Args:
        chapters: List of chapters in chronological order

    Returns:
        EarlyWindowStats if any Q1 early plays exist, None otherwise
    """

    home_points = 0
    away_points = 0
    final_home_score = 0
    final_away_score = 0
    window_end_seconds = 720  # Start of Q1
    chapter_ids: list[str] = []

    found_early_plays = False

    for chapter in chapters:
        # Only look at Q1
        period = chapter.period
        if period is None and chapter.plays:
            period = chapter.plays[0].raw_data.get("quarter")

        if period != 1:
            continue

        # Check each play in the chapter
        for play in chapter.plays:
            # Get time remaining
            clock_str = play.raw_data.get("game_clock")
            time_remaining = None
            if clock_str and ":" in clock_str:
                try:
                    parts = clock_str.split(":")
                    time_remaining = int(parts[0]) * 60 + int(parts[1])
                except (ValueError, IndexError):
                    pass

            if time_remaining is None:
                continue

            # Only include plays in early window (time > 6:00)
            if time_remaining <= EARLY_WINDOW_DURATION_SECONDS:
                continue

            found_early_plays = True

            # Track scores
            home_score = play.raw_data.get("home_score", 0) or 0
            away_score = play.raw_data.get("away_score", 0) or 0

            # Update final scores (latest play in window)
            if time_remaining < window_end_seconds:
                window_end_seconds = time_remaining

            final_home_score = home_score
            final_away_score = away_score

        # Track chapter inclusion
        if chapter.chapter_id not in chapter_ids and found_early_plays:
            # Check if this chapter has any plays in the early window
            for play in chapter.plays:
                clock_str = play.raw_data.get("game_clock")
                if clock_str and ":" in clock_str:
                    try:
                        parts = clock_str.split(":")
                        time_remaining = int(parts[0]) * 60 + int(parts[1])
                        if time_remaining > EARLY_WINDOW_DURATION_SECONDS:
                            chapter_ids.append(chapter.chapter_id)
                            break
                    except (ValueError, IndexError):
                        pass

    if not found_early_plays:
        return None

    # Calculate points scored in window (from score difference)
    # This is a simplification - we use final scores from the window
    home_points = final_home_score
    away_points = final_away_score
    total_points = home_points + away_points
    final_margin = abs(final_home_score - final_away_score)

    return EarlyWindowStats(
        home_points=home_points,
        away_points=away_points,
        total_points=total_points,
        final_home_score=final_home_score,
        final_away_score=final_away_score,
        final_margin=final_margin,
        window_end_seconds=window_end_seconds,
        chapter_ids_in_window=chapter_ids,
    )


@dataclass
class SectionBeatOverride:
    """Result of section-level beat detection.

    Used to override opening section beat with FAST_START or EARLY_CONTROL.
    """

    beat_type: BeatType
    triggered_rule: str
    debug_info: dict[str, Any]


def detect_section_fast_start(
    early_stats: EarlyWindowStats,
) -> SectionBeatOverride | None:
    """Detect FAST_START at section level.

    FAST_START is detected when:
    - Combined points >= 30 in early window
    - Absolute score margin <= 6

    Args:
        early_stats: Statistics from early window

    Returns:
        SectionBeatOverride if FAST_START detected, None otherwise
    """
    # Check combined points threshold
    if early_stats.total_points < FAST_START_MIN_COMBINED_POINTS:
        return None

    # Check margin threshold
    if early_stats.final_margin > FAST_START_MAX_MARGIN:
        return None

    return SectionBeatOverride(
        beat_type=BeatType.FAST_START,
        triggered_rule="SECTION_FAST_START",
        debug_info={
            "total_points": early_stats.total_points,
            "final_margin": early_stats.final_margin,
            "min_points_threshold": FAST_START_MIN_COMBINED_POINTS,
            "max_margin_threshold": FAST_START_MAX_MARGIN,
            "final_score": f"{early_stats.final_home_score}-{early_stats.final_away_score}",
        },
    )


def detect_section_early_control(
    early_stats: EarlyWindowStats,
) -> SectionBeatOverride | None:
    """Detect EARLY_CONTROL at section level.

    EARLY_CONTROL is detected when:
    - One team leads by >= 8 points
    - That team scores >= 65% of total points in window

    Args:
        early_stats: Statistics from early window

    Returns:
        SectionBeatOverride if EARLY_CONTROL detected, None otherwise
    """
    # Must have a clear leader
    if early_stats.leading_team is None:
        return None

    # Check lead threshold
    if early_stats.final_margin < EARLY_CONTROL_MIN_LEAD:
        return None

    # Check scoring share threshold
    if early_stats.leading_team_share < EARLY_CONTROL_MIN_SHARE_PCT:
        return None

    return SectionBeatOverride(
        beat_type=BeatType.EARLY_CONTROL,
        triggered_rule="SECTION_EARLY_CONTROL",
        debug_info={
            "leading_team": early_stats.leading_team,
            "final_margin": early_stats.final_margin,
            "leading_team_points": early_stats.leading_team_points,
            "total_points": early_stats.total_points,
            "leading_team_share": round(early_stats.leading_team_share, 3),
            "min_lead_threshold": EARLY_CONTROL_MIN_LEAD,
            "min_share_threshold": EARLY_CONTROL_MIN_SHARE_PCT,
            "final_score": f"{early_stats.final_home_score}-{early_stats.final_away_score}",
        },
    )


def detect_opening_section_beat(
    chapters: list["Chapter"],
) -> SectionBeatOverride | None:
    """Detect section-level beat for opening section.

    Checks for EARLY_CONTROL first (takes precedence), then FAST_START.
    These beats are mutually exclusive - exactly one may be assigned.

    Args:
        chapters: List of chapters in chronological order

    Returns:
        SectionBeatOverride if EARLY_CONTROL or FAST_START detected, None otherwise
    """
    # Compute early window stats
    early_stats = compute_early_window_stats(chapters)
    if early_stats is None:
        return None

    # EARLY_CONTROL takes precedence
    early_control = detect_section_early_control(early_stats)
    if early_control is not None:
        return early_control

    # Then check FAST_START
    fast_start = detect_section_fast_start(early_stats)
    if fast_start is not None:
        return fast_start

    return None


# ============================================================================
# CHAPTER CONTEXT (INPUT)
# ============================================================================


@dataclass
class ChapterContext:
    """Context needed for beat classification.

    All the information about a chapter needed to assign a beat type.
    This is computed from chapter data + running stats.
    """

    # Chapter identity
    chapter_id: str
    chapter_index: int  # 0-indexed position in game

    # Time context
    period: int | None  # 1-4 for regulation, 5+ for OT
    time_remaining_seconds: int | None  # Seconds remaining in period
    is_overtime: bool  # True if period > 4

    # Score context
    home_score: int
    away_score: int
    score_margin: int  # abs(home_score - away_score)

    # Section stats (from SectionDelta)
    home_points_scored: int
    away_points_scored: int
    total_points_scored: int

    # Possession/play metrics
    total_plays: int
    possessions_estimate: int

    # Shot/rebound metrics (for descriptor detection)
    total_fg_made: int
    total_fg_attempts: int | None  # May not be available
    total_rebounds: int | None  # May not be available

    # Run window detection (Phase 2.2)
    qualifying_run_windows: list[RunWindow] = field(default_factory=list)
    has_qualifying_run: bool = False  # Convenience flag

    # Response window detection (Phase 2.3)
    qualifying_response_windows: list[ResponseWindow] = field(default_factory=list)
    has_qualifying_response: bool = False  # Convenience flag

    # Back-and-forth window detection (Phase 2.4)
    back_and_forth_window: BackAndForthWindow | None = None
    has_qualifying_back_and_forth: bool = False  # Convenience flag

    # Previous chapter info (for cross-chapter RESPONSE detection)
    previous_beat_type: BeatType | None = None
    previous_scoring_team: str | None = None  # "home" or "away"
    previous_run_windows: list[RunWindow] = field(default_factory=list)  # Phase 2.3

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        result = {
            "chapter_id": self.chapter_id,
            "chapter_index": self.chapter_index,
            "period": self.period,
            "time_remaining_seconds": self.time_remaining_seconds,
            "is_overtime": self.is_overtime,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "score_margin": self.score_margin,
            "home_points_scored": self.home_points_scored,
            "away_points_scored": self.away_points_scored,
            "total_points_scored": self.total_points_scored,
            "total_plays": self.total_plays,
            "possessions_estimate": self.possessions_estimate,
            "total_fg_made": self.total_fg_made,
            "has_qualifying_run": self.has_qualifying_run,
            "has_qualifying_response": self.has_qualifying_response,
            "has_qualifying_back_and_forth": self.has_qualifying_back_and_forth,
            "previous_beat_type": self.previous_beat_type.value
            if self.previous_beat_type
            else None,
        }
        # Include qualifying run windows if present
        if self.qualifying_run_windows:
            result["qualifying_run_windows"] = [
                w.to_dict() for w in self.qualifying_run_windows
            ]
        # Include qualifying response windows if present
        if self.qualifying_response_windows:
            result["qualifying_response_windows"] = [
                r.to_dict() for r in self.qualifying_response_windows
            ]
        # Include back-and-forth window if present
        if self.back_and_forth_window:
            result["back_and_forth_window"] = self.back_and_forth_window.to_dict()
        return result


# ============================================================================
# CLASSIFICATION RESULT (OUTPUT)
# ============================================================================


@dataclass
class BeatClassification:
    """Result of beat classification for a single chapter.

    Contains:
    - The assigned beat type (primary beat)
    - Descriptors (secondary context, may be empty)
    - The rule that triggered assignment
    - Debug information

    Phase 2.1: Added descriptors field for MISSED_SHOT_CONTEXT, etc.
    """

    chapter_id: str
    beat_type: BeatType
    triggered_rule: str  # Human-readable rule name
    debug_info: dict[str, Any]  # Context used for decision
    descriptors: set[BeatDescriptor] = field(
        default_factory=set
    )  # Phase 2.1: Secondary descriptors

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API/debugging."""
        result = {
            "chapter_id": self.chapter_id,
            "beat_type": self.beat_type.value,
            "triggered_rule": self.triggered_rule,
            "debug_info": self.debug_info,
        }
        # Include descriptors if present
        if self.descriptors:
            result["descriptors"] = [d.value for d in self.descriptors]
        return result


# ============================================================================
# HELPER: TIME PARSING
# ============================================================================


def parse_game_clock_to_seconds(clock_str: str | None) -> int | None:
    """Parse game clock string to seconds remaining.

    Args:
        clock_str: Clock string like "12:00", "5:30", "0:45"

    Returns:
        Seconds remaining, or None if unparseable
    """
    if not clock_str:
        return None

    try:
        if ":" in clock_str:
            parts = clock_str.split(":")
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
    except (ValueError, IndexError):
        pass

    return None


# ============================================================================
# CONTEXT BUILDER
# ============================================================================


def build_chapter_context(
    chapter: Chapter,
    chapter_index: int,
    section_delta: SectionDelta | None,
    previous_result: BeatClassification | None,
    home_team_key: str | None = None,
    away_team_key: str | None = None,
    previous_context: ChapterContext
    | None = None,  # Phase 2.3: for cross-chapter RESPONSE
) -> ChapterContext:
    """Build classification context from chapter and stats.

    Args:
        chapter: The chapter to classify
        chapter_index: 0-indexed position in game
        section_delta: Stats for this chapter (from running_stats)
        previous_result: Classification result of previous chapter
        home_team_key: Home team key for team identification
        away_team_key: Away team key for team identification
        previous_context: Previous chapter's context (for cross-chapter RESPONSE)

    Returns:
        ChapterContext ready for classification
    """
    # Extract period from chapter or plays
    period = chapter.period
    if period is None and chapter.plays:
        period = chapter.plays[0].raw_data.get("quarter")

    # Determine if overtime
    is_overtime = period is not None and period > 4

    # Extract time remaining from last play
    time_remaining_seconds = None
    if chapter.plays:
        last_play = chapter.plays[-1]
        clock_str = last_play.raw_data.get("game_clock")
        time_remaining_seconds = parse_game_clock_to_seconds(clock_str)

    # Extract scores from last play
    home_score = 0
    away_score = 0
    if chapter.plays:
        last_play = chapter.plays[-1]
        home_score = last_play.raw_data.get("home_score", 0) or 0
        away_score = last_play.raw_data.get("away_score", 0) or 0

    score_margin = abs(home_score - away_score)

    # Extract stats from section delta
    home_points_scored = 0
    away_points_scored = 0
    possessions_estimate = 0
    total_fg_made = 0

    if section_delta:
        # Get team stats
        for team_key, team_delta in section_delta.teams.items():
            if team_key == home_team_key:
                home_points_scored = team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate
            elif team_key == away_team_key:
                away_points_scored = team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate
            else:
                # Unknown team - add to whichever has less
                if home_points_scored <= away_points_scored:
                    home_points_scored += team_delta.points_scored
                else:
                    away_points_scored += team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate

        # Get player FG stats
        for player_delta in section_delta.players.values():
            total_fg_made += player_delta.fg_made

    total_points_scored = home_points_scored + away_points_scored
    total_plays = len(chapter.plays)

    # Extract play data for window detection
    play_data = [p.raw_data for p in chapter.plays]

    # Compute qualifying run windows (Phase 2.2)
    qualifying_runs = get_qualifying_run_windows(play_data)
    has_qualifying_run = len(qualifying_runs) > 0

    # Compute qualifying response windows (Phase 2.3)
    # Response windows can follow runs within this chapter
    qualifying_responses = get_qualifying_response_windows(play_data, qualifying_runs)
    has_qualifying_response = len(qualifying_responses) > 0

    # Compute back-and-forth window (Phase 2.4)
    back_and_forth_window = get_qualifying_back_and_forth_window(play_data)
    has_qualifying_back_and_forth = back_and_forth_window is not None

    # Previous chapter info
    previous_beat_type = previous_result.beat_type if previous_result else None
    previous_run_windows: list[RunWindow] = []

    # Get previous chapter's qualifying run windows for cross-chapter RESPONSE
    if previous_context is not None:
        previous_run_windows = previous_context.qualifying_run_windows

    # Determine previous scoring team (simplified)
    previous_scoring_team = None
    if previous_result and section_delta:
        # This would need more context; for now, leave as None
        pass

    return ChapterContext(
        chapter_id=chapter.chapter_id,
        chapter_index=chapter_index,
        period=period,
        time_remaining_seconds=time_remaining_seconds,
        is_overtime=is_overtime,
        home_score=home_score,
        away_score=away_score,
        score_margin=score_margin,
        home_points_scored=home_points_scored,
        away_points_scored=away_points_scored,
        total_points_scored=total_points_scored,
        total_plays=total_plays,
        possessions_estimate=possessions_estimate,
        total_fg_made=total_fg_made,
        total_fg_attempts=None,  # Not tracked yet
        total_rebounds=None,  # Not tracked yet
        qualifying_run_windows=qualifying_runs,
        has_qualifying_run=has_qualifying_run,
        qualifying_response_windows=qualifying_responses,
        has_qualifying_response=has_qualifying_response,
        back_and_forth_window=back_and_forth_window,
        has_qualifying_back_and_forth=has_qualifying_back_and_forth,
        previous_beat_type=previous_beat_type,
        previous_scoring_team=previous_scoring_team,
        previous_run_windows=previous_run_windows,
    )


# ============================================================================
# BEAT CLASSIFICATION RULES (PRIORITY ORDER)
# ============================================================================


def _check_overtime(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 1: OVERTIME (FORCED)

    If chapter occurs during overtime, beat_type = OVERTIME.
    No further evaluation.
    """
    if ctx.is_overtime:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.OVERTIME,
            triggered_rule="RULE_1_OVERTIME",
            debug_info={"period": ctx.period, "is_overtime": True},
        )
    return None


def _check_closing_sequence(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 2: CLOSING_SEQUENCE (Phase 2.6)

    Chapter qualifies when:
    - Quarter = Q4
    - Game clock ≤ 2:00
    - Absolute score margin ≤ 8

    This marks the final stretch of close games.
    """
    # Must be regulation (period 4 or less)
    if ctx.is_overtime:
        return None

    # Must be Q4
    if ctx.period != 4:
        return None

    # Must have time data
    if ctx.time_remaining_seconds is None:
        return None

    # Must be ≤ 2:00 (120 seconds)
    if ctx.time_remaining_seconds > CLOSING_SEQUENCE_TIME_THRESHOLD:
        return None

    # Phase 2.6: Must have close margin (≤ 8)
    if ctx.score_margin > CLOSING_SEQUENCE_MARGIN_THRESHOLD:
        return None

    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.CLOSING_SEQUENCE,
        triggered_rule="RULE_2_CLOSING_SEQUENCE",
        debug_info={
            "period": ctx.period,
            "time_remaining_seconds": ctx.time_remaining_seconds,
            "time_threshold": CLOSING_SEQUENCE_TIME_THRESHOLD,
            "score_margin": ctx.score_margin,
            "margin_threshold": CLOSING_SEQUENCE_MARGIN_THRESHOLD,
        },
    )


def _check_crunch_setup(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 3: CRUNCH_SETUP (Phase 2.6)

    Chapter qualifies when:
    - Quarter = Q4
    - Game clock ≤ 5:00
    - Absolute score margin ≤ 10

    Note: CLOSING_SEQUENCE (checked before this) handles ≤ 2:00 cases,
    so this effectively handles 2:00 < clock ≤ 5:00 when margin ≤ 10.
    """
    # Must be regulation Q4
    if ctx.is_overtime:
        return None

    if ctx.period != 4:
        return None

    if ctx.time_remaining_seconds is None:
        return None

    # Must be ≤ 5:00 (300s)
    if ctx.time_remaining_seconds > CRUNCH_SETUP_TIME_THRESHOLD:
        return None

    # Phase 2.6: Score margin ≤ 10 (expanded from ≤ 5)
    if ctx.score_margin > CRUNCH_SETUP_MARGIN_THRESHOLD:
        return None

    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.CRUNCH_SETUP,
        triggered_rule="RULE_3_CRUNCH_SETUP",
        debug_info={
            "period": ctx.period,
            "time_remaining_seconds": ctx.time_remaining_seconds,
            "time_threshold": CRUNCH_SETUP_TIME_THRESHOLD,
            "score_margin": ctx.score_margin,
            "margin_threshold": CRUNCH_SETUP_MARGIN_THRESHOLD,
        },
    )


def _check_run(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 4: RUN (Phase 2.2 - Run Window Detection)

    A RUN is detected when a qualifying run window exists within the chapter.

    A run window qualifies if:
    - One team scored ≥ 6 unanswered points, AND
    - The run caused a lead change, OR
    - The run increased the margin by ≥ 8 points

    This captures real momentum swings, not just raw scoring clusters.
    """
    if ctx.has_qualifying_run:
        # Get the most significant qualifying run for debug info
        best_run = max(ctx.qualifying_run_windows, key=lambda r: r.points_scored)
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.RUN,
            triggered_rule="RULE_4_RUN",
            debug_info={
                "qualifying_run_count": len(ctx.qualifying_run_windows),
                "best_run_team": best_run.team,
                "best_run_points": best_run.points_scored,
                "best_run_caused_lead_change": best_run.caused_lead_change,
                "best_run_margin_expansion": best_run.margin_expansion,
                "run_window_threshold": RUN_WINDOW_THRESHOLD,
                "margin_expansion_threshold": RUN_MARGIN_EXPANSION_THRESHOLD,
            },
        )
    return None


def _check_response(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 5: RESPONSE (Phase 2.3 - Response Window Detection)

    A RESPONSE is classified when the trailing team outscores the leading team
    after a qualifying RUN. This can happen:
    1. Within the same chapter (intra-chapter response after a RUN)
    2. In the chapter following a RUN (cross-chapter response)

    No requirement for:
    - Both teams to score
    - Full erasure of the RUN
    - Lead change
    """
    # Check 1: Intra-chapter response (RUN + RESPONSE in same chapter)
    if ctx.has_qualifying_response:
        best_response = max(
            ctx.qualifying_response_windows,
            key=lambda r: r.responding_team_points - r.run_team_points,
        )
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.RESPONSE,
            triggered_rule="RULE_5_RESPONSE_INTRA_CHAPTER",
            debug_info={
                "response_type": "intra_chapter",
                "responding_team": best_response.responding_team,
                "responding_team_points": best_response.responding_team_points,
                "run_team_points": best_response.run_team_points,
                "point_differential": best_response.responding_team_points
                - best_response.run_team_points,
            },
        )

    # Check 2: Cross-chapter response (previous chapter had RUN, this chapter has response)
    if ctx.previous_beat_type == BeatType.RUN and ctx.previous_run_windows:
        # Get the last RUN from previous chapter to determine responding team
        last_run = ctx.previous_run_windows[-1]
        responding_team = "away" if last_run.team == "home" else "home"

        # Calculate scoring in this chapter
        if responding_team == "home":
            responding_points = ctx.home_points_scored
            run_team_points = ctx.away_points_scored
        else:
            responding_points = ctx.away_points_scored
            run_team_points = ctx.home_points_scored

        # RESPONSE if responding team outscored the run team
        if responding_points > run_team_points:
            return BeatClassification(
                chapter_id=ctx.chapter_id,
                beat_type=BeatType.RESPONSE,
                triggered_rule="RULE_5_RESPONSE_CROSS_CHAPTER",
                debug_info={
                    "response_type": "cross_chapter",
                    "previous_beat_type": ctx.previous_beat_type.value,
                    "responding_team": responding_team,
                    "responding_team_points": responding_points,
                    "run_team_points": run_team_points,
                    "point_differential": responding_points - run_team_points,
                },
            )

    return None


def _check_stall(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 7: STALL

    If low scoring, few possessions, AND no clear run, response, or miss fest.

    This is a neutral "nothing is happening" beat.
    Use sparingly, but deterministically.
    """
    # Already checked RUN, RESPONSE, MISSED_SHOT_FEST
    # STALL is for low-action chapters

    # Few plays (< 5) AND low scoring (< 4 points)
    if ctx.total_plays < 5 and ctx.total_points_scored < 4:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.STALL,
            triggered_rule="RULE_7_STALL",
            debug_info={
                "total_plays": ctx.total_plays,
                "total_points_scored": ctx.total_points_scored,
            },
        )

    # Low possessions estimate AND low scoring
    if ctx.possessions_estimate < 3 and ctx.total_points_scored < 4:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.STALL,
            triggered_rule="RULE_7_STALL",
            debug_info={
                "possessions_estimate": ctx.possessions_estimate,
                "total_points_scored": ctx.total_points_scored,
            },
        )

    return None


def _check_back_and_forth(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 10: BACK_AND_FORTH (Phase 2.4 - Window Detection)

    A BACK_AND_FORTH beat is detected when the chapter exhibits high lead volatility:
    - ≥ 2 lead changes, OR
    - ≥ 3 ties (score becoming tied)

    No quarter restriction - can occur at any time in the game.
    Higher priority than default fallback.
    """
    if ctx.has_qualifying_back_and_forth and ctx.back_and_forth_window:
        window = ctx.back_and_forth_window
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.BACK_AND_FORTH,
            triggered_rule="RULE_10_BACK_AND_FORTH",
            debug_info={
                "lead_change_count": window.lead_change_count,
                "tie_count": window.tie_count,
                "lead_changes_threshold": BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD,
                "ties_threshold": BACK_AND_FORTH_TIES_THRESHOLD,
                "start_score": f"{window.start_home_score}-{window.start_away_score}",
                "end_score": f"{window.end_home_score}-{window.end_away_score}",
            },
        )
    return None


def _default_back_and_forth(ctx: ChapterContext) -> BeatClassification:
    """RULE 11: BACK_AND_FORTH (DEFAULT)

    If none of the above rules apply, beat_type = BACK_AND_FORTH.

    This is the safe fallback. If unsure, use this.
    """
    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.BACK_AND_FORTH,
        triggered_rule="RULE_11_DEFAULT_BACK_AND_FORTH",
        debug_info={"reason": "No other rule matched"},
    )


# ============================================================================
# MAIN CLASSIFICATION FUNCTION
# ============================================================================


def _compute_descriptors(ctx: ChapterContext) -> set[BeatDescriptor]:
    """Compute descriptors for a chapter.

    Phase 2.1: Descriptors are secondary context that may coexist with any primary beat.

    Args:
        ctx: ChapterContext with all classification inputs

    Returns:
        Set of applicable BeatDescriptor values (may be empty)
    """
    descriptors: set[BeatDescriptor] = set()

    # MISSED_SHOT_CONTEXT: Low points per play indicates cold shooting
    if ctx.total_plays >= 5:
        points_per_play = ctx.total_points_scored / ctx.total_plays
        if points_per_play < MISSED_SHOT_PPP_THRESHOLD:
            descriptors.add(BeatDescriptor.MISSED_SHOT_CONTEXT)

    return descriptors


def classify_chapter_beat(ctx: ChapterContext) -> BeatClassification:
    """Classify a single chapter's beat type.

    Phase 2.1: MISSED_SHOT_FEST is no longer a primary beat.
    It's now a descriptor (MISSED_SHOT_CONTEXT) that coexists with primary beats.

    Applies rules in priority order (top wins):
    1. OVERTIME (forced)
    2. CLOSING_SEQUENCE
    3. CRUNCH_SETUP
    4. RUN
    5. RESPONSE
    6. STALL
    7. FAST_START
    8. EARLY_CONTROL
    9. BACK_AND_FORTH (default)

    After primary beat is determined, descriptors are computed and attached.

    Args:
        ctx: ChapterContext with all classification inputs

    Returns:
        BeatClassification with exactly one beat_type and optional descriptors
    """
    # Apply rules in priority order
    result = _check_overtime(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_closing_sequence(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_crunch_setup(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_run(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_response(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    # Phase 2.1: MISSED_SHOT_FEST removed from primary beat assignment
    # It's now handled as a descriptor in _compute_descriptors()

    result = _check_stall(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    # Phase 2.4: Check for qualifying back-and-forth window
    result = _check_back_and_forth(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    # Default fallback
    result = _default_back_and_forth(ctx)
    result.descriptors = _compute_descriptors(ctx)
    return result


# ============================================================================
# BATCH CLASSIFICATION
# ============================================================================


def classify_all_chapters(
    chapters: list[Chapter],
    section_deltas: list[SectionDelta] | None = None,
    home_team_key: str | None = None,
    away_team_key: str | None = None,
) -> list[BeatClassification]:
    """Classify beat types for all chapters in a game.

    Args:
        chapters: List of chapters in chronological order
        section_deltas: List of SectionDeltas (one per chapter)
        home_team_key: Home team key for identification
        away_team_key: Away team key for identification

    Returns:
        List of BeatClassification, one per chapter
    """
    results: list[BeatClassification] = []
    contexts: list[ChapterContext] = []  # Track contexts for cross-chapter RESPONSE

    for i, chapter in enumerate(chapters):
        # Get corresponding section delta
        delta = (
            section_deltas[i] if section_deltas and i < len(section_deltas) else None
        )

        # Get previous result and context (for RESPONSE detection)
        previous_result = results[-1] if results else None
        previous_context = contexts[-1] if contexts else None

        # Build context
        ctx = build_chapter_context(
            chapter=chapter,
            chapter_index=i,
            section_delta=delta,
            previous_result=previous_result,
            home_team_key=home_team_key,
            away_team_key=away_team_key,
            previous_context=previous_context,
        )
        contexts.append(ctx)

        # Classify
        result = classify_chapter_beat(ctx)
        results.append(result)

    return results


# ============================================================================
# DEBUG OUTPUT
# ============================================================================


def format_classification_debug(results: list[BeatClassification]) -> str:
    """Format classification results for debug output.

    Args:
        results: List of BeatClassification

    Returns:
        Human-readable debug string
    """
    lines = ["Beat Classification Results:", "=" * 50]

    for result in results:
        line = f"{result.chapter_id}: {result.beat_type.value} (via {result.triggered_rule})"
        if result.descriptors:
            descriptors_str = ", ".join(d.value for d in result.descriptors)
            line += f" [descriptors: {descriptors_str}]"
        lines.append(line)

    return "\n".join(lines)


def get_beat_distribution(results: list[BeatClassification]) -> dict[str, int]:
    """Get distribution of beat types.

    Args:
        results: List of BeatClassification

    Returns:
        Dict of beat_type -> count
    """
    distribution: dict[str, int] = {}

    for result in results:
        beat = result.beat_type.value
        distribution[beat] = distribution.get(beat, 0) + 1

    return distribution
