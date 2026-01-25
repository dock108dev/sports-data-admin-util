"""
Virtual Boundary Detection for Chapters.

This module detects momentum shifts within chapters that do NOT
cause chapter splits. These "virtual boundaries" are stored for
AI enrichment and debug analysis.

VIRTUAL BOUNDARY TYPES:
- RUN_START: Start of unanswered scoring run (>=6 points)
- RUN_END: End of scoring run (opposing team scores)
- LEAD_CHANGE: Leading team switched
- TIE_CREATION: Game became tied after one team was leading

DESIGN PRINCIPLES:
- Deterministic: Same plays -> same virtual boundaries
- Non-invasive: Does NOT affect chapter splitting
- Inform-only: Stored for context, not persisted to DB

Phase 1.1: This is observability-only. Virtual boundaries do not
affect chapter counts or downstream behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .boundary_rules import (
    BoundaryType,
    BoundaryMarker,
    VirtualBoundaryReason,
)

if TYPE_CHECKING:
    from .types import Chapter


# Threshold for detecting a scoring run (per spec: >=6 unanswered points)
RUN_THRESHOLD_POINTS = 6


def detect_virtual_boundaries(chapter: Chapter) -> list[BoundaryMarker]:
    """Detect virtual boundaries within a chapter.

    Scans plays sequentially to identify momentum shifts:
    - RUN_START: When one team scores >=6 unanswered points
    - RUN_END: When opposing team scores after a run
    - LEAD_CHANGE: When leading team switches (home <-> away)
    - TIE_CREATION: When game becomes tied after one team was leading

    Args:
        chapter: Chapter to analyze

    Returns:
        List of BoundaryMarker objects (may be empty).
        All markers have boundary_type=VIRTUAL.
    """
    if not chapter.plays:
        return []

    boundaries: list[BoundaryMarker] = []

    # Initialize state from first play's scores (if available)
    first_play_data = chapter.plays[0].raw_data
    prev_home_score = first_play_data.get("home_score") or 0
    prev_away_score = first_play_data.get("away_score") or 0

    # Determine initial leader
    if prev_home_score > prev_away_score:
        prev_leader: str | None = "home"
    elif prev_away_score > prev_home_score:
        prev_leader = "away"
    else:
        prev_leader = None  # Tied

    # Run tracking state
    run_team: str | None = None
    run_points: int = 0
    run_start_idx: int | None = None
    run_announced: bool = False  # Have we emitted RUN_START for current run?

    for play in chapter.plays:
        raw = play.raw_data
        home_score = raw.get("home_score") or 0
        away_score = raw.get("away_score") or 0

        # Calculate score changes since last play
        home_delta = home_score - prev_home_score
        away_delta = away_score - prev_away_score

        # Determine current leader
        if home_score > away_score:
            curr_leader: str | None = "home"
        elif away_score > home_score:
            curr_leader = "away"
        else:
            curr_leader = None  # Tied

        score_snapshot = (home_score, away_score)

        # --- LEAD CHANGE DETECTION ---
        # Lead change: one team was leading, now the other team is leading
        if prev_leader is not None and curr_leader is not None:
            if prev_leader != curr_leader:
                boundaries.append(
                    BoundaryMarker(
                        boundary_type=BoundaryType.VIRTUAL,
                        play_index=play.index,
                        reason=VirtualBoundaryReason.LEAD_CHANGE.value,
                        team_id=curr_leader,
                        score_snapshot=score_snapshot,
                    )
                )

        # --- TIE CREATION DETECTION ---
        # Tie creation: one team was leading, now it's tied
        if prev_leader is not None and curr_leader is None:
            boundaries.append(
                BoundaryMarker(
                    boundary_type=BoundaryType.VIRTUAL,
                    play_index=play.index,
                    reason=VirtualBoundaryReason.TIE_CREATION.value,
                    team_id=None,
                    score_snapshot=score_snapshot,
                )
            )

        # --- RUN DETECTION ---
        if home_delta > 0 and away_delta == 0:
            # Home scored, away did not
            if run_team == "home":
                # Extend existing home run
                run_points += home_delta
            else:
                # Previous run (if any) just ended
                if run_team == "away" and run_announced:
                    boundaries.append(
                        BoundaryMarker(
                            boundary_type=BoundaryType.VIRTUAL,
                            play_index=play.index,
                            reason=VirtualBoundaryReason.RUN_END.value,
                            team_id="away",
                            score_snapshot=score_snapshot,
                        )
                    )
                # Start new home run
                run_team = "home"
                run_points = home_delta
                run_start_idx = play.index
                run_announced = False

            # Check if we just reached run threshold
            if run_points >= RUN_THRESHOLD_POINTS and not run_announced:
                boundaries.append(
                    BoundaryMarker(
                        boundary_type=BoundaryType.VIRTUAL,
                        play_index=run_start_idx
                        if run_start_idx is not None
                        else play.index,
                        reason=VirtualBoundaryReason.RUN_START.value,
                        team_id="home",
                        score_snapshot=score_snapshot,
                    )
                )
                run_announced = True

        elif away_delta > 0 and home_delta == 0:
            # Away scored, home did not
            if run_team == "away":
                # Extend existing away run
                run_points += away_delta
            else:
                # Previous run (if any) just ended
                if run_team == "home" and run_announced:
                    boundaries.append(
                        BoundaryMarker(
                            boundary_type=BoundaryType.VIRTUAL,
                            play_index=play.index,
                            reason=VirtualBoundaryReason.RUN_END.value,
                            team_id="home",
                            score_snapshot=score_snapshot,
                        )
                    )
                # Start new away run
                run_team = "away"
                run_points = away_delta
                run_start_idx = play.index
                run_announced = False

            # Check if we just reached run threshold
            if run_points >= RUN_THRESHOLD_POINTS and not run_announced:
                boundaries.append(
                    BoundaryMarker(
                        boundary_type=BoundaryType.VIRTUAL,
                        play_index=run_start_idx
                        if run_start_idx is not None
                        else play.index,
                        reason=VirtualBoundaryReason.RUN_START.value,
                        team_id="away",
                        score_snapshot=score_snapshot,
                    )
                )
                run_announced = True

        elif home_delta > 0 and away_delta > 0:
            # Both teams scored (unusual, e.g., and-one or correction)
            # End any active run
            if run_announced:
                boundaries.append(
                    BoundaryMarker(
                        boundary_type=BoundaryType.VIRTUAL,
                        play_index=play.index,
                        reason=VirtualBoundaryReason.RUN_END.value,
                        team_id=run_team,
                        score_snapshot=score_snapshot,
                    )
                )
            # Reset run state
            run_team = None
            run_points = 0
            run_start_idx = None
            run_announced = False

        # No scoring (home_delta == 0 and away_delta == 0): run continues unchanged

        # Update previous state for next iteration
        prev_home_score = home_score
        prev_away_score = away_score
        if curr_leader is not None:
            prev_leader = curr_leader
        # Note: If curr_leader is None (tied), we keep prev_leader as the last team
        # that was leading. This allows lead changes from tie to be detected.

    return boundaries
