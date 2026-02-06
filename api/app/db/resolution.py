"""Entity resolution and PBP snapshot models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from .base import Base
from .sports import SportsGame
from .pipeline import GamePipelineRun
from .scraper import SportsScrapeRun


class PBPSnapshotType(str, Enum):
    """Type of PBP snapshot."""

    raw = "raw"
    normalized = "normalized"
    resolved = "resolved"


class ResolutionStatus(str, Enum):
    """Status of entity resolution."""

    success = "success"
    failed = "failed"
    ambiguous = "ambiguous"
    partial = "partial"


class PBPSnapshot(Base):
    """Snapshot of play-by-play data for inspectability."""

    __tablename__ = "sports_pbp_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sports_game_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scrape_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sports_scrape_runs.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plays_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'::jsonb")
    )
    resolution_stats: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame")
    pipeline_run: Mapped[GamePipelineRun | None] = relationship("GamePipelineRun")
    scrape_run: Mapped["SportsScrapeRun | None"] = relationship("SportsScrapeRun")

    __table_args__ = (Index("idx_pbp_snapshots_game_type", "game_id", "snapshot_type"),)


class EntityResolution(Base):
    """Tracks how teams and players are resolved from source identifiers."""

    __tablename__ = "sports_entity_resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sports_game_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )

    source_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    source_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    resolved_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    resolution_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )

    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_play_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_play_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame")
    pipeline_run: Mapped[GamePipelineRun | None] = relationship("GamePipelineRun")

    __table_args__ = (
        Index("idx_entity_resolutions_game_type", "game_id", "entity_type"),
    )
