"""NBA advanced stats Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NBAAdvancedTeamStats(BaseModel):
    """Team-level advanced stats from stats.nba.com endpoints."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    is_home: bool = Field(..., alias="isHome")

    # Efficiency
    off_rating: float | None = Field(None, alias="offRating")
    def_rating: float | None = Field(None, alias="defRating")
    net_rating: float | None = Field(None, alias="netRating")
    pace: float | None = None
    pie: float | None = None

    # Shooting
    efg_pct: float | None = Field(None, alias="efgPct")
    ts_pct: float | None = Field(None, alias="tsPct")
    fg_pct: float | None = Field(None, alias="fgPct")
    fg3_pct: float | None = Field(None, alias="fg3Pct")
    ft_pct: float | None = Field(None, alias="ftPct")

    # Rebounding
    orb_pct: float | None = Field(None, alias="orbPct")
    drb_pct: float | None = Field(None, alias="drbPct")
    reb_pct: float | None = Field(None, alias="rebPct")

    # Playmaking
    ast_pct: float | None = Field(None, alias="astPct")
    ast_ratio: float | None = Field(None, alias="astRatio")
    ast_tov_ratio: float | None = Field(None, alias="astTovRatio")

    # Ball security
    tov_pct: float | None = Field(None, alias="tovPct")

    # Free throws
    ft_rate: float | None = Field(None, alias="ftRate")

    # Hustle (team totals)
    contested_shots: int | None = Field(None, alias="contestedShots")
    deflections: int | None = None
    charges_drawn: int | None = Field(None, alias="chargesDrawn")
    loose_balls_recovered: int | None = Field(None, alias="looseBallsRecovered")

    # Paint / transition
    paint_points: int | None = Field(None, alias="paintPoints")
    fastbreak_points: int | None = Field(None, alias="fastbreakPoints")
    second_chance_points: int | None = Field(None, alias="secondChancePoints")
    points_off_turnovers: int | None = Field(None, alias="pointsOffTurnovers")
    bench_points: int | None = Field(None, alias="benchPoints")


class NBAAdvancedPlayerStats(BaseModel):
    """Player-level advanced stats from stats.nba.com endpoints."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    player_name: str = Field(..., alias="playerName")
    is_home: bool = Field(..., alias="isHome")

    # Minutes
    minutes: float | None = None

    # Efficiency
    off_rating: float | None = Field(None, alias="offRating")
    def_rating: float | None = Field(None, alias="defRating")
    net_rating: float | None = Field(None, alias="netRating")
    usg_pct: float | None = Field(None, alias="usgPct")
    pie: float | None = None

    # Shooting efficiency
    ts_pct: float | None = Field(None, alias="tsPct")
    efg_pct: float | None = Field(None, alias="efgPct")

    # Shooting context
    contested_2pt_fga: int | None = Field(None, alias="contested2ptFga")
    contested_2pt_fgm: int | None = Field(None, alias="contested2ptFgm")
    uncontested_2pt_fga: int | None = Field(None, alias="uncontested2ptFga")
    uncontested_2pt_fgm: int | None = Field(None, alias="uncontested2ptFgm")
    contested_3pt_fga: int | None = Field(None, alias="contested3ptFga")
    contested_3pt_fgm: int | None = Field(None, alias="contested3ptFgm")
    uncontested_3pt_fga: int | None = Field(None, alias="uncontested3ptFga")
    uncontested_3pt_fgm: int | None = Field(None, alias="uncontested3ptFgm")

    # Pull-up / catch-and-shoot
    pull_up_fga: int | None = Field(None, alias="pullUpFga")
    pull_up_fgm: int | None = Field(None, alias="pullUpFgm")
    catch_shoot_fga: int | None = Field(None, alias="catchShootFga")
    catch_shoot_fgm: int | None = Field(None, alias="catchShootFgm")

    # Tracking
    speed: float | None = None
    distance: float | None = None
    touches: float | None = None
    time_of_possession: float | None = Field(None, alias="timeOfPossession")

    # Hustle
    contested_shots: int | None = Field(None, alias="contestedShots")
    deflections: int | None = None
    charges_drawn: int | None = Field(None, alias="chargesDrawn")
    loose_balls_recovered: int | None = Field(None, alias="looseBallsRecovered")
    screen_assists: int | None = Field(None, alias="screenAssists")
