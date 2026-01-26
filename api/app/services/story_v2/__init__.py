"""Story V2: Condensed moment-based game narratives."""

from .schema import CondensedMoment, StoryV2Output, validate_moment, validate_story
from .moment_builder import (
    PlayData,
    BuilderResult,
    BoundaryReason,
    MomentBuildError,
    build_condensed_moments,
    plays_from_raw,
)
from .explicit_play_selector import (
    SelectionRule,
    SelectionError,
    SelectionResult,
    SelectionDebugInfo,
    select_explicit_plays,
    apply_selection_to_moment,
    select_plays_for_moments,
    validate_selection,
)
from .moment_renderer import (
    RenderError,
    ValidationError,
    RenderInput,
    RenderResult,
    RenderDebugInfo,
    build_prompt,
    validate_narrative,
    render_moment,
    render_moments,
    update_moment_with_narrative,
)
from .story_builder import (
    AssemblyError,
    assemble_story,
)
from .validators import (
    ContractViolation,
    ValidationResult,
    TraceabilityResult,
    validate_moment_structure,
    validate_story_structure,
    validate_plays_exist,
    validate_forbidden_language,
    validate_narrative_traceability,
    validate_no_future_references,
    validate_story_contract,
    validate_moment_contract,
    trace_sentence_to_plays,
    trace_narrative_to_plays,
    explain_moment_backing,
    FORBIDDEN_ABSTRACT_TERMS,
    FORBIDDEN_TEMPORAL_TERMS,
    FORBIDDEN_SUMMARY_TERMS,
    FORBIDDEN_META_TERMS,
)

__all__ = [
    # Schema
    "CondensedMoment",
    "StoryV2Output",
    "validate_moment",
    "validate_story",
    # Moment Builder
    "PlayData",
    "BuilderResult",
    "BoundaryReason",
    "MomentBuildError",
    "build_condensed_moments",
    "plays_from_raw",
    # Explicit Play Selector
    "SelectionRule",
    "SelectionError",
    "SelectionResult",
    "SelectionDebugInfo",
    "select_explicit_plays",
    "apply_selection_to_moment",
    "select_plays_for_moments",
    "validate_selection",
    # Moment Renderer
    "RenderError",
    "ValidationError",
    "RenderInput",
    "RenderResult",
    "RenderDebugInfo",
    "build_prompt",
    "validate_narrative",
    "render_moment",
    "render_moments",
    "update_moment_with_narrative",
    # Story Builder
    "AssemblyError",
    "assemble_story",
    # Validators
    "ContractViolation",
    "ValidationResult",
    "TraceabilityResult",
    "validate_moment_structure",
    "validate_story_structure",
    "validate_plays_exist",
    "validate_forbidden_language",
    "validate_narrative_traceability",
    "validate_no_future_references",
    "validate_story_contract",
    "validate_moment_contract",
    "trace_sentence_to_plays",
    "trace_narrative_to_plays",
    "explain_moment_backing",
    "FORBIDDEN_ABSTRACT_TERMS",
    "FORBIDDEN_TEMPORAL_TERMS",
    "FORBIDDEN_SUMMARY_TERMS",
    "FORBIDDEN_META_TERMS",
]
