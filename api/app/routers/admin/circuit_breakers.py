"""Admin endpoint: circuit breaker telemetry.

GET /api/admin/circuit-breakers — returns current in-memory state for
every registered breaker plus the 50 most recent trip events from DB.

Requires admin API key (enforced at router registration level in main.py).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.telemetry import CircuitBreakerTripEvent
from app.services.circuit_breaker_registry import registry

logger = logging.getLogger(__name__)

router = APIRouter()

_ALIAS_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BreakerStateResponse(BaseModel):
    model_config = _ALIAS_CFG

    name: str
    is_open: bool
    trip_count: int
    last_trip_reason: Optional[str] = None
    last_trip_at: Optional[datetime] = None
    last_reset_at: Optional[datetime] = None


class TripEventResponse(BaseModel):
    model_config = _ALIAS_CFG

    id: int
    breaker_name: str
    reason: str
    tripped_at: datetime


class CircuitBreakersResponse(BaseModel):
    model_config = _ALIAS_CFG

    breakers: list[BreakerStateResponse]
    recent_trips: list[TripEventResponse]


@router.get("/circuit-breakers", response_model=CircuitBreakersResponse)
async def get_circuit_breakers(
    db: AsyncSession = Depends(get_db),
) -> CircuitBreakersResponse:
    """Return current state for all registered circuit breakers and recent trip history."""
    breaker_states = [
        BreakerStateResponse(
            name=s.name,
            is_open=s.is_open,
            trip_count=s.trip_count,
            last_trip_reason=s.last_trip_reason,
            last_trip_at=s.last_trip_at,
            last_reset_at=s.last_reset_at,
        )
        for s in registry.get_all()
    ]

    result = await db.execute(
        select(CircuitBreakerTripEvent)
        .order_by(desc(CircuitBreakerTripEvent.tripped_at))
        .limit(50)
    )
    rows = result.scalars().all()
    recent_trips = [
        TripEventResponse(
            id=row.id,
            breaker_name=row.breaker_name,
            reason=row.reason,
            tripped_at=row.tripped_at,
        )
        for row in rows
    ]

    return CircuitBreakersResponse(breakers=breaker_states, recent_trips=recent_trips)
