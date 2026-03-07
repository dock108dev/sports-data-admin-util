"""Simulation job manager for sync and async execution.

Manages simulation lifecycle: submission, execution, status tracking,
and result retrieval. Integrates with ``SimulationCache`` to avoid
redundant work and ``SimulationRepository`` for persistence.

Usage::

    manager = SimulationJobManager()
    job_id = manager.submit_job(params)
    result = manager.get_job_result(job_id)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from enum import Enum
from typing import Any

from .simulation_cache import SimulationCache
from .simulation_repository import SimulationRepository

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Simulation job lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class _JobRecord:
    """Internal record tracking a simulation job."""

    __slots__ = (
        "job_id", "status", "params", "result", "error",
        "created_at", "completed_at", "future",
    )

    def __init__(self, job_id: str, params: dict[str, Any]) -> None:
        self.job_id = job_id
        self.status = JobStatus.PENDING
        self.params = params
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.completed_at: float | None = None
        self.future: Future[dict[str, Any]] | None = None


class SimulationJobManager:
    """Manages simulation job submission, execution, and retrieval.

    Supports both synchronous (blocking) and asynchronous (background
    thread) execution modes.

    Args:
        cache: Shared cache instance. Creates one if not provided.
        repository: Shared repository instance. Creates one if not provided.
        max_workers: Thread pool size for async jobs.
    """

    def __init__(
        self,
        cache: SimulationCache | None = None,
        repository: SimulationRepository | None = None,
        max_workers: int = 2,
    ) -> None:
        self._cache = cache or SimulationCache()
        self._repository = repository or SimulationRepository()
        self._jobs: dict[str, _JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    @property
    def cache(self) -> SimulationCache:
        """Expose the cache for external reads."""
        return self._cache

    @property
    def repository(self) -> SimulationRepository:
        """Expose the repository for external reads."""
        return self._repository

    def submit_job(
        self,
        params: dict[str, Any],
        *,
        sync: bool = True,
    ) -> str:
        """Submit a simulation job.

        Checks the cache first. If a cached result exists, the job
        completes immediately. Otherwise runs the simulation.

        Args:
            params: Simulation parameters (sport, teams, iterations, etc).
            sync: If ``True``, block until complete. If ``False``,
                run in a background thread.

        Returns:
            Job ID for result retrieval.
        """
        job_id = str(uuid.uuid4())

        # Check cache
        cache_key = self._cache.generate_cache_key(params)
        cached = self._cache.get(cache_key)
        if cached is not None:
            record = _JobRecord(job_id, params)
            record.status = JobStatus.COMPLETED
            record.result = cached
            record.completed_at = time.time()
            with self._lock:
                self._jobs[job_id] = record
            logger.info("job_cache_hit", extra={"job_id": job_id})
            return job_id

        record = _JobRecord(job_id, params)

        if sync:
            record.status = JobStatus.RUNNING
            with self._lock:
                self._jobs[job_id] = record
            self._run_job(record, cache_key)
        else:
            with self._lock:
                self._jobs[job_id] = record
            future = self._executor.submit(self._run_job, record, cache_key)
            record.future = future

        return job_id

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the current status of a job.

        Returns:
            Dict with ``job_id``, ``status``, and optionally ``error``.
        """
        with self._lock:
            record = self._jobs.get(job_id)

        if record is None:
            return {"job_id": job_id, "status": "not_found"}

        result: dict[str, Any] = {
            "job_id": job_id,
            "status": record.status.value,
            "created_at": record.created_at,
        }
        if record.completed_at:
            result["completed_at"] = record.completed_at
        if record.error:
            result["error"] = record.error
        return result

    def get_job_result(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve the result of a completed job.

        Args:
            job_id: The job identifier from ``submit_job``.

        Returns:
            Simulation result dict, or ``None`` if not completed.
        """
        with self._lock:
            record = self._jobs.get(job_id)

        if record is None:
            return None

        if record.status != JobStatus.COMPLETED:
            return None

        return record.result

    def _run_job(
        self,
        record: _JobRecord,
        cache_key: str,
    ) -> dict[str, Any]:
        """Execute a simulation job.

        Runs the appropriate simulation based on params, caches the
        result, and stores it in the repository.
        """
        record.status = JobStatus.RUNNING
        try:
            result = self._execute_simulation(record.params)
            record.result = result
            record.status = JobStatus.COMPLETED
            record.completed_at = time.time()

            # Cache the result
            mode = record.params.get("mode", "pregame")
            self._cache.set(cache_key, result, mode=mode)

            # Persist to repository
            metadata = {
                "sport": record.params.get("sport", "unknown"),
                "mode": mode,
            }
            if "home_team" in record.params:
                metadata["home_team"] = record.params["home_team"]
            if "away_team" in record.params:
                metadata["away_team"] = record.params["away_team"]

            self._repository.save_simulation(
                result, job_id=record.job_id, metadata=metadata,
            )

            logger.info("job_completed", extra={"job_id": record.job_id})
            return result

        except Exception as exc:
            record.status = JobStatus.FAILED
            record.error = str(exc)
            record.completed_at = time.time()
            logger.error(
                "job_failed",
                extra={"job_id": record.job_id, "error": str(exc)},
            )
            return {}

    def _execute_simulation(self, params: dict[str, Any]) -> dict[str, Any]:
        """Route to the appropriate simulation engine based on params."""
        sport = params.get("sport", "mlb")
        mode = params.get("mode", "pregame")
        iterations = params.get("iterations", 5000)
        seed = params.get("seed")

        if mode == "live":
            from .live_simulation_engine import LiveSimulationEngine
            engine = LiveSimulationEngine(sport)
            game_state = {
                k: v for k, v in params.items()
                if k in ("inning", "half", "outs", "bases", "score",
                         "home_probabilities", "away_probabilities")
            }
            return engine.simulate_from_state(
                game_state, iterations=iterations, seed=seed,
            )

        # Pregame simulation
        from ..services.analytics_service import AnalyticsService
        svc = AnalyticsService()
        game_context: dict[str, Any] = {}
        if "home_team" in params:
            game_context["home_team"] = params["home_team"]
        if "away_team" in params:
            game_context["away_team"] = params["away_team"]
        if "home_probabilities" in params:
            game_context["home_probabilities"] = params["home_probabilities"]
        if "away_probabilities" in params:
            game_context["away_probabilities"] = params["away_probabilities"]

        return svc.run_full_simulation(
            sport=sport,
            game_context=game_context,
            iterations=iterations,
            seed=seed,
            sportsbook=params.get("sportsbook"),
        )
