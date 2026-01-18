"""Task 3.1: Back-and-forth chapter moments.

Detects early-game volatility clusters and wraps FLIP/TIE sequences
into single "chapter" moments to improve readability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import ChapterConfig, DEFAULT_CHAPTER_CONFIG

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class VolatilityCluster:
    """Detected volatility cluster that may become a chapter."""

    start_idx: int
    end_idx: int
    play_span: int = 0
    lead_changes: int = 0
    ties: int = 0
    moments_count: int = 0
    absorbed_moment_ids: list[str] = field(default_factory=list)
    start_score: tuple[int, int] = (0, 0)
    end_score: tuple[int, int] = (0, 0)
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

    moments: list["Moment"] = field(default_factory=list)
    clusters_detected: list[VolatilityCluster] = field(default_factory=list)
    chapters_created: int = 0
    moments_absorbed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapters_created": self.chapters_created,
            "moments_absorbed": self.moments_absorbed,
            "clusters": [c.to_dict() for c in self.clusters_detected],
        }


def get_moment_quarter(moment: "Moment", events: Sequence[dict[str, Any]]) -> int:
    """Get the quarter a moment belongs to."""
    if 0 <= moment.start_play < len(events):
        return events[moment.start_play].get("quarter", 1) or 1
    return 1


def detect_volatility_clusters(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: ChapterConfig = DEFAULT_CHAPTER_CONFIG,
) -> list[VolatilityCluster]:
    """Detect early-game volatility clusters that could become chapters."""
    from ..moments import MomentType

    if not moments:
        return []

    clusters: list[VolatilityCluster] = []
    i = 0

    while i < len(moments):
        moment = moments[i]
        quarter = get_moment_quarter(moment, events)

        if quarter > config.max_quarter_for_chapter:
            i += 1
            continue

        if moment.type in (MomentType.FLIP, MomentType.TIE):
            cluster = _scan_for_cluster(moments, events, i, config)
            if cluster is not None:
                clusters.append(cluster)
                i = cluster.end_idx + 1
                continue

        i += 1

    return clusters


def _scan_for_cluster(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    start_idx: int,
    config: ChapterConfig,
) -> VolatilityCluster | None:
    """Scan from start_idx to find a volatility cluster."""
    from ..moments import MomentType

    if start_idx >= len(moments):
        return None

    cluster = VolatilityCluster(start_idx=start_idx, end_idx=start_idx)
    lead_changes = 0
    ties = 0
    absorbed_ids: list[str] = []

    first_moment = moments[start_idx]
    cluster.start_score = first_moment.score_before
    cluster.quarter = get_moment_quarter(first_moment, events)

    j = start_idx
    while j < len(moments):
        moment = moments[j]
        quarter = get_moment_quarter(moment, events)

        if quarter > config.max_quarter_for_chapter:
            break

        if moment.type.value in config.protected_types:
            break

        if moment.type.value not in config.absorbable_types:
            break

        if moment.type == MomentType.FLIP:
            lead_changes += 1
        elif moment.type == MomentType.TIE:
            ties += 1

        absorbed_ids.append(moment.id)
        cluster.end_idx = j
        cluster.end_score = moment.score_after

        j += 1

        total_plays = moments[cluster.end_idx].end_play - first_moment.start_play + 1
        if total_plays > config.max_plays_for_chapter:
            break

    cluster.moments_count = cluster.end_idx - cluster.start_idx + 1
    cluster.lead_changes = lead_changes
    cluster.ties = ties
    cluster.absorbed_moment_ids = absorbed_ids
    cluster.play_span = (
        moments[cluster.end_idx].end_play - first_moment.start_play + 1
    )

    if cluster.moments_count < 2:
        return None

    if cluster.play_span < config.min_plays_for_chapter:
        return None

    if (
        lead_changes < config.min_lead_changes_for_chapter
        and ties < config.min_ties_for_chapter
    ):
        return None

    return cluster


def create_chapter_moments(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    config: ChapterConfig = DEFAULT_CHAPTER_CONFIG,
) -> ChapterResult:
    """Create chapter moments by absorbing volatility clusters."""
    from ..moments import Moment, MomentType, MomentReason

    result = ChapterResult()
    clusters = detect_volatility_clusters(moments, events, config)
    result.clusters_detected = clusters

    if not clusters:
        result.moments = list(moments)
        return result

    output_moments: list[Moment] = []
    absorbed_indices: set[int] = set()

    for cluster in clusters:
        for idx in range(cluster.start_idx, cluster.end_idx + 1):
            absorbed_indices.add(idx)
        result.chapters_created += 1
        result.moments_absorbed += cluster.moments_count

    for i, moment in enumerate(moments):
        if i not in absorbed_indices:
            output_moments.append(moment)

    for cluster in clusters:
        first_moment = moments[cluster.start_idx]
        last_moment = moments[cluster.end_idx]

        chapter = Moment(
            id=f"chapter_{first_moment.id}",
            type=MomentType.NEUTRAL,
            start_play=first_moment.start_play,
            end_play=last_moment.end_play,
            play_count=cluster.play_span,
            score_before=cluster.start_score,
            score_after=cluster.end_score,
            ladder_tier_before=first_moment.ladder_tier_before,
            ladder_tier_after=last_moment.ladder_tier_after,
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

        output_moments.append(chapter)

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
        },
    )

    return result
