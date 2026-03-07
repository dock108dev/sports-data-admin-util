"""MLB Monte Carlo game simulation.

Simulates individual MLB games at the plate-appearance level using
matchup probability distributions. Designed for high-volume use —
all calculations are stateless with no database calls.

Game flow:
    9 innings (or more for ties), each with two half-innings.
    Each half-inning runs plate appearances until 3 outs.
    Events are sampled from probability distributions produced
    by the matchup engine.
"""

from __future__ import annotations

import random
from typing import Any

# Event constants — order matters for weighted selection.
EVENTS = [
    "strikeout",
    "out",
    "walk",
    "single",
    "double",
    "triple",
    "home_run",
]

# Default probability distribution (league-average approximation).
_DEFAULT_PROBS: dict[str, float] = {
    "strikeout_probability": 0.22,
    "walk_probability": 0.08,
    "single_probability": 0.15,
    "double_probability": 0.05,
    "triple_probability": 0.01,
    "home_run_probability": 0.03,
}

_MAX_EXTRA_INNINGS = 10


class MLBGameSimulator:
    """Simulate a single MLB game using plate-appearance probabilities."""

    def simulate_game(
        self,
        game_context: dict[str, Any],
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        """Simulate one complete MLB game.

        Args:
            game_context: Must contain ``home_probabilities`` and
                ``away_probabilities`` dicts with event probability keys.
                Missing keys fall back to league-average defaults.
            rng: Optional ``random.Random`` instance for determinism.

        Returns:
            Dict with ``home_score``, ``away_score``, and ``winner``.
        """
        if rng is None:
            rng = random.Random()

        home_probs = _build_weights(game_context.get("home_probabilities", {}))
        away_probs = _build_weights(game_context.get("away_probabilities", {}))

        home_score = 0
        away_score = 0

        # Regulation: 9 innings
        for inning in range(1, 10):
            away_score += self._simulate_half_inning(away_probs, rng)
            # Bottom of 9th: skip if home already ahead
            if inning == 9 and home_score > away_score:
                break
            home_score += self._simulate_half_inning(home_probs, rng)
            # Walk-off in bottom of 9th
            if inning == 9 and home_score > away_score:
                break

        # Extra innings
        extra = 0
        while home_score == away_score and extra < _MAX_EXTRA_INNINGS:
            away_score += self._simulate_half_inning(away_probs, rng)
            home_score += self._simulate_half_inning(home_probs, rng)
            extra += 1

        winner = "home" if home_score >= away_score else "away"

        return {
            "home_score": home_score,
            "away_score": away_score,
            "winner": winner,
        }

    def _simulate_half_inning(
        self,
        weights: list[float],
        rng: random.Random,
    ) -> int:
        """Simulate one half-inning, returning runs scored."""
        outs = 0
        bases = [False, False, False]  # 1st, 2nd, 3rd
        runs = 0

        while outs < 3:
            event = rng.choices(EVENTS, weights=weights, k=1)[0]

            if event == "strikeout" or event == "out":
                outs += 1

            elif event == "walk":
                runs += _advance_walk(bases)

            elif event == "single":
                runs += _advance_single(bases)

            elif event == "double":
                runs += _advance_double(bases)

            elif event == "triple":
                runs += _advance_triple(bases)

            elif event == "home_run":
                runs += _advance_home_run(bases)

        return runs


# ---------------------------------------------------------------------------
# Base-runner advancement helpers (simplified model)
# ---------------------------------------------------------------------------


def _advance_walk(bases: list[bool]) -> int:
    """Walk: batter to 1st, force advancement only."""
    runs = 0
    if bases[0]:
        if bases[1]:
            if bases[2]:
                runs += 1  # runner scores from 3rd
            bases[2] = True
        bases[1] = True
    bases[0] = True
    return runs


def _advance_single(bases: list[bool]) -> int:
    """Single: runners advance 1 base, runner on 2nd scores."""
    runs = 0
    if bases[2]:
        runs += 1
        bases[2] = False
    if bases[1]:
        runs += 1  # runner on 2nd scores on single
        bases[1] = False
    if bases[0]:
        bases[1] = True
        bases[0] = False
    bases[0] = True
    return runs


def _advance_double(bases: list[bool]) -> int:
    """Double: runners advance 2 bases."""
    runs = 0
    if bases[2]:
        runs += 1
        bases[2] = False
    if bases[1]:
        runs += 1
        bases[1] = False
    if bases[0]:
        bases[2] = True
        bases[0] = False
    bases[1] = True
    return runs


def _advance_triple(bases: list[bool]) -> int:
    """Triple: all runners score."""
    runs = sum(bases)
    bases[0] = False
    bases[1] = False
    bases[2] = True
    return runs


def _advance_home_run(bases: list[bool]) -> int:
    """Home run: all runners + batter score."""
    runs = sum(bases) + 1
    bases[0] = False
    bases[1] = False
    bases[2] = False
    return runs


# ---------------------------------------------------------------------------
# Weight construction
# ---------------------------------------------------------------------------


def _build_weights(probs: dict[str, float]) -> list[float]:
    """Convert a probability dict into ordered weights for ``EVENTS``.

    Maps probability keys to event order. Generic "out" absorbs the
    remaining probability mass after all named events.
    """
    k_prob = max(probs.get("strikeout_probability", _DEFAULT_PROBS["strikeout_probability"]), 0.0)
    bb_prob = max(probs.get("walk_probability", _DEFAULT_PROBS["walk_probability"]), 0.0)
    single = max(probs.get("single_probability", _DEFAULT_PROBS["single_probability"]), 0.0)
    double = max(probs.get("double_probability", _DEFAULT_PROBS["double_probability"]), 0.0)
    triple = max(probs.get("triple_probability", _DEFAULT_PROBS["triple_probability"]), 0.0)
    hr = max(probs.get("home_run_probability", _DEFAULT_PROBS["home_run_probability"]), 0.0)

    named_total = k_prob + bb_prob + single + double + triple + hr
    out_prob = max(1.0 - named_total, 0.0)

    # Order matches EVENTS: strikeout, out, walk, single, double, triple, home_run
    return [k_prob, out_prob, bb_prob, single, double, triple, hr]
