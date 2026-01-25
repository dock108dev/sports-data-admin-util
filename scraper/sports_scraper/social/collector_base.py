"""Shared interfaces for X collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .models import CollectedPost


class XCollectorStrategy(ABC):
    """Abstract base class for X post collection strategies."""

    @abstractmethod
    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        """
        Collect posts from an X account within a time window.

        Args:
            x_handle: X handle to collect from (without @)
            window_start: Start of collection window
            window_end: End of collection window

        Returns:
            List of collected posts
        """
        raise NotImplementedError
