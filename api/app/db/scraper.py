"""Scraper and job tracking models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
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
from sqlalchemy.sql import text

from .base import Base
from .sports import SportsLeague


class SportsScrapeRun(Base):
    """Tracks ingestion/scrape job runs."""

    __tablename__ = "sports_scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scraper_type: Mapped[str] = mapped_column(String(50), nullable=False)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    season_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    requested_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    league: Mapped[SportsLeague] = relationship(
        "SportsLeague", back_populates="scrape_runs"
    )

    __table_args__ = (
        Index("idx_scrape_runs_league_status", "league_id", "status"),
        Index("idx_scrape_runs_created", "created_at"),
    )


class SportsJobRun(Base):
    """Tracks phase-level job execution for monitoring."""

    __tablename__ = "sports_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    leagues: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_job_runs_phase_started", "phase", "started_at"),)


class SportsGameConflict(Base):
    """Conflict records for duplicate or ambiguous game identity."""

    __tablename__ = "sports_game_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conflict_game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    conflict_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "conflict_game_id",
            "external_id",
            "source",
            name="uq_game_conflict",
        ),
        Index("idx_game_conflicts_league_created", "league_id", "created_at"),
    )


class SportsMissingPbp(Base):
    """Records games missing play-by-play data when status requires it."""

    __tablename__ = "sports_missing_pbp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("idx_missing_pbp_league_status", "league_id", "status"),)
