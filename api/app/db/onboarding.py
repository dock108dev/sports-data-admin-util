"""Onboarding models — prospect-facing submissions (club claims, etc.)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ClubClaim(Base):
    """A prospect's 'claim your club' onboarding submission.

    Written by the public `POST /api/onboarding/club-claims` endpoint.
    `claim_id` is the public handle returned to the caller; `id` is never
    exposed over the wire.
    """

    __tablename__ = "club_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    club_name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str] = mapped_column(String(320), index=True)
    expected_entries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(20), default="new", server_default="new"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
