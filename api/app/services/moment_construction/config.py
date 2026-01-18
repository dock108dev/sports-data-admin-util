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
    """Configuration for mega-moment splitting.
    
    Mega-moments (80+ plays) are split into 2-3 readable chapters
    using semantic boundaries like runs, tier changes, and quarter transitions.
    """

    # Thresholds
    mega_moment_threshold: int = 50  # Minimum plays to consider splitting
    large_mega_threshold: int = 80  # "Large" mega-moment requiring aggressive splitting
    
    # Segment constraints
    min_segment_plays: int = 10  # Minimum plays per segment
    max_splits_per_moment: int = 2  # Maximum splits (creates 3 segments)
    min_plays_between_splits: int = 15  # Minimum gap between split points
    target_segment_plays: int = 30  # Ideal segment size for large mega-moments
    
    # Run detection
    run_min_points: int = 6  # Minimum points for a run to trigger split
    enable_run_splits: bool = True
    
    # Tier change detection
    tier_change_min_delta: int = 1  # Minimum tier change to trigger split
    enable_tier_splits: bool = True
    
    # Timeout detection
    enable_timeout_splits: bool = True
    
    # Quarter transition detection (NEW)
    enable_quarter_splits: bool = True  # Split at quarter boundaries
    
    # Sustained pressure detection (NEW)
    enable_pressure_splits: bool = True  # Split when one team dominates
    pressure_min_plays: int = 12  # Minimum plays for sustained pressure
    pressure_min_point_diff: int = 8  # Points gained during pressure period
    
    # Scoring drought detection (NEW)
    enable_drought_splits: bool = True  # Split after scoring droughts
    drought_min_plays: int = 8  # Minimum plays without scoring
    
    # Split point scoring (for selecting best points)
    priority_tier_change: int = 0  # Highest priority
    priority_quarter: int = 1
    priority_run_start: int = 2
    priority_pressure: int = 3
    priority_timeout: int = 4
    priority_drought: int = 5


@dataclass
class ClosingConfig:
    """Configuration for closing expansion (late-game narrative detail).
    
    When the game is close late, we STOP collapsing and START expanding
    to provide play-by-play tension detail.
    
    A closing situation is:
    - Q4 or OT
    - inside the final_seconds_window (e.g. last 3 minutes)
    - game tier ≤ max_closing_tier (close game)
    """
    
    # Window definition
    final_seconds_window: int = 180  # 3 minutes = 180 seconds
    min_quarter_for_closing: int = 4  # Q4 minimum (5+ = OT)
    max_closing_tier: int = 1  # Tier must be ≤ this for expansion
    
    # Expansion behavior
    allow_short_moments: bool = True  # Allow 1-3 play moments
    min_closing_plays: int = 1  # Minimum plays for a closing moment
    relax_flip_tie_density: bool = True  # Allow multiple FLIP/TIE close together
    
    # Limits
    max_closing_moments: int = 10  # Hard cap on moments in closing window
    max_expansion_ratio: float = 2.0  # At most 2x the pre-expansion count
    
    # Protected types that should never be merged in closing
    protected_closing_types: frozenset = field(
        default_factory=lambda: frozenset({
            "FLIP",
            "TIE", 
            "CLOSING_CONTROL",
            "HIGH_IMPACT",
        })
    )


DEFAULT_CHAPTER_CONFIG = ChapterConfig()
DEFAULT_QUOTA_CONFIG = QuotaConfig()
DEFAULT_SPLIT_CONFIG = SplitConfig()
DEFAULT_CLOSING_CONFIG = ClosingConfig()
