"""Base simulation engine interface.

Each sport provides its own simulation implementation that plugs into
this interface. The core engine handles iteration counting, result
aggregation, and output formatting.

Supports three usage modes:

1. **Legacy** — ``SimulationEngine("mlb").simulate_game(ctx)`` returns a
   ``SimulationResult`` placeholder (backward-compatible).
2. **Full Monte Carlo** — ``SimulationEngine("mlb").run_simulation(ctx,
   iterations=10000, seed=42)`` delegates to a sport-specific game
   simulator via ``SimulationRunner`` and returns aggregated results.
3. **ML-enhanced** — When ``ml_model`` is set in ``game_context``, the
   engine loads the ML model from the registry and uses its probability
   output for simulation.
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
    via ``SimulationRunner``. Optionally integrates ML models when
    ``game_context["ml_model"]`` is specified.
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

        If ``game_context`` contains ``ml_model`` (a model type string
        like ``"plate_appearance"``), the engine loads the active ML
        model from the registry and injects its probability output
        into the game context before simulating.

        Args:
            game_context: Sport-specific game setup data including
                probability distributions from the matchup engine.
                Optional ``ml_model`` key to enable ML integration.
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

        # ML model integration: inject probabilities if requested
        context = dict(game_context)
        ml_model_type = context.pop("ml_model", None)
        if ml_model_type:
            context = self._apply_ml_model(context, ml_model_type)

        runner = SimulationRunner()
        return runner.run_simulations(
            simulator, context,
            iterations=iterations, seed=seed,
        )

    def _apply_ml_model(
        self,
        game_context: dict[str, Any],
        model_type: str,
    ) -> dict[str, Any]:
        """Load an ML model and inject its predictions into the context.

        Args:
            game_context: Current game context.
            model_type: Model type to load (e.g., ``"plate_appearance"``).

        Returns:
            Updated game context with ML-generated probabilities.
        """
        try:
            from app.analytics.models.core.model_registry import ModelRegistry
            registry = ModelRegistry()
            model = registry.get_active_model(self.sport, model_type)
            if model is None:
                logger.warning(
                    "ml_model_not_found",
                    extra={"sport": self.sport, "model_type": model_type},
                )
                return game_context

            features = game_context.get("features", {})
            probs = model.predict_proba(features)

            # Convert to simulation probability keys if the model supports it
            if hasattr(model, "to_simulation_probs"):
                sim_probs = model.to_simulation_probs(probs)
            else:
                sim_probs = probs

            # Apply to both home and away unless specific overrides exist
            if "home_probabilities" not in game_context:
                game_context["home_probabilities"] = sim_probs
            if "away_probabilities" not in game_context:
                game_context["away_probabilities"] = sim_probs

            game_context["_ml_model_used"] = model_type
            logger.info(
                "ml_model_applied",
                extra={"sport": self.sport, "model_type": model_type},
            )

        except Exception as exc:
            logger.error(
                "ml_model_error",
                extra={"sport": self.sport, "error": str(exc)},
            )

        return game_context

    def _run_single_iteration(
        self,
        game_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute one simulation iteration.

        Override in sport-specific subclasses.
        """
        return {}
