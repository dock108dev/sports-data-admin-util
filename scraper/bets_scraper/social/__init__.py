"""
Social media integration for game timeline posts.

This module provides infrastructure for collecting and managing
social posts from team X accounts.
"""

from .models import CollectedPost, PostCollectionJob, PostCollectionResult
from .collector import (
    XPostCollector,
    XCollectorStrategy,
    MockXCollector,
    XApiCollector,
    PlaywrightXCollector,
)

__all__ = [
    "CollectedPost",
    "PostCollectionJob",
    "PostCollectionResult",
    "XPostCollector",
    "XCollectorStrategy",
    "MockXCollector",
    "XApiCollector",
    "PlaywrightXCollector",
]

