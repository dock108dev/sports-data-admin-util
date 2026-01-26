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

__all__ = [
    "CondensedMoment",
    "StoryV2Output",
    "validate_moment",
    "validate_story",
    "PlayData",
    "BuilderResult",
    "BoundaryReason",
    "MomentBuildError",
    "build_condensed_moments",
    "plays_from_raw",
    "SelectionRule",
    "SelectionError",
    "SelectionResult",
    "SelectionDebugInfo",
    "select_explicit_plays",
    "apply_selection_to_moment",
    "select_plays_for_moments",
    "validate_selection",
]
