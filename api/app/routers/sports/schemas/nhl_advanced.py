"""NHL advanced stats Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NHLAdvancedTeamStats(BaseModel):
    """Team-level advanced stats (MoneyPuck xGoals-derived)."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    is_home: bool = Field(..., alias="isHome")

    # Shot quality
    xgoals_for: float | None = Field(None, alias="xgoalsFor")
    xgoals_against: float | None = Field(None, alias="xgoalsAgainst")
    xgoals_pct: float | None = Field(None, alias="xgoalsPct")

    # Possession
    corsi_for: int | None = Field(None, alias="corsiFor")
    corsi_against: int | None = Field(None, alias="corsiAgainst")
    corsi_pct: float | None = Field(None, alias="corsiPct")
    fenwick_for: int | None = Field(None, alias="fenwickFor")
    fenwick_against: int | None = Field(None, alias="fenwickAgainst")
    fenwick_pct: float | None = Field(None, alias="fenwickPct")

    # Shooting
    shots_for: int | None = Field(None, alias="shotsFor")
    shots_against: int | None = Field(None, alias="shotsAgainst")
    shooting_pct: float | None = Field(None, alias="shootingPct")
    save_pct: float | None = Field(None, alias="savePct")
    pdo: float | None = None

    # Danger zones
    high_danger_shots_for: int | None = Field(None, alias="highDangerShotsFor")
    high_danger_goals_for: int | None = Field(None, alias="highDangerGoalsFor")
    high_danger_shots_against: int | None = Field(None, alias="highDangerShotsAgainst")
    high_danger_goals_against: int | None = Field(None, alias="highDangerGoalsAgainst")


class NHLSkaterAdvancedStats(BaseModel):
    """Skater-level advanced stats (MoneyPuck-derived)."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    player_name: str = Field(..., alias="playerName")
    is_home: bool = Field(..., alias="isHome")

    # xGoals
    xgoals_for: float | None = Field(None, alias="xgoalsFor")
    xgoals_against: float | None = Field(None, alias="xgoalsAgainst")
    on_ice_xgoals_pct: float | None = Field(None, alias="onIceXgoalsPct")

    # Shots
    shots: int | None = None
    goals: int | None = None
    shooting_pct: float | None = Field(None, alias="shootingPct")

    # Per-60 rates
    goals_per_60: float | None = Field(None, alias="goalsPer60")
    assists_per_60: float | None = Field(None, alias="assistsPer60")
    points_per_60: float | None = Field(None, alias="pointsPer60")
    shots_per_60: float | None = Field(None, alias="shotsPer60")

    # Impact
    game_score: float | None = Field(None, alias="gameScore")


class NHLGoalieAdvancedStats(BaseModel):
    """Goalie-level advanced stats (MoneyPuck-derived)."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    player_name: str = Field(..., alias="playerName")
    is_home: bool = Field(..., alias="isHome")

    # Core
    xgoals_against: float | None = Field(None, alias="xgoalsAgainst")
    goals_against: int | None = Field(None, alias="goalsAgainst")
    goals_saved_above_expected: float | None = Field(None, alias="goalsSavedAboveExpected")
    save_pct: float | None = Field(None, alias="savePct")

    # Danger zone saves
    high_danger_save_pct: float | None = Field(None, alias="highDangerSavePct")
    medium_danger_save_pct: float | None = Field(None, alias="mediumDangerSavePct")
    low_danger_save_pct: float | None = Field(None, alias="lowDangerSavePct")
    shots_against: int | None = Field(None, alias="shotsAgainst")
