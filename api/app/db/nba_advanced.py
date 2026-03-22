"""NBA advanced game stats (boxscoreadvancedv3 / hustlev2 / tracking-derived, post-game).

Contains team-level and player-level advanced stats sourced from
stats.nba.com boxscore endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from .base import Base


class NBAGameAdvancedStats(Base):
    """Team-level advanced stats for an NBA game.

    Derived from stats.nba.com boxscoreadvancedv3, boxscorehustlev2, and
    boxscoreplayertrackingv3 endpoints. Computed post-game only.

    Two rows per game (home + away). Categories:
    - Efficiency: offensive/defensive rating, pace, PIE
    - Shooting: eFG%, TS%, FG%, 3P%, FT%
    - Rebounding: ORB%, DRB%, REB%
    - Playmaking: AST%, AST ratio, AST/TOV ratio
    - Ball security: TOV%
    - Free throws: FT rate (FTA/FGA)
    - Hustle: contested shots, deflections, charges drawn, loose balls
    - Paint/transition: paint points, fastbreak points, second-chance points
    """

    __tablename__ = "nba_game_advanced_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Efficiency
    off_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    def_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    pace: Mapped[float | None] = mapped_column(Float, nullable=True)
    pie: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Shooting
    efg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fg3_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ft_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Rebounding
    orb_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    drb_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    reb_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Playmaking
    ast_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ast_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ast_tov_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Ball security
    tov_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Free throws
    ft_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Hustle (team totals aggregated from player hustle stats)
    contested_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deflections: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charges_drawn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loose_balls_recovered: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Paint / transition
    paint_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fastbreak_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    second_chance_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points_off_turnovers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bench_points: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Extensibility
    raw_extras: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    game = relationship("SportsGame", back_populates="nba_advanced_stats")
    team = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_nba_advanced_game_team"),
        Index("idx_nba_advanced_game", "game_id"),
        Index("idx_nba_advanced_team", "team_id"),
    )


class NBAPlayerAdvancedStats(Base):
    """Player-level advanced stats for an NBA game.

    Combines data from boxscoreadvancedv3 (efficiency, shooting efficiency),
    boxscorehustlev2 (hustle metrics), and boxscoreplayertrackingv3 (tracking).
    """

    __tablename__ = "nba_player_advanced_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    player_external_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    player_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Minutes
    minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Efficiency
    off_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    def_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    usg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    pie: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Shooting efficiency
    ts_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    efg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Shooting context (contested/uncontested)
    contested_2pt_fga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contested_2pt_fgm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uncontested_2pt_fga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uncontested_2pt_fgm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contested_3pt_fga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contested_3pt_fgm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uncontested_3pt_fga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uncontested_3pt_fgm: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Pull-up / catch-and-shoot
    pull_up_fga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pull_up_fgm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    catch_shoot_fga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    catch_shoot_fgm: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Tracking
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    touches: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_of_possession: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Hustle
    contested_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deflections: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charges_drawn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loose_balls_recovered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screen_assists: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Extensibility
    raw_extras: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    game = relationship("SportsGame", back_populates="nba_player_advanced_stats")
    team = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint(
            "game_id", "team_id", "player_external_ref",
            name="uq_nba_player_advanced_game_team_player",
        ),
        Index("idx_nba_player_advanced_game", "game_id"),
        Index("idx_nba_player_advanced_team", "team_id"),
    )
