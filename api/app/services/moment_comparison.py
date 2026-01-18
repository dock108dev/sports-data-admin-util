"""Phase 5: UI & Workflow Support

This module provides:
- TASK 5.1: Compare Versions A/B View
  - Side-by-side comparison of two moment outputs
  - High-level summary metrics
  - Distribution metrics
  - Timeline alignment
  - Merge/suppression visibility

- TASK 5.2: Narrative Quality Checklist + Auto Flags
  - Soft validations that emit warnings
  - Q1 flip spam, Q4 underrepresentation, etc.

This module is observer + advisor, not decision-maker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .moments import Moment

logger = logging.getLogger(__name__)


# =============================================================================
# TASK 5.1: COMPARE VERSIONS A/B VIEW
# =============================================================================


@dataclass
class HighLevelSummary:
    """High-level summary metrics for a moment set."""
    
    total_moments: int = 0
    target_budget: int = 0
    actual_count: int = 0
    
    # Half distribution
    first_half_count: int = 0
    second_half_count: int = 0
    first_half_pct: float = 0.0
    
    # Quarter distribution
    moments_per_quarter: dict[int, int] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "total_moments": self.total_moments,
            "target_budget": self.target_budget,
            "actual_count": self.actual_count,
            "first_half_count": self.first_half_count,
            "second_half_count": self.second_half_count,
            "first_half_pct": round(self.first_half_pct * 100, 1),
            "moments_per_quarter": self.moments_per_quarter,
        }


@dataclass
class DistributionMetrics:
    """Distribution metrics for comparison."""
    
    # By trigger type
    by_trigger_type: dict[str, int] = field(default_factory=dict)
    
    # By tier
    by_tier: dict[int, int] = field(default_factory=dict)
    
    # Play counts
    avg_play_count: float = 0.0
    min_play_count: int = 0
    max_play_count: int = 0
    
    # Special moments
    mega_moment_count: int = 0
    chapter_moment_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "by_trigger_type": self.by_trigger_type,
            "by_tier": self.by_tier,
            "avg_play_count": round(self.avg_play_count, 1),
            "min_play_count": self.min_play_count,
            "max_play_count": self.max_play_count,
            "mega_moment_count": self.mega_moment_count,
            "chapter_moment_count": self.chapter_moment_count,
        }


@dataclass 
class TimelineRow:
    """A row in the timeline comparison."""
    
    play_start: int
    play_end: int
    
    # Old version
    old_moment_id: str | None = None
    old_type: str | None = None
    old_importance: float = 0.0
    old_top_scorer: str | None = None
    old_team_diff: int = 0
    
    # New version
    new_moment_id: str | None = None
    new_type: str | None = None
    new_importance: float = 0.0
    new_top_scorer: str | None = None
    new_team_diff: int = 0
    
    # Diff status
    status: str = "unchanged"  # "unchanged", "added", "removed", "modified"
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "play_range": f"{self.play_start}-{self.play_end}",
            "old": {
                "moment_id": self.old_moment_id,
                "type": self.old_type,
                "importance": round(self.old_importance, 2) if self.old_importance else None,
                "top_scorer": self.old_top_scorer,
                "team_diff": self.old_team_diff,
            } if self.old_moment_id else None,
            "new": {
                "moment_id": self.new_moment_id,
                "type": self.new_type,
                "importance": round(self.new_importance, 2) if self.new_importance else None,
                "top_scorer": self.new_top_scorer,
                "team_diff": self.new_team_diff,
            } if self.new_moment_id else None,
            "status": self.status,
        }


@dataclass
class DisplacementEntry:
    """Entry for a moment that was merged/suppressed/dropped."""
    
    moment_id: str
    reason: str  # "merged", "absorbed_to_chapter", "rank_select_dropped", "suppressed"
    importance_rank: int = 0
    importance_score: float = 0.0
    displaced_by: list[str] = field(default_factory=list)
    absorbed_into: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "reason": self.reason,
            "importance_rank": self.importance_rank,
            "importance_score": round(self.importance_score, 2),
            "displaced_by": self.displaced_by,
            "absorbed_into": self.absorbed_into,
        }


@dataclass
class ComparisonResult:
    """Result of comparing two moment sets."""
    
    # Summaries
    old_summary: HighLevelSummary = field(default_factory=HighLevelSummary)
    new_summary: HighLevelSummary = field(default_factory=HighLevelSummary)
    
    # Distributions
    old_distribution: DistributionMetrics = field(default_factory=DistributionMetrics)
    new_distribution: DistributionMetrics = field(default_factory=DistributionMetrics)
    
    # Timeline
    timeline: list[TimelineRow] = field(default_factory=list)
    
    # Displacements
    displacements: list[DisplacementEntry] = field(default_factory=list)
    
    # Delta highlights
    moment_count_delta: int = 0
    first_half_pct_delta: float = 0.0
    avg_play_count_delta: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "old_summary": self.old_summary.to_dict(),
            "new_summary": self.new_summary.to_dict(),
            "old_distribution": self.old_distribution.to_dict(),
            "new_distribution": self.new_distribution.to_dict(),
            "timeline": [r.to_dict() for r in self.timeline],
            "displacements": [d.to_dict() for d in self.displacements],
            "deltas": {
                "moment_count": self.moment_count_delta,
                "first_half_pct": round(self.first_half_pct_delta * 100, 1),
                "avg_play_count": round(self.avg_play_count_delta, 1),
            },
        }


def _compute_high_level_summary(
    moments: Sequence["Moment"],
    target_budget: int = 0,
) -> HighLevelSummary:
    """Compute high-level summary for a moment set."""
    summary = HighLevelSummary()
    summary.total_moments = len(moments)
    summary.actual_count = len(moments)
    summary.target_budget = target_budget
    
    if not moments:
        return summary
    
    # Quarter distribution
    for m in moments:
        # Estimate quarter from play index (rough heuristic)
        # Assume ~100 plays per quarter for NBA
        quarter = min(4, max(1, (m.start_play // 100) + 1))
        summary.moments_per_quarter[quarter] = (
            summary.moments_per_quarter.get(quarter, 0) + 1
        )
    
    # First/second half
    for m in moments:
        quarter = min(4, max(1, (m.start_play // 100) + 1))
        if quarter <= 2:
            summary.first_half_count += 1
        else:
            summary.second_half_count += 1
    
    if summary.total_moments > 0:
        summary.first_half_pct = summary.first_half_count / summary.total_moments
    
    return summary


def _compute_distribution_metrics(
    moments: Sequence["Moment"],
    mega_threshold: int = 50,
) -> DistributionMetrics:
    """Compute distribution metrics for a moment set."""
    metrics = DistributionMetrics()
    
    if not moments:
        return metrics
    
    # By trigger type
    for m in moments:
        type_name = m.type.value if hasattr(m.type, 'value') else str(m.type)
        metrics.by_trigger_type[type_name] = (
            metrics.by_trigger_type.get(type_name, 0) + 1
        )
    
    # By tier
    for m in moments:
        tier = getattr(m, 'ladder_tier_after', 0) or 0
        metrics.by_tier[tier] = metrics.by_tier.get(tier, 0) + 1
    
    # Play counts
    play_counts = [m.play_count for m in moments]
    if play_counts:
        metrics.avg_play_count = sum(play_counts) / len(play_counts)
        metrics.min_play_count = min(play_counts)
        metrics.max_play_count = max(play_counts)
    
    # Special moments
    metrics.mega_moment_count = sum(1 for m in moments if m.play_count >= mega_threshold)
    metrics.chapter_moment_count = sum(1 for m in moments if getattr(m, 'is_chapter', False))
    
    return metrics


def _align_timeline(
    old_moments: Sequence["Moment"],
    new_moments: Sequence["Moment"],
) -> list[TimelineRow]:
    """Align old and new moments by play range for comparison."""
    timeline: list[TimelineRow] = []
    
    # Build lookup by play range
    old_by_start: dict[int, "Moment"] = {m.start_play: m for m in old_moments}
    new_by_start: dict[int, "Moment"] = {m.start_play: m for m in new_moments}
    
    all_starts = sorted(set(old_by_start.keys()) | set(new_by_start.keys()))
    
    for start in all_starts:
        old_m = old_by_start.get(start)
        new_m = new_by_start.get(start)
        
        row = TimelineRow(
            play_start=start,
            play_end=max(
                old_m.end_play if old_m else start,
                new_m.end_play if new_m else start,
            ),
        )
        
        if old_m:
            row.old_moment_id = old_m.id
            row.old_type = old_m.type.value if hasattr(old_m.type, 'value') else str(old_m.type)
            row.old_importance = getattr(old_m, 'importance_score', 0.0)
            if hasattr(old_m, 'moment_boxscore') and old_m.moment_boxscore:
                top = old_m.moment_boxscore.top_scorer
                if top:
                    row.old_top_scorer = top[0]
                row.old_team_diff = old_m.moment_boxscore.team_totals.net
        
        if new_m:
            row.new_moment_id = new_m.id
            row.new_type = new_m.type.value if hasattr(new_m.type, 'value') else str(new_m.type)
            row.new_importance = getattr(new_m, 'importance_score', 0.0)
            if hasattr(new_m, 'moment_boxscore') and new_m.moment_boxscore:
                top = new_m.moment_boxscore.top_scorer
                if top:
                    row.new_top_scorer = top[0]
                row.new_team_diff = new_m.moment_boxscore.team_totals.net
        
        # Determine status
        if old_m and new_m:
            if row.old_type == row.new_type:
                row.status = "unchanged"
            else:
                row.status = "modified"
        elif old_m and not new_m:
            row.status = "removed"
        else:
            row.status = "added"
        
        timeline.append(row)
    
    return timeline


def compare_moment_versions(
    old_moments: Sequence["Moment"],
    new_moments: Sequence["Moment"],
    old_target_budget: int = 0,
    new_target_budget: int = 0,
    rank_records: Sequence[dict[str, Any]] | None = None,
    chapter_absorptions: dict[str, str] | None = None,
) -> ComparisonResult:
    """Compare two versions of moments for the same game.
    
    Args:
        old_moments: Previous version moments
        new_moments: New version moments
        old_target_budget: Target budget for old version
        new_target_budget: Target budget for new version
        rank_records: Optional rank+select records showing dropped moments
        chapter_absorptions: Optional dict of moment_id -> chapter_id absorptions
    
    Returns:
        ComparisonResult with full comparison data
    """
    result = ComparisonResult()
    
    # Compute summaries
    result.old_summary = _compute_high_level_summary(old_moments, old_target_budget)
    result.new_summary = _compute_high_level_summary(new_moments, new_target_budget)
    
    # Compute distributions
    result.old_distribution = _compute_distribution_metrics(old_moments)
    result.new_distribution = _compute_distribution_metrics(new_moments)
    
    # Align timeline
    result.timeline = _align_timeline(old_moments, new_moments)
    
    # Compute deltas
    result.moment_count_delta = (
        result.new_summary.total_moments - result.old_summary.total_moments
    )
    result.first_half_pct_delta = (
        result.new_summary.first_half_pct - result.old_summary.first_half_pct
    )
    result.avg_play_count_delta = (
        result.new_distribution.avg_play_count - result.old_distribution.avg_play_count
    )
    
    # Build displacement entries from rank records
    new_ids = {m.id for m in new_moments}
    
    if rank_records:
        for record in rank_records:
            if not record.get("selected", True):
                result.displacements.append(DisplacementEntry(
                    moment_id=record.get("moment_id", ""),
                    reason="rank_select_dropped",
                    importance_rank=record.get("importance_rank", 0),
                    importance_score=record.get("importance_score", 0.0),
                    displaced_by=record.get("displaced_by", []),
                ))
    
    # Add chapter absorptions
    if chapter_absorptions:
        for absorbed_id, chapter_id in chapter_absorptions.items():
            if absorbed_id not in new_ids:
                result.displacements.append(DisplacementEntry(
                    moment_id=absorbed_id,
                    reason="absorbed_to_chapter",
                    absorbed_into=chapter_id,
                ))
    
    return result


# =============================================================================
# TASK 5.2: NARRATIVE QUALITY CHECKLIST + AUTO FLAGS
# =============================================================================


class FlagSeverity(Enum):
    """Severity level for narrative flags."""
    INFO = "info"
    WARN = "warn"


@dataclass
class NarrativeFlag:
    """A narrative quality warning/flag."""
    
    flag_id: str
    severity: FlagSeverity
    title: str
    message: str
    related_moment_ids: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "flag_id": self.flag_id,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "related_moment_ids": self.related_moment_ids,
            "details": self.details,
        }


@dataclass
class NarrativeCheckConfig:
    """Configuration for narrative quality checks."""
    
    # Q1 flip spam thresholds
    q1_flip_max_count: int = 4
    q1_max_pct_of_total: float = 0.25
    
    # Q4 underrepresentation
    q4_min_count_close_game: int = 4
    close_game_margin: int = 10
    
    # Mega-moment threshold
    mega_moment_threshold: int = 50
    
    # Closing sequence
    closing_required_for_close_games: bool = True
    
    # Optional checks
    max_neutral_pct: float = 0.5
    require_players_in_summaries: bool = True
    min_run_count_close_game: int = 2
    min_importance_variance: float = 0.1


@dataclass
class NarrativeCheckResult:
    """Result of narrative quality checks."""
    
    flags: list[NarrativeFlag] = field(default_factory=list)
    checks_run: int = 0
    warnings_count: int = 0
    info_count: int = 0
    
    @property
    def has_warnings(self) -> bool:
        return self.warnings_count > 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "flags": [f.to_dict() for f in self.flags],
            "checks_run": self.checks_run,
            "warnings_count": self.warnings_count,
            "info_count": self.info_count,
            "has_warnings": self.has_warnings,
        }


def _check_q1_flip_spam(
    moments: Sequence["Moment"],
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check for early-game flip/tie spam."""
    from .moments import MomentType
    
    # Find Q1 moments (first ~100 plays)
    q1_moments = [m for m in moments if m.start_play < 100]
    
    flip_tie_moments = [
        m for m in q1_moments
        if m.type in (MomentType.FLIP, MomentType.TIE)
    ]
    
    flip_count = len(flip_tie_moments)
    total = len(moments)
    
    # Check thresholds
    exceeds_count = flip_count >= config.q1_flip_max_count
    exceeds_pct = total > 0 and (len(q1_moments) / total) > config.q1_max_pct_of_total
    
    if exceeds_count or exceeds_pct:
        return NarrativeFlag(
            flag_id="q1_flip_spam",
            severity=FlagSeverity.WARN,
            title="Q1 Flip Spam Detected",
            message=f"Early-game flip spam detected — {flip_count} FLIP/TIE moments in Q1. Consider summarization.",
            related_moment_ids=[m.id for m in flip_tie_moments],
            details={
                "q1_flip_count": flip_count,
                "q1_moment_count": len(q1_moments),
                "total_moments": total,
                "q1_pct": round(len(q1_moments) / total * 100, 1) if total else 0,
            },
        )
    
    return None


def _check_q4_underrepresented(
    moments: Sequence["Moment"],
    final_margin: int,
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check if Q4/OT is underrepresented in close games."""
    # Close game check
    if abs(final_margin) > config.close_game_margin:
        return None
    
    # Find Q4+ moments (plays 300+)
    q4_moments = [m for m in moments if m.start_play >= 300]
    
    if len(q4_moments) < config.q4_min_count_close_game:
        return NarrativeFlag(
            flag_id="q4_underrepresented",
            severity=FlagSeverity.WARN,
            title="Q4 Underrepresented",
            message=f"Late-game coverage appears thin for a close finish. Only {len(q4_moments)} moments in Q4+.",
            related_moment_ids=[m.id for m in q4_moments],
            details={
                "q4_moment_count": len(q4_moments),
                "min_expected": config.q4_min_count_close_game,
                "final_margin": final_margin,
            },
        )
    
    return None


def _check_mega_moments(
    moments: Sequence["Moment"],
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check for mega-moments that may be unreadable."""
    mega_moments = [
        m for m in moments
        if m.play_count >= config.mega_moment_threshold
    ]
    
    if mega_moments:
        return NarrativeFlag(
            flag_id="mega_moment_detected",
            severity=FlagSeverity.WARN,
            title="Mega-Moment Detected",
            message=f"Found {len(mega_moments)} moment(s) with {config.mega_moment_threshold}+ plays. Long neutral stretches may be unreadable.",
            related_moment_ids=[m.id for m in mega_moments],
            details={
                "mega_moment_count": len(mega_moments),
                "largest_play_count": max(m.play_count for m in mega_moments),
            },
        )
    
    return None


def _check_closing_sequence(
    moments: Sequence["Moment"],
    final_margin: int,
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check if a closing sequence exists for close games."""
    from .moments import MomentType
    
    # Only check close games
    if not config.closing_required_for_close_games:
        return None
    if abs(final_margin) > config.close_game_margin:
        return None
    
    # Look for closing control or late-game moments
    closing_moments = [
        m for m in moments
        if m.type == MomentType.CLOSING_CONTROL
        or (m.start_play >= 400 and m.type in (MomentType.LEAD_BUILD, MomentType.FLIP))
    ]
    
    if not closing_moments:
        return NarrativeFlag(
            flag_id="closing_sequence_missing",
            severity=FlagSeverity.WARN,
            title="Closing Sequence Missing",
            message="No clear closing chapter detected for this close game.",
            details={
                "final_margin": final_margin,
                "late_game_moments": len([m for m in moments if m.start_play >= 400]),
            },
        )
    
    return None


def _check_excessive_neutral(
    moments: Sequence["Moment"],
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check for excessive NEUTRAL moments."""
    from .moments import MomentType
    
    neutral_count = sum(1 for m in moments if m.type == MomentType.NEUTRAL)
    total = len(moments)
    
    if total > 0 and (neutral_count / total) > config.max_neutral_pct:
        return NarrativeFlag(
            flag_id="excessive_neutral",
            severity=FlagSeverity.INFO,
            title="Excessive NEUTRAL Moments",
            message=f"{neutral_count}/{total} moments ({round(neutral_count/total*100)}%) are NEUTRAL. Consider more specific triggers.",
            details={
                "neutral_count": neutral_count,
                "total_moments": total,
                "neutral_pct": round(neutral_count / total * 100, 1),
            },
        )
    
    return None


def _check_no_players(
    moments: Sequence["Moment"],
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check if any moments mention players."""
    if not config.require_players_in_summaries:
        return None
    
    moments_with_players = 0
    for m in moments:
        if hasattr(m, 'narrative_summary') and m.narrative_summary:
            if m.narrative_summary.players_referenced:
                moments_with_players += 1
        elif hasattr(m, 'moment_boxscore') and m.moment_boxscore:
            if m.moment_boxscore.points_by_player:
                moments_with_players += 1
    
    if moments_with_players == 0:
        return NarrativeFlag(
            flag_id="no_players_mentioned",
            severity=FlagSeverity.INFO,
            title="No Players Mentioned",
            message="No players were identified in any moment summaries. Check PBP data quality.",
            details={
                "total_moments": len(moments),
            },
        )
    
    return None


def _check_no_runs_close_game(
    moments: Sequence["Moment"],
    final_margin: int,
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check for runs in close games."""
    from .moments import MomentType
    
    # Only check close games
    if abs(final_margin) > config.close_game_margin:
        return None
    
    run_moments = [
        m for m in moments
        if m.type == MomentType.MOMENTUM_SHIFT
        or (hasattr(m, 'run_info') and m.run_info)
    ]
    
    if len(run_moments) < config.min_run_count_close_game:
        return NarrativeFlag(
            flag_id="no_runs_detected",
            severity=FlagSeverity.INFO,
            title="No Runs Detected",
            message=f"Only {len(run_moments)} run(s) detected in a close game. Close games typically have scoring runs.",
            details={
                "run_count": len(run_moments),
                "final_margin": final_margin,
            },
        )
    
    return None


def _check_importance_variance(
    moments: Sequence["Moment"],
    config: NarrativeCheckConfig,
) -> NarrativeFlag | None:
    """Check for low importance variance (all moments rated similarly)."""
    if len(moments) < 5:
        return None
    
    scores = [
        getattr(m, 'importance_score', 0.0)
        for m in moments
        if hasattr(m, 'importance_score')
    ]
    
    if not scores:
        return None
    
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    
    if variance < config.min_importance_variance:
        return NarrativeFlag(
            flag_id="low_importance_variance",
            severity=FlagSeverity.INFO,
            title="Low Importance Variance",
            message="All moments have similar importance scores. Differentiation may be weak.",
            details={
                "variance": round(variance, 4),
                "min_score": round(min(scores), 2),
                "max_score": round(max(scores), 2),
            },
        )
    
    return None


def run_narrative_quality_checks(
    moments: Sequence["Moment"],
    final_margin: int = 0,
    config: NarrativeCheckConfig | None = None,
) -> NarrativeCheckResult:
    """Run all narrative quality checks on a moment set.
    
    Args:
        moments: The moments to check
        final_margin: Final score margin (home - away)
        config: Optional configuration for thresholds
    
    Returns:
        NarrativeCheckResult with all flags
    """
    if config is None:
        config = NarrativeCheckConfig()
    
    result = NarrativeCheckResult()
    
    # Core checks (required)
    checks = [
        _check_q1_flip_spam(moments, config),
        _check_q4_underrepresented(moments, final_margin, config),
        _check_mega_moments(moments, config),
        _check_closing_sequence(moments, final_margin, config),
    ]
    
    # Optional checks
    checks.extend([
        _check_excessive_neutral(moments, config),
        _check_no_players(moments, config),
        _check_no_runs_close_game(moments, final_margin, config),
        _check_importance_variance(moments, config),
    ])
    
    result.checks_run = len(checks)
    
    for flag in checks:
        if flag:
            result.flags.append(flag)
            if flag.severity == FlagSeverity.WARN:
                result.warnings_count += 1
            else:
                result.info_count += 1
    
    return result


# =============================================================================
# COMBINED WORKFLOW SUPPORT
# =============================================================================


@dataclass
class WorkflowAnalysis:
    """Complete workflow analysis for a game."""
    
    comparison: ComparisonResult | None = None
    quality_check: NarrativeCheckResult = field(default_factory=NarrativeCheckResult)
    game_id: str = ""
    version_a: str = ""
    version_b: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "version_a": self.version_a,
            "version_b": self.version_b,
            "comparison": self.comparison.to_dict() if self.comparison else None,
            "quality_check": self.quality_check.to_dict(),
        }


def analyze_game_workflow(
    game_id: str,
    old_moments: Sequence["Moment"] | None,
    new_moments: Sequence["Moment"],
    final_margin: int = 0,
    old_version: str = "v1",
    new_version: str = "v2",
    old_target_budget: int = 0,
    new_target_budget: int = 0,
    rank_records: Sequence[dict[str, Any]] | None = None,
    quality_config: NarrativeCheckConfig | None = None,
) -> WorkflowAnalysis:
    """Analyze a game for the workflow UI.
    
    This provides everything needed for the Compare Versions view
    and narrative quality checklist.
    
    Args:
        game_id: Game identifier
        old_moments: Previous version moments (None if first run)
        new_moments: New version moments
        final_margin: Final score margin
        old_version: Label for old version
        new_version: Label for new version
        old_target_budget: Target budget for old version
        new_target_budget: Target budget for new version
        rank_records: Optional rank+select records
        quality_config: Optional quality check configuration
    
    Returns:
        WorkflowAnalysis with comparison and quality data
    """
    analysis = WorkflowAnalysis(
        game_id=game_id,
        version_a=old_version,
        version_b=new_version,
    )
    
    # Run comparison if old moments exist
    if old_moments:
        analysis.comparison = compare_moment_versions(
            old_moments,
            new_moments,
            old_target_budget,
            new_target_budget,
            rank_records,
        )
    
    # Run quality checks on new moments
    analysis.quality_check = run_narrative_quality_checks(
        new_moments,
        final_margin,
        quality_config,
    )
    
    return analysis
