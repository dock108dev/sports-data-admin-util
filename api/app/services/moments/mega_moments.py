"""Mega-moment detection and splitting.

This module handles:
- Back-and-forth phase detection
- Quarter boundary finding
- Splitting oversized moments into smaller chunks
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ..lead_ladder import Leader, compute_lead_state

from .types import Moment, MomentType
from .helpers import create_moment, get_score

logger = logging.getLogger(__name__)


def detect_back_and_forth_phase(
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    thresholds: Sequence[int],
) -> bool:
    """Detect if a moment represents a back-and-forth phase.

    Criteria:
    - Multiple small lead changes within the moment
    - Score stays within tier 0-1 (close game)
    - No sustained runs (no 8+ point unanswered runs)

    Returns True if this is a volatile back-and-forth sequence.
    """
    if end_idx - start_idx < 20:
        return False

    lead_changes = 0
    ties = 0
    max_tier = 0
    prev_leader = None
    prev_score = None
    max_run_length = 0
    current_run_length = 0
    last_scoring_team = None

    for i in range(start_idx, end_idx + 1):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue

        home_score = event.get("home_score") or 0
        away_score = event.get("away_score") or 0

        if prev_score is not None:
            if home_score > prev_score[0] or away_score > prev_score[1]:
                scoring_team = "home" if home_score > prev_score[0] else "away"

                if scoring_team == last_scoring_team:
                    current_run_length += 1
                    max_run_length = max(max_run_length, current_run_length)
                else:
                    current_run_length = 1
                    last_scoring_team = scoring_team

        state = compute_lead_state(home_score, away_score, thresholds)
        max_tier = max(max_tier, state.tier)

        if (
            prev_leader is not None
            and state.leader != prev_leader
            and state.leader != Leader.TIED
        ):
            lead_changes += 1

        if state.leader == Leader.TIED and (
            prev_leader is None or prev_leader != Leader.TIED
        ):
            ties += 1

        prev_leader = state.leader
        prev_score = (home_score, away_score)

    is_volatile = lead_changes >= 3 or ties >= 3
    is_close = max_tier <= 1
    no_sustained_run = max_run_length < 8

    return is_volatile and is_close and no_sustained_run


def find_quarter_boundaries(
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
) -> list[int]:
    """Find quarter boundary indices within a moment.

    Returns indices where the quarter changes.
    """
    boundaries: list[int] = []
    prev_quarter = None

    for i in range(start_idx, end_idx + 1):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue

        quarter = event.get("quarter")
        if prev_quarter is not None and quarter != prev_quarter:
            boundaries.append(i)
        prev_quarter = quarter

    return boundaries


def split_mega_moment(
    moment: Moment,
    events: list[dict[str, Any]],
    thresholds: Sequence[int],
    game_context: dict[str, str],
    max_plays: int = 50,
) -> list[Moment]:
    """Split a mega-moment into smaller chunks at natural break points.

    Break points (in priority order):
    1. Quarter boundaries
    2. Every max_plays if no quarter boundaries available

    Preserves score continuity and moment IDs.
    """
    if moment.play_count <= max_plays:
        return [moment]

    quarter_boundaries = find_quarter_boundaries(events, moment.start_play, moment.end_play)

    if not quarter_boundaries:
        split_points: list[int] = []
        current = moment.start_play + max_plays
        while current < moment.end_play:
            split_points.append(current)
            current += max_plays
    else:
        split_points = quarter_boundaries

    sub_moments: list[Moment] = []
    current_start = moment.start_play
    moment_id_counter = 0

    if current_start > 0:
        current_score_before = get_score(events[current_start - 1])
    else:
        current_score_before = (0, 0)

    for split_idx in split_points:
        if split_idx <= current_start:
            continue

        score_before = current_score_before

        end_idx_for_sub = split_idx - 1
        score_after = get_score(events[end_idx_for_sub])

        if score_after == (0, 0) and end_idx_for_sub > current_start:
            for j in range(end_idx_for_sub - 1, current_start - 1, -1):
                temp_score = get_score(events[j])
                if temp_score != (0, 0):
                    score_after = temp_score
                    end_idx_for_sub = j
                    break

        start_state = compute_lead_state(score_before[0], score_before[1], thresholds)
        end_state = compute_lead_state(score_after[0], score_after[1], thresholds)

        if start_state.leader != end_state.leader:
            sub_type = (
                MomentType.FLIP if end_state.leader != Leader.TIED else MomentType.TIE
            )
        elif end_state.tier > start_state.tier:
            sub_type = MomentType.LEAD_BUILD
        elif end_state.tier < start_state.tier:
            sub_type = MomentType.CUT
        else:
            sub_type = MomentType.NEUTRAL

        sub_moment = create_moment(
            moment_id=moment_id_counter,
            events=events,
            start_idx=current_start,
            end_idx=end_idx_for_sub,
            moment_type=sub_type,
            thresholds=thresholds,
            boundary=None,
            score_before=score_before,
            game_context=game_context,
        )

        sub_moment.id = f"{moment.id}_sub{moment_id_counter}"
        sub_moments.append(sub_moment)

        current_start = split_idx
        current_score_before = score_after
        moment_id_counter += 1

    # Create final sub-moment
    if current_start <= moment.end_play:
        score_before = current_score_before

        sub_moment = create_moment(
            moment_id=moment_id_counter,
            events=events,
            start_idx=current_start,
            end_idx=moment.end_play,
            moment_type=moment.type,
            thresholds=thresholds,
            boundary=None,
            score_before=score_before,
            game_context=game_context,
        )

        sub_moment.id = f"{moment.id}_sub{moment_id_counter}"
        sub_moments.append(sub_moment)

    logger.info(
        "mega_moment_split",
        extra={
            "original_id": moment.id,
            "original_plays": moment.play_count,
            "sub_moments": len(sub_moments),
            "split_points": len(split_points),
        },
    )

    return sub_moments
