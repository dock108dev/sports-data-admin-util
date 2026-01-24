"""
Section Signal Evaluation: Metrics for determining section quality.

This module provides functions to evaluate the "signal" (meaningfulness)
of story sections based on scoring, lead changes, runs, and other events.

SIGNAL THRESHOLD:
A section is underpowered if BOTH:
- Total points scored < 8
- Meaningful events < 3 (scoring plays, lead changes, run events, ties)

THIN SECTION:
A section is thin if BOTH:
- Total points scored ≤ 4
- Number of scoring plays ≤ 2

LUMPY SECTION:
A section is lumpy if single player accounts for ≥ 65% of section points.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Chapter
    from .section_types import StorySection


# ============================================================================
# SIGNAL THRESHOLD CONSTANTS
# ============================================================================

# Minimum points scored in a section to be considered "powered"
SECTION_MIN_POINTS_THRESHOLD = 8

# Minimum meaningful events in a section to be considered "powered"
SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD = 3


# ============================================================================
# THIN SECTION CONSTANTS
# ============================================================================

# A section is "thin" if BOTH conditions are true
THIN_SECTION_MAX_POINTS = 4  # Total points scored ≤ 4
THIN_SECTION_MAX_SCORING_PLAYS = 2  # Number of scoring plays ≤ 2


# ============================================================================
# LUMPY SECTION CONSTANTS (DOMINANCE CAPPING)
# ============================================================================

# A section is "lumpy" if single player has ≥ this % of section points
LUMPY_DOMINANCE_THRESHOLD_PCT = 0.65  # 65%

# Cap dominant player contribution at this % of section points
DOMINANCE_CAP_PCT = 0.60  # 60%


# ============================================================================
# INTERNAL HELPER FUNCTIONS
# ============================================================================


def _count_scoring_plays(chapters: list["Chapter"], chapter_ids: list[str]) -> int:
    """Count scoring plays in the given chapters.

    A scoring play is any play where the score changes.
    """
    count = 0
    chapters_map = {ch.chapter_id: ch for ch in chapters}

    for chapter_id in chapter_ids:
        chapter = chapters_map.get(chapter_id)
        if not chapter or not chapter.plays:
            continue

        prev_home = None
        prev_away = None

        for play in chapter.plays:
            raw = play.raw_data
            home = raw.get("home_score") or 0
            away = raw.get("away_score") or 0

            if prev_home is not None and prev_away is not None:
                if home != prev_home or away != prev_away:
                    count += 1

            prev_home = home
            prev_away = away

    return count


def _count_lead_changes_and_ties(
    chapters: list["Chapter"], chapter_ids: list[str]
) -> tuple[int, int]:
    """Count lead changes and tie creations in the given chapters.

    Returns:
        Tuple of (lead_change_count, tie_creation_count)
    """
    lead_changes = 0
    tie_creations = 0
    chapters_map = {ch.chapter_id: ch for ch in chapters}

    prev_leader: str | None = None
    first_play = True

    for chapter_id in chapter_ids:
        chapter = chapters_map.get(chapter_id)
        if not chapter or not chapter.plays:
            continue

        for play in chapter.plays:
            raw = play.raw_data
            home = raw.get("home_score") or 0
            away = raw.get("away_score") or 0

            # Determine current leader
            if home > away:
                curr_leader: str | None = "home"
            elif away > home:
                curr_leader = "away"
            else:
                curr_leader = None  # Tied

            if not first_play:
                # Lead change: one team was leading, now the other is
                if prev_leader is not None and curr_leader is not None:
                    if prev_leader != curr_leader:
                        lead_changes += 1

                # Tie creation: one team was leading, now tied
                if prev_leader is not None and curr_leader is None:
                    tie_creations += 1

            # Update for next iteration
            if curr_leader is not None:
                prev_leader = curr_leader
            first_play = False

    return lead_changes, tie_creations


def _count_run_events(chapters: list["Chapter"], chapter_ids: list[str]) -> int:
    """Count run start/end events in the given chapters.

    A run starts when one team scores >= 6 unanswered points.
    A run ends when the opposing team scores.
    """
    from .virtual_boundaries import RUN_THRESHOLD_POINTS

    run_events = 0
    chapters_map = {ch.chapter_id: ch for ch in chapters}

    run_team: str | None = None
    run_points: int = 0
    run_announced: bool = False
    prev_home: int | None = None
    prev_away: int | None = None

    for chapter_id in chapter_ids:
        chapter = chapters_map.get(chapter_id)
        if not chapter or not chapter.plays:
            continue

        for play in chapter.plays:
            raw = play.raw_data
            home = raw.get("home_score") or 0
            away = raw.get("away_score") or 0

            if prev_home is not None and prev_away is not None:
                home_delta = home - prev_home
                away_delta = away - prev_away

                if home_delta > 0 and away_delta == 0:
                    # Home scored
                    if run_team == "home":
                        run_points += home_delta
                    else:
                        if run_team == "away" and run_announced:
                            run_events += 1  # RUN_END
                        run_team = "home"
                        run_points = home_delta
                        run_announced = False

                    if run_points >= RUN_THRESHOLD_POINTS and not run_announced:
                        run_events += 1  # RUN_START
                        run_announced = True

                elif away_delta > 0 and home_delta == 0:
                    # Away scored
                    if run_team == "away":
                        run_points += away_delta
                    else:
                        if run_team == "home" and run_announced:
                            run_events += 1  # RUN_END
                        run_team = "away"
                        run_points = away_delta
                        run_announced = False

                    if run_points >= RUN_THRESHOLD_POINTS and not run_announced:
                        run_events += 1  # RUN_START
                        run_announced = True

                elif home_delta > 0 and away_delta > 0:
                    # Both scored - end any run
                    if run_announced:
                        run_events += 1  # RUN_END
                    run_team = None
                    run_points = 0
                    run_announced = False

            prev_home = home
            prev_away = away

    return run_events


# ============================================================================
# PUBLIC API
# ============================================================================


def count_meaningful_events(section: "StorySection", chapters: list["Chapter"]) -> int:
    """Count meaningful events in a section.

    Meaningful events include:
    - Scoring plays
    - Lead changes
    - Run start/end
    - Tie creation

    Args:
        section: The section to evaluate
        chapters: All chapters (for looking up chapter content)

    Returns:
        Total count of meaningful events
    """
    chapter_ids = section.chapters_included

    scoring_plays = _count_scoring_plays(chapters, chapter_ids)
    lead_changes, tie_creations = _count_lead_changes_and_ties(chapters, chapter_ids)
    run_events = _count_run_events(chapters, chapter_ids)

    return scoring_plays + lead_changes + tie_creations + run_events


def get_section_total_points(section: "StorySection") -> int:
    """Get total points scored in a section (both teams combined)."""
    total = 0
    for team_delta in section.team_stat_deltas.values():
        total += team_delta.points_scored
    return total


def is_section_underpowered(
    section: "StorySection",
    chapters: list["Chapter"],
) -> bool:
    """Check if a section is underpowered (below signal threshold).

    A section is underpowered if BOTH:
    - Total points scored < SECTION_MIN_POINTS_THRESHOLD (8)
    - Meaningful event count < SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD (3)

    Args:
        section: The section to evaluate
        chapters: All chapters (for meaningful event detection)

    Returns:
        True if the section is underpowered
    """
    total_points = get_section_total_points(section)
    meaningful_events = count_meaningful_events(section, chapters)

    # Underpowered if BOTH conditions are true
    return (
        total_points < SECTION_MIN_POINTS_THRESHOLD
        and meaningful_events < SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD
    )


def count_section_scoring_plays(
    section: "StorySection", chapters: list["Chapter"]
) -> int:
    """Count number of scoring plays in a section.

    A scoring play is any play where the score changes.
    """
    return _count_scoring_plays(chapters, section.chapters_included)


def is_section_thin(section: "StorySection", chapters: list["Chapter"]) -> bool:
    """Check if a section is thin (very low signal).

    A section is thin if BOTH:
    - Total points scored ≤ THIN_SECTION_MAX_POINTS (4)
    - Number of scoring plays ≤ THIN_SECTION_MAX_SCORING_PLAYS (2)

    Thin sections must ALWAYS be merged, never dropped.

    Args:
        section: The section to evaluate
        chapters: All chapters (for scoring play count)

    Returns:
        True if the section is thin
    """
    total_points = get_section_total_points(section)
    scoring_plays = count_section_scoring_plays(section, chapters)

    return (
        total_points <= THIN_SECTION_MAX_POINTS
        and scoring_plays <= THIN_SECTION_MAX_SCORING_PLAYS
    )


def get_dominant_player_share(section: "StorySection") -> tuple[str | None, float]:
    """Get the most dominant player and their share of section points.

    Args:
        section: The section to evaluate

    Returns:
        Tuple of (player_key, share_pct) where share_pct is 0.0-1.0.
        Returns (None, 0.0) if no players or no points.
    """
    total_points = get_section_total_points(section)
    if total_points == 0:
        return None, 0.0

    max_player_key = None
    max_player_points = 0

    for player_key, delta in section.player_stat_deltas.items():
        if delta.points_scored > max_player_points:
            max_player_points = delta.points_scored
            max_player_key = player_key

    if max_player_key is None:
        return None, 0.0

    share = max_player_points / total_points
    return max_player_key, share


def is_section_lumpy(section: "StorySection") -> bool:
    """Check if a section is lumpy (dominated by single player).

    A section is lumpy if a single player accounts for ≥ 65% of section points.

    Args:
        section: The section to evaluate

    Returns:
        True if the section is lumpy
    """
    _, share = get_dominant_player_share(section)
    return share >= LUMPY_DOMINANCE_THRESHOLD_PCT
