"""Unit tests for compact mode thresholds service."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from api.app import db_models
from api.app.services.compact_mode_thresholds import get_thresholds_for_sport


class TestCompactModeThresholds(unittest.IsolatedAsyncioTestCase):
    async def test_get_thresholds_for_sport_returns_thresholds(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        thresholds = db_models.CompactModeThreshold(
            id=1,
            sport_id=1,
            thresholds=[1, 2, 3],
            description="Test thresholds",
        )
        result.scalar_one_or_none.return_value = thresholds
        session.execute.return_value = result

        response = await get_thresholds_for_sport(1, session=session)

        self.assertEqual(response.thresholds, [1, 2, 3])
        self.assertEqual(response.description, "Test thresholds")
        session.execute.assert_awaited_once()
