"""EV strategy configuration — book lists, eligibility rules, confidence tiers.

Static, version-controlled config for the Sharp Book EV Baseline Framework.
All books are still ingested/persisted; exclusion is SQL-level at query time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class ConfidenceTier(str, Enum):
    """Confidence tier for EV estimates."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class EVStrategyConfig:
    """Configuration for a single EV calculation strategy."""

    strategy_name: str  # e.g., "pinnacle_devig"
    eligible_sharp_books: tuple[str, ...]  # Reference price sources (display names)
    min_qualifying_books: int  # Per-side minimum non-excluded books
    max_reference_staleness_seconds: int  # observed_at vs now()
    confidence_tier: ConfidenceTier
    allow_longshots: bool  # Informational only in Phase 1
    max_fair_odds_divergence: float  # Max |fair_american - median_american| allowed


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """Result of evaluating whether EV can be computed for a market."""

    eligible: bool
    strategy_config: EVStrategyConfig | None
    disabled_reason: str | None  # "no_strategy" | "reference_missing" | "reference_stale" | "insufficient_books" | "fair_odds_outlier"
    ev_method: str | None  # e.g., "pinnacle_devig"
    confidence_tier: str | None  # "high" | "medium" | "low"


# ---------------------------------------------------------------------------
# Book lists
# ---------------------------------------------------------------------------

# Books excluded from EV comparisons (offshore / exchanges / prediction markets).
# All books still ingested and persisted; exclusion is SQL-level at query time.
EXCLUDED_BOOKS: frozenset[str] = frozenset(
    {
        # Offshore — unreliable lines for EV
        "BetOnline.ag",
        "Bovada",
        # Prediction markets / exchanges — not traditional sportsbooks
        "Kalshi",
        "Polymarket",
    }
)

# Books included in EV comparisons (reputable licensed sportsbooks + sharp books).
# These are the only books available via our configured Odds API regions
# (us, us_ex, eu, uk).
INCLUDED_BOOKS: frozenset[str] = frozenset(
    {
        # US sportsbooks
        "BetMGM",
        "BetRivers",
        "Caesars",
        "DraftKings",
        "FanDuel",
        # EU / sharp
        "Pinnacle",
        "888sport",
        "William Hill",
        # UK sportsbooks
        "Betfair Exchange",
        "Betfair Sportsbook",
        "Ladbrokes",
        "Paddy Power",
        "William Hill (UK)",
    }
)


# ---------------------------------------------------------------------------
# Strategy map: (league, market_category) -> EVStrategyConfig | None
# ---------------------------------------------------------------------------

_PINNACLE_MAINLINE_NBA_NHL = EVStrategyConfig(
    strategy_name="pinnacle_devig",
    eligible_sharp_books=("Pinnacle",),
    min_qualifying_books=3,
    max_reference_staleness_seconds=3600,  # 1 hour
    confidence_tier=ConfidenceTier.HIGH,
    allow_longshots=False,
    max_fair_odds_divergence=150,  # Tight — mainlines are efficient
)

_PINNACLE_MAINLINE_NCAAB = EVStrategyConfig(
    strategy_name="pinnacle_devig",
    eligible_sharp_books=("Pinnacle",),
    min_qualifying_books=3,
    max_reference_staleness_seconds=1800,  # 30 minutes
    confidence_tier=ConfidenceTier.MEDIUM,
    allow_longshots=False,
    max_fair_odds_divergence=200,  # Wider — less liquid
)

_PINNACLE_PLAYER_PROP = EVStrategyConfig(
    strategy_name="pinnacle_devig",
    eligible_sharp_books=("Pinnacle",),
    min_qualifying_books=3,
    max_reference_staleness_seconds=1800,  # 30 minutes
    confidence_tier=ConfidenceTier.LOW,
    allow_longshots=False,
    max_fair_odds_divergence=250,  # Widest for non-alt — thin Pinnacle coverage
)

_PINNACLE_TEAM_PROP = EVStrategyConfig(
    strategy_name="pinnacle_devig",
    eligible_sharp_books=("Pinnacle",),
    min_qualifying_books=3,
    max_reference_staleness_seconds=1800,  # 30 minutes
    confidence_tier=ConfidenceTier.MEDIUM,
    allow_longshots=False,
    max_fair_odds_divergence=200,
)

_PINNACLE_ALTERNATE = EVStrategyConfig(
    strategy_name="pinnacle_devig",
    eligible_sharp_books=("Pinnacle",),
    min_qualifying_books=3,
    max_reference_staleness_seconds=1800,  # 30 minutes
    confidence_tier=ConfidenceTier.LOW,
    allow_longshots=False,
    max_fair_odds_divergence=300,  # Widest — alt lines inherently have wider vig
)

# Map of (league_code, market_category) -> EVStrategyConfig | None
# None means EV is disabled for that combination.
_STRATEGY_MAP: dict[tuple[str, str], EVStrategyConfig | None] = {
    # NBA
    ("NBA", "mainline"): _PINNACLE_MAINLINE_NBA_NHL,
    ("NBA", "player_prop"): _PINNACLE_PLAYER_PROP,
    ("NBA", "team_prop"): _PINNACLE_TEAM_PROP,
    ("NBA", "alternate"): _PINNACLE_ALTERNATE,
    ("NBA", "period"): None,
    ("NBA", "game_prop"): None,
    # NHL
    ("NHL", "mainline"): _PINNACLE_MAINLINE_NBA_NHL,
    ("NHL", "player_prop"): _PINNACLE_PLAYER_PROP,
    ("NHL", "team_prop"): _PINNACLE_TEAM_PROP,
    ("NHL", "alternate"): _PINNACLE_ALTERNATE,
    ("NHL", "period"): None,
    ("NHL", "game_prop"): None,
    # NCAAB
    ("NCAAB", "mainline"): _PINNACLE_MAINLINE_NCAAB,
    ("NCAAB", "player_prop"): _PINNACLE_PLAYER_PROP,
    ("NCAAB", "team_prop"): _PINNACLE_TEAM_PROP,
    ("NCAAB", "alternate"): _PINNACLE_ALTERNATE,
    ("NCAAB", "period"): None,
    ("NCAAB", "game_prop"): None,
}


# ---------------------------------------------------------------------------
# Logit-space extrapolation constants
# ---------------------------------------------------------------------------

# Per-sport, per-market logit slope (logit shift per 0.5-point line change).
# Operates in log-odds space so tails naturally compress.
# Roughly calibrated: near 50%, a 1-half-point shift ≈ 1.5% prob (basketball).
HALF_POINT_LOGIT_SLOPE: dict[str, dict[str, float]] = {
    "NBA": {"spreads": 0.12, "totals": 0.10, "team_totals": 0.15},
    "NCAAB": {"spreads": 0.14, "totals": 0.12, "team_totals": 0.18},
    "NHL": {"spreads": 0.35, "totals": 0.30, "team_totals": 0.40},
}

# Max number of half-points we'll extrapolate (beyond → too uncertain).
# Per-market limits: team totals capped tighter (5 full points) vs game totals (10).
MAX_EXTRAPOLATION_HALF_POINTS: dict[str, dict[str, int]] = {
    "NBA": {"spreads": 12, "totals": 12, "team_totals": 8},
    "NCAAB": {"spreads": 12, "totals": 12, "team_totals": 8},
    "NHL": {"spreads": 6, "totals": 6, "team_totals": 6},
}

# Max divergence (probability space) between extrapolated fair prob and median
# implied prob across non-sharp books.  Catches phantom EV from long-distance
# extrapolation drift (e.g., fair 80% vs market consensus 53%).
MAX_EXTRAPOLATED_PROB_DIVERGENCE: float = 0.15


def extrapolation_confidence(n_half_points: float) -> str:
    """Return confidence tier based on how far we're extrapolating.

    Args:
        n_half_points: Number of half-points from the reference line.

    Returns:
        "medium" for 1-2 half-points, "low" for 3+.
    """
    abs_hp = abs(n_half_points)
    if abs_hp <= 2:
        return "medium"
    return "low"


def get_strategy(league_code: str, market_category: str) -> EVStrategyConfig | None:
    """Look up the EV strategy for a (league, market_category) pair.

    Args:
        league_code: League code (e.g., "NBA", "NHL", "NCAAB").
        market_category: Market category (e.g., "mainline", "player_prop").

    Returns:
        EVStrategyConfig if EV is enabled for this combination, None otherwise.
    """
    return _STRATEGY_MAP.get((league_code.upper(), market_category))
