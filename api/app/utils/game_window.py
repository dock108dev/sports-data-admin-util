"""
Game social window calculations.

Defines the time window for capturing social posts around a game.
Used to determine which posts are relevant to a specific game.
"""

from datetime import datetime, timedelta
from typing import NamedTuple


class GameWindowConfig(NamedTuple):
    """Configuration for social capture window."""

    pre_game_hours: int = 2
    post_game_hours: int = 3


DEFAULT_CONFIG = GameWindowConfig()


class GameWindow(NamedTuple):
    """Time window for capturing social posts."""

    game_id: int
    game_start: datetime
    window_start: datetime
    window_end: datetime

    @property
    def duration_hours(self) -> float:
        """Total window duration in hours."""
        return (self.window_end - self.window_start).total_seconds() / 3600


def calculate_game_window(
    game_id: int,
    game_start: datetime,
    config: GameWindowConfig = DEFAULT_CONFIG,
) -> GameWindow:
    """
    Calculate the social capture window for a game.

    Args:
        game_id: The database ID of the game
        game_start: When the game starts
        config: Window configuration (pre/post game hours)

    Returns:
        GameWindow with calculated timestamps
    """
    return GameWindow(
        game_id=game_id,
        game_start=game_start,
        window_start=game_start - timedelta(hours=config.pre_game_hours),
        window_end=game_start + timedelta(hours=config.post_game_hours),
    )


def is_within_window(post_time: datetime, window: GameWindow) -> bool:
    """
    Check if a post timestamp falls within the game window.

    Args:
        post_time: When the post was created
        window: The game window to check against

    Returns:
        True if post is within the window
    """
    return window.window_start <= post_time <= window.window_end


def get_game_phase(post_time: datetime, window: GameWindow) -> str:
    """
    Determine the phase of the game based on post time.

    Args:
        post_time: When the post was created
        window: The game window

    Returns:
        Phase name: 'pre_game', 'in_game', 'post_game', or 'outside'
    """
    if post_time < window.window_start:
        return "outside"
    elif post_time < window.game_start:
        return "pre_game"
    elif post_time <= window.game_start + timedelta(hours=2.5):
        # Typical NBA game is ~2.5 hours
        return "in_game"
    elif post_time <= window.window_end:
        return "post_game"
    else:
        return "outside"

