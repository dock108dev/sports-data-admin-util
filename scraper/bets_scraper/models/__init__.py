"""Common typed models shared across scrapers."""

from .schemas import (
    GameIdentification,
    IngestionConfig,
    NormalizedGame,
    NormalizedOddsSnapshot,
    NormalizedPlayerBoxscore,
    NormalizedPlayerSeasonStats,
    NormalizedPlay,
    NormalizedPlayByPlay,
    NormalizedTeamBoxscore,
    NormalizedTeamSeasonStats,
    TeamIdentity,
)

__all__ = [
    "TeamIdentity",
    "GameIdentification",
    "NormalizedGame",
    "NormalizedTeamBoxscore",
    "NormalizedPlayerBoxscore",
    "NormalizedTeamSeasonStats",
    "NormalizedPlayerSeasonStats",
    "NormalizedOddsSnapshot",
    "NormalizedPlay",
    "NormalizedPlayByPlay",
    "IngestionConfig",
]
