"""Task 3.3: Semantic mega-moment splitting.

Splits oversized moments at semantic break points (runs, tier changes,
timeouts) to improve readability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import SplitConfig, DEFAULT_SPLIT_CONFIG

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class SplitPoint:
    """A potential split point within a mega-moment."""

    play_index: int
    split_reason: str  # "run_start", "tier_change", "timeout_after_swing"
    score_at_split: tuple[int, int] = (0, 0)
    tier_at_split: int = 0
    run_team: str | None = None
    run_points: int = 0
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
    """Result of splitting a single mega-moment."""

    original_moment_id: str
    original_play_count: int
    was_split: bool = False
    split_points_found: list[SplitPoint] = field(default_factory=list)
    split_points_used: list[SplitPoint] = field(default_factory=list)
    segments: list[SplitSegment] = field(default_factory=list)
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
    mega_moments_found: int = 0
    mega_moments_split: int = 0
    total_segments_created: int = 0
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
    """Find semantic split points within a mega-moment."""
    from ..lead_ladder import compute_lead_state

    split_points: list[SplitPoint] = []

    moment_events = [
        e
        for e in events
        if e.get("event_type") == "pbp"
        and moment.start_play <= events.index(e) <= moment.end_play
    ]

    if len(moment_events) < config.min_segment_plays * 2:
        return []

    prev_tier = moment.ladder_tier_before
    run_tracker: dict[str, int] = {"home": 0, "away": 0}
    last_scorer: str | None = None

    for i, event in enumerate(moment_events):
        play_idx = moment.start_play + i

        if i < config.min_segment_plays:
            continue
        if i > len(moment_events) - config.min_segment_plays:
            continue

        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        state = compute_lead_state(home_score, away_score, thresholds)

        # Run detection
        if config.enable_run_splits:
            points_scored = event.get("points_scored", 0) or 0
            scoring_team = event.get("scoring_team")

            if points_scored > 0 and scoring_team:
                run_tracker[scoring_team] = (
                    run_tracker.get(scoring_team, 0) + points_scored
                )
                other_team = "away" if scoring_team == "home" else "home"

                if last_scorer != scoring_team:
                    run_tracker = {scoring_team: points_scored, other_team: 0}

                if run_tracker.get(scoring_team, 0) >= config.run_min_points:
                    split_points.append(
                        SplitPoint(
                            play_index=play_idx,
                            split_reason="run_start",
                            score_at_split=(home_score, away_score),
                            tier_at_split=state.tier,
                            run_team=scoring_team,
                            run_points=run_tracker.get(scoring_team, 0),
                        )
                    )
                    run_tracker = {"home": 0, "away": 0}

                last_scorer = scoring_team

        # Tier change detection
        if config.enable_tier_splits:
            if abs(state.tier - prev_tier) >= config.tier_change_min_delta:
                split_points.append(
                    SplitPoint(
                        play_index=play_idx,
                        split_reason="tier_change",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        tier_before=prev_tier,
                        tier_after=state.tier,
                    )
                )
                prev_tier = state.tier

        # Timeout detection
        if config.enable_timeout_splits:
            event_type = event.get("event_type_detail", "").lower()
            if "timeout" in event_type:
                recent_swing = False
                for j in range(max(0, i - 5), i):
                    recent_event = moment_events[j]
                    recent_home = recent_event.get("home_score", 0) or 0
                    recent_away = recent_event.get("away_score", 0) or 0
                    recent_state = compute_lead_state(
                        recent_home, recent_away, thresholds
                    )
                    if abs(recent_state.tier - state.tier) >= 1:
                        recent_swing = True
                        break

                if recent_swing:
                    split_points.append(
                        SplitPoint(
                            play_index=play_idx,
                            split_reason="timeout_after_swing",
                            score_at_split=(home_score, away_score),
                            tier_at_split=state.tier,
                        )
                    )

        prev_tier = state.tier

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
    """Select the best split points respecting minimum guards."""
    if not split_points:
        return []

    selected: list[SplitPoint] = []
    last_split_idx = moment.start_play

    priority = {"tier_change": 0, "run_start": 1, "timeout_after_swing": 2}
    sorted_points = sorted(
        split_points,
        key=lambda sp: (priority.get(sp.split_reason, 99), sp.play_index),
    )

    for sp in sorted_points:
        if len(selected) >= config.max_splits_per_moment:
            break

        if sp.play_index - last_split_idx < config.min_plays_between_splits:
            continue

        if moment.end_play - sp.play_index < config.min_segment_plays:
            continue

        selected.append(sp)
        last_split_idx = sp.play_index

    return sorted(selected, key=lambda sp: sp.play_index)


def split_mega_moment(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> MegaMomentSplitResult:
    """Split a single mega-moment into readable segments."""
    result = MegaMomentSplitResult(
        original_moment_id=moment.id,
        original_play_count=moment.play_count,
    )

    if moment.play_count < config.mega_moment_threshold:
        result.skip_reason = "below_threshold"
        return result

    split_points = find_split_points(moment, events, thresholds, config)
    result.split_points_found = split_points

    if not split_points:
        result.skip_reason = "no_split_points_found"
        return result

    selected_points = select_best_split_points(split_points, moment, config)
    result.split_points_used = selected_points

    if not selected_points:
        result.skip_reason = "no_valid_split_points"
        return result

    result.was_split = True

    segment_starts = [moment.start_play] + [sp.play_index for sp in selected_points]
    segment_ends = [sp.play_index - 1 for sp in selected_points] + [moment.end_play]

    for i, (start, end) in enumerate(zip(segment_starts, segment_ends)):
        score_before = (
            moment.score_before if i == 0 else selected_points[i - 1].score_at_split
        )
        score_after = (
            selected_points[i].score_at_split
            if i < len(selected_points)
            else moment.score_after
        )

        split_reason = "" if i == 0 else selected_points[i - 1].split_reason

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
    """Apply semantic splitting to all mega-moments."""
    from ..moments import Moment, MomentReason

    result = SplittingResult()
    output_moments: list[Moment] = []

    for moment in moments:
        if moment.play_count < config.mega_moment_threshold:
            output_moments.append(moment)
            continue

        result.mega_moments_found += 1

        split_result = split_mega_moment(moment, events, thresholds, config)
        result.split_results.append(split_result)

        if not split_result.was_split:
            output_moments.append(moment)
            continue

        result.mega_moments_split += 1

        for i, segment in enumerate(split_result.segments):
            new_moment = Moment(
                id=f"{moment.id}_seg{i+1}",
                type=moment.type,
                start_play=segment.start_play,
                end_play=segment.end_play,
                play_count=segment.play_count,
                score_before=segment.score_before,
                score_after=segment.score_after,
                ladder_tier_before=(
                    moment.ladder_tier_before if i == 0 else moment.ladder_tier_after
                ),
                ladder_tier_after=moment.ladder_tier_after,
                teams=moment.teams,
                team_in_control=moment.team_in_control,
            )

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

            proportion = segment.play_count / moment.play_count
            new_moment.importance_score = moment.importance_score * proportion
            new_moment.importance_factors = {
                "inherited_from": moment.id,
                "proportion": round(proportion, 2),
                "segment_index": i,
                "split_reason": segment.split_reason or "start",
            }

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
        },
    )

    return result
