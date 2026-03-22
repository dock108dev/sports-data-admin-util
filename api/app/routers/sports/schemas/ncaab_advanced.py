"""NCAAB advanced stats Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NCAABAdvancedTeamStats(BaseModel):
    """Team-level four-factor advanced stats."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    is_home: bool = Field(..., alias="isHome")

    # Efficiency
    possessions: float | None = None
    off_rating: float | None = Field(None, alias="offRating")
    def_rating: float | None = Field(None, alias="defRating")
    net_rating: float | None = Field(None, alias="netRating")
    pace: float | None = None

    # Four factors (offense)
    off_efg_pct: float | None = Field(None, alias="offEfgPct")
    off_tov_pct: float | None = Field(None, alias="offTovPct")
    off_orb_pct: float | None = Field(None, alias="offOrbPct")
    off_ft_rate: float | None = Field(None, alias="offFtRate")

    # Four factors (defense)
    def_efg_pct: float | None = Field(None, alias="defEfgPct")
    def_tov_pct: float | None = Field(None, alias="defTovPct")
    def_orb_pct: float | None = Field(None, alias="defOrbPct")
    def_ft_rate: float | None = Field(None, alias="defFtRate")

    # Shooting splits
    fg_pct: float | None = Field(None, alias="fgPct")
    three_pt_pct: float | None = Field(None, alias="threePtPct")
    ft_pct: float | None = Field(None, alias="ftPct")
    three_pt_rate: float | None = Field(None, alias="threePtRate")


class NCAABAdvancedPlayerStats(BaseModel):
    """Player-level advanced stats."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    player_name: str = Field(..., alias="playerName")
    is_home: bool = Field(..., alias="isHome")

    # Minutes
    minutes: float | None = None

    # Efficiency
    off_rating: float | None = Field(None, alias="offRating")
    usg_pct: float | None = Field(None, alias="usgPct")

    # Shooting
    ts_pct: float | None = Field(None, alias="tsPct")
    efg_pct: float | None = Field(None, alias="efgPct")

    # Impact
    game_score: float | None = Field(None, alias="gameScore")

    # Volume
    points: int | None = None
    rebounds: int | None = None
    assists: int | None = None
    steals: int | None = None
    blocks: int | None = None
    turnovers: int | None = None
