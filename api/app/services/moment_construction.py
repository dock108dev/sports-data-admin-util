"""Phase 3: Moment Construction Improvements

This module handles post-selection moment reshaping to improve readability
and chapter structure. It does NOT change which moments are selected.

TASK 3.1: Back-and-Forth Chapter Moments
- Detect early-game volatility clusters
- Wrap FLIP/TIE sequences into single "chapter" moments
- Makes early game readable, not spammy

TASK 3.2: Dynamic Quarter Quotas
- Replace fixed per-quarter cap (7) with context-aware quotas
- Close games: Q4 expands (9-12), Q1/Q2 compress
- Blowouts: all quarters compressed

This module operates AFTER selection (Phase 2) is complete.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .moments import Moment

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class ChapterConfig:
    """Configuration for back-and-forth chapter detection."""
    
    # Minimum plays to consider for chapter creation
    min_plays_for_chapter: int = 8
    
    # Maximum plays for a chapter (beyond this, keep separate)
    max_plays_for_chapter: int = 40
    
    # Volatility thresholds
    min_lead_changes_for_chapter: int = 2
    min_ties_for_chapter: int = 1
    
    # Time gating: primarily Q1 and early Q2
    max_quarter_for_chapter: int = 2  # Q1-Q2 only
    
    # Types that can be absorbed into a chapter
    absorbable_types: frozenset = field(default_factory=lambda: frozenset({
        "FLIP", "TIE", "NEUTRAL", "CUT", "LEAD_BUILD"
    }))
    
    # Types that CANNOT be absorbed (always stay separate)
    protected_types: frozenset = field(default_factory=lambda: frozenset({
        "CLOSING_CONTROL", "HIGH_IMPACT", "MOMENTUM_SHIFT"
    }))


@dataclass
class QuotaConfig:
    """Configuration for dynamic quarter quotas."""
    
    # Baseline quota per quarter
    baseline_quota: int = 6
    
    # Minimum quota (never go below)
    min_quota: int = 2
    
    # Maximum quota (even for Q4 in thrillers)
    max_quota: int = 12
    
    # Close game thresholds
    close_game_margin: int = 8
    close_game_q4_bonus: int = 4
    
    # Blowout thresholds
    blowout_margin: int = 20
    blowout_reduction: int = 2
    
    # OT bonus
    ot_quota: int = 4


DEFAULT_CHAPTER_CONFIG = ChapterConfig()
DEFAULT_QUOTA_CONFIG = QuotaConfig()


# =============================================================================
# TASK 3.1: BACK-AND-FORTH CHAPTER MOMENTS
# =============================================================================


@dataclass
class VolatilityCluster:
    """Detected volatility cluster that may become a chapter."""
    
    start_idx: int  # Index in moments list
    end_idx: int    # Index in moments list (inclusive)
    
    # Stats
    play_span: int = 0
    lead_changes: int = 0
    ties: int = 0
    moments_count: int = 0
    
    # Moment IDs absorbed
    absorbed_moment_ids: list[str] = field(default_factory=list)
    
    # Scores
    start_score: tuple[int, int] = (0, 0)
    end_score: tuple[int, int] = (0, 0)
    
    # Quarter info
    quarter: int = 1
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "play_span": self.play_span,
            "lead_changes": self.lead_changes,
            "ties": self.ties,
            "moments_count": self.moments_count,
            "absorbed_moment_ids": self.absorbed_moment_ids,
            "start_score": self.start_score,
            "end_score": self.end_score,
            "quarter": self.quarter,
        }


@dataclass
class ChapterResult:
    """Result of chapter construction."""
    
    # Output moments (with chapters applied)
    moments: list["Moment"] = field(default_factory=list)
    
    # Detected clusters
    clusters_detected: list[VolatilityCluster] = field(default_factory=list)
    
    # Chapters created
    chapters_created: int = 0
    moments_absorbed: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "chapters_created": self.chapters_created,
            "moments_absorbed": self.moments_absorbed,
            "clusters": [c.to_dict() for c in self.clusters_detected],
        }


def detect_volatility_clusters(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: ChapterConfig = DEFAULT_CHAPTER_CONFIG,
) -> list[VolatilityCluster]:
    """Detect early-game volatility clusters that could become chapters.
    
    A volatility cluster is a sequence of moments with:
    - Multiple lead changes
    - Multiple ties
    - Margin oscillation within Tier 0-1
    - Primarily in Q1-Q2
    
    Args:
        moments: Selected moments
        events: Timeline events
        config: Chapter configuration
    
    Returns:
        List of detected volatility clusters
    """
    from .moments import MomentType
    
    if not moments:
        return []
    
    clusters: list[VolatilityCluster] = []
    
    # Scan for clusters of FLIP/TIE moments in early game
    i = 0
    while i < len(moments):
        moment = moments[i]
        
        # Get quarter for this moment
        quarter = _get_moment_quarter(moment, events)
        
        # Only consider early game
        if quarter > config.max_quarter_for_chapter:
            i += 1
            continue
        
        # Check if this starts a potential cluster
        if moment.type in (MomentType.FLIP, MomentType.TIE):
            # Look ahead for more volatility
            cluster = _scan_for_cluster(moments, events, i, config)
            if cluster is not None:
                clusters.append(cluster)
                i = cluster.end_idx + 1
                continue
        
        i += 1
    
    return clusters


def _get_moment_quarter(moment: "Moment", events: Sequence[dict[str, Any]]) -> int:
    """Get the quarter a moment belongs to."""
    if 0 <= moment.start_play < len(events):
        return events[moment.start_play].get("quarter", 1) or 1
    return 1


def _scan_for_cluster(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    start_idx: int,
    config: ChapterConfig,
) -> VolatilityCluster | None:
    """Scan from start_idx to find a volatility cluster."""
    from .moments import MomentType
    
    if start_idx >= len(moments):
        return None
    
    cluster = VolatilityCluster(start_idx=start_idx, end_idx=start_idx)
    
    lead_changes = 0
    ties = 0
    absorbed_ids: list[str] = []
    
    first_moment = moments[start_idx]
    cluster.start_score = first_moment.score_before
    cluster.quarter = _get_moment_quarter(first_moment, events)
    
    j = start_idx
    while j < len(moments):
        moment = moments[j]
        
        # Check quarter - don't cross into late game
        quarter = _get_moment_quarter(moment, events)
        if quarter > config.max_quarter_for_chapter:
            break
        
        # Check if moment type is absorbable
        if moment.type.value in config.protected_types:
            break
        
        if moment.type.value not in config.absorbable_types:
            break
        
        # Count volatility
        if moment.type == MomentType.FLIP:
            lead_changes += 1
        elif moment.type == MomentType.TIE:
            ties += 1
        
        absorbed_ids.append(moment.id)
        cluster.end_idx = j
        cluster.end_score = moment.score_after
        
        j += 1
        
        # Check if we've gone too far
        total_plays = moments[cluster.end_idx].end_play - first_moment.start_play + 1
        if total_plays > config.max_plays_for_chapter:
            break
    
    # Validate cluster
    cluster.moments_count = cluster.end_idx - cluster.start_idx + 1
    cluster.lead_changes = lead_changes
    cluster.ties = ties
    cluster.absorbed_moment_ids = absorbed_ids
    cluster.play_span = moments[cluster.end_idx].end_play - first_moment.start_play + 1
    
    # Must have at least 2 moments and meet volatility thresholds
    if cluster.moments_count < 2:
        return None
    
    if cluster.play_span < config.min_plays_for_chapter:
        return None
    
    if lead_changes < config.min_lead_changes_for_chapter and ties < config.min_ties_for_chapter:
        return None
    
    return cluster


def create_chapter_moments(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: ChapterConfig = DEFAULT_CHAPTER_CONFIG,
) -> ChapterResult:
    """Create chapter moments by absorbing volatility clusters.
    
    Args:
        moments: Selected moments (after Phase 2)
        events: Timeline events
        config: Chapter configuration
    
    Returns:
        ChapterResult with chapter moments applied
    """
    from .moments import Moment, MomentType, MomentReason
    
    result = ChapterResult()
    
    # Detect clusters
    clusters = detect_volatility_clusters(moments, events, config)
    result.clusters_detected = clusters
    
    if not clusters:
        result.moments = list(moments)
        return result
    
    # Build new moments list with chapters
    output_moments: list[Moment] = []
    absorbed_indices: set[int] = set()
    
    for cluster in clusters:
        # Mark all moments in cluster as absorbed
        for idx in range(cluster.start_idx, cluster.end_idx + 1):
            absorbed_indices.add(idx)
        
        # Create chapter moment
        first_moment = moments[cluster.start_idx]
        last_moment = moments[cluster.end_idx]
        
        chapter = Moment(
            id=f"chapter_{first_moment.id}",
            type=MomentType.NEUTRAL,  # Chapter is a container
            start_play=first_moment.start_play,
            end_play=last_moment.end_play,
            play_count=cluster.play_span,
            score_before=cluster.start_score,
            score_after=cluster.end_score,
            ladder_tier_before=first_moment.ladder_tier_before,
            ladder_tier_after=last_moment.ladder_tier_after,
            teams=first_moment.teams,
            is_chapter=True,  # Mark as chapter
        )
        
        # Set chapter reason
        chapter.reason = MomentReason(
            trigger="back_and_forth_chapter",
            control_shift=None,
            narrative_delta=f"traded leads {cluster.lead_changes}x, {cluster.ties} ties",
        )
        
        # Copy importance from highest-importance absorbed moment
        max_importance = max(
            moments[i].importance_score 
            for i in range(cluster.start_idx, cluster.end_idx + 1)
        )
        chapter.importance_score = max_importance
        chapter.importance_factors = {
            "chapter": True,
            "absorbed_count": cluster.moments_count,
            "lead_changes": cluster.lead_changes,
            "ties": cluster.ties,
        }
        
        # Store chapter metadata
        chapter.chapter_info = {
            "absorbed_moment_ids": cluster.absorbed_moment_ids,
            "lead_changes": cluster.lead_changes,
            "ties": cluster.ties,
            "play_span": cluster.play_span,
            "creation_reason": "early_volatility_cluster",
        }
        
        result.chapters_created += 1
        result.moments_absorbed += cluster.moments_count
    
    # Build output: non-absorbed moments + chapters
    for i, moment in enumerate(moments):
        if i not in absorbed_indices:
            output_moments.append(moment)
    
    # Insert chapter moments at the right positions
    for cluster in clusters:
        first_moment = moments[cluster.start_idx]
        chapter_moment = None
        
        # Find the chapter we created for this cluster
        for i, moment in enumerate(moments):
            if i in absorbed_indices and i == cluster.start_idx:
                # Create chapter here
                chapter = Moment(
                    id=f"chapter_{first_moment.id}",
                    type=MomentType.NEUTRAL,
                    start_play=first_moment.start_play,
                    end_play=moments[cluster.end_idx].end_play,
                    play_count=cluster.play_span,
                    score_before=cluster.start_score,
                    score_after=cluster.end_score,
                    ladder_tier_before=first_moment.ladder_tier_before,
                    ladder_tier_after=moments[cluster.end_idx].ladder_tier_after,
                    teams=first_moment.teams,
                    is_chapter=True,
                )
                chapter.reason = MomentReason(
                    trigger="back_and_forth_chapter",
                    control_shift=None,
                    narrative_delta=f"traded leads {cluster.lead_changes}x, {cluster.ties} ties",
                )
                max_importance = max(
                    moments[j].importance_score 
                    for j in range(cluster.start_idx, cluster.end_idx + 1)
                )
                chapter.importance_score = max_importance
                chapter.importance_factors = {
                    "chapter": True,
                    "absorbed_count": cluster.moments_count,
                    "lead_changes": cluster.lead_changes,
                    "ties": cluster.ties,
                }
                chapter.chapter_info = {
                    "absorbed_moment_ids": cluster.absorbed_moment_ids,
                    "lead_changes": cluster.lead_changes,
                    "ties": cluster.ties,
                    "play_span": cluster.play_span,
                    "creation_reason": "early_volatility_cluster",
                }
                chapter_moment = chapter
                break
        
        if chapter_moment:
            output_moments.append(chapter_moment)
    
    # Sort by start_play to maintain chronological order
    output_moments.sort(key=lambda m: m.start_play)
    
    result.moments = output_moments
    
    logger.info(
        "chapter_moments_created",
        extra={
            "clusters_detected": len(clusters),
            "chapters_created": result.chapters_created,
            "moments_absorbed": result.moments_absorbed,
            "original_count": len(moments),
            "final_count": len(output_moments),
        }
    )
    
    return result


# =============================================================================
# TASK 3.2: DYNAMIC QUARTER QUOTAS
# =============================================================================


@dataclass
class QuarterQuota:
    """Computed quota for a single quarter."""
    
    quarter: int
    base_quota: int
    computed_quota: int
    
    # Adjustments applied
    close_game_bonus: int = 0
    blowout_reduction: int = 0
    importance_bonus: int = 0
    
    # Current state
    moments_in_quarter: int = 0
    needs_compression: bool = False
    
    # Moments merged due to quota
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
    
    # Output moments (after quota enforcement)
    moments: list["Moment"] = field(default_factory=list)
    
    # Quotas per quarter
    quotas: dict[int, QuarterQuota] = field(default_factory=dict)
    
    # Game signals used
    final_margin: int = 0
    is_close_game: bool = False
    is_blowout: bool = False
    has_overtime: bool = False
    
    # Compression stats
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


def compute_quarter_quotas(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: QuotaConfig = DEFAULT_QUOTA_CONFIG,
) -> dict[int, QuarterQuota]:
    """Compute dynamic quotas for each quarter based on game context.
    
    Args:
        moments: Selected moments
        events: Timeline events
        config: Quota configuration
    
    Returns:
        Dict of quarter -> QuarterQuota
    """
    # Determine game context
    final_margin = _compute_final_margin(events)
    is_close_game = final_margin <= config.close_game_margin
    is_blowout = final_margin >= config.blowout_margin
    has_overtime = _has_overtime(events)
    
    # Get max quarter
    max_quarter = max(
        (e.get("quarter", 1) or 1 for e in events if e.get("event_type") == "pbp"),
        default=4
    )
    
    # Count moments per quarter
    moments_per_quarter: dict[int, int] = {}
    importance_per_quarter: dict[int, float] = {}
    
    for moment in moments:
        quarter = _get_moment_quarter(moment, events)
        moments_per_quarter[quarter] = moments_per_quarter.get(quarter, 0) + 1
        importance_per_quarter[quarter] = importance_per_quarter.get(quarter, 0) + moment.importance_score
    
    # Compute quotas
    quotas: dict[int, QuarterQuota] = {}
    
    for q in range(1, max_quarter + 1):
        quota = QuarterQuota(
            quarter=q,
            base_quota=config.baseline_quota,
            computed_quota=config.baseline_quota,
            moments_in_quarter=moments_per_quarter.get(q, 0),
        )
        
        # Apply close game bonus to Q4+
        if is_close_game and q >= 4:
            quota.close_game_bonus = config.close_game_q4_bonus
        
        # Apply blowout reduction to all quarters
        if is_blowout:
            quota.blowout_reduction = config.blowout_reduction
            # Extra reduction for early quarters in blowouts
            if q <= 2:
                quota.blowout_reduction += 1
        
        # Importance density bonus for Q4
        if q >= 4:
            avg_importance = importance_per_quarter.get(q, 0) / max(moments_per_quarter.get(q, 1), 1)
            if avg_importance > 5.0:  # High importance density
                quota.importance_bonus = 2
        
        # Compute final quota
        quota.computed_quota = (
            quota.base_quota
            + quota.close_game_bonus
            - quota.blowout_reduction
            + quota.importance_bonus
        )
        
        # Clamp to bounds
        quota.computed_quota = max(config.min_quota, min(config.max_quota, quota.computed_quota))
        
        # Check if compression needed
        quota.needs_compression = quota.moments_in_quarter > quota.computed_quota
        
        quotas[q] = quota
    
    # Handle OT
    if has_overtime:
        for q in range(5, max_quarter + 1):
            if q not in quotas:
                quotas[q] = QuarterQuota(
                    quarter=q,
                    base_quota=config.ot_quota,
                    computed_quota=config.ot_quota,
                    moments_in_quarter=moments_per_quarter.get(q, 0),
                )
    
    return quotas


def _compute_final_margin(events: Sequence[dict[str, Any]]) -> int:
    """Get the final score margin."""
    pbp_events = [e for e in events if e.get("event_type") == "pbp"]
    if not pbp_events:
        return 0
    
    last_event = pbp_events[-1]
    home = last_event.get("home_score", 0) or 0
    away = last_event.get("away_score", 0) or 0
    return abs(home - away)


def _has_overtime(events: Sequence[dict[str, Any]]) -> bool:
    """Check if game went to overtime."""
    max_quarter = max(
        (e.get("quarter", 1) or 1 for e in events if e.get("event_type") == "pbp"),
        default=4
    )
    return max_quarter > 4


def enforce_quarter_quotas(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: QuotaConfig = DEFAULT_QUOTA_CONFIG,
) -> QuotaResult:
    """Enforce dynamic quarter quotas by merging excess moments.
    
    This does NOT re-select moments - it merges the lowest-importance
    adjacent moments within each quarter to meet the quota.
    
    Args:
        moments: Selected moments (after Phase 2)
        events: Timeline events
        config: Quota configuration
    
    Returns:
        QuotaResult with quota-enforced moments
    """
    from .moments_merging import merge_two_moments
    
    result = QuotaResult()
    result.final_margin = _compute_final_margin(events)
    result.is_close_game = result.final_margin <= config.close_game_margin
    result.is_blowout = result.final_margin >= config.blowout_margin
    result.has_overtime = _has_overtime(events)
    
    # Compute quotas
    quotas = compute_quarter_quotas(moments, events, config)
    result.quotas = quotas
    
    # Group moments by quarter
    moments_by_quarter: dict[int, list["Moment"]] = {}
    for moment in moments:
        quarter = _get_moment_quarter(moment, events)
        if quarter not in moments_by_quarter:
            moments_by_quarter[quarter] = []
        moments_by_quarter[quarter].append(moment)
    
    # Enforce quotas per quarter
    output_moments: list["Moment"] = []
    
    for quarter in sorted(moments_by_quarter.keys()):
        quarter_moments = moments_by_quarter[quarter]
        quota = quotas.get(quarter)
        
        if quota is None or not quota.needs_compression:
            output_moments.extend(quarter_moments)
            continue
        
        # Need to compress this quarter
        result.quarters_compressed += 1
        
        # Merge lowest-importance adjacent moments until we meet quota
        while len(quarter_moments) > quota.computed_quota:
            # Find lowest importance moment that can be merged
            min_importance = float('inf')
            merge_idx = -1
            
            for i in range(len(quarter_moments) - 1):
                # Consider merging moment i with i+1
                combined_importance = min(
                    quarter_moments[i].importance_score,
                    quarter_moments[i + 1].importance_score
                )
                if combined_importance < min_importance:
                    min_importance = combined_importance
                    merge_idx = i
            
            if merge_idx < 0:
                break
            
            # Merge moments at merge_idx and merge_idx+1
            merged = merge_two_moments(
                quarter_moments[merge_idx],
                quarter_moments[merge_idx + 1]
            )
            
            # Record merged IDs
            quota.merged_moment_ids.append(quarter_moments[merge_idx].id)
            quota.merged_moment_ids.append(quarter_moments[merge_idx + 1].id)
            result.moments_merged += 1
            
            # Replace in list
            quarter_moments = (
                quarter_moments[:merge_idx] + 
                [merged] + 
                quarter_moments[merge_idx + 2:]
            )
        
        output_moments.extend(quarter_moments)
    
    # Sort chronologically
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
        }
    )
    
    return result


# =============================================================================
# TASK 3.3: SEMANTIC MEGA-MOMENT SPLITTING
# =============================================================================


@dataclass
class SplitConfig:
    """Configuration for mega-moment splitting."""
    
    # Threshold for mega-moment (plays)
    mega_moment_threshold: int = 50
    
    # Minimum segment size (plays) - prevents micro-fragments
    min_segment_plays: int = 10
    
    # Maximum splits per mega-moment
    max_splits_per_moment: int = 2  # Results in 2-3 segments
    
    # Minimum plays between splits
    min_plays_between_splits: int = 15
    
    # Split point detection thresholds
    run_min_points: int = 6  # Minimum run to consider as split point
    tier_change_min_delta: int = 1  # Minimum tier change to split
    
    # Enable/disable specific split types
    enable_run_splits: bool = True
    enable_tier_splits: bool = True
    enable_timeout_splits: bool = True


DEFAULT_SPLIT_CONFIG = SplitConfig()


@dataclass
class SplitPoint:
    """A potential split point within a mega-moment."""
    
    play_index: int  # Index in the events list
    split_reason: str  # "run_start", "tier_change", "timeout_after_swing"
    
    # Context
    score_at_split: tuple[int, int] = (0, 0)
    tier_at_split: int = 0
    
    # For runs
    run_team: str | None = None
    run_points: int = 0
    
    # For tier changes
    tier_before: int = 0
    tier_after: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "play_index": self.play_index,
            "split_reason": self.split_reason,
            "score_at_split": self.score_at_split,
            "tier_at_split": self.tier_at_split,
            "run_team": self.run_team,
            "run_points": self.run_points,
            "tier_before": self.tier_before,
            "tier_after": self.tier_after,
        }


@dataclass
class SplitSegment:
    """A segment created from splitting a mega-moment."""
    
    start_play: int
    end_play: int
    play_count: int
    
    # Scores
    score_before: tuple[int, int] = (0, 0)
    score_after: tuple[int, int] = (0, 0)
    
    # Reason for this segment
    split_reason: str = ""  # Why split happened before this segment
    parent_moment_id: str = ""
    segment_index: int = 0  # 0, 1, 2...
    
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
    """Result of splitting a single mega-moment."""
    
    original_moment_id: str
    original_play_count: int
    was_split: bool = False
    
    # Split points considered
    split_points_found: list[SplitPoint] = field(default_factory=list)
    split_points_used: list[SplitPoint] = field(default_factory=list)
    
    # Resulting segments
    segments: list[SplitSegment] = field(default_factory=list)
    
    # Reason if not split
    skip_reason: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "original_moment_id": self.original_moment_id,
            "original_play_count": self.original_play_count,
            "was_split": self.was_split,
            "split_points_found": len(self.split_points_found),
            "split_points_used": [sp.to_dict() for sp in self.split_points_used],
            "segments": [s.to_dict() for s in self.segments],
            "skip_reason": self.skip_reason,
        }


@dataclass
class SplittingResult:
    """Result of mega-moment splitting pass."""
    
    moments: list["Moment"] = field(default_factory=list)
    
    # Stats
    mega_moments_found: int = 0
    mega_moments_split: int = 0
    total_segments_created: int = 0
    
    # Per-moment results
    split_results: list[MegaMomentSplitResult] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "mega_moments_found": self.mega_moments_found,
            "mega_moments_split": self.mega_moments_split,
            "total_segments_created": self.total_segments_created,
            "split_results": [r.to_dict() for r in self.split_results],
        }


def find_split_points(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> list[SplitPoint]:
    """Find semantic split points within a mega-moment.
    
    Split points are detected at:
    1. Start of scoring runs
    2. Lead tier changes
    3. Timeouts after big swings
    
    Args:
        moment: The mega-moment to analyze
        events: Timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration
    
    Returns:
        List of potential split points, sorted by play index
    """
    from .lead_ladder import compute_lead_state
    
    split_points: list[SplitPoint] = []
    
    # Get events within this moment
    moment_events = [
        e for e in events 
        if e.get("event_type") == "pbp" 
        and moment.start_play <= events.index(e) <= moment.end_play
    ]
    
    if len(moment_events) < config.min_segment_plays * 2:
        return []  # Not enough plays to split
    
    # Track state
    prev_tier = moment.ladder_tier_before
    prev_leader: str | None = None
    run_tracker: dict[str, int] = {"home": 0, "away": 0}
    last_scorer: str | None = None
    
    for i, event in enumerate(moment_events):
        play_idx = moment.start_play + i
        
        # Skip if too close to start or end
        if i < config.min_segment_plays:
            continue
        if i > len(moment_events) - config.min_segment_plays:
            continue
        
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        
        # Compute current lead state
        state = compute_lead_state(home_score, away_score, thresholds)
        
        # 1. Scoring run detection
        if config.enable_run_splits:
            points_scored = event.get("points_scored", 0) or 0
            scoring_team = event.get("scoring_team")
            
            if points_scored > 0 and scoring_team:
                # Update run tracker
                run_tracker[scoring_team] = run_tracker.get(scoring_team, 0) + points_scored
                other_team = "away" if scoring_team == "home" else "home"
                
                # Check if this starts a significant run
                if last_scorer != scoring_team:
                    # Run broken - check if a new run starts here
                    run_tracker = {scoring_team: points_scored, other_team: 0}
                
                # If run reaches threshold, mark split point
                if run_tracker.get(scoring_team, 0) >= config.run_min_points:
                    # Find the start of this run
                    split_points.append(SplitPoint(
                        play_index=play_idx,
                        split_reason="run_start",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        run_team=scoring_team,
                        run_points=run_tracker.get(scoring_team, 0),
                    ))
                    # Reset to avoid duplicate
                    run_tracker = {"home": 0, "away": 0}
                
                last_scorer = scoring_team
        
        # 2. Tier change detection
        if config.enable_tier_splits:
            if abs(state.tier - prev_tier) >= config.tier_change_min_delta:
                split_points.append(SplitPoint(
                    play_index=play_idx,
                    split_reason="tier_change",
                    score_at_split=(home_score, away_score),
                    tier_at_split=state.tier,
                    tier_before=prev_tier,
                    tier_after=state.tier,
                ))
                prev_tier = state.tier
        
        # 3. Timeout after swing detection
        if config.enable_timeout_splits:
            event_type = event.get("event_type_detail", "").lower()
            if "timeout" in event_type:
                # Check if there was a recent swing (tier change or run)
                # Look back a few plays
                recent_swing = False
                for j in range(max(0, i - 5), i):
                    recent_event = moment_events[j]
                    recent_home = recent_event.get("home_score", 0) or 0
                    recent_away = recent_event.get("away_score", 0) or 0
                    recent_state = compute_lead_state(recent_home, recent_away, thresholds)
                    if abs(recent_state.tier - state.tier) >= 1:
                        recent_swing = True
                        break
                
                if recent_swing:
                    split_points.append(SplitPoint(
                        play_index=play_idx,
                        split_reason="timeout_after_swing",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                    ))
        
        prev_tier = state.tier
    
    # Remove duplicates and sort by play index
    unique_points: dict[int, SplitPoint] = {}
    for sp in split_points:
        if sp.play_index not in unique_points:
            unique_points[sp.play_index] = sp
    
    return sorted(unique_points.values(), key=lambda sp: sp.play_index)


def select_best_split_points(
    split_points: list[SplitPoint],
    moment: "Moment",
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> list[SplitPoint]:
    """Select the best split points respecting minimum guards.
    
    Rules:
    - Maximum max_splits_per_moment splits
    - Minimum min_plays_between_splits between splits
    - Minimum min_segment_plays at start/end
    
    Args:
        split_points: All potential split points
        moment: The moment being split
        config: Split configuration
    
    Returns:
        Selected split points (up to max_splits_per_moment)
    """
    if not split_points:
        return []
    
    selected: list[SplitPoint] = []
    last_split_idx = moment.start_play
    
    # Priority order: tier_change > run_start > timeout_after_swing
    priority = {"tier_change": 0, "run_start": 1, "timeout_after_swing": 2}
    sorted_points = sorted(split_points, key=lambda sp: (priority.get(sp.split_reason, 99), sp.play_index))
    
    for sp in sorted_points:
        if len(selected) >= config.max_splits_per_moment:
            break
        
        # Check minimum distance from last split
        if sp.play_index - last_split_idx < config.min_plays_between_splits:
            continue
        
        # Check minimum distance to end
        if moment.end_play - sp.play_index < config.min_segment_plays:
            continue
        
        selected.append(sp)
        last_split_idx = sp.play_index
    
    # Re-sort by play index
    return sorted(selected, key=lambda sp: sp.play_index)


def split_mega_moment(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> MegaMomentSplitResult:
    """Split a single mega-moment into readable segments.
    
    Args:
        moment: The mega-moment to split
        events: Timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration
    
    Returns:
        MegaMomentSplitResult with segments
    """
    result = MegaMomentSplitResult(
        original_moment_id=moment.id,
        original_play_count=moment.play_count,
    )
    
    # Check if this is actually a mega-moment
    if moment.play_count < config.mega_moment_threshold:
        result.skip_reason = "below_threshold"
        return result
    
    # Find split points
    split_points = find_split_points(moment, events, thresholds, config)
    result.split_points_found = split_points
    
    if not split_points:
        result.skip_reason = "no_split_points_found"
        return result
    
    # Select best split points
    selected_points = select_best_split_points(split_points, moment, config)
    result.split_points_used = selected_points
    
    if not selected_points:
        result.skip_reason = "no_valid_split_points"
        return result
    
    # Create segments
    result.was_split = True
    
    segment_starts = [moment.start_play] + [sp.play_index for sp in selected_points]
    segment_ends = [sp.play_index - 1 for sp in selected_points] + [moment.end_play]
    
    for i, (start, end) in enumerate(zip(segment_starts, segment_ends)):
        # Get scores at boundaries
        score_before = moment.score_before if i == 0 else selected_points[i-1].score_at_split
        score_after = selected_points[i].score_at_split if i < len(selected_points) else moment.score_after
        
        split_reason = "" if i == 0 else selected_points[i-1].split_reason
        
        segment = SplitSegment(
            start_play=start,
            end_play=end,
            play_count=end - start + 1,
            score_before=score_before,
            score_after=score_after,
            split_reason=split_reason,
            parent_moment_id=moment.id,
            segment_index=i,
        )
        result.segments.append(segment)
    
    return result


def apply_mega_moment_splitting(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> SplittingResult:
    """Apply semantic splitting to all mega-moments.
    
    Args:
        moments: Selected moments (after Phase 2 and earlier Phase 3 steps)
        events: Timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration
    
    Returns:
        SplittingResult with split moments
    """
    from .moments import Moment, MomentType, MomentReason
    
    result = SplittingResult()
    output_moments: list[Moment] = []
    
    for moment in moments:
        # Check if mega-moment
        if moment.play_count < config.mega_moment_threshold:
            output_moments.append(moment)
            continue
        
        result.mega_moments_found += 1
        
        # Split the mega-moment
        split_result = split_mega_moment(moment, events, thresholds, config)
        result.split_results.append(split_result)
        
        if not split_result.was_split:
            output_moments.append(moment)
            continue
        
        result.mega_moments_split += 1
        
        # Create new moments from segments
        for i, segment in enumerate(split_result.segments):
            new_moment = Moment(
                id=f"{moment.id}_seg{i+1}",
                type=moment.type,
                start_play=segment.start_play,
                end_play=segment.end_play,
                play_count=segment.play_count,
                score_before=segment.score_before,
                score_after=segment.score_after,
                ladder_tier_before=moment.ladder_tier_before if i == 0 else moment.ladder_tier_after,
                ladder_tier_after=moment.ladder_tier_after,
                teams=moment.teams,
                team_in_control=moment.team_in_control,
            )
            
            # Set reason
            if segment.split_reason:
                narrative = {
                    "run_start": "momentum shift began",
                    "tier_change": "game dynamics changed",
                    "timeout_after_swing": "regrouping after swing",
                }.get(segment.split_reason, "narrative continuation")
            else:
                narrative = "opening phase"
            
            new_moment.reason = MomentReason(
                trigger="semantic_split",
                control_shift=moment.team_in_control,
                narrative_delta=narrative,
            )
            
            # Inherit importance (proportional to play count)
            proportion = segment.play_count / moment.play_count
            new_moment.importance_score = moment.importance_score * proportion
            new_moment.importance_factors = {
                "inherited_from": moment.id,
                "proportion": round(proportion, 2),
                "segment_index": i,
                "split_reason": segment.split_reason or "start",
            }
            
            # Mark as split segment
            new_moment.is_chapter = False
            new_moment.chapter_info = {
                "is_split_segment": True,
                "parent_moment_id": moment.id,
                "segment_index": i,
                "total_segments": len(split_result.segments),
                "split_reason": segment.split_reason,
            }
            
            output_moments.append(new_moment)
            result.total_segments_created += 1
    
    # Sort chronologically
    output_moments.sort(key=lambda m: m.start_play)
    result.moments = output_moments
    
    logger.info(
        "mega_moment_splitting_applied",
        extra={
            "mega_moments_found": result.mega_moments_found,
            "mega_moments_split": result.mega_moments_split,
            "total_segments_created": result.total_segments_created,
            "original_count": len(moments),
            "final_count": len(output_moments),
        }
    )
    
    return result


# =============================================================================
# COMBINED PHASE 3 APPLICATION
# =============================================================================


@dataclass
class ConstructionResult:
    """Combined result of Phase 3 construction improvements."""
    
    moments: list["Moment"] = field(default_factory=list)
    
    # Task 3.1: Chapter results
    chapter_result: ChapterResult | None = None
    
    # Task 3.2: Quota results
    quota_result: QuotaResult | None = None
    
    # Task 3.3: Splitting results
    splitting_result: SplittingResult | None = None
    
    # Summary
    original_count: int = 0
    final_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": "3_construction",
            "original_count": self.original_count,
            "final_count": self.final_count,
            "task_3_1_chapters": self.chapter_result.to_dict() if self.chapter_result else None,
            "task_3_2_quotas": self.quota_result.to_dict() if self.quota_result else None,
            "task_3_3_splitting": self.splitting_result.to_dict() if self.splitting_result else None,
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
            "mega_moments_split": result.splitting_result.mega_moments_split if result.splitting_result else 0,
        }
    )
    
    return result
