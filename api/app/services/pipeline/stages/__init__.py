"""Pipeline stage implementations."""

from .normalize_pbp import execute_normalize_pbp
from .generate_moments import execute_generate_moments
from .validate_moments import execute_validate_moments
from .render_narratives import execute_render_narratives
from .group_blocks import execute_group_blocks
from .render_blocks import execute_render_blocks
from .validate_blocks import execute_validate_blocks
from .finalize_moments import execute_finalize_moments
from .embedded_tweets import (
    select_embedded_tweets,
    enforce_embedded_caps,
    apply_embedded_tweets_to_blocks,
    select_and_assign_embedded_tweets,
    DefaultTweetScorer,
)

__all__ = [
    "execute_normalize_pbp",
    "execute_generate_moments",
    "execute_validate_moments",
    "execute_render_narratives",
    "execute_group_blocks",
    "execute_render_blocks",
    "execute_validate_blocks",
    "execute_finalize_moments",
    # Embedded tweet selection (Phase 4)
    "select_embedded_tweets",
    "enforce_embedded_caps",
    "apply_embedded_tweets_to_blocks",
    "select_and_assign_embedded_tweets",
    "DefaultTweetScorer",
]
