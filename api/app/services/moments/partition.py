"""Game partitioning into moments.

This module contains the main partition_game algorithm that:
1. Normalizes scores
2. Detects boundaries (tier crossings, runs)
3. Creates moments from boundaries
4. Merges and validates moments
5. Applies importance scoring
6. Applies narrative selection
7. Applies construction improvements
8. Enriches moments with player data
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ..lead_ladder import compute_lead_state, Leader
from ..moments_normalization import normalize_scores
from ..moments_boundaries import (
    BoundaryEvent,
    get_canonical_pbp_indices,
    detect_boundaries,
    detect_run_boundaries,
)
from ..moments_runs import DetectedRun, detect_runs, find_run_for_moment, run_to_info
from ..moments_merging import (
    merge_invalid_moments,
    merge_consecutive_moments,
    enforce_quarter_limits,
)
from ..moments_validation import (
    validate_score_continuity,
    assert_moment_continuity,
    validate_moment_coverage,
)

from .types import Moment, MomentType, RunInfo
from .config import DEFAULT_HYSTERESIS_PLAYS, DEFAULT_FLIP_HYSTERESIS_PLAYS, DEFAULT_TIE_HYSTERESIS_PLAYS
from .helpers import create_moment, get_score, is_period_opener
from .mega_moments import detect_back_and_forth_phase, find_quarter_boundaries, split_mega_moment
from .game_structure import (
    build_game_phase_context,
    GamePhaseContext,
)

logger = logging.getLogger(__name__)


def partition_game(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    thresholds: Sequence[int] | None = None,
    hysteresis_plays: int = DEFAULT_HYSTERESIS_PLAYS,
    flip_hysteresis_plays: int = DEFAULT_FLIP_HYSTERESIS_PLAYS,
    tie_hysteresis_plays: int = DEFAULT_TIE_HYSTERESIS_PLAYS,
    game_context: dict[str, str] | None = None,
) -> list[Moment]:
    """Partition a game timeline into moments based on Lead Ladder.

    CORE GUARANTEES:
    1. Every CANONICAL PBP play belongs to exactly ONE moment
    2. Moments are contiguous (no gaps in canonical stream)
    3. Moments are chronologically ordered by start_play
    4. Moment count stays within sport-specific budget
    5. Every moment has a reason for existing
    6. Score continuity is preserved
    7. Participants are RESOLVED and FROZEN on the moment

    Args:
        timeline: Full timeline events (PBP + social)
        summary: Game summary metadata
        thresholds: Lead Ladder tier thresholds
        hysteresis_plays: Number of plays to confirm tier changes
        flip_hysteresis_plays: Number of plays leader must hold to confirm FLIP
        tie_hysteresis_plays: Number of plays to confirm TIE
        game_context: Team names and abbreviations for resolution
    """
    if not timeline:
        return []

    _game_context = game_context or {}

    # Normalize scores before any processing
    normalized = normalize_scores(timeline)
    events = normalized.events

    if normalized.had_corrections():
        logger.info(
            "score_normalization_applied",
            extra={
                "corrections_count": len(normalized.normalizations),
                "reasons": [n.reason for n in normalized.normalizations],
            },
        )

    # Determine sport from summary
    sport = summary.get("sport", "NBA") if isinstance(summary, dict) else "NBA"

    # Build authoritative game phase context
    phase_context = build_game_phase_context(events, sport=sport)

    logger.info(
        "game_phase_context_initialized",
        extra=phase_context.to_dict(),
    )

    # Get CANONICAL PBP event indices
    pbp_indices = get_canonical_pbp_indices(events)
    if not pbp_indices:
        logger.warning(
            "partition_game_no_canonical_pbp", extra={"timeline_len": len(events)}
        )
        return []

    if thresholds is None:
        logger.warning(
            "partition_game_no_thresholds: No thresholds provided, using minimal default [5]"
        )
        thresholds = [5]

    # Detect tier-based boundaries
    tier_boundaries, density_gate_decisions, tier_false_drama = detect_boundaries(
        events,
        pbp_indices,
        thresholds,
        hysteresis_plays,
        flip_hysteresis_plays,
        tie_hysteresis_plays,
    )

    # Log density gating results if any FLIP/TIE events were processed
    if density_gate_decisions:
        suppressed = [d for d in density_gate_decisions if d.density_gate_applied]
        if suppressed:
            logger.info(
                "flip_tie_density_gating_applied",
                extra={
                    "total_evaluated": len(density_gate_decisions),
                    "suppressed_count": len(suppressed),
                    "suppressed_events": [
                        {
                            "index": d.event_index,
                            "type": d.crossing_type,
                            "reason": d.reason,
                            "plays_since_last": d.plays_since_last,
                            "seconds_since_last": d.seconds_since_last,
                            "is_in_closing": d.is_in_closing_window,
                        }
                        for d in suppressed
                    ],
                },
            )

    # Log late false drama suppression for tier boundaries
    if tier_false_drama:
        suppressed = [d for d in tier_false_drama if d.suppressed]
        if suppressed:
            logger.info(
                "late_false_drama_tier_suppression",
                extra={
                    "total_evaluated": len(tier_false_drama),
                    "suppressed_count": len(suppressed),
                    "suppressed_events": [
                        {
                            "index": d.event_index,
                            "type": d.crossing_type,
                            "margin": d.margin_after,
                            "tier": d.tier_after,
                            "seconds": d.seconds_remaining,
                        }
                        for d in suppressed
                    ],
                },
            )

    # Detect runs and evaluate for boundary creation
    runs = detect_runs(events)
    run_boundaries, run_decisions, run_false_drama = detect_run_boundaries(
        events, runs, thresholds, tier_boundaries
    )
    
    # Log late false drama suppression for run boundaries
    if run_false_drama:
        suppressed = [d for d in run_false_drama if d.suppressed]
        if suppressed:
            logger.info(
                "late_false_drama_run_suppression",
                extra={
                    "total_evaluated": len(run_false_drama),
                    "suppressed_count": len(suppressed),
                    "suppressed_runs": [
                        {
                            "index": d.event_index,
                            "margin": d.margin_after,
                            "tier": d.tier_after,
                            "seconds": d.seconds_remaining,
                        }
                        for d in suppressed
                    ],
                },
            )

    if run_boundaries:
        logger.info(
            "run_boundaries_created",
            extra={
                "run_boundaries_count": len(run_boundaries),
                "total_runs_evaluated": len(runs),
                "decisions": [
                    {
                        "points": d.run_points,
                        "reason": d.reason,
                        "created": d.created_boundary,
                    }
                    for d in run_decisions
                ],
            },
        )

    # Merge all boundaries and sort by index
    boundaries = tier_boundaries + run_boundaries
    boundaries.sort(key=lambda b: b.index)

    # Build moments from boundaries
    moments: list[Moment] = []
    moment_id = 0

    boundary_at: dict[int, BoundaryEvent] = {b.index: b for b in boundaries}

    current_start: int | None = None
    current_type: MomentType = MomentType.NEUTRAL
    current_boundary: BoundaryEvent | None = None
    current_is_period_start = False

    moment_start_score = (0, 0)
    current_score = (0, 0)
    prev_event: dict[str, Any] | None = None

    for idx, i in enumerate(pbp_indices):
        event = events[i]

        is_opener = is_period_opener(event, prev_event)
        if is_opener:
            current_is_period_start = True

        if i in boundary_at:
            boundary = boundary_at[i]

            if current_start is not None:
                prev_idx = pbp_indices[idx - 1]
                moment = create_moment(
                    moment_id=moment_id,
                    events=events,
                    start_idx=current_start,
                    end_idx=prev_idx,
                    moment_type=current_type,
                    thresholds=thresholds,
                    boundary=current_boundary,
                    score_before=moment_start_score,
                    game_context=_game_context,
                )
                moment.is_period_start = current_is_period_start
                moments.append(moment)
                moment_id += 1

                moment_start_score = current_score
                current_is_period_start = is_opener

            current_start = i
            current_type = boundary.moment_type
            current_boundary = boundary
        else:
            if current_start is None:
                current_start = i
                current_type = MomentType.NEUTRAL
                current_is_period_start = is_opener

        current_score = get_score(event)
        prev_event = event

    # Close final moment
    if current_start is not None:
        moment = create_moment(
            moment_id=moment_id,
            events=events,
            start_idx=current_start,
            end_idx=pbp_indices[-1],
            moment_type=current_type,
            thresholds=thresholds,
            boundary=current_boundary,
            score_before=moment_start_score,
            game_context=_game_context,
        )
        moment.is_period_start = current_is_period_start
        moments.append(moment)

    # Attach runs to moments as metadata
    _attach_runs_to_moments(moments, runs)

    # Merge consecutive same-type moments
    pre_merge_count = len(moments)
    moments = merge_consecutive_moments(moments)

    # Enforce per-quarter limits
    moments = enforce_quarter_limits(moments, events)

    # Merge invalid moments
    moments = merge_invalid_moments(moments)

    # Split mega-moments
    split_moments: list[Moment] = []
    mega_moment_count = 0
    for moment in moments:
        if moment.play_count > 50 and moment.type in (
            MomentType.NEUTRAL,
            MomentType.CUT,
            MomentType.LEAD_BUILD,
        ):
            mega_moment_count += 1
            logger.info(
                "mega_moment_detected",
                extra={
                    "moment_id": moment.id,
                    "type": moment.type.value,
                    "play_count": moment.play_count,
                    "score_range": f"{moment.score_start} → {moment.score_end}",
                },
            )

            is_back_and_forth = detect_back_and_forth_phase(
                events, moment.start_play, moment.end_play, thresholds
            )

            logger.info(
                "back_and_forth_check",
                extra={
                    "moment_id": moment.id,
                    "is_back_and_forth": is_back_and_forth,
                },
            )

            if is_back_and_forth:
                sub_moments = split_mega_moment(
                    moment, events, thresholds, _game_context, max_plays=40
                )
                split_moments.extend(sub_moments)

                for sub in sub_moments:
                    if (
                        sub.type in (MomentType.CUT, MomentType.LEAD_BUILD)
                        and sub.play_count > 20
                    ):
                        sub.type = MomentType.NEUTRAL
                        if sub.reason:
                            sub.reason.narrative_delta = "back and forth"
            else:
                quarter_boundaries = find_quarter_boundaries(
                    events, moment.start_play, moment.end_play
                )
                logger.info(
                    "quarter_boundaries_found",
                    extra={
                        "moment_id": moment.id,
                        "boundary_count": len(quarter_boundaries),
                    },
                )
                if quarter_boundaries:
                    sub_moments = split_mega_moment(
                        moment, events, thresholds, _game_context, max_plays=100
                    )
                    split_moments.extend(sub_moments)
                else:
                    split_moments.append(moment)
        else:
            split_moments.append(moment)

    if mega_moment_count > 0:
        logger.info(
            "mega_moment_splitting_complete",
            extra={
                "mega_moments_detected": mega_moment_count,
                "moments_before": len(moments),
                "moments_after": len(split_moments),
            },
        )

    moments = split_moments

    # sport already determined at start of function

    # Renumber moment IDs
    for i, m in enumerate(moments):
        m.id = f"m_{i + 1:03d}"

    # Compute importance scores
    from ..moment_importance import score_all_moments, log_importance_summary

    importance_factors_list = score_all_moments(moments, events, thresholds)
    for moment, factors in zip(moments, importance_factors_list):
        moment.importance_score = factors.importance_score
        moment.importance_factors = factors.to_dict()

    log_importance_summary(moments, importance_factors_list)

    pre_selection_count = len(moments)

    # Apply narrative selection
    from ..moment_selection import apply_narrative_selection

    moments, selection_result = apply_narrative_selection(
        moments, events, thresholds, sport
    )

    if selection_result.rank_select:
        logger.info(
            "phase_2_2_rank_select_applied",
            extra={
                "candidates": selection_result.rank_select.total_candidates,
                "selected": selection_result.rank_select.selected_count,
                "rejected": selection_result.rank_select.rejected_count,
                "min_selected_importance": selection_result.rank_select.min_selected_importance,
                "max_rejected_importance": selection_result.rank_select.max_rejected_importance,
            },
        )

    logger.info(
        "narrative_selection_applied",
        extra={
            "pre_selection": pre_selection_count,
            "post_selection": len(moments),
            "target_budget": selection_result.budget.target_moment_count,
            "early_game_count": selection_result.early_game_count,
            "closing_count": selection_result.closing_count,
            "swaps_performed": selection_result.swaps_performed,
        },
    )

    post_phase2_count = len(moments)

    # Apply construction improvements
    from ..moment_construction import apply_construction_improvements

    construction_result = apply_construction_improvements(moments, events, thresholds)
    moments = construction_result.moments

    if construction_result.chapter_result:
        logger.info(
            "phase_3_1_chapters_applied",
            extra={
                "chapters_created": construction_result.chapter_result.chapters_created,
                "moments_absorbed": construction_result.chapter_result.moments_absorbed,
            },
        )

    if construction_result.quota_result:
        logger.info(
            "phase_3_2_quotas_applied",
            extra={
                "is_close_game": construction_result.quota_result.is_close_game,
                "is_blowout": construction_result.quota_result.is_blowout,
                "quarters_compressed": construction_result.quota_result.quarters_compressed,
                "moments_merged": construction_result.quota_result.moments_merged,
            },
        )

    if construction_result.splitting_result:
        logger.info(
            "phase_3_3_splitting_applied",
            extra={
                "mega_moments_found": construction_result.splitting_result.mega_moments_found,
                "mega_moments_split": construction_result.splitting_result.mega_moments_split,
                "total_segments_created": construction_result.splitting_result.total_segments_created,
            },
        )

    # Enrich moments with player data
    from ..moment_enrichment import enrich_moments_with_boxscore

    home_team = (
        summary.get("home_team", {}).get("name", "Home")
        if isinstance(summary, dict)
        else "Home"
    )
    away_team = (
        summary.get("away_team", {}).get("name", "Away")
        if isinstance(summary, dict)
        else "Away"
    )

    enrichment_result = enrich_moments_with_boxscore(
        moments, events, home_team, away_team
    )
    moments = enrichment_result.moments

    logger.info(
        "phase_4_enrichment_applied",
        extra={
            "moments_enriched": enrichment_result.moments_enriched,
            "players_identified": enrichment_result.players_identified,
            "total_scoring_plays": enrichment_result.total_scoring_plays,
        },
    )

    # Validate
    validate_moment_coverage(moments, pbp_indices)
    validate_score_continuity(moments)
    assert_moment_continuity(moments)

    # Final renumber
    for i, m in enumerate(moments):
        m.id = f"m_{i + 1:03d}"

    logger.info(
        "partition_game_complete",
        extra={
            "pre_merge_count": pre_merge_count,
            "post_phase2_count": post_phase2_count,
            "post_phase3_count": len(moments),
            "target_budget": selection_result.budget.target_moment_count,
            "dynamic_budget_signals": selection_result.budget.signals.to_dict(),
            "chapters_created": (
                construction_result.chapter_result.chapters_created
                if construction_result.chapter_result
                else 0
            ),
            "notable_count": sum(1 for m in moments if m.is_notable),
            "phase_context": phase_context.to_dict(),
        },
    )

    return moments


def _attach_runs_to_moments(
    moments: list[Moment],
    runs: list[DetectedRun],
) -> None:
    """Attach detected runs to moments as metadata.

    PROMOTION RULES:
    - A run is promoted to run_info ONLY if it caused a tier change
    - Runs that didn't cause tier changes become key_play_ids

    This modifies moments in place.
    """
    PROMOTABLE_TYPES = {MomentType.LEAD_BUILD, MomentType.CUT, MomentType.FLIP}
    attached_runs: set[int] = set()

    for moment in moments:
        run = find_run_for_moment(runs, moment.start_play, moment.end_play)

        if run is None:
            continue

        run_idx = runs.index(run)
        if run_idx in attached_runs:
            continue

        if moment.type in PROMOTABLE_TYPES:
            moment.run_info = run_to_info(run)
            attached_runs.add(run_idx)

            if moment.note:
                moment.note = f"{moment.note} ({run.points}-0 run)"
            else:
                moment.note = f"{run.points}-0 run"
        else:
            for play_id in run.play_ids:
                if play_id not in moment.key_play_ids:
                    moment.key_play_ids.append(play_id)
            attached_runs.add(run_idx)


def get_notable_moments(moments: list[Moment]) -> list[Moment]:
    """Return moments that are notable (is_notable=True).

    Notable moments are a VIEW of moments, not a separate entity.
    They are filtered client-side or server-side from the full moment list.
    """
    return [m for m in moments if m.is_notable]


def validate_moments(
    timeline: Sequence[dict[str, Any]],
    moments: list[Moment],
) -> bool:
    """Validate moment partitioning.

    Checks:
    1. All PBP plays are assigned to exactly one moment
    2. Moments are ordered chronologically
    3. No overlapping moment boundaries

    Returns:
        True if valid

    Raises:
        MomentValidationError: If validation fails
    """
    from ..moments_validation import MomentValidationError

    if not moments:
        return True

    pbp_indices = {
        i for i, e in enumerate(timeline) if e.get("event_type") == "pbp"
    }

    for i in range(1, len(moments)):
        if moments[i].start_play < moments[i - 1].start_play:
            raise MomentValidationError(
                f"Moments not chronological: {moments[i-1].id} starts at "
                f"{moments[i-1].start_play}, {moments[i].id} starts at {moments[i].start_play}"
            )

    for i in range(1, len(moments)):
        if moments[i].start_play <= moments[i - 1].end_play:
            raise MomentValidationError(
                f"Overlapping moments: {moments[i-1].id} ends at {moments[i-1].end_play}, "
                f"{moments[i].id} starts at {moments[i].start_play}"
            )

    covered: set[int] = set()
    for moment in moments:
        for idx in range(moment.start_play, moment.end_play + 1):
            covered.add(idx)

    uncovered_pbp = pbp_indices - covered
    if uncovered_pbp:
        raise MomentValidationError(
            f"Uncovered PBP plays: {sorted(uncovered_pbp)[:10]}..."
        )

    return True
