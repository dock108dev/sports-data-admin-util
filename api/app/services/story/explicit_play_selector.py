"""
Story Explicit Play Selector: Deterministic selection of plays to narrate.

This module determines WHICH plays inside a CondensedMoment MUST be
explicitly narrated. Selection is deterministic, grounded in concrete
PBP signals, and contains no narrative generation.

AUTHORITATIVE INPUTS:
- docs/story_contract.md
- docs/pbp_story_assumptions.md
- story/schema.py
- story/moment_builder.py

SELECTION RULES (applied in priority order):

1. SCORING_PLAY
   - Any play that changes the score (home_score or away_score delta)
   - All scoring plays in a moment are selected

2. TURNOVER_TO_SCORE
   - A turnover play that directly precedes a scoring play
   - The turnover is selected IN ADDITION to the scoring play
   - "Directly precedes" means the next play in sequence is a score

3. FOUL_TO_POINTS
   - A foul play followed by made free throws
   - The foul is selected if free throws result in points
   - Does not double-select the free throws (already selected as scoring)

4. FALLBACK
   - If no plays selected by rules 1-3, select the LAST play
   - Guarantees non-empty selection for contract compliance

GUARANTEES:
- explicitly_narrated_play_ids is NON-EMPTY
- explicitly_narrated_play_ids ⊂ play_ids
- Selection is deterministic for identical inputs
- No plays from outside the moment are referenced
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .moment_builder import (
    PlayData,
    TURNOVER_KEYWORDS,
    FOUL_KEYWORDS,
    FREE_THROW_KEYWORDS,
    _normalize_text,
    _contains_keyword,
)
from .schema import CondensedMoment, ScoreTuple, SchemaValidationError


class SelectionRule(Enum):
    """Concrete rules used to select explicitly narrated plays."""

    SCORING_PLAY = "SCORING_PLAY"
    TURNOVER_TO_SCORE = "TURNOVER_TO_SCORE"
    FOUL_TO_POINTS = "FOUL_TO_POINTS"
    FALLBACK_LAST_PLAY = "FALLBACK_LAST_PLAY"


class SelectionError(Exception):
    """Raised when play selection fails due to contract violation."""

    pass


@dataclass
class SelectionDebugInfo:
    """Debug information for explicit play selection."""

    selected_play_ids: tuple[int, ...]
    rules_applied: tuple[SelectionRule, ...]
    fallback_used: bool
    play_rule_mapping: dict[int, SelectionRule]


@dataclass
class SelectionResult:
    """Result of explicit play selection."""

    explicitly_narrated_play_ids: tuple[int, ...]
    debug_info: SelectionDebugInfo | None = None


def _is_turnover(play: PlayData) -> bool:
    """Detect if play is a turnover event."""
    return (
        _contains_keyword(play.description, TURNOVER_KEYWORDS)
        or _contains_keyword(play.play_type, TURNOVER_KEYWORDS)
    )


def _is_foul(play: PlayData) -> bool:
    """Detect if play is a foul event."""
    return (
        _contains_keyword(play.description, FOUL_KEYWORDS)
        or _contains_keyword(play.play_type, FOUL_KEYWORDS)
    )


def _is_free_throw(play: PlayData) -> bool:
    """Detect if play is a free throw event."""
    return (
        _contains_keyword(play.description, FREE_THROW_KEYWORDS)
        or _contains_keyword(play.play_type, FREE_THROW_KEYWORDS)
    )


def _is_made_free_throw(play: PlayData, prev_home: int, prev_away: int) -> bool:
    """Detect if play is a made free throw (changes score and is FT)."""
    if not _is_free_throw(play):
        return False
    return play.home_score != prev_home or play.away_score != prev_away


def _detect_score_changes(plays: list[PlayData]) -> list[tuple[int, PlayData]]:
    """Detect all plays that change the score.

    Returns list of (index_in_list, play) tuples for scoring plays.
    Uses score comparison to detect changes, not play_type heuristics.
    """
    scoring_plays: list[tuple[int, PlayData]] = []

    if not plays:
        return scoring_plays

    # First play: check if score is non-zero at start
    # This handles the case where a moment starts with an already-scored play
    # Per contract, score_before is the score before the moment starts
    # So first play having non-zero score doesn't mean it scored

    # Compare each play to its predecessor
    for i in range(len(plays)):
        if i == 0:
            # First play in moment - we cannot determine if it scored
            # without knowing the score_before the moment
            # This will be handled by the caller who has that context
            continue

        prev_home = plays[i - 1].home_score
        prev_away = plays[i - 1].away_score

        if plays[i].home_score != prev_home or plays[i].away_score != prev_away:
            scoring_plays.append((i, plays[i]))

    return scoring_plays


def _detect_turnovers_to_scores(
    plays: list[PlayData],
    scoring_indices: set[int],
) -> list[tuple[int, PlayData]]:
    """Detect turnovers that directly precede scoring plays.

    A turnover is selected if the NEXT play in the moment is a scoring play.
    """
    turnovers: list[tuple[int, PlayData]] = []

    for i, play in enumerate(plays):
        if not _is_turnover(play):
            continue

        # Check if next play is a scoring play
        next_index = i + 1
        if next_index in scoring_indices:
            turnovers.append((i, play))

    return turnovers


def _detect_fouls_to_points(
    plays: list[PlayData],
    scoring_indices: set[int],
) -> list[tuple[int, PlayData]]:
    """Detect fouls that lead to points via free throws.

    A foul is selected if:
    - It is followed by free throw(s) in the same moment
    - At least one of those free throws results in points (score change)
    """
    fouls: list[tuple[int, PlayData]] = []

    for i, play in enumerate(plays):
        if not _is_foul(play):
            continue

        # Look for subsequent free throws that score
        found_scoring_ft = False
        for j in range(i + 1, len(plays)):
            subsequent = plays[j]

            if _is_free_throw(subsequent):
                # Check if this FT resulted in points
                if j in scoring_indices:
                    found_scoring_ft = True
                    break
            else:
                # Non-FT play encountered; stop looking
                break

        if found_scoring_ft:
            fouls.append((i, play))

    return fouls


def select_explicit_plays(
    plays: Sequence[PlayData],
    score_before: tuple[int, int],
    *,
    debug: bool = False,
) -> SelectionResult:
    """Select plays to be explicitly narrated from a moment's plays.

    Args:
        plays: Ordered sequence of plays within the moment
        score_before: (home, away) score before the first play
        debug: If True, include debug information

    Returns:
        SelectionResult with explicitly_narrated_play_ids

    Raises:
        SelectionError: If selection fails or results in empty set
    """
    if not plays:
        raise SelectionError("Cannot select from empty play list")

    plays_list = list(plays)
    selected_ids: set[int] = set()
    play_rule_mapping: dict[int, SelectionRule] = {}
    rules_applied: set[SelectionRule] = set()

    # Build augmented play list with score_before for first play comparison
    # We need to detect if the first play itself is a scoring play
    prev_home, prev_away = score_before

    # RULE 1: SCORING_PLAY - detect all scoring plays
    scoring_indices: set[int] = set()

    for i, play in enumerate(plays_list):
        is_scoring = (play.home_score != prev_home or play.away_score != prev_away)

        if is_scoring:
            scoring_indices.add(i)
            selected_ids.add(play.play_index)
            play_rule_mapping[play.play_index] = SelectionRule.SCORING_PLAY
            rules_applied.add(SelectionRule.SCORING_PLAY)

        # Update prev scores for next iteration
        prev_home = play.home_score
        prev_away = play.away_score

    # RULE 2: TURNOVER_TO_SCORE - turnovers directly preceding scores
    turnovers = _detect_turnovers_to_scores(plays_list, scoring_indices)
    for _, play in turnovers:
        if play.play_index not in selected_ids:
            selected_ids.add(play.play_index)
            play_rule_mapping[play.play_index] = SelectionRule.TURNOVER_TO_SCORE
            rules_applied.add(SelectionRule.TURNOVER_TO_SCORE)

    # RULE 3: FOUL_TO_POINTS - fouls leading to free throw points
    fouls = _detect_fouls_to_points(plays_list, scoring_indices)
    for _, play in fouls:
        if play.play_index not in selected_ids:
            selected_ids.add(play.play_index)
            play_rule_mapping[play.play_index] = SelectionRule.FOUL_TO_POINTS
            rules_applied.add(SelectionRule.FOUL_TO_POINTS)

    # RULE 4: FALLBACK - if nothing selected, use last play
    fallback_used = False
    if not selected_ids:
        last_play = plays_list[-1]
        selected_ids.add(last_play.play_index)
        play_rule_mapping[last_play.play_index] = SelectionRule.FALLBACK_LAST_PLAY
        rules_applied.add(SelectionRule.FALLBACK_LAST_PLAY)
        fallback_used = True

    # Sort selected IDs by play_index order (preserve chronology)
    sorted_ids = tuple(sorted(selected_ids))

    # Validation: ensure non-empty and subset of input
    if not sorted_ids:
        raise SelectionError("Selection resulted in empty set (should be impossible)")

    input_ids = {p.play_index for p in plays_list}
    for pid in sorted_ids:
        if pid not in input_ids:
            raise SelectionError(
                f"Selected play_id {pid} not in moment's plays (internal error)"
            )

    debug_info = None
    if debug:
        debug_info = SelectionDebugInfo(
            selected_play_ids=sorted_ids,
            rules_applied=tuple(sorted(rules_applied, key=lambda r: r.value)),
            fallback_used=fallback_used,
            play_rule_mapping=play_rule_mapping,
        )

    return SelectionResult(
        explicitly_narrated_play_ids=sorted_ids,
        debug_info=debug_info,
    )


def apply_selection_to_moment(
    moment: CondensedMoment,
    plays: Sequence[PlayData],
    *,
    debug: bool = False,
) -> tuple[CondensedMoment, SelectionDebugInfo | None]:
    """Apply explicit play selection to a CondensedMoment.

    Creates a new CondensedMoment with explicitly_narrated_play_ids populated
    based on the selection rules.

    Args:
        moment: The moment to update (read-only, returns new instance)
        plays: The underlying PBP plays for this moment
        debug: If True, return debug information

    Returns:
        Tuple of (updated CondensedMoment, optional debug info)

    Raises:
        SelectionError: If plays don't match moment or selection fails
    """
    # Validate plays match moment
    moment_play_ids = set(moment.play_ids)
    input_play_ids = {p.play_index for p in plays}

    if moment_play_ids != input_play_ids:
        missing = moment_play_ids - input_play_ids
        extra = input_play_ids - moment_play_ids
        raise SelectionError(
            f"Plays don't match moment. Missing: {missing}, Extra: {extra}"
        )

    # Extract score_before from moment
    score_before = (moment.score_before.home, moment.score_before.away)

    # Perform selection
    result = select_explicit_plays(plays, score_before, debug=debug)

    # Create new moment with updated selection
    new_moment = CondensedMoment(
        play_ids=moment.play_ids,
        explicitly_narrated_play_ids=result.explicitly_narrated_play_ids,
        start_clock=moment.start_clock,
        end_clock=moment.end_clock,
        period=moment.period,
        score_before=moment.score_before,
        score_after=moment.score_after,
        narrative=moment.narrative,
    )

    return new_moment, result.debug_info


def select_plays_for_moments(
    moments: Sequence[CondensedMoment],
    plays_by_moment: Sequence[Sequence[PlayData]],
    *,
    debug: bool = False,
) -> list[tuple[CondensedMoment, SelectionDebugInfo | None]]:
    """Apply explicit play selection to multiple moments.

    Args:
        moments: Sequence of moments to update
        plays_by_moment: Corresponding plays for each moment (same order)
        debug: If True, include debug information

    Returns:
        List of (updated moment, optional debug info) tuples

    Raises:
        SelectionError: If counts don't match or any selection fails
    """
    if len(moments) != len(plays_by_moment):
        raise SelectionError(
            f"Moment count ({len(moments)}) doesn't match "
            f"plays_by_moment count ({len(plays_by_moment)})"
        )

    results: list[tuple[CondensedMoment, SelectionDebugInfo | None]] = []

    for moment, plays in zip(moments, plays_by_moment):
        updated_moment, debug_info = apply_selection_to_moment(
            moment, plays, debug=debug
        )
        results.append((updated_moment, debug_info))

    return results


def validate_selection(
    moment: CondensedMoment,
) -> None:
    """Validate that a moment's explicit play selection meets contract requirements.

    Raises SelectionError if validation fails.
    """
    # Non-empty check
    if not moment.explicitly_narrated_play_ids:
        raise SelectionError(
            f"Moment has empty explicitly_narrated_play_ids (contract violation)"
        )

    # Subset check
    play_ids_set = set(moment.play_ids)
    narrated_set = set(moment.explicitly_narrated_play_ids)

    if not narrated_set.issubset(play_ids_set):
        extra = narrated_set - play_ids_set
        raise SelectionError(
            f"explicitly_narrated_play_ids contains IDs not in play_ids: {extra}"
        )

    # No duplicates check
    if len(moment.explicitly_narrated_play_ids) != len(narrated_set):
        raise SelectionError(
            f"explicitly_narrated_play_ids contains duplicates"
        )
