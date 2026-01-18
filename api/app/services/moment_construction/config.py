"""Configuration for moment construction improvements.

This module defines configuration dataclasses for:
- Chapter creation (Task 3.1)
- Dynamic quarter quotas (Task 3.2)
- Mega-moment splitting (Task 3.3)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChapterConfig:
    """Configuration for back-and-forth chapter detection."""

    min_plays_for_chapter: int = 8
    max_plays_for_chapter: int = 40
    min_lead_changes_for_chapter: int = 2
    min_ties_for_chapter: int = 1
    max_quarter_for_chapter: int = 2  # Q1-Q2 only

    absorbable_types: frozenset = field(
        default_factory=lambda: frozenset(
            {"FLIP", "TIE", "NEUTRAL", "CUT", "LEAD_BUILD"}
        )
    )

    protected_types: frozenset = field(
        default_factory=lambda: frozenset(
            {"CLOSING_CONTROL", "HIGH_IMPACT", "MOMENTUM_SHIFT"}
        )
    )


@dataclass
class QuotaConfig:
    """Configuration for dynamic quarter quotas."""

    baseline_quota: int = 6
    min_quota: int = 2
    max_quota: int = 12
    close_game_margin: int = 8
    close_game_q4_bonus: int = 4
    blowout_margin: int = 20
    blowout_reduction: int = 2
    ot_quota: int = 4


@dataclass
class SplitConfig:
    """Configuration for mega-moment splitting."""

    mega_moment_threshold: int = 50
    min_segment_plays: int = 10
    max_splits_per_moment: int = 2
    min_plays_between_splits: int = 15
    run_min_points: int = 6
    tier_change_min_delta: int = 1
    enable_run_splits: bool = True
    enable_tier_splits: bool = True
    enable_timeout_splits: bool = True


DEFAULT_CHAPTER_CONFIG = ChapterConfig()
DEFAULT_QUOTA_CONFIG = QuotaConfig()
DEFAULT_SPLIT_CONFIG = SplitConfig()
