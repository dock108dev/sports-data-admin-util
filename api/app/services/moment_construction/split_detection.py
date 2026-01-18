"""Split point detection.

Finds semantic split points within mega-moments based on narrative cues.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence, TYPE_CHECKING

from .config import SplitConfig, DEFAULT_SPLIT_CONFIG
from .split_types import SplitPoint

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


def find_split_points(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> list[SplitPoint]:
    """Find semantic split points within a mega-moment.

    Scans the moment for natural narrative break points:
    - Tier changes (Lead Ladder crossings)
    - Quarter transitions
    - Scoring runs beginning
    - Sustained pressure periods ending
    - Timeouts after momentum swings
    - Scoring drought endings

    Args:
        moment: The mega-moment to analyze
        events: All timeline events
        thresholds: Lead Ladder thresholds
        config: Split configuration

    Returns:
        List of potential split points, sorted by play index
    """
    from ..lead_ladder import compute_lead_state

    split_points: list[SplitPoint] = []

    # Build list of PBP events within this moment
    moment_events: list[tuple[int, dict[str, Any]]] = []
    for idx in range(moment.start_play, moment.end_play + 1):
        if idx < len(events):
            event = events[idx]
            if event.get("event_type") == "pbp":
                moment_events.append((idx, event))

    if len(moment_events) < config.min_segment_plays * 2:
        logger.debug(
            "split_points_skipped_too_few_events",
            extra={
                "moment_id": moment.id,
                "event_count": len(moment_events),
                "min_required": config.min_segment_plays * 2,
            },
        )
        return []

    # State tracking
    prev_tier = moment.ladder_tier_before
    prev_quarter: int | None = None
    run_tracker: dict[str, int] = {"home": 0, "away": 0}
    last_scorer: str | None = None

    # Pressure tracking
    pressure_start_idx: int | None = None
    pressure_start_score: tuple[int, int] = (0, 0)
    pressure_team: str | None = None
    pressure_plays: int = 0

    # Drought tracking
    last_scoring_idx: int = 0

    for local_idx, (play_idx, event) in enumerate(moment_events):
        # Skip edges to ensure minimum segment size
        if local_idx < config.min_segment_plays:
            continue
        if local_idx > len(moment_events) - config.min_segment_plays:
            continue

        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        state = compute_lead_state(home_score, away_score, thresholds)
        quarter = event.get("quarter", 1) or 1

        # --- Quarter transition detection ---
        if config.enable_quarter_splits and prev_quarter is not None:
            if quarter != prev_quarter:
                split_points.append(
                    SplitPoint(
                        play_index=play_idx,
                        split_reason="quarter",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        priority=config.priority_quarter,
                        quarter_before=prev_quarter,
                        quarter_after=quarter,
                    )
                )
                logger.debug(
                    "split_point_found_quarter",
                    extra={
                        "moment_id": moment.id,
                        "play_index": play_idx,
                        "quarter_before": prev_quarter,
                        "quarter_after": quarter,
                    },
                )
        prev_quarter = quarter

        # --- Tier change detection ---
        if config.enable_tier_splits:
            tier_delta = abs(state.tier - prev_tier)
            if tier_delta >= config.tier_change_min_delta:
                split_points.append(
                    SplitPoint(
                        play_index=play_idx,
                        split_reason="tier_change",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        priority=config.priority_tier_change,
                        tier_before=prev_tier,
                        tier_after=state.tier,
                    )
                )
                logger.debug(
                    "split_point_found_tier_change",
                    extra={
                        "moment_id": moment.id,
                        "play_index": play_idx,
                        "tier_before": prev_tier,
                        "tier_after": state.tier,
                    },
                )
                prev_tier = state.tier

        # --- Run detection ---
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
                            priority=config.priority_run_start,
                            run_team=scoring_team,
                            run_points=run_tracker.get(scoring_team, 0),
                        )
                    )
                    logger.debug(
                        "split_point_found_run",
                        extra={
                            "moment_id": moment.id,
                            "play_index": play_idx,
                            "run_team": scoring_team,
                            "run_points": run_tracker.get(scoring_team, 0),
                        },
                    )
                    run_tracker = {"home": 0, "away": 0}

                last_scorer = scoring_team
                last_scoring_idx = local_idx

        # --- Sustained pressure detection ---
        if config.enable_pressure_splits:
            points_scored = event.get("points_scored", 0) or 0
            scoring_team = event.get("scoring_team")

            if points_scored > 0 and scoring_team:
                if pressure_team is None:
                    # Start tracking pressure
                    pressure_start_idx = local_idx
                    pressure_start_score = (
                        home_score - points_scored if scoring_team == "home" else home_score,
                        away_score - points_scored if scoring_team == "away" else away_score,
                    )
                    pressure_team = scoring_team
                    pressure_plays = 1
                elif scoring_team == pressure_team:
                    # Continue pressure
                    pressure_plays += 1
                else:
                    # Pressure ended - check if it was significant
                    if pressure_start_idx is not None:
                        pressure_point_diff = (
                            (home_score - pressure_start_score[0]) if pressure_team == "home"
                            else (away_score - pressure_start_score[1])
                        )

                        if (pressure_plays >= config.pressure_min_plays
                                and pressure_point_diff >= config.pressure_min_point_diff):
                            split_points.append(
                                SplitPoint(
                                    play_index=play_idx,
                                    split_reason="pressure_end",
                                    score_at_split=(home_score, away_score),
                                    tier_at_split=state.tier,
                                    priority=config.priority_pressure,
                                    pressure_team=pressure_team,
                                    pressure_points=pressure_point_diff,
                                    pressure_plays=pressure_plays,
                                )
                            )
                            logger.debug(
                                "split_point_found_pressure_end",
                                extra={
                                    "moment_id": moment.id,
                                    "play_index": play_idx,
                                    "pressure_team": pressure_team,
                                    "pressure_points": pressure_point_diff,
                                    "pressure_plays": pressure_plays,
                                },
                            )

                    # Reset and start new pressure tracking
                    pressure_start_idx = local_idx
                    pressure_start_score = (
                        home_score - points_scored if scoring_team == "home" else home_score,
                        away_score - points_scored if scoring_team == "away" else away_score,
                    )
                    pressure_team = scoring_team
                    pressure_plays = 1

        # --- Timeout after swing detection ---
        if config.enable_timeout_splits:
            event_type = event.get("event_type_detail", "").lower()
            if "timeout" in event_type:
                recent_swing = False
                for j in range(max(0, local_idx - 5), local_idx):
                    _, recent_event = moment_events[j]
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
                            priority=config.priority_timeout,
                        )
                    )
                    logger.debug(
                        "split_point_found_timeout",
                        extra={
                            "moment_id": moment.id,
                            "play_index": play_idx,
                        },
                    )

        # --- Scoring drought detection ---
        if config.enable_drought_splits:
            plays_since_score = local_idx - last_scoring_idx
            points_scored = event.get("points_scored", 0) or 0

            if points_scored > 0 and plays_since_score >= config.drought_min_plays:
                split_points.append(
                    SplitPoint(
                        play_index=play_idx,
                        split_reason="drought_end",
                        score_at_split=(home_score, away_score),
                        tier_at_split=state.tier,
                        priority=config.priority_drought,
                        drought_plays=plays_since_score,
                    )
                )
                logger.debug(
                    "split_point_found_drought_end",
                    extra={
                        "moment_id": moment.id,
                        "play_index": play_idx,
                        "drought_plays": plays_since_score,
                    },
                )

        prev_tier = state.tier

    # Deduplicate by play index, keeping highest priority (lowest number)
    unique_points: dict[int, SplitPoint] = {}
    for sp in split_points:
        if sp.play_index not in unique_points:
            unique_points[sp.play_index] = sp
        elif sp.priority < unique_points[sp.play_index].priority:
            unique_points[sp.play_index] = sp

    result = sorted(unique_points.values(), key=lambda sp: sp.play_index)

    logger.debug(
        "split_points_found",
        extra={
            "moment_id": moment.id,
            "total_found": len(result),
            "by_reason": count_by_reason(result),
        },
    )

    return result


def count_by_reason(split_points: list[SplitPoint]) -> dict[str, int]:
    """Count split points by reason for diagnostics."""
    counts: dict[str, int] = {}
    for sp in split_points:
        counts[sp.split_reason] = counts.get(sp.split_reason, 0) + 1
    return counts
