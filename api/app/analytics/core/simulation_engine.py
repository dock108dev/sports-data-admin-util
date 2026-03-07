"""Base simulation engine interface.

Each sport provides its own simulation implementation that plugs into
this interface. The core engine handles iteration counting, result
aggregation, and output formatting.

Supports two usage modes:

1. **Legacy** — ``SimulationEngine("mlb").simulate_game(ctx)`` returns a
   ``SimulationResult`` placeholder (backward-compatible).
2. **Full Monte Carlo** — ``SimulationEngine("mlb").run_simulation(ctx,
   iterations=10000, seed=42)`` delegates to a sport-specific game
   simulator via ``SimulationRunner`` and returns aggregated results.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from .simulation_runner import SimulationRunner
from .types import SimulationResult

logger = logging.getLogger(__name__)

# Registry mapping sport codes to (module_path, class_name).
_SPORT_SIMULATORS: dict[str, tuple[str, str]] = {
    "mlb": ("app.analytics.sports.mlb.game_simulator", "MLBGameSimulator"),
}


class SimulationEngine:
    """Sport-agnostic simulation orchestrator.

    Routes to sport-specific game simulators and aggregates results
    via ``SimulationRunner``.
    """

    def __init__(self, sport: str) -> None:
        self.sport = sport.lower()
        self._simulator: Any | None = None

    def _get_sport_simulator(self) -> Any:
        """Lazily load and cache the sport-specific game simulator."""
        if self._simulator is not None:
            return self._simulator

        entry = _SPORT_SIMULATORS.get(self.sport)
        if entry is None:
            logger.warning("no_simulator_module", extra={"sport": self.sport})
            return None

        module_path, class_name = entry
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        self._simulator = cls()
        return self._simulator

    def simulate_game(
        self,
        game_context: dict[str, Any],
        iterations: int = 1000,
    ) -> SimulationResult:
        """Run a game simulation over N iterations.

        Backward-compatible entry point. For full Monte Carlo results
        with aggregated statistics, use ``run_simulation()`` instead.

        Args:
            game_context: Sport-specific game setup data.
            iterations: Number of simulation iterations.

        Returns:
            Aggregated simulation result.
        """
        simulator = self._get_sport_simulator()
        if simulator is None:
            return SimulationResult(sport=self.sport, iterations=iterations)

        runner = SimulationRunner()
        summary = runner.run_simulations(
            simulator, game_context, iterations=iterations,
        )
        return SimulationResult(
            sport=self.sport,
            iterations=iterations,
            summary=summary,
        )

    def run_simulation(
        self,
        game_context: dict[str, Any],
        iterations: int = 10_000,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Run a full Monte Carlo simulation with aggregated results.

        Args:
            game_context: Sport-specific game setup data including
                probability distributions from the matchup engine.
            iterations: Number of games to simulate.
            seed: Optional seed for deterministic results.

        Returns:
            Dict with win probabilities, average scores, and
            score distribution.
        """
        simulator = self._get_sport_simulator()
        if simulator is None:
            return {
                "home_win_probability": 0.0,
                "away_win_probability": 0.0,
                "average_home_score": 0.0,
                "average_away_score": 0.0,
                "score_distribution": {},
                "iterations": 0,
            }

        runner = SimulationRunner()
        return runner.run_simulations(
            simulator, game_context,
            iterations=iterations, seed=seed,
        )

    def _run_single_iteration(
        self,
        game_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute one simulation iteration.

        Override in sport-specific subclasses.
        """
        return {}
