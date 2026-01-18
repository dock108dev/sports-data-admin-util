"""Backwards compatibility alias for moment_llm package.

All imports are re-exported from the moment_llm package.
Use `from app.services.moment_llm import ...` for new code.
"""

# Re-export everything from moment_llm for backwards compatibility
from .moment_llm import (
    # Feature flags
    LLMFeatureFlags,
    # Tone profiles
    ToneConfig,
    ToneProfile,
    # Rewriting
    LLMCallFn,
    MomentRewriteInput,
    MomentRewriteOutput,
    build_moment_rewrite_prompt,
    create_mock_llm,
    rewrite_moment_with_llm,
    # Guardrails
    ValidationResult,
    validate_length,
    validate_llm_output,
    validate_player_mentions,
    validate_sentence_count,
    validate_stat_preservation,
    # Transitions
    TransitionInput,
    TransitionOutput,
    build_transition_prompt,
    generate_transitions,
    parse_transition_response,
    validate_transitions,
    # Combined
    AugmentationResult,
    augment_game_narrative,
)

__all__ = [
    "LLMFeatureFlags",
    "ToneConfig",
    "ToneProfile",
    "LLMCallFn",
    "MomentRewriteInput",
    "MomentRewriteOutput",
    "build_moment_rewrite_prompt",
    "create_mock_llm",
    "rewrite_moment_with_llm",
    "ValidationResult",
    "validate_length",
    "validate_llm_output",
    "validate_player_mentions",
    "validate_sentence_count",
    "validate_stat_preservation",
    "TransitionInput",
    "TransitionOutput",
    "build_transition_prompt",
    "generate_transitions",
    "parse_transition_response",
    "validate_transitions",
    "AugmentationResult",
    "augment_game_narrative",
]
