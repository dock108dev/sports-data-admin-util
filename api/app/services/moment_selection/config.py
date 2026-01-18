"""Configuration for moment selection.

This module defines configuration for:
- Static budgets per sport (Phase 2.2)
- Dynamic budget calculation (Phase 2.3)
- Pacing constraints (Phase 2.4)
"""

from __future__ import annotations

from dataclasses import dataclass


# Static budgets per sport (legacy values, used as Phase 2.2 baseline)
STATIC_BUDGET = {
    "NBA": 30,
    "NHL": 25,
    "NFL": 25,
    "MLS": 20,
    "SOCCER": 20,
}
DEFAULT_STATIC_BUDGET = 30


@dataclass
class BudgetConfig:
    """Configurable parameters for dynamic budget calculation."""

    # Base budget (starting point before adjustments)
    base_budget: int = 22

    # Hard bounds
    min_budget: int = 10
    max_budget: int = 40

    # Final margin impact
    margin_blowout_threshold: int = 20
    margin_close_threshold: int = 5
    margin_blowout_penalty: float = -6.0
    margin_close_bonus: float = 4.0

    # Closeness duration impact (% of game in tier 0-1)
    closeness_high_threshold: float = 0.6
    closeness_low_threshold: float = 0.2
    closeness_thriller_bonus: float = 6.0
    closeness_onesided_penalty: float = -4.0

    # Lead change impact (late-weighted)
    lead_changes_high_threshold: int = 8
    lead_changes_low_threshold: int = 2
    lead_changes_bonus_per: float = 0.5
    lead_changes_cap: float = 5.0

    # Overtime impact
    overtime_bonus_per_period: float = 4.0
    overtime_cap: float = 8.0

    # Comeback depth impact
    comeback_significant_threshold: int = 12
    comeback_bonus: float = 3.0


@dataclass
class PacingConfig:
    """Configurable parameters for pacing constraints."""

    # Early-game cap (Q1 + Q2)
    early_game_max_percentage: float = 0.35
    early_game_override_importance: float = 8.0

    # Closing reservation (Q4 + OT)
    closing_min_percentage_close: float = 0.35
    closing_min_percentage_normal: float = 0.20
    closing_min_moments: int = 3

    # Act structure enforcement
    require_opening_moment: bool = True
    require_middle_moment: bool = True
    require_closing_moment: bool = True

    # Close game threshold for higher closing reservation
    close_game_margin_threshold: int = 8


DEFAULT_BUDGET_CONFIG = BudgetConfig()
DEFAULT_PACING_CONFIG = PacingConfig()
