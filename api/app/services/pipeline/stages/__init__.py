"""Pipeline stage implementations.

Legacy moment stages removed. System is now chapters-first.
"""

from .normalize_pbp import execute_normalize_pbp

__all__ = [
    "execute_normalize_pbp",
]
