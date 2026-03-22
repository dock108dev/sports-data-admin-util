"""NCAAB advanced game stats (four-factor analytics, post-game).

Contains team-level and player-level advanced stats derived from
CBB API boxscore data. Computes tempo-free four-factor analytics
(eFG%, TOV%, ORB%, FT Rate) plus efficiency ratings for every D1 game.
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


class NCAABGameAdvancedStats(Base):
    """Team-level four-factor advanced stats for an NCAAB game.

    Derived from CBB API boxscore data already stored in
    sports_team_boxscores. Computed post-game only (deterministic).

    Two rows per game (home + away). Covers:
    - Efficiency: possessions, off/def/net rating, pace
    - Four factors (offense): eFG%, TOV%, ORB%, FT rate
    - Four factors (defense): opponent's offensive numbers
    - Shooting splits: FG%, 3PT%, FT%, 3PT rate
    """

    __tablename__ = "ncaab_game_advanced_stats"

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
    possessions: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    def_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    pace: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Four factors (offense)
    off_efg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_tov_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_orb_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_ft_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Four factors (defense -- opponent's offensive numbers)
    def_efg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    def_tov_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    def_orb_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    def_ft_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Shooting splits
    fg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    three_pt_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ft_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    three_pt_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

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
    game = relationship("SportsGame", back_populates="ncaab_advanced_stats")
    team = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_ncaab_advanced_game_team"),
        Index("idx_ncaab_advanced_game", "game_id"),
        Index("idx_ncaab_advanced_team", "team_id"),
    )


class NCAABPlayerAdvancedStats(Base):
    """Player-level advanced stats for an NCAAB game.

    Derived from CBB API player boxscore data. Includes efficiency,
    shooting, impact metrics, and volume stats.
    """

    __tablename__ = "ncaab_player_advanced_stats"

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
    usg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Shooting
    ts_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    efg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Impact
    game_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Volume
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rebounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assists: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turnovers: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
    game = relationship("SportsGame", back_populates="ncaab_player_advanced_stats")
    team = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint(
            "game_id", "team_id", "player_external_ref",
            name="uq_ncaab_player_advanced_game_team_player",
        ),
        Index("idx_ncaab_player_advanced_game", "game_id"),
        Index("idx_ncaab_player_advanced_team", "team_id"),
    )
