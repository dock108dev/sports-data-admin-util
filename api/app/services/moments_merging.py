"""
Moment Merging Logic.

Handles merging of moments to enforce budget constraints and narrative coherence.
Merging is the primary mechanism for reducing moment count while maintaining
complete timeline coverage.

Key principles:
- Invalid moments are always merged
- Consecutive same-type moments are merged
- Budget is strictly enforced
- Protected types (FLIP, CLOSING_CONTROL, HIGH_IMPACT) are never merged
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from .moments import Moment

logger = logging.getLogger(__name__)

# Moment types that can NEVER be merged (dramatic moments)
PROTECTED_TYPES_SET = frozenset({"FLIP", "CLOSING_CONTROL", "HIGH_IMPACT"})

# Moment types that should always be merged when consecutive
ALWAYS_MERGE_TYPES_SET = frozenset({"NEUTRAL", "LEAD_BUILD", "CUT"})

# Per-quarter/period limits prevent "chaotic quarter" bloat
QUARTER_MOMENT_LIMIT = 7  # Max moments per quarter/period


def is_valid_moment(moment: Moment) -> bool:
    """
    HARD VALIDITY GATE: A moment must represent a narrative state change.

    A moment is valid if:
    1. It has a causal trigger (not 'unknown' or 'stable' with no change)
    2. It has participants (teams)
    3. It represents a meaningful state change (score, control, ladder)
    4. It is NOT a micro-moment (< 2 plays) unless it's a high-impact transition
    """
    # Import here to avoid circular dependency
    from .moments import MomentType

    # Rule 0: Must have a causal trigger
    if not moment.reason or moment.reason.trigger in ("unknown", "stable"):
        # Stable moments are only valid if they actually have a score change
        if moment.score_before == moment.score_after:
            return False

    # Rule 1: Must have teams
    if not moment.teams:
        return False

    # Rule 2: Micro-moment protection
    if moment.play_count < 2:
        # Only allow single-play moments for high-impact transitions
        if moment.type not in (MomentType.FLIP, MomentType.TIE, MomentType.CLOSING_CONTROL, MomentType.HIGH_IMPACT):
            return False

    # Rule 3: Narrative change
    if (moment.score_before != moment.score_after or
        moment.ladder_tier_before != moment.ladder_tier_after or
        moment.type in (MomentType.FLIP, MomentType.TIE, MomentType.CLOSING_CONTROL, MomentType.HIGH_IMPACT)):
        return True

    return False


def can_merge_moments(m1: Moment, m2: Moment) -> bool:
    """
    Determine if two adjacent moments can be merged.

    MERGE RULES (from spec):
    - Same MomentType → ALWAYS merge
    - Same team_in_control → MERGE (unless protected type)
    - No intervening FLIP, TIE, or CLOSING_CONTROL
    - Low-value moments → ALWAYS merge (they have no narrative value)

    Protected types (FLIP, CLOSING_CONTROL, HIGH_IMPACT) are NEVER merged.
    """
    # Import here to avoid circular dependency
    from .moments import MomentType

    PROTECTED_TYPES = frozenset({
        MomentType.FLIP,
        MomentType.CLOSING_CONTROL,
        MomentType.HIGH_IMPACT,
    })

    ALWAYS_MERGE_TYPES = frozenset({
        MomentType.NEUTRAL,
        MomentType.LEAD_BUILD,
        MomentType.CUT,
    })

    # Low-value moments can always be merged (they have no narrative value)
    if not is_valid_moment(m1) or not is_valid_moment(m2):
        # But don't merge low-value moments with protected types
        if not (m1.type in PROTECTED_TYPES or m2.type in PROTECTED_TYPES):
            return True

    # Never merge protected types
    if m1.type in PROTECTED_TYPES or m2.type in PROTECTED_TYPES:
        return False

    # Always merge same type + same control
    if m1.type == m2.type:
        return True

    # Merge NEUTRAL with anything except protected
    if m1.type == MomentType.NEUTRAL or m2.type == MomentType.NEUTRAL:
        return True

    # Merge consecutive LEAD_BUILD or CUT if same control
    if m1.type in ALWAYS_MERGE_TYPES and m2.type in ALWAYS_MERGE_TYPES:
        if m1.team_in_control == m2.team_in_control:
            return True

    # Don't merge TIE with other types (TIE is a narrative pivot)
    if m1.type == MomentType.TIE or m2.type == MomentType.TIE:
        return False

    return False


def merge_two_moments(m1: Moment, m2: Moment) -> Moment:
    """
    Merge two adjacent moments into one.

    The resulting moment:
    - Spans from m1.start_play to m2.end_play
    - Takes the more significant type
    - Combines key_play_ids
    - Takes the final control state
    """
    # Import here to avoid circular dependency
    from .moments import Moment, MomentType

    # Determine the dominant type (more significant)
    type_priority = {
        MomentType.FLIP: 10,
        MomentType.CLOSING_CONTROL: 9,
        MomentType.HIGH_IMPACT: 8,
        MomentType.TIE: 7,
        MomentType.CUT: 6,
        MomentType.LEAD_BUILD: 5,
        MomentType.NEUTRAL: 1,
    }

    if type_priority.get(m2.type, 0) > type_priority.get(m1.type, 0):
        dominant_type = m2.type
        dominant_reason = m2.reason
    else:
        dominant_type = m1.type
        dominant_reason = m1.reason

    # Combine key plays
    combined_key_plays = list(set(m1.key_play_ids + m2.key_play_ids))
    combined_key_plays.sort()

    # Build merged reason if needed
    if dominant_reason is None and m1.reason:
        dominant_reason = m1.reason

    merged = Moment(
        id=m1.id,  # Will be renumbered later
        type=dominant_type,
        start_play=m1.start_play,
        end_play=m2.end_play,
        play_count=m2.end_play - m1.start_play + 1,
        score_before=m1.score_before,
        score_after=m2.score_after,
        score_start=m1.score_start,
        score_end=m2.score_end,
        ladder_tier_before=m1.ladder_tier_before,
        ladder_tier_after=m2.ladder_tier_after,
        team_in_control=m2.team_in_control,
        teams=list(set(m1.teams + m2.teams)),
        primary_team=m2.primary_team or m1.primary_team,
        players=m1.players + m2.players,  # Combine player contributions
        key_play_ids=combined_key_plays,
        clock=f"{m1.clock.split('–')[0]}–{m2.clock.split('–')[-1]}" if m1.clock and m2.clock else m1.clock or m2.clock,
        reason=dominant_reason,
        is_notable=m1.is_notable or m2.is_notable,
        is_period_start=m1.is_period_start,
        note=m2.note or m1.note,
        run_info=m2.run_info or m1.run_info,
        bucket=m2.bucket or m1.bucket,
        phase_state=m1.phase_state,  # PROMPT 2: Preserve phase state from start
        narrative_context=m1.narrative_context,  # PROMPT 2: Preserve narrative context
    )
    
    # PROMPT 2: Update narrative context to reflect merge
    if merged.narrative_context:
        merged.narrative_context.is_continuation = True  # Merged moments are continuations

    return merged


def merge_invalid_moments(moments: list[Moment]) -> list[Moment]:
    """
    HARD VALIDITY ENFORCEMENT: Merge all invalid moments into adjacent valid ones.

    A moment is invalid if it fails the is_valid_moment() gate (no narrative change).
    These moments are absorbed into the nearest valid moment (prefer previous).
    """
    if not moments:
        return moments

    merged: list[Moment] = []

    for moment in moments:
        if not is_valid_moment(moment):
            # Invalid moment - merge into previous valid moment if possible
            if merged:
                logger.info(
                    "absorbing_invalid_moment",
                    extra={
                        "invalid_moment_id": moment.id,
                        "invalid_type": moment.type.value,
                        "invalid_score": f"{moment.score_before} → {moment.score_after}",
                        "merged_into": merged[-1].id,
                    },
                )
                merged[-1] = merge_two_moments(merged[-1], moment)
            else:
                # This is the first moment and it's invalid - keep it
                # It will be merged with the next valid moment
                merged.append(moment)
        else:
            # Current moment is valid
            # Check if we should absorb the previous moment if it was the first and invalid
            if len(merged) == 1 and not is_valid_moment(merged[0]):
                first = merged.pop()
                logger.info(
                    "absorbing_initial_invalid_moment",
                    extra={
                        "invalid_moment_id": first.id,
                        "merged_into": moment.id,
                    }
                )
                merged.append(merge_two_moments(first, moment))
            else:
                merged.append(moment)

    return merged


def merge_consecutive_moments(moments: list[Moment]) -> list[Moment]:
    """
    Merge consecutive same-type moments aggressively.

    This is the PRIMARY mechanism for reducing moment count.

    These should NEVER be separate moments:
    - LEAD_BUILD → LEAD_BUILD
    - CUT → CUT
    - NEUTRAL → NEUTRAL

    If control didn't change, the moment didn't change.
    """
    if len(moments) <= 1:
        return moments

    merged: list[Moment] = [moments[0]]

    for current in moments[1:]:
        prev = merged[-1]

        if can_merge_moments(prev, current):
            # Merge into previous
            merged[-1] = merge_two_moments(prev, current)
        else:
            merged.append(current)

    return merged


def get_quarter_for_play(play_idx: int, events: Sequence[dict[str, Any]]) -> int | None:
    """Get quarter number for a play index."""
    if play_idx < 0 or play_idx >= len(events):
        return None
    event = events[play_idx]
    return event.get("quarter")


def enforce_quarter_limits(
    moments: list[Moment],
    events: Sequence[dict[str, Any]],
) -> list[Moment]:
    """
    Enforce per-quarter moment limits to prevent chaotic quarters.

    A quarter with 10+ moments is narratively confusing.
    This merges excess moments within each quarter.
    """
    # Import here to avoid circular dependency
    from .moments import MomentType

    if not moments:
        return moments

    # Group moments by quarter
    quarter_moments: dict[int, list[int]] = {}  # quarter -> list of moment indices
    for i, m in enumerate(moments):
        q = get_quarter_for_play(m.start_play, events)
        if q is not None:
            if q not in quarter_moments:
                quarter_moments[q] = []
            quarter_moments[q].append(i)

    # Find quarters over limit
    to_merge: set[int] = set()  # moment indices to merge with previous
    for q, indices in quarter_moments.items():
        if len(indices) > QUARTER_MOMENT_LIMIT:
            excess = len(indices) - QUARTER_MOMENT_LIMIT
            # Mark the least important moments for merging
            # Prefer merging NEUTRAL, LEAD_BUILD, CUT in that order
            scored = []
            for idx in indices[1:]:  # Skip first moment in quarter
                m = moments[idx]
                if m.type == MomentType.NEUTRAL:
                    priority = 0
                elif m.type in (MomentType.LEAD_BUILD, MomentType.CUT):
                    priority = 1
                elif m.type == MomentType.TIE:
                    priority = 3
                else:
                    priority = 4  # Protected types
                scored.append((priority, m.play_count, idx))

            # Sort by priority (lowest first) then play_count (lowest first)
            scored.sort(key=lambda x: (x[0], x[1]))

            # Mark top 'excess' for merging
            for _, _, idx in scored[:excess]:
                to_merge.add(idx)

    if not to_merge:
        return moments

    # Merge marked moments into previous
    result = []
    for i, m in enumerate(moments):
        if i in to_merge and result:
            # Merge into previous
            result[-1] = merge_two_moments(result[-1], m)
        else:
            result.append(m)

    if len(result) < len(moments):
        logger.info(
            "quarter_limits_enforced",
            extra={
                "original_count": len(moments),
                "final_count": len(result),
                "merged_count": len(moments) - len(result),
            },
        )

    return result


def enforce_budget(moments: list[Moment], budget: int) -> list[Moment]:
    """
    Force moments under budget. This is a HARD CLAMP.

    Priority for merging (least important first):
    1. Consecutive NEUTRAL moments
    2. Consecutive LEAD_BUILD moments
    3. Consecutive CUT moments
    4. (HARD CLAMP) Any consecutive same-type moments
    5. (HARD CLAMP) Any consecutive moments (last resort)

    The budget IS enforced. No exceptions.
    """
    # Import here to avoid circular dependency
    from .moments import MomentType

    if len(moments) <= budget:
        return moments

    initial_count = len(moments)

    # Phase 1: Soft merges (preferred)
    iterations = 0
    max_iterations = 20

    while len(moments) > budget and iterations < max_iterations:
        iterations += 1
        merged = False

        # First pass: merge any remaining NEUTRAL sequences
        for i in range(len(moments) - 1):
            if i >= len(moments) - 1:
                break
            if moments[i].type == MomentType.NEUTRAL and moments[i + 1].type == MomentType.NEUTRAL:
                moments[i] = merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break

        if merged or len(moments) <= budget:
            continue

        # Second pass: merge LEAD_BUILD sequences
        for i in range(len(moments) - 1):
            if i >= len(moments) - 1:
                break
            if moments[i].type == MomentType.LEAD_BUILD and moments[i + 1].type == MomentType.LEAD_BUILD:
                moments[i] = merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break

        if merged or len(moments) <= budget:
            continue

        # Third pass: merge CUT sequences
        for i in range(len(moments) - 1):
            if i >= len(moments) - 1:
                break
            if moments[i].type == MomentType.CUT and moments[i + 1].type == MomentType.CUT:
                moments[i] = merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break

        if merged or len(moments) <= budget:
            continue

        if not merged:
            break  # Move to hard clamp phase

    # Phase 2: HARD CLAMP - merge any consecutive same-type moments
    while len(moments) > budget:
        merged = False
        for i in range(len(moments) - 2):  # Don't merge the last moment
            if moments[i].type == moments[i + 1].type:
                moments[i] = merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break
        if not merged:
            break

    # Phase 3: NUCLEAR OPTION - merge any consecutive moments
    while len(moments) > budget:
        # Find the smallest moment to absorb
        if len(moments) <= 2:
            break

        # Merge the moment with fewest plays into its neighbor
        min_plays = float('inf')
        merge_idx = 1  # Default to second moment
        for i in range(1, len(moments) - 1):  # Skip first and last
            if moments[i].play_count < min_plays:
                min_plays = moments[i].play_count
                merge_idx = i

        # Merge into previous
        moments[merge_idx - 1] = merge_two_moments(moments[merge_idx - 1], moments[merge_idx])
        moments.pop(merge_idx)

    if len(moments) < initial_count:
        logger.info(
            "budget_enforced",
            extra={
                "initial_count": initial_count,
                "final_count": len(moments),
                "budget": budget,
                "hard_clamp_used": len(moments) != initial_count,
            },
        )

    return moments
