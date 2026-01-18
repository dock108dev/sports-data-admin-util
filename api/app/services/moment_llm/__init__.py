"""Phase 6: LLM Augmentation & Narrative Guardrails.

This package introduces the LLM as a controlled enhancement layer, not a decision-maker.

CRITICAL RULES:
- LLM cannot select moments
- LLM cannot change ordering
- LLM cannot invent stats
- LLM cannot override templates
- LLM cannot fix upstream bugs

If the LLM fails, we fall back — not forward.

Tasks:
- 6.1: Constrained LLM Rewrite (per-moment)
- 6.2: Full-Game Narrative Stitching
- 6.3: Tone & Style Profiles
- 6.4: LLM Safety & Regression Guards
- 6.5: Kill Switch & Feature Flags
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .feature_flags import LLMFeatureFlags
from .tone_profiles import ToneConfig, ToneProfile
from .rewriting import (
    LLMCallFn,
    MomentRewriteInput,
    MomentRewriteOutput,
    build_moment_rewrite_prompt,
    create_mock_llm,
    rewrite_moment_with_llm,
)
from .guardrails import (
    ValidationResult,
    validate_length,
    validate_llm_output,
    validate_player_mentions,
    validate_sentence_count,
    validate_stat_preservation,
)
from .transitions import (
    TransitionInput,
    TransitionOutput,
    build_transition_prompt,
    generate_transitions,
    parse_transition_response,
    validate_transitions,
)

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class AugmentationResult:
    """Result of full LLM augmentation."""

    moment_rewrites: dict[str, MomentRewriteOutput] = field(default_factory=dict)
    transitions: TransitionOutput = field(default_factory=TransitionOutput)
    moments_rewritten: int = 0
    moments_fallback: int = 0
    flags_used: LLMFeatureFlags = field(default_factory=LLMFeatureFlags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_rewrites": {
                k: v.to_dict() for k, v in self.moment_rewrites.items()
            },
            "transitions": self.transitions.to_dict(),
            "moments_rewritten": self.moments_rewritten,
            "moments_fallback": self.moments_fallback,
        }


def augment_game_narrative(
    moments: Sequence["Moment"],
    llm_call: LLMCallFn | None,
    home_team: str = "",
    away_team: str = "",
    flags: LLMFeatureFlags | None = None,
    tone: ToneProfile = ToneProfile.NEUTRAL,
    game_id: str = "",
    league: str = "",
) -> AugmentationResult:
    """Apply LLM augmentation to a full game.

    This is the main entry point for Phase 6 augmentation.

    Args:
        moments: All moments for the game
        llm_call: Function to call LLM (None = no LLM)
        home_team: Home team name
        away_team: Away team name
        flags: Feature flags
        tone: Tone profile to use
        game_id: Game identifier for overrides
        league: League code for overrides

    Returns:
        AugmentationResult with all rewrites and transitions
    """
    result = AugmentationResult()

    if flags is None:
        flags = LLMFeatureFlags.all_disabled()

    effective_flags = flags.for_game(game_id, league)
    result.flags_used = effective_flags

    if llm_call is None:
        logger.info("LLM augmentation skipped: no LLM provided")
        return result

    if not any(
        [
            effective_flags.enable_moment_rewrite,
            effective_flags.enable_transitions,
        ]
    ):
        logger.info("LLM augmentation skipped: all features disabled")
        return result

    tone_config = ToneConfig.from_profile(tone)
    if not effective_flags.enable_tone_profiles:
        tone_config = ToneConfig.from_profile(ToneProfile.NEUTRAL)

    if effective_flags.enable_moment_rewrite:
        for moment in moments:
            rewrite = rewrite_moment_with_llm(moment, llm_call, tone_config)
            result.moment_rewrites[moment.id] = rewrite

            if rewrite.used_fallback:
                result.moments_fallback += 1
            else:
                result.moments_rewritten += 1

    if effective_flags.enable_transitions:
        result.transitions = generate_transitions(
            moments, llm_call, home_team, away_team, tone_config
        )

    logger.info(
        "llm_augmentation_complete",
        extra={
            "moments_rewritten": result.moments_rewritten,
            "moments_fallback": result.moments_fallback,
            "transitions_generated": not result.transitions.used_fallback,
        },
    )

    return result


__all__ = [
    # Feature flags
    "LLMFeatureFlags",
    # Tone profiles
    "ToneConfig",
    "ToneProfile",
    # Rewriting
    "LLMCallFn",
    "MomentRewriteInput",
    "MomentRewriteOutput",
    "build_moment_rewrite_prompt",
    "create_mock_llm",
    "rewrite_moment_with_llm",
    # Guardrails
    "ValidationResult",
    "validate_length",
    "validate_llm_output",
    "validate_player_mentions",
    "validate_sentence_count",
    "validate_stat_preservation",
    # Transitions
    "TransitionInput",
    "TransitionOutput",
    "build_transition_prompt",
    "generate_transitions",
    "parse_transition_response",
    "validate_transitions",
    # Combined
    "AugmentationResult",
    "augment_game_narrative",
]
