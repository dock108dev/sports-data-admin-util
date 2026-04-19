"""Quality review queue model — human review escalation for low-scoring flows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from .base import Base


class QualityReviewQueue(Base):
    """Flows escalated for human review because their combined quality score
    fell below the grader escalation threshold.

    Status lifecycle: pending → reviewed | dismissed.
    """

    __tablename__ = "quality_review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flow_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_game_stories.id", ondelete="CASCADE"),
        nullable=False,
    )
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
    )
    sport: Mapped[str] = mapped_column(String(20), nullable=False)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False)
    tier1_score: Mapped[float] = mapped_column(Float, nullable=False)
    tier2_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier_breakdown: Mapped[dict] = mapped_column(
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_quality_review_queue_flow_id", "flow_id"),
        Index("idx_quality_review_queue_status", "status"),
        Index("idx_quality_review_queue_sport", "sport"),
    )
