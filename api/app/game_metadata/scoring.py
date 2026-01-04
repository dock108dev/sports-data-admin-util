"""Scoring helpers for game metadata."""

from __future__ import annotations

import logging

from .models import GameContext

logger = logging.getLogger(__name__)

NOT_IMPLEMENTED_MESSAGE = "Game metadata scoring is not implemented yet."


def score_game_context(context: GameContext) -> float:
    """Score a game context for metadata ordering.

    Raises:
        NotImplementedError: Until scoring rules are defined.
    """
    logger.error(NOT_IMPLEMENTED_MESSAGE, extra={"game_id": context.game_id})
    raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)
