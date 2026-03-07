"""Simulation result repository for persistent storage.

Stores simulation outputs for historical review and reuse. Uses an
in-memory store by default; subclass or swap the backend for database
persistence when needed.

Usage::

    repo = SimulationRepository()
    sim_id = repo.save_simulation(result_dict)
    stored = repo.get_simulation(sim_id)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class SimulationRepository:
    """Stores and retrieves simulation results.

    Default implementation uses an in-memory dict. Replace ``_store``
    with a database-backed implementation for production persistence.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def save_simulation(
        self,
        result: dict[str, Any],
        *,
        job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a simulation result.

        Args:
            result: Simulation output dict.
            job_id: Optional job ID to associate with.
            metadata: Optional metadata (sport, teams, timestamp, etc).

        Returns:
            Unique simulation ID.
        """
        sim_id = job_id or str(uuid.uuid4())
        record: dict[str, Any] = {
            "simulation_id": sim_id,
            "result": result,
            "metadata": metadata or {},
            "created_at": time.time(),
        }
        self._store[sim_id] = record
        logger.info("simulation_saved", extra={"simulation_id": sim_id})
        return sim_id

    def get_simulation(self, simulation_id: str) -> dict[str, Any] | None:
        """Retrieve a stored simulation by ID.

        Args:
            simulation_id: The unique simulation identifier.

        Returns:
            The stored record dict or ``None`` if not found.
        """
        return self._store.get(simulation_id)

    def list_simulations(
        self,
        sport: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List stored simulations, optionally filtered by sport.

        Args:
            sport: Filter by sport code.
            limit: Maximum number of results.

        Returns:
            List of simulation records, newest first.
        """
        records = list(self._store.values())

        if sport:
            records = [
                r for r in records
                if r.get("metadata", {}).get("sport") == sport
            ]

        records.sort(key=lambda r: r.get("created_at", 0), reverse=True)
        return records[:limit]

    def delete_simulation(self, simulation_id: str) -> bool:
        """Remove a stored simulation.

        Returns:
            ``True`` if found and removed.
        """
        return self._store.pop(simulation_id, None) is not None
