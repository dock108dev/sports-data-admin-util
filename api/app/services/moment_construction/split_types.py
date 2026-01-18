"""Splitting data types.

Dataclasses and constants used by the mega-moment splitting system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..moments import Moment


# Types that are FORBIDDEN for semantic splits
# These can only originate from boundary detection
FORBIDDEN_SEMANTIC_SPLIT_TYPES: frozenset[str] = frozenset({
    "FLIP",
    "TIE",
})

# Default type to normalize forbidden types to
DEFAULT_SEMANTIC_SPLIT_TYPE = "NEUTRAL"


@dataclass
class SplitPoint:
    """A potential split point within a mega-moment.

    Split reasons:
    - tier_change: Lead Ladder tier changed significantly
    - quarter: Quarter boundary transition
    - run_start: A scoring run began
    - pressure_end: Sustained pressure by one team ended
    - timeout_after_swing: Timeout called after momentum swing
    - drought_end: Scoring drought ended
    """

    play_index: int
    split_reason: str
    score_at_split: tuple[int, int] = (0, 0)
    tier_at_split: int = 0
    priority: int = 99  # Lower is higher priority

    # Tier change specifics
    tier_before: int = 0
    tier_after: int = 0

    # Run specifics
    run_team: str | None = None
    run_points: int = 0

    # Quarter specifics
    quarter_before: int = 0
    quarter_after: int = 0

    # Pressure specifics
    pressure_team: str | None = None
    pressure_points: int = 0
    pressure_plays: int = 0

    # Drought specifics
    drought_plays: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = {
            "play_index": self.play_index,
            "split_reason": self.split_reason,
            "score_at_split": self.score_at_split,
            "tier_at_split": self.tier_at_split,
            "priority": self.priority,
        }

        # Add reason-specific fields
        if self.split_reason == "tier_change":
            result["tier_before"] = self.tier_before
            result["tier_after"] = self.tier_after
        elif self.split_reason == "run_start":
            result["run_team"] = self.run_team
            result["run_points"] = self.run_points
        elif self.split_reason == "quarter":
            result["quarter_before"] = self.quarter_before
            result["quarter_after"] = self.quarter_after
        elif self.split_reason == "pressure_end":
            result["pressure_team"] = self.pressure_team
            result["pressure_points"] = self.pressure_points
            result["pressure_plays"] = self.pressure_plays
        elif self.split_reason == "drought_end":
            result["drought_plays"] = self.drought_plays

        return result


@dataclass
class SplitSegment:
    """A segment created from splitting a mega-moment."""

    start_play: int
    end_play: int
    play_count: int
    score_before: tuple[int, int] = (0, 0)
    score_after: tuple[int, int] = (0, 0)
    split_reason: str = ""
    parent_moment_id: str = ""
    segment_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_play": self.start_play,
            "end_play": self.end_play,
            "play_count": self.play_count,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "split_reason": self.split_reason,
            "parent_moment_id": self.parent_moment_id,
            "segment_index": self.segment_index,
        }


@dataclass
class MegaMomentSplitResult:
    """Result of splitting a single mega-moment.

    Contains detailed diagnostics about:
    - Why splits were applied or skipped
    - Which semantic rules fired
    - Final segment composition
    """

    original_moment_id: str
    original_play_count: int
    was_split: bool = False
    is_large_mega: bool = False  # 80+ plays
    split_points_found: list[SplitPoint] = field(default_factory=list)
    split_points_used: list[SplitPoint] = field(default_factory=list)
    split_points_skipped: list[SplitPoint] = field(default_factory=list)
    segments: list[SplitSegment] = field(default_factory=list)
    skip_reason: str | None = None
    split_reasons_fired: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # Count points found by reason
        found_by_reason: dict[str, int] = {}
        for sp in self.split_points_found:
            found_by_reason[sp.split_reason] = found_by_reason.get(sp.split_reason, 0) + 1

        return {
            "original_moment_id": self.original_moment_id,
            "original_play_count": self.original_play_count,
            "was_split": self.was_split,
            "is_large_mega": self.is_large_mega,
            "split_points_found_count": len(self.split_points_found),
            "split_points_found_by_reason": found_by_reason,
            "split_points_used": [sp.to_dict() for sp in self.split_points_used],
            "split_points_skipped_count": len(self.split_points_skipped),
            "segments": [s.to_dict() for s in self.segments],
            "segment_play_counts": [s.play_count for s in self.segments],
            "skip_reason": self.skip_reason,
            "split_reasons_fired": self.split_reasons_fired,
        }


@dataclass
class SemanticSplitTypeNormalization:
    """Record of a type normalization for a semantic split moment.

    Tracks when a FLIP or TIE type is corrected to a valid semantic split type.
    This ensures FLIP/TIE moments only originate from boundary detection.
    """
    moment_id: str
    original_type: str
    corrected_type: str
    parent_moment_id: str
    segment_index: int
    reason: str = "forbidden_type_for_semantic_split"

    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "original_type": self.original_type,
            "corrected_type": self.corrected_type,
            "parent_moment_id": self.parent_moment_id,
            "segment_index": self.segment_index,
            "reason": self.reason,
        }


@dataclass
class SplittingResult:
    """Result of mega-moment splitting pass.

    Contains summary statistics and detailed results for each mega-moment.
    """

    moments: list["Moment"] = field(default_factory=list)
    mega_moments_found: int = 0
    mega_moments_split: int = 0
    large_mega_moments_found: int = 0
    large_mega_moments_split: int = 0
    total_segments_created: int = 0
    split_results: list[MegaMomentSplitResult] = field(default_factory=list)
    type_normalizations: list[SemanticSplitTypeNormalization] = field(default_factory=list)
    split_reasons_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mega_moments_found": self.mega_moments_found,
            "mega_moments_split": self.mega_moments_split,
            "large_mega_moments_found": self.large_mega_moments_found,
            "large_mega_moments_split": self.large_mega_moments_split,
            "total_segments_created": self.total_segments_created,
            "split_reasons_summary": self.split_reasons_summary,
            "split_results": [r.to_dict() for r in self.split_results],
            "type_normalizations": [n.to_dict() for n in self.type_normalizations],
            "types_normalized_count": len(self.type_normalizations),
        }
