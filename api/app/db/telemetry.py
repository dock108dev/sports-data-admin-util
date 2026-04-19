"""Telemetry models for operational observability."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CircuitBreakerTripEvent(Base):
    """Persisted record of a circuit breaker trip.

    Written by the background flush task; queryable without restarting
    the service.  Useful for correlating Redis failures with request
    degradation over time.
    """

    __tablename__ = "circuit_breaker_trip_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    breaker_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    tripped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        Index("ix_cb_trip_events_name_tripped", "breaker_name", "tripped_at"),
    )
