"""VALIDATE_MOMENTS Stage Implementation.

This stage validates that moment data strictly complies with the Story contract.
It does NOT generate data. It does NOT repair data. It exists to FAIL when
the contract is violated.

STORY CONTRACT ENFORCEMENT
==========================
This stage is the contract lock. After this stage passes:
- Story data cannot drift
- Later AI steps cannot lie
- Debugging becomes mechanical

VALIDATION RULES
================
1. Non-Empty play_ids - Every moment must contain ≥1 play_id
2. Explicit Narration Guarantee - explicitly_narrated_play_ids must be non-empty
   and a strict subset of play_ids
3. No Overlapping Plays - No play_id may appear in more than one moment
4. Canonical Ordering - Moments must be strictly ordered by first play_index
5. Valid Play References - All play_ids must exist in normalized PBP data
6. Score Never Decreases - Score values are cumulative and must never decrease
7. Score Continuity - score_before(n) must equal score_after(n-1) for all moments

GUARANTEES
==========
- Validation is deterministic (same input always produces same result)
- Errors are specific (exact play_ids and moment indices)
- Failures are loud (stage fails, pipeline stops)
- Results are reviewable (structured JSON errors)

PROHIBITIONS
============
- No OpenAI calls
- No narrative text
- No story persistence
- No silent corrections
- No best-effort behavior
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models import StageInput, StageOutput

logger = logging.getLogger(__name__)


class ValidationError:
    """A single validation error with structured details."""

    def __init__(
        self,
        code: str,
        message: str,
        moment_indices: list[int] | None = None,
        play_ids: list[int] | None = None,
    ):
        self.code = code
        self.message = message
        self.moment_indices = moment_indices
        self.play_ids = play_ids

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.moment_indices is not None:
            result["moment_indices"] = self.moment_indices
        if self.play_ids is not None:
            result["play_ids"] = self.play_ids
        return result


def _validate_non_empty_play_ids(moments: list[dict[str, Any]]) -> list[ValidationError]:
    """Rule 1: Every moment must contain ≥1 play_id.

    Args:
        moments: List of moment dicts

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []

    for idx, moment in enumerate(moments):
        play_ids = moment.get("play_ids", [])
        if not play_ids:
            errors.append(
                ValidationError(
                    code="EMPTY_PLAY_IDS",
                    message=f"Moment {idx} has no play_ids",
                    moment_indices=[idx],
                )
            )

    return errors


def _validate_explicit_narration(moments: list[dict[str, Any]]) -> list[ValidationError]:
    """Rule 2: explicitly_narrated_play_ids must be non-empty and ⊂ play_ids.

    Args:
        moments: List of moment dicts

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []

    for idx, moment in enumerate(moments):
        play_ids = set(moment.get("play_ids", []))
        narrated_ids = moment.get("explicitly_narrated_play_ids", [])

        # Check non-empty
        if not narrated_ids:
            errors.append(
                ValidationError(
                    code="EMPTY_NARRATION",
                    message=f"Moment {idx} has no explicitly_narrated_play_ids",
                    moment_indices=[idx],
                )
            )
            continue

        # Check subset relationship
        narrated_set = set(narrated_ids)
        invalid_ids = narrated_set - play_ids
        if invalid_ids:
            errors.append(
                ValidationError(
                    code="NARRATION_NOT_SUBSET",
                    message=(
                        f"Moment {idx} has narrated play_ids not in play_ids: "
                        f"{sorted(invalid_ids)}"
                    ),
                    moment_indices=[idx],
                    play_ids=sorted(invalid_ids),
                )
            )

    return errors


def _validate_no_overlapping_plays(moments: list[dict[str, Any]]) -> list[ValidationError]:
    """Rule 3: No play_id may appear in more than one moment.

    Args:
        moments: List of moment dicts

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []

    # Track which moments contain each play_id
    play_to_moments: dict[int, list[int]] = {}

    for idx, moment in enumerate(moments):
        for play_id in moment.get("play_ids", []):
            if play_id not in play_to_moments:
                play_to_moments[play_id] = []
            play_to_moments[play_id].append(idx)

    # Find overlapping play_ids
    for play_id, moment_indices in play_to_moments.items():
        if len(moment_indices) > 1:
            errors.append(
                ValidationError(
                    code="OVERLAPPING_PLAY_IDS",
                    message=f"Play {play_id} appears in multiple moments",
                    moment_indices=moment_indices,
                    play_ids=[play_id],
                )
            )

    return errors


def _validate_canonical_ordering(moments: list[dict[str, Any]]) -> list[ValidationError]:
    """Rule 4: Moments must be strictly ordered by first play_index.

    Ordering is based on play_index only (not clock or period).
    Equal ordering is a hard failure.

    Args:
        moments: List of moment dicts

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []

    prev_first_play = -1
    prev_moment_idx = -1

    for idx, moment in enumerate(moments):
        play_ids = moment.get("play_ids", [])
        if not play_ids:
            # Already caught by Rule 1, skip here
            continue

        first_play = play_ids[0]

        if first_play <= prev_first_play:
            errors.append(
                ValidationError(
                    code="ORDERING_VIOLATION",
                    message=(
                        f"Moment {idx} has first play_id {first_play} which is "
                        f"<= moment {prev_moment_idx}'s first play_id {prev_first_play}"
                    ),
                    moment_indices=[prev_moment_idx, idx],
                    play_ids=[prev_first_play, first_play],
                )
            )

        prev_first_play = first_play
        prev_moment_idx = idx

    return errors


def _validate_play_references(
    moments: list[dict[str, Any]],
    valid_play_ids: set[int],
) -> list[ValidationError]:
    """Rule 5: All play_ids must exist in normalized PBP data.

    Args:
        moments: List of moment dicts
        valid_play_ids: Set of play_ids from PBP data

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []

    for idx, moment in enumerate(moments):
        play_ids = moment.get("play_ids", [])
        invalid_ids = [pid for pid in play_ids if pid not in valid_play_ids]

        if invalid_ids:
            errors.append(
                ValidationError(
                    code="INVALID_PLAY_REFERENCE",
                    message=(
                        f"Moment {idx} references non-existent play_ids: {invalid_ids}"
                    ),
                    moment_indices=[idx],
                    play_ids=invalid_ids,
                )
            )

    return errors


def _validate_score_never_decreases(moments: list[dict[str, Any]]) -> list[ValidationError]:
    """Rule 6: Score values must never decrease within a game.

    Scores are cumulative. A score decrease indicates data corruption
    or a normalization failure.

    Args:
        moments: List of moment dicts with score_before and score_after

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []

    prev_home_score = 0
    prev_away_score = 0

    for idx, moment in enumerate(moments):
        score_before = moment.get("score_before", [0, 0])
        score_after = moment.get("score_after", [0, 0])

        # Unpack scores (format: [away, home])
        away_before = score_before[0] if len(score_before) > 0 else 0
        home_before = score_before[1] if len(score_before) > 1 else 0
        away_after = score_after[0] if len(score_after) > 0 else 0
        home_after = score_after[1] if len(score_after) > 1 else 0

        # Check score_before doesn't decrease from previous moment's score_after
        if away_before < prev_away_score or home_before < prev_home_score:
            errors.append(
                ValidationError(
                    code="SCORE_DECREASE_BEFORE",
                    message=(
                        f"Moment {idx} score_before [{away_before}, {home_before}] is less than "
                        f"previous score [{prev_away_score}, {prev_home_score}]"
                    ),
                    moment_indices=[idx],
                )
            )

        # Check score_after doesn't decrease from score_before
        if away_after < away_before or home_after < home_before:
            errors.append(
                ValidationError(
                    code="SCORE_DECREASE_WITHIN",
                    message=(
                        f"Moment {idx} score_after [{away_after}, {home_after}] is less than "
                        f"score_before [{away_before}, {home_before}]"
                    ),
                    moment_indices=[idx],
                )
            )

        # Update tracking for next iteration
        prev_away_score = away_after
        prev_home_score = home_after

    return errors


def _validate_score_continuity(moments: list[dict[str, Any]]) -> list[ValidationError]:
    """Rule 7: score_before(n) must equal score_after(n-1) for all adjacent moments.

    This is the CRITICAL invariant that ensures narrative continuity.
    Any gap means plays are missing or scores were corrupted.

    Args:
        moments: List of moment dicts with score_before and score_after

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []

    if len(moments) < 2:
        return errors  # Need at least 2 moments to check continuity

    for idx in range(1, len(moments)):
        prev_moment = moments[idx - 1]
        curr_moment = moments[idx]

        prev_score_after = prev_moment.get("score_after", [0, 0])
        curr_score_before = curr_moment.get("score_before", [0, 0])

        # Compare scores
        if prev_score_after != curr_score_before:
            errors.append(
                ValidationError(
                    code="SCORE_CONTINUITY_BREAK",
                    message=(
                        f"Score continuity violation between moments {idx - 1} and {idx}: "
                        f"moment {idx - 1} score_after={prev_score_after} != "
                        f"moment {idx} score_before={curr_score_before}"
                    ),
                    moment_indices=[idx - 1, idx],
                )
            )

    return errors


async def execute_validate_moments(stage_input: StageInput) -> StageOutput:
    """Execute the VALIDATE_MOMENTS stage.

    Validates that moment data strictly complies with the Story contract.
    Returns success with validated=true, or RAISES an exception on failure.

    The exception message contains structured JSON error data for reviewability.

    Args:
        stage_input: Input containing previous_output with moments and pbp_events

    Returns:
        StageOutput with {"validated": true, "errors": []}

    Raises:
        ValueError: If any validation rule is violated. The error message
            contains JSON with {"validated": false, "errors": [...]}
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting VALIDATE_MOMENTS for game {game_id}")

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("VALIDATE_MOMENTS requires previous stage output")

    # Get moments from GENERATE_MOMENTS
    moments = previous_output.get("moments")
    if moments is None:
        raise ValueError("No moments in previous stage output")

    # Get pbp_events from NORMALIZE_PBP (for play_id validation)
    pbp_events = previous_output.get("pbp_events")
    if not pbp_events:
        raise ValueError("No pbp_events in previous stage output")

    # Build set of valid play_ids from PBP
    valid_play_ids: set[int] = set()
    for event in pbp_events:
        play_index = event.get("play_index")
        if play_index is not None:
            valid_play_ids.add(play_index)

    output.add_log(f"Validating {len(moments)} moments against {len(valid_play_ids)} plays")

    # Collect all validation errors
    all_errors: list[ValidationError] = []

    # Rule 1: Non-Empty play_ids
    output.add_log("Checking Rule 1: Non-empty play_ids")
    rule1_errors = _validate_non_empty_play_ids(moments)
    all_errors.extend(rule1_errors)
    if rule1_errors:
        output.add_log(f"Rule 1 FAILED: {len(rule1_errors)} violations", level="error")
    else:
        output.add_log("Rule 1 PASSED")

    # Rule 2: Explicit Narration Guarantee
    output.add_log("Checking Rule 2: Explicit narration guarantee")
    rule2_errors = _validate_explicit_narration(moments)
    all_errors.extend(rule2_errors)
    if rule2_errors:
        output.add_log(f"Rule 2 FAILED: {len(rule2_errors)} violations", level="error")
    else:
        output.add_log("Rule 2 PASSED")

    # Rule 3: No Overlapping Plays
    output.add_log("Checking Rule 3: No overlapping plays")
    rule3_errors = _validate_no_overlapping_plays(moments)
    all_errors.extend(rule3_errors)
    if rule3_errors:
        output.add_log(f"Rule 3 FAILED: {len(rule3_errors)} violations", level="error")
    else:
        output.add_log("Rule 3 PASSED")

    # Rule 4: Canonical Ordering
    output.add_log("Checking Rule 4: Canonical ordering")
    rule4_errors = _validate_canonical_ordering(moments)
    all_errors.extend(rule4_errors)
    if rule4_errors:
        output.add_log(f"Rule 4 FAILED: {len(rule4_errors)} violations", level="error")
    else:
        output.add_log("Rule 4 PASSED")

    # Rule 5: Valid Play References
    output.add_log("Checking Rule 5: Valid play references")
    rule5_errors = _validate_play_references(moments, valid_play_ids)
    all_errors.extend(rule5_errors)
    if rule5_errors:
        output.add_log(f"Rule 5 FAILED: {len(rule5_errors)} violations", level="error")
    else:
        output.add_log("Rule 5 PASSED")

    # Rule 6: Score Never Decreases
    output.add_log("Checking Rule 6: Score never decreases")
    rule6_errors = _validate_score_never_decreases(moments)
    all_errors.extend(rule6_errors)
    if rule6_errors:
        output.add_log(f"Rule 6 FAILED: {len(rule6_errors)} violations", level="error")
    else:
        output.add_log("Rule 6 PASSED")

    # Rule 7: Score Continuity (score_before[n] == score_after[n-1])
    output.add_log("Checking Rule 7: Score continuity across moments")
    rule7_errors = _validate_score_continuity(moments)
    all_errors.extend(rule7_errors)
    if rule7_errors:
        output.add_log(f"Rule 7 FAILED: {len(rule7_errors)} violations", level="error")
    else:
        output.add_log("Rule 7 PASSED")

    # Build validation result
    if all_errors:
        # Validation FAILED - build structured error output and raise
        error_count = len(all_errors)
        error_dicts = [e.to_dict() for e in all_errors]

        # Log to Python logging for system visibility
        logger.error(
            "Moment validation failed",
            extra={
                "game_id": game_id,
                "error_count": error_count,
                "errors": error_dicts,
            },
        )

        # Build structured output as JSON string for error_details
        validation_output = {
            "validated": False,
            "errors": error_dicts,
        }

        # Raise with structured JSON in message (saved to error_details)
        # This allows reviewers to parse the error and see exact failures
        raise ValueError(json.dumps(validation_output))

    # Validation PASSED
    output.add_log(f"All {len(moments)} moments passed validation")
    output.add_log("VALIDATE_MOMENTS completed successfully")

    # Output matches required shape exactly:
    # {
    #   "validated": true,
    #   "errors": []
    # }
    output.data = {"validated": True, "errors": []}

    return output
