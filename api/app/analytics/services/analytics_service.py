"""Service layer connecting analytics logic to API endpoints.

Provides a clean interface for the router layer to call without
needing to know about engine internals or sport module resolution.

Pipeline: AggregationEngine → ProfileBuilder → MetricsEngine
          → MatchupEngine → SimulationEngine → SimulationAnalysis
"""

from __future__ import annotations

from typing import Any

from app.analytics.core.analytics_engine import AnalyticsEngine
from app.analytics.core.matchup_engine import MatchupEngine
from app.analytics.core.simulation_analysis import SimulationAnalysis
from app.analytics.core.simulation_engine import SimulationEngine
from app.analytics.core.types import (
    MatchupProfile,
    PlayerProfile,
    TeamProfile,
)


class AnalyticsService:
    """High-level analytics service used by API routes."""

    def get_team_analysis(self, sport: str, team_id: str) -> TeamProfile:
        """Retrieve team analytical profile.

        Args:
            sport: Sport code (e.g., ``"mlb"``).
            team_id: Team identifier.

        Returns:
            Populated TeamProfile.
        """
        engine = AnalyticsEngine(sport)
        return engine.get_team_profile(team_id)

    def get_player_analysis(self, sport: str, player_id: str) -> PlayerProfile:
        """Retrieve player analytical profile.

        Args:
            sport: Sport code.
            player_id: Player identifier.

        Returns:
            Populated PlayerProfile.
        """
        engine = AnalyticsEngine(sport)
        return engine.get_player_profile(player_id)

    def get_matchup_analysis(
        self,
        sport: str,
        entity_a: str,
        entity_b: str,
    ) -> MatchupProfile:
        """Analyze a matchup between two entities.

        Args:
            sport: Sport code.
            entity_a: First entity identifier.
            entity_b: Second entity identifier.

        Returns:
            MatchupProfile with comparison data.
        """
        engine = AnalyticsEngine(sport)
        return engine.get_matchup(entity_a, entity_b)

    def get_matchup_probabilities(
        self,
        sport: str,
        player_a: PlayerProfile,
        player_b: PlayerProfile,
    ) -> MatchupProfile:
        """Calculate matchup probabilities between two player profiles.

        Args:
            sport: Sport code.
            player_a: First player profile.
            player_b: Second player profile.

        Returns:
            MatchupProfile with probability distributions.
        """
        engine = MatchupEngine(sport)
        return engine.calculate_player_vs_player(player_a, player_b)

    def run_full_simulation(
        self,
        sport: str,
        game_context: dict[str, Any],
        iterations: int = 10_000,
        seed: int | None = None,
        sportsbook: dict[str, Any] | None = None,
        use_lineup: bool = False,
    ) -> dict[str, Any]:
        """Run a Monte Carlo simulation with full analysis.

        Args:
            sport: Sport code.
            game_context: Probability distributions for home/away teams.
            iterations: Number of games to simulate.
            seed: Optional seed for deterministic results.
            sportsbook: Optional sportsbook lines for comparison.
            use_lineup: If True, use lineup-aware simulation.

        Returns:
            Dict with win probabilities, score distributions, and
            optional sportsbook comparison.
        """
        sim = SimulationEngine(sport)
        result = sim.run_simulation(
            game_context, iterations=iterations, seed=seed,
            keep_results=True, use_lineup=use_lineup,
        )

        raw_results = result.pop("raw_results", None)
        if raw_results is None:
            return result

        # Preserve event_summary and diagnostics computed by the runner
        event_summary = result.get("event_summary")
        diagnostics = result.get("_diagnostics")
        prob_source = result.get("probability_source")
        prob_meta = result.get("probability_meta")

        analysis = SimulationAnalysis(sport)
        summary = analysis.summarize_results(raw_results, sportsbook=sportsbook)

        # Re-attach data that summarize_results doesn't know about
        if event_summary is not None:
            summary["event_summary"] = event_summary
        if diagnostics is not None:
            summary["_diagnostics"] = diagnostics
        if prob_source is not None:
            summary["probability_source"] = prob_source
        if prob_meta is not None:
            summary["probability_meta"] = prob_meta

        return summary

