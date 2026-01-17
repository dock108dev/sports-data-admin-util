"""
Lead Ladder threshold configuration access.

This module is the SINGLE SOURCE OF TRUTH for lead thresholds (Lead Ladder).
Thresholds are stored in the database per league and define meaningful
separation levels for detecting narrative boundaries.

Lead Ladder values by sport (stored in compact_mode_thresholds table):
- NBA / NCAAB: [3, 6, 10, 16] points
- NFL / NCAAF: [1, 2, 3, 5] possessions (approximated as scores)
- MLB: [1, 2, 3, 5] runs
- NHL: [1, 2, 3] goals

IMPORTANT: This module fails loudly if thresholds are missing.
There are NO hardcoded fallbacks. All leagues must have configured thresholds.
"""

from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import db_models
from ..db import get_async_session

logger = logging.getLogger(__name__)


# =============================================================================
# PURE FUNCTIONS (No DB access - can be used anywhere)
# =============================================================================


def get_lead_tier(margin: int, thresholds: Sequence[int]) -> int:
    """
    Calculate the lead tier based on margin and threshold ladder.

    This is a PURE FUNCTION - no database access, no side effects.
    It can be called synchronously from anywhere.

    The tier represents how significant the lead is:
    - Tier 0: Lead is below the first threshold (small lead)
    - Tier 1: Lead >= thresholds[0] (meaningful separation)
    - Tier 2: Lead >= thresholds[1] (comfortable lead)
    - Tier N: Lead >= thresholds[N-1] (increasingly decisive)

    Args:
        margin: Absolute point/score difference (always >= 0)
        thresholds: Ascending list of threshold values, e.g. [3, 6, 10, 16]

    Returns:
        Tier level (0 to len(thresholds))

    Example:
        >>> get_lead_tier(5, [3, 6, 10, 16])
        1  # 5 >= 3 but < 6
        >>> get_lead_tier(10, [3, 6, 10, 16])
        3  # 10 >= 10 but < 16
        >>> get_lead_tier(20, [3, 6, 10, 16])
        4  # 20 >= 16 (max tier)
    """
    if not thresholds:
        return 0

    margin = abs(margin)
    tier = 0
    for threshold in thresholds:
        if margin >= threshold:
            tier += 1
        else:
            break
    return tier


def get_tier_label(tier: int, max_tier: int) -> str:
    """
    Get a human-readable label for a lead tier.

    Args:
        tier: Current tier (0 to max_tier)
        max_tier: Maximum possible tier (len(thresholds))

    Returns:
        Label like "small", "meaningful", "comfortable", "large", "decisive"
    """
    if tier == 0:
        return "small"
    if max_tier <= 1:
        return "meaningful"

    # Map tier to label based on position in ladder
    ratio = tier / max_tier
    if ratio <= 0.25:
        return "meaningful"
    if ratio <= 0.5:
        return "comfortable"
    if ratio <= 0.75:
        return "large"
    return "decisive"


# =============================================================================
# DATABASE ACCESS FUNCTIONS
# =============================================================================


class ThresholdsNotFoundError(Exception):
    """Raised when lead thresholds are not configured for a league."""

    def __init__(self, identifier: str | int) -> None:
        self.identifier = identifier
        super().__init__(
            f"Lead thresholds not found for '{identifier}'. "
            "All leagues must have configured thresholds in compact_mode_thresholds table."
        )


async def _fetch_thresholds_by_sport_id(
    session: AsyncSession,
    sport_id: int,
) -> db_models.CompactModeThreshold:
    """Fetch thresholds by sport_id. Raises ThresholdsNotFoundError if missing."""
    stmt = select(db_models.CompactModeThreshold).where(
        db_models.CompactModeThreshold.sport_id == sport_id
    )
    result = await session.execute(stmt)
    thresholds = result.scalar_one_or_none()
    if thresholds is None:
        logger.error("Lead thresholds not found for sport_id=%s", sport_id)
        raise ThresholdsNotFoundError(sport_id)
    return thresholds


async def _fetch_thresholds_by_league_code(
    session: AsyncSession,
    league_code: str,
) -> db_models.CompactModeThreshold:
    """Fetch thresholds by league code. Raises ThresholdsNotFoundError if missing."""
    stmt = (
        select(db_models.CompactModeThreshold)
        .join(db_models.SportsLeague)
        .where(db_models.SportsLeague.code == league_code)
    )
    result = await session.execute(stmt)
    thresholds = result.scalar_one_or_none()
    if thresholds is None:
        logger.error("Lead thresholds not found for league_code=%s", league_code)
        raise ThresholdsNotFoundError(league_code)
    return thresholds


async def get_thresholds_for_sport(
    sport_id: int,
    session: AsyncSession | None = None,
) -> db_models.CompactModeThreshold:
    """
    Return lead thresholds for the requested sport by ID.

    FAILS LOUDLY if thresholds are not configured.
    There are no default fallbacks.

    Args:
        sport_id: The sports_leagues.id value
        session: Optional session (creates one if not provided)

    Returns:
        CompactModeThreshold model with .thresholds list

    Raises:
        ThresholdsNotFoundError: If thresholds not configured for this sport
    """
    if session is not None:
        return await _fetch_thresholds_by_sport_id(session, sport_id)

    async with get_async_session() as local_session:
        return await _fetch_thresholds_by_sport_id(local_session, sport_id)


async def get_thresholds_for_league(
    league_code: str,
    session: AsyncSession | None = None,
) -> list[int]:
    """
    Return lead threshold values for the requested league by code.

    This is the primary entry point for Lead Ladder access.
    FAILS LOUDLY if thresholds are not configured.

    Args:
        league_code: League code like "NBA", "NHL", "NCAAB"
        session: Optional session (creates one if not provided)

    Returns:
        List of threshold values, e.g. [3, 6, 10, 16] for NBA

    Raises:
        ThresholdsNotFoundError: If thresholds not configured for this league

    Example:
        >>> thresholds = await get_thresholds_for_league("NBA")
        >>> thresholds
        [3, 6, 10, 16]
    """
    if session is not None:
        record = await _fetch_thresholds_by_league_code(session, league_code)
        return list(record.thresholds)

    async with get_async_session() as local_session:
        record = await _fetch_thresholds_by_league_code(local_session, league_code)
        return list(record.thresholds)


# =============================================================================
# BACKWARDS COMPATIBILITY
# =============================================================================

# Legacy alias - prefer get_thresholds_for_sport()
async def getThresholdsForSport(
    sport_id: int,
    session: AsyncSession | None = None,
) -> db_models.CompactModeThreshold:
    """
    Return compact mode thresholds for the requested sport.

    DEPRECATED: Use get_thresholds_for_sport() or get_thresholds_for_league() instead.
    """
    return await get_thresholds_for_sport(sport_id, session)
