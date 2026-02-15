"""EV strategy configuration — book lists, eligibility rules, confidence tiers.

Static, version-controlled config for the Sharp Book EV Baseline Framework.
All books are still ingested/persisted; exclusion is SQL-level at query time.
"""

from __future__ import annotations

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

# Books excluded from EV comparisons (junk / offshore / low-quality lines).
# All books still ingested and persisted; exclusion is SQL-level at query time.
EXCLUDED_BOOKS: frozenset[str] = frozenset(
    {
        "BetOnline.ag",
        "BetRivers",
        "BetUS",
        "Bovada",
        "GTbets",
        "LowVig.ag",
        "MyBookie.ag",
        "Nitrogen",
        "SuperBook",
        "TwinSpires",
        "Wind Creek (Betfred PA)",
        "WynnBET",
        "Bally Bet",
        "Betsson",
        "Coolbet",
        "Marathonbet",
        "Matchbook",
        "NordicBet",
        "William Hill (US)",
        "1xBet",
    }
)

# Books included in EV comparisons (reputable US-licensed or sharp).
INCLUDED_BOOKS: frozenset[str] = frozenset(
    {
        "BetMGM",
        "Caesars",
        "DraftKings",
        "ESPNBet",
        "FanDuel",
        "Fanatics",
        "Hard Rock Bet",
        "Pinnacle",
        "PointsBet (US)",
        "bet365",
        "Betway",
        "Circa Sports",
        "Fliff",
        "SI Sportsbook",
        "theScore Bet",
        "Tipico",
        "Unibet",
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


def get_strategy(league_code: str, market_category: str) -> EVStrategyConfig | None:
    """Look up the EV strategy for a (league, market_category) pair.

    Args:
        league_code: League code (e.g., "NBA", "NHL", "NCAAB").
        market_category: Market category (e.g., "mainline", "player_prop").

    Returns:
        EVStrategyConfig if EV is enabled for this combination, None otherwise.
    """
    return _STRATEGY_MAP.get((league_code.upper(), market_category))
