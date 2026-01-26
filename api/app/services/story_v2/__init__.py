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
]
