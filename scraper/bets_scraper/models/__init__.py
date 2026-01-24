"""Common typed models shared across scrapers."""

from .schemas import (
    GameIdentification,
    IngestionConfig,
    NormalizedGame,
    NormalizedOddsSnapshot,
    NormalizedPlayerBoxscore,
    NormalizedPlay,
    NormalizedPlayByPlay,
    NormalizedTeamBoxscore,
    TeamIdentity,
)

__all__ = [
    "TeamIdentity",
    "GameIdentification",
    "NormalizedGame",
    "NormalizedTeamBoxscore",
    "NormalizedPlayerBoxscore",
    "NormalizedOddsSnapshot",
    "NormalizedPlay",
    "NormalizedPlayByPlay",
    "IngestionConfig",
]
