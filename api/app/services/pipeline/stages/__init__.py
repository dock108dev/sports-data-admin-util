"""Pipeline stage implementations.

Each stage is a standalone module that can be executed independently.
Stages consume the output of the previous stage and produce output
for the next stage.

Stage execution order:
1. normalize_pbp - Builds normalized PBP events with phases
2. derive_signals - Computes lead states and tier crossings
3. generate_moments - Partitions game into moments
4. validate_moments - Runs validation checks
5. finalize_moments - Persists final artifact
"""

from .normalize_pbp import execute_normalize_pbp
from .derive_signals import execute_derive_signals
from .generate_moments import execute_generate_moments
from .validate_moments import execute_validate_moments
from .finalize_moments import execute_finalize_moments

__all__ = [
    "execute_normalize_pbp",
    "execute_derive_signals",
    "execute_generate_moments",
    "execute_validate_moments",
    "execute_finalize_moments",
]
