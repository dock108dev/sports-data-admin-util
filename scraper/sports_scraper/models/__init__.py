"""Common typed models shared across scrapers."""

from .schemas import (
    GameIdentification,
    IngestionConfig,
    NormalizedGame,
    NormalizedOddsSnapshot,
    NormalizedPlay,
    NormalizedPlayByPlay,
    NormalizedPlayerBoxscore,
    NormalizedTeamBoxscore,
    TeamIdentity,
    classify_market,
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
    "classify_market",
]
