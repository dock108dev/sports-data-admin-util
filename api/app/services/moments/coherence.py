"""Narrative coherence enforcement for moments.

PHASE 4: Post-construction pass that ensures moment list represents
a coherent story by:
1. Removing fake comebacks
2. Suppressing late-game false drama
3. Detecting and handling dormancy
4. Filtering low-quality semantic splits
5. Enforcing narrative flow rules

This runs AFTER moment creation and BEFORE AI enrichment.
"""

from __future__ import annotations

import logging
from typing import Any

from .types import Moment, MomentType
from .narrative_state import (
    NarrativeState,
    build_narrative_state,
    is_genuine_state_change,
    is_fake_comeback,
    should_suppress_late_game_cut,
    is_dormant_window,
    should_suppress_semantic_split,
)
from ..moments_merging import merge_two_moments

logger = logging.getLogger(__name__)


def enforce_narrative_coherence(
    moments: list[Moment],
    summary: dict[str, Any],
) -> list[Moment]:
    """Enforce narrative coherence across moments.
    
    PHASE 4: Final structural pass before AI enrichment.
    
    This function:
    1. Builds narrative state for each moment
    2. Removes moments that don't represent genuine state changes
    3. Suppresses fake comebacks
    4. Suppresses late-game false drama
    5. Handles dormancy windows
    6. Filters low-quality semantic splits
    7. Merges adjacent no-change moments
    
    Args:
        moments: List of moments (post-construction)
        summary: Game summary dict
    
    Returns:
        Filtered list of coherent moments
    """
    if not moments:
        return moments
    
    logger.info(
        "coherence_enforcement_starting",
        extra={"moment_count": len(moments)},
    )
    
    # Pass 1: Build narrative states
    states = _build_narrative_states(moments)
    
    # Pass 2: Mark moments for suppression
    suppression_flags = _mark_suppressions(moments, states)
    
    # Pass 3: Filter suppressed moments
    filtered_moments = _filter_suppressed_moments(moments, suppression_flags)
    
    # Pass 4: Merge adjacent no-change moments
    coherent_moments = _merge_no_change_moments(filtered_moments)
    
    # Pass 5: Downgrade repeated patterns
    final_moments = _downgrade_repeated_patterns(coherent_moments)
    
    suppressed_count = len(moments) - len(final_moments)
    logger.info(
        "coherence_enforcement_complete",
        extra={
            "original_count": len(moments),
            "final_count": len(final_moments),
            "suppressed_count": suppressed_count,
        },
    )
    
    return final_moments


def _build_narrative_states(moments: list[Moment]) -> list[NarrativeState]:
    """Build narrative state for each moment.
    
    Args:
        moments: List of moments
    
    Returns:
        List of NarrativeState objects (same length as moments)
    """
    states: list[NarrativeState] = []
    previous_state: NarrativeState | None = None
    
    for moment in moments:
        # Get phase progress from narrative context
        phase_progress = 0.5
        is_closing_window = False
        
        if moment.narrative_context:
            phase_progress = moment.narrative_context.phase_progress
            is_closing_window = moment.narrative_context.is_closing_window
        elif moment.phase_state and hasattr(moment.phase_state, 'to_dict'):
            phase_dict = moment.phase_state.to_dict()
            phase_progress = phase_dict.get('game_progress', 0.5)
            is_closing_window = phase_dict.get('is_closing_window', False)
        
        # Build state
        state = build_narrative_state(
            moment=moment,
            previous_state=previous_state,
            phase_progress=phase_progress,
            is_closing_window=is_closing_window,
        )
        
        states.append(state)
        previous_state = state
    
    return states


def _mark_suppressions(
    moments: list[Moment],
    states: list[NarrativeState],
) -> list[dict[str, Any]]:
    """Mark moments for suppression based on coherence rules.
    
    Args:
        moments: List of moments
        states: List of narrative states (same length)
    
    Returns:
        List of suppression flags (same length)
        Each flag is a dict with:
        - suppress: bool
        - reason: str
        - action: "suppress" | "merge" | "downgrade" | "keep"
    """
    flags: list[dict[str, Any]] = []
    previous_state: NarrativeState | None = None
    
    for idx, (moment, state) in enumerate(zip(moments, states)):
        flag = {
            "suppress": False,
            "reason": "keep",
            "action": "keep",
        }
        
        # Check 1: Genuine state change
        is_genuine, reason = is_genuine_state_change(moment, state, previous_state)
        if not is_genuine:
            flag["suppress"] = True
            flag["reason"] = reason
            flag["action"] = "merge"
            logger.debug(
                "moment_marked_for_suppression",
                extra={
                    "moment_id": moment.id,
                    "reason": reason,
                    "type": moment.type.value,
                },
            )
        
        # Check 2: Fake comeback
        if is_fake_comeback(moment, state, previous_state, idx):
            flag["suppress"] = True
            flag["reason"] = "fake_comeback"
            flag["action"] = "suppress"
            logger.debug(
                "fake_comeback_detected",
                extra={"moment_id": moment.id, "type": moment.type.value},
            )
        
        # Check 3: Late-game false drama
        if should_suppress_late_game_cut(moment, state):
            flag["suppress"] = True
            flag["reason"] = "late_game_false_drama"
            flag["action"] = "suppress"
            logger.debug(
                "late_game_cut_suppressed",
                extra={"moment_id": moment.id, "tier": moment.ladder_tier_after},
            )
        
        # Check 4: Dormancy suppression (semantic splits only)
        if is_dormant_window(state) and should_suppress_semantic_split(moment, state, previous_state):
            flag["suppress"] = True
            flag["reason"] = "dormant_semantic_split"
            flag["action"] = "suppress"
            logger.debug(
                "dormant_split_suppressed",
                extra={"moment_id": moment.id, "dormant_plays": state.dormant_play_count},
            )
        
        # Check 5: Low-quality semantic split
        if should_suppress_semantic_split(moment, state, previous_state):
            flag["suppress"] = True
            flag["reason"] = "low_quality_semantic_split"
            flag["action"] = "suppress"
            logger.debug(
                "semantic_split_suppressed",
                extra={"moment_id": moment.id},
            )
        
        flags.append(flag)
        previous_state = state
    
    return flags


def _filter_suppressed_moments(
    moments: list[Moment],
    flags: list[dict[str, Any]],
) -> list[Moment]:
    """Filter out suppressed moments.
    
    Args:
        moments: List of moments
        flags: List of suppression flags
    
    Returns:
        Filtered list of moments
    """
    filtered: list[Moment] = []
    
    for moment, flag in zip(moments, flags):
        if not flag["suppress"]:
            filtered.append(moment)
        else:
            logger.debug(
                "moment_suppressed",
                extra={
                    "moment_id": moment.id,
                    "type": moment.type.value,
                    "reason": flag["reason"],
                    "action": flag["action"],
                },
            )
    
    return filtered


def _merge_no_change_moments(moments: list[Moment]) -> list[Moment]:
    """Merge adjacent moments with no narrative change.
    
    Args:
        moments: List of moments
    
    Returns:
        List with adjacent no-change moments merged
    """
    if len(moments) <= 1:
        return moments
    
    merged: list[Moment] = []
    i = 0
    
    while i < len(moments):
        current = moments[i]
        
        # Check if next moment is also no-change
        if i + 1 < len(moments):
            next_moment = moments[i + 1]
            
            # Merge if both are NEUTRAL or both are same type with same control
            should_merge = False
            
            if (current.type == MomentType.NEUTRAL and
                next_moment.type == MomentType.NEUTRAL):
                should_merge = True
            
            if (current.type == next_moment.type and
                current.team_in_control == next_moment.team_in_control and
                current.type in [MomentType.CUT, MomentType.LEAD_BUILD]):
                # Check if tier didn't change much
                if abs(current.ladder_tier_after - next_moment.ladder_tier_after) <= 1:
                    should_merge = True
            
            if should_merge:
                merged_moment = merge_two_moments(current, next_moment)
                logger.debug(
                    "adjacent_moments_merged",
                    extra={
                        "moment1_id": current.id,
                        "moment2_id": next_moment.id,
                        "merged_id": merged_moment.id,
                    },
                )
                merged.append(merged_moment)
                i += 2  # Skip next
                continue
        
        merged.append(current)
        i += 1
    
    return merged


def _downgrade_repeated_patterns(moments: list[Moment]) -> list[Moment]:
    """Downgrade repeated moment patterns.
    
    PHASE 4: If we see CUT → CUT → CUT with same control and no threat increase,
    downgrade later ones to NEUTRAL.
    
    Args:
        moments: List of moments
    
    Returns:
        List with repeated patterns downgraded
    """
    if len(moments) <= 2:
        return moments
    
    downgraded: list[Moment] = []
    consecutive_cut_count = 0
    consecutive_build_count = 0
    
    for i, moment in enumerate(moments):
        should_downgrade = False
        
        # Track consecutive CUTs
        if moment.type == MomentType.CUT:
            consecutive_cut_count += 1
            consecutive_build_count = 0
            
            # Downgrade if 3+ consecutive CUTs with same control
            if consecutive_cut_count >= 3:
                # Check if control unchanged
                if i >= 2:
                    prev1 = moments[i - 1]
                    prev2 = moments[i - 2]
                    if (moment.team_in_control == prev1.team_in_control ==
                        prev2.team_in_control):
                        should_downgrade = True
        
        # Track consecutive LEAD_BUILDs
        elif moment.type == MomentType.LEAD_BUILD:
            consecutive_build_count += 1
            consecutive_cut_count = 0
            
            # Downgrade if 4+ consecutive builds (blowout padding)
            if consecutive_build_count >= 4:
                should_downgrade = True
        
        else:
            consecutive_cut_count = 0
            consecutive_build_count = 0
        
        if should_downgrade:
            # Create downgraded copy
            downgraded_moment = Moment(
                id=moment.id,
                type=MomentType.NEUTRAL,  # Downgrade to NEUTRAL
                events=moment.events,
                score_before=moment.score_before,
                score_after=moment.score_after,
                ladder_tier_before=moment.ladder_tier_before,
                ladder_tier_after=moment.ladder_tier_after,
                reason=moment.reason,
                team_in_control=moment.team_in_control,
                run_info=moment.run_info,
                headline=moment.headline,
                summary=moment.summary,
                importance=moment.importance,
                key_play_ids=moment.key_play_ids,
                player_contributions=moment.player_contributions,
                is_period_start=moment.is_period_start,
                recap_context=moment.recap_context,
                bucket=moment.bucket,
                phase_state=moment.phase_state,
                narrative_context=moment.narrative_context,
            )
            logger.debug(
                "moment_downgraded",
                extra={
                    "moment_id": moment.id,
                    "original_type": moment.type.value,
                    "new_type": "NEUTRAL",
                    "reason": f"consecutive_{moment.type.value.lower()}",
                },
            )
            downgraded.append(downgraded_moment)
        else:
            downgraded.append(moment)
    
    return downgraded


def add_narrative_delta_to_moments(moments: list[Moment]) -> None:
    """Add narrative_delta field to moment reasons.
    
    PHASE 4: Classify each moment's narrative impact.
    
    Modifies moments in place.
    
    Args:
        moments: List of moments
    """
    if not moments:
        return
    
    states = _build_narrative_states(moments)
    previous_state: NarrativeState | None = None
    
    for moment, state in zip(moments, states):
        if not moment.reason:
            continue
        
        # Determine narrative delta
        delta = "no_change"
        
        if not previous_state:
            delta = "opening"
        elif state.threat_level.value != previous_state.threat_level.value:
            if state.threat_level.value > previous_state.threat_level.value:
                delta = "threat_increase"
            else:
                delta = "threat_decrease"
        elif state.control_strength.value != previous_state.control_strength.value:
            if state.control_strength.value > previous_state.control_strength.value:
                delta = "control_increase"
            else:
                delta = "control_decrease"
        elif state.controlling_team != previous_state.controlling_team:
            delta = "control_shift"
        elif state.phase != previous_state.phase:
            delta = "phase_transition"
        elif moment.ladder_tier_after != moment.ladder_tier_before:
            delta = "tier_change"
        
        # Update reason's narrative_delta
        moment.reason.narrative_delta = delta
        
        previous_state = state
