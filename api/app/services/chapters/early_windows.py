"""
Early Window Detection: Section-level beat detection for opening sections.

Detects FAST_START and EARLY_CONTROL at the section level based on
early-game (first 6:00 of Q1) statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from .beat_types import (
    BeatType,
    EARLY_WINDOW_DURATION_SECONDS,
    FAST_START_MIN_COMBINED_POINTS,
    FAST_START_MAX_MARGIN,
    EARLY_CONTROL_MIN_LEAD,
    EARLY_CONTROL_MIN_SHARE_PCT,
)

if TYPE_CHECKING:
    from .types import Chapter


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

    # Calculate points scored in window
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
    if early_stats.total_points < FAST_START_MIN_COMBINED_POINTS:
        return None

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
    if early_stats.leading_team is None:
        return None

    if early_stats.final_margin < EARLY_CONTROL_MIN_LEAD:
        return None

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
