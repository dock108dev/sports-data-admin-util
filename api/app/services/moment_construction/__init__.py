"""Moment construction improvements (Phase 3).

This package handles post-selection moment reshaping:
- Task 3.1: Back-and-forth chapter moments
- Task 3.2: Dynamic quarter quotas
- Task 3.3: Semantic mega-moment splitting

Usage:
    from app.services.moment_construction import apply_construction_improvements
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import (
    ChapterConfig,
    QuotaConfig,
    SplitConfig,
    DEFAULT_CHAPTER_CONFIG,
    DEFAULT_QUOTA_CONFIG,
    DEFAULT_SPLIT_CONFIG,
)
from .chapters import (
    ChapterResult,
    VolatilityCluster,
    create_chapter_moments,
    detect_volatility_clusters,
)
from .quotas import (
    QuarterQuota,
    QuotaResult,
    compute_quarter_quotas,
    enforce_quarter_quotas,
)
from .splitting import (
    MegaMomentSplitResult,
    SplitPoint,
    SplitSegment,
    SplittingResult,
    apply_mega_moment_splitting,
    find_split_points,
    select_best_split_points,
    split_mega_moment,
)

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class ConstructionResult:
    """Combined result of Phase 3 construction improvements."""

    moments: list["Moment"] = field(default_factory=list)
    chapter_result: ChapterResult | None = None
    quota_result: QuotaResult | None = None
    splitting_result: SplittingResult | None = None
    original_count: int = 0
    final_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": "3_construction",
            "original_count": self.original_count,
            "final_count": self.final_count,
            "task_3_1_chapters": (
                self.chapter_result.to_dict() if self.chapter_result else None
            ),
            "task_3_2_quotas": (
                self.quota_result.to_dict() if self.quota_result else None
            ),
            "task_3_3_splitting": (
                self.splitting_result.to_dict() if self.splitting_result else None
            ),
        }


def apply_construction_improvements(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int] = (),
    chapter_config: ChapterConfig = DEFAULT_CHAPTER_CONFIG,
    quota_config: QuotaConfig = DEFAULT_QUOTA_CONFIG,
    split_config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> ConstructionResult:
    """Apply Phase 3 construction improvements.

    Order of operations:
    1. Create back-and-forth chapters (Task 3.1)
    2. Enforce quarter quotas (Task 3.2)
    3. Split mega-moments semantically (Task 3.3)

    Args:
        moments: Selected moments (after Phase 2)
        events: Timeline events
        thresholds: Lead Ladder thresholds (for splitting)
        chapter_config: Chapter configuration
        quota_config: Quota configuration
        split_config: Splitting configuration

    Returns:
        ConstructionResult with improved moments
    """
    result = ConstructionResult()
    result.original_count = len(moments)

    if not moments:
        return result

    # Task 3.1: Create chapter moments
    chapter_result = create_chapter_moments(moments, events, chapter_config)
    result.chapter_result = chapter_result
    current_moments = chapter_result.moments

    # Task 3.2: Enforce quarter quotas
    quota_result = enforce_quarter_quotas(current_moments, events, quota_config)
    result.quota_result = quota_result
    current_moments = quota_result.moments

    # Task 3.3: Split mega-moments semantically
    if thresholds:
        splitting_result = apply_mega_moment_splitting(
            current_moments, events, thresholds, split_config
        )
        result.splitting_result = splitting_result
        current_moments = splitting_result.moments

    result.moments = current_moments
    result.final_count = len(current_moments)

    logger.info(
        "construction_improvements_applied",
        extra={
            "original_count": result.original_count,
            "after_chapters": len(chapter_result.moments),
            "after_quotas": len(quota_result.moments),
            "final_count": result.final_count,
            "chapters_created": chapter_result.chapters_created,
            "moments_absorbed": chapter_result.moments_absorbed,
            "quarters_compressed": quota_result.quarters_compressed,
            "mega_moments_split": (
                result.splitting_result.mega_moments_split
                if result.splitting_result
                else 0
            ),
        },
    )

    return result


__all__ = [
    # Configuration
    "ChapterConfig",
    "QuotaConfig",
    "SplitConfig",
    "DEFAULT_CHAPTER_CONFIG",
    "DEFAULT_QUOTA_CONFIG",
    "DEFAULT_SPLIT_CONFIG",
    # Chapters (Task 3.1)
    "ChapterResult",
    "VolatilityCluster",
    "create_chapter_moments",
    "detect_volatility_clusters",
    # Quotas (Task 3.2)
    "QuarterQuota",
    "QuotaResult",
    "compute_quarter_quotas",
    "enforce_quarter_quotas",
    # Splitting (Task 3.3)
    "MegaMomentSplitResult",
    "SplitPoint",
    "SplitSegment",
    "SplittingResult",
    "apply_mega_moment_splitting",
    "find_split_points",
    "select_best_split_points",
    "split_mega_moment",
    # Combined
    "ConstructionResult",
    "apply_construction_improvements",
]
