"""Cache models for OpenAI and other services."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .sports import SportsGame


class OpenAIResponseCache(Base):
    """Cache for OpenAI API responses to avoid redundant calls during testing."""

    __tablename__ = "openai_response_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False
    )
    batch_key: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame")

    __table_args__ = (
        UniqueConstraint("game_id", "batch_key", name="uq_openai_cache_game_batch"),
        Index("idx_openai_cache_game_id", "game_id"),
    )
