"""Configuration and user state models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .sports import SportsGame, SportsLeague


class CompactModeThreshold(Base):
    """Compact mode threshold configuration per sport."""

    __tablename__ = "compact_mode_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    thresholds: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    league: Mapped[SportsLeague] = relationship("SportsLeague")


class GameReadingPosition(Base):
    """Tracks a user's last-read position for a game timeline."""

    __tablename__ = "game_reading_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column("user_id", Text, nullable=False, index=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    moment: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    scroll_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    game: Mapped[SportsGame] = relationship("SportsGame")

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_reading_position_user_game"),
        Index("idx_reading_positions_user_game", "user_id", "game_id"),
    )
