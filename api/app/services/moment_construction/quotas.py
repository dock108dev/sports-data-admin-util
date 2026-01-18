"""Task 3.2: Dynamic quarter quotas.

Replaces fixed per-quarter cap with context-aware quotas based on
game signals (close game, blowout, overtime).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import QuotaConfig, DEFAULT_QUOTA_CONFIG
from .chapters import get_moment_quarter

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class QuarterQuota:
    """Computed quota for a single quarter."""

    quarter: int
    base_quota: int
    computed_quota: int
    close_game_bonus: int = 0
    blowout_reduction: int = 0
    importance_bonus: int = 0
    moments_in_quarter: int = 0
    needs_compression: bool = False
    merged_moment_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarter": self.quarter,
            "base_quota": self.base_quota,
            "computed_quota": self.computed_quota,
            "adjustments": {
                "close_game_bonus": self.close_game_bonus,
                "blowout_reduction": self.blowout_reduction,
                "importance_bonus": self.importance_bonus,
            },
            "moments_in_quarter": self.moments_in_quarter,
            "needs_compression": self.needs_compression,
            "merged_moment_ids": self.merged_moment_ids,
        }


@dataclass
class QuotaResult:
    """Result of quota enforcement."""

    moments: list["Moment"] = field(default_factory=list)
    quotas: dict[int, QuarterQuota] = field(default_factory=dict)
    final_margin: int = 0
    is_close_game: bool = False
    is_blowout: bool = False
    has_overtime: bool = False
    quarters_compressed: int = 0
    moments_merged: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_signals": {
                "final_margin": self.final_margin,
                "is_close_game": self.is_close_game,
                "is_blowout": self.is_blowout,
                "has_overtime": self.has_overtime,
            },
            "quotas": {q: quota.to_dict() for q, quota in self.quotas.items()},
            "compression": {
                "quarters_compressed": self.quarters_compressed,
                "moments_merged": self.moments_merged,
            },
        }


def compute_final_margin(events: Sequence[dict[str, Any]]) -> int:
    """Get the final score margin."""
    pbp_events = [e for e in events if e.get("event_type") == "pbp"]
    if not pbp_events:
        return 0
    last_event = pbp_events[-1]
    home = last_event.get("home_score", 0) or 0
    away = last_event.get("away_score", 0) or 0
    return abs(home - away)


def has_overtime(events: Sequence[dict[str, Any]]) -> bool:
    """Check if game went to overtime."""
    max_quarter = max(
        (e.get("quarter", 1) or 1 for e in events if e.get("event_type") == "pbp"),
        default=4,
    )
    return max_quarter > 4


def compute_quarter_quotas(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: QuotaConfig = DEFAULT_QUOTA_CONFIG,
) -> dict[int, QuarterQuota]:
    """Compute dynamic quotas for each quarter based on game context."""
    final_margin = compute_final_margin(events)
    is_close_game = final_margin <= config.close_game_margin
    is_blowout = final_margin >= config.blowout_margin
    game_has_overtime = has_overtime(events)

    max_quarter = max(
        (e.get("quarter", 1) or 1 for e in events if e.get("event_type") == "pbp"),
        default=4,
    )

    moments_per_quarter: dict[int, int] = {}
    importance_per_quarter: dict[int, float] = {}

    for moment in moments:
        quarter = get_moment_quarter(moment, events)
        moments_per_quarter[quarter] = moments_per_quarter.get(quarter, 0) + 1
        importance_per_quarter[quarter] = (
            importance_per_quarter.get(quarter, 0) + moment.importance_score
        )

    quotas: dict[int, QuarterQuota] = {}

    for q in range(1, max_quarter + 1):
        quota = QuarterQuota(
            quarter=q,
            base_quota=config.baseline_quota,
            computed_quota=config.baseline_quota,
            moments_in_quarter=moments_per_quarter.get(q, 0),
        )

        if is_close_game and q >= 4:
            quota.close_game_bonus = config.close_game_q4_bonus

        if is_blowout:
            quota.blowout_reduction = config.blowout_reduction
            if q <= 2:
                quota.blowout_reduction += 1

        if q >= 4:
            avg_importance = importance_per_quarter.get(q, 0) / max(
                moments_per_quarter.get(q, 1), 1
            )
            if avg_importance > 5.0:
                quota.importance_bonus = 2

        quota.computed_quota = (
            quota.base_quota
            + quota.close_game_bonus
            - quota.blowout_reduction
            + quota.importance_bonus
        )

        quota.computed_quota = max(
            config.min_quota, min(config.max_quota, quota.computed_quota)
        )
        quota.needs_compression = quota.moments_in_quarter > quota.computed_quota
        quotas[q] = quota

    if game_has_overtime:
        for q in range(5, max_quarter + 1):
            if q not in quotas:
                quotas[q] = QuarterQuota(
                    quarter=q,
                    base_quota=config.ot_quota,
                    computed_quota=config.ot_quota,
                    moments_in_quarter=moments_per_quarter.get(q, 0),
                )

    return quotas


def enforce_quarter_quotas(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: QuotaConfig = DEFAULT_QUOTA_CONFIG,
) -> QuotaResult:
    """Enforce dynamic quarter quotas by merging excess moments."""
    from ..moments_merging import merge_two_moments

    result = QuotaResult()
    result.final_margin = compute_final_margin(events)
    result.is_close_game = result.final_margin <= config.close_game_margin
    result.is_blowout = result.final_margin >= config.blowout_margin
    result.has_overtime = has_overtime(events)

    quotas = compute_quarter_quotas(moments, events, config)
    result.quotas = quotas

    moments_by_quarter: dict[int, list["Moment"]] = {}
    for moment in moments:
        quarter = get_moment_quarter(moment, events)
        if quarter not in moments_by_quarter:
            moments_by_quarter[quarter] = []
        moments_by_quarter[quarter].append(moment)

    output_moments: list["Moment"] = []

    for quarter in sorted(moments_by_quarter.keys()):
        quarter_moments = moments_by_quarter[quarter]
        quota = quotas.get(quarter)

        if quota is None or not quota.needs_compression:
            output_moments.extend(quarter_moments)
            continue

        result.quarters_compressed += 1

        while len(quarter_moments) > quota.computed_quota:
            min_importance = float("inf")
            merge_idx = -1

            for i in range(len(quarter_moments) - 1):
                combined_importance = min(
                    quarter_moments[i].importance_score,
                    quarter_moments[i + 1].importance_score,
                )
                if combined_importance < min_importance:
                    min_importance = combined_importance
                    merge_idx = i

            if merge_idx < 0:
                break

            merged = merge_two_moments(
                quarter_moments[merge_idx], quarter_moments[merge_idx + 1]
            )

            quota.merged_moment_ids.append(quarter_moments[merge_idx].id)
            quota.merged_moment_ids.append(quarter_moments[merge_idx + 1].id)
            result.moments_merged += 1

            quarter_moments = (
                quarter_moments[:merge_idx]
                + [merged]
                + quarter_moments[merge_idx + 2 :]
            )

        output_moments.extend(quarter_moments)

    output_moments.sort(key=lambda m: m.start_play)
    result.moments = output_moments

    logger.info(
        "quarter_quotas_enforced",
        extra={
            "is_close_game": result.is_close_game,
            "is_blowout": result.is_blowout,
            "final_margin": result.final_margin,
            "quarters_compressed": result.quarters_compressed,
            "moments_merged": result.moments_merged,
            "original_count": len(moments),
            "final_count": len(output_moments),
        },
    )

    return result
