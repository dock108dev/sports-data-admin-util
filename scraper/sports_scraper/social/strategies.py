"""
X post collection strategies.

Includes mock implementations for tests.
"""

from __future__ import annotations

from datetime import datetime

from ..logging import logger
from .collector_base import XCollectorStrategy
from .models import CollectedPost


class MockXCollector(XCollectorStrategy):
    """
    Mock collector for testing without X API access.

    Returns empty results - real data should come from actual X integration.
    """

    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        logger.info(
            "mock_x_collector_called",
            x_handle=x_handle,
            window_start=str(window_start),
            window_end=str(window_end),
        )
        return []
