"""VALIDATE_MOMENTS Stage Implementation.

This stage runs validation checks on the generated moments to ensure
they meet quality requirements before finalization.

Input: GeneratedMomentsOutput from GENERATE_MOMENTS stage
Output: ValidationOutput with passed status and any errors/warnings
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import ValidationOutput, StageInput, StageOutput

logger = logging.getLogger(__name__)


def _validate_moment_structure(moment: dict[str, Any]) -> list[str]:
    """Validate a single moment has required fields."""
    errors = []
    required_fields = ["id", "type", "start_play", "end_play", "play_count"]
    
    for field in required_fields:
        if field not in moment:
            errors.append(f"Moment missing required field: {field}")
    
    return errors


def _validate_moment_ordering(moments: list[dict[str, Any]]) -> list[str]:
    """Validate moments are in chronological order."""
    errors = []
    
    for i in range(1, len(moments)):
        prev = moments[i - 1]
        curr = moments[i]
        
        if curr.get("start_play", 0) < prev.get("start_play", 0):
            errors.append(
                f"Moments not chronological: {prev.get('id')} starts at "
                f"{prev.get('start_play')}, {curr.get('id')} starts at {curr.get('start_play')}"
            )
    
    return errors


def _validate_no_overlaps(moments: list[dict[str, Any]]) -> list[str]:
    """Validate moments don't overlap."""
    errors = []
    
    for i in range(1, len(moments)):
        prev = moments[i - 1]
        curr = moments[i]
        
        if curr.get("start_play", 0) <= prev.get("end_play", 0):
            errors.append(
                f"Overlapping moments: {prev.get('id')} ends at {prev.get('end_play')}, "
                f"{curr.get('id')} starts at {curr.get('start_play')}"
            )
    
    return errors


def _validate_score_continuity(moments: list[dict[str, Any]]) -> list[str]:
    """Validate score is continuous between moments."""
    warnings = []
    
    for i in range(1, len(moments)):
        prev = moments[i - 1]
        curr = moments[i]
        
        prev_end = prev.get("score_after", (0, 0))
        curr_start = curr.get("score_before", (0, 0))
        
        # Handle tuple or list format
        if isinstance(prev_end, (list, tuple)) and isinstance(curr_start, (list, tuple)):
            if len(prev_end) >= 2 and len(curr_start) >= 2:
                if prev_end[0] != curr_start[0] or prev_end[1] != curr_start[1]:
                    warnings.append(
                        f"Score discontinuity between {prev.get('id')} and {curr.get('id')}: "
                        f"{prev_end} -> {curr_start}"
                    )
    
    return warnings


def _validate_budget(moments: list[dict[str, Any]], budget: int) -> list[str]:
    """Validate moment count is within budget."""
    warnings = []
    
    if len(moments) > budget:
        warnings.append(
            f"Moment count ({len(moments)}) exceeds budget ({budget})"
        )
    
    return warnings


def _validate_reason_present(moments: list[dict[str, Any]]) -> list[str]:
    """Validate all moments have a reason for existing."""
    warnings = []
    
    for moment in moments:
        if not moment.get("reason"):
            warnings.append(f"Moment {moment.get('id')} missing reason")
    
    return warnings


async def execute_validate_moments(
    stage_input: StageInput,
) -> StageOutput:
    """Execute the VALIDATE_MOMENTS stage.
    
    Runs validation checks on the generated moments:
    - Structure validation (required fields)
    - Ordering validation (chronological)
    - Overlap detection
    - Score continuity
    - Budget compliance
    - Reason presence
    
    Args:
        stage_input: Input containing previous_output from GENERATE_MOMENTS
        
    Returns:
        StageOutput with ValidationOutput data
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id
    
    output.add_log(f"Starting VALIDATE_MOMENTS for game {game_id}")
    
    # Get input from previous stage
    prev_output = stage_input.previous_output
    if prev_output is None:
        raise ValueError("VALIDATE_MOMENTS requires output from GENERATE_MOMENTS stage")
    
    moments = prev_output.get("moments", [])
    budget = prev_output.get("budget", 30)
    
    if not moments:
        raise ValueError("No moments in previous stage output")
    
    output.add_log(f"Validating {len(moments)} moments")
    
    errors: list[str] = []
    warnings: list[str] = []
    validation_details: dict[str, Any] = {}
    
    # Run validations
    output.add_log("Checking moment structure...")
    for moment in moments:
        structure_errors = _validate_moment_structure(moment)
        errors.extend(structure_errors)
    validation_details["structure_errors"] = len([e for e in errors if "missing required field" in e])
    
    output.add_log("Checking chronological ordering...")
    ordering_errors = _validate_moment_ordering(moments)
    errors.extend(ordering_errors)
    validation_details["ordering_errors"] = len(ordering_errors)
    
    output.add_log("Checking for overlaps...")
    overlap_errors = _validate_no_overlaps(moments)
    errors.extend(overlap_errors)
    validation_details["overlap_errors"] = len(overlap_errors)
    
    output.add_log("Checking score continuity...")
    continuity_warnings = _validate_score_continuity(moments)
    warnings.extend(continuity_warnings)
    validation_details["score_discontinuities"] = len(continuity_warnings)
    
    output.add_log("Checking budget compliance...")
    budget_warnings = _validate_budget(moments, budget)
    warnings.extend(budget_warnings)
    validation_details["budget_exceeded"] = len(budget_warnings) > 0
    
    output.add_log("Checking reason presence...")
    reason_warnings = _validate_reason_present(moments)
    warnings.extend(reason_warnings)
    validation_details["missing_reasons"] = len(reason_warnings)
    
    # Determine pass/fail
    # Critical errors: structure, ordering, overlaps
    critical_passed = len(errors) == 0
    # Overall pass includes warnings (but they don't block)
    passed = critical_passed
    
    output.add_log(f"Validation complete: {len(errors)} errors, {len(warnings)} warnings")
    
    if errors:
        for error in errors[:5]:  # Log first 5 errors
            output.add_log(f"ERROR: {error}", "error")
    
    if warnings:
        for warning in warnings[:5]:  # Log first 5 warnings
            output.add_log(f"WARNING: {warning}", "warning")
    
    # Build output
    validation_output = ValidationOutput(
        passed=passed,
        critical_passed=critical_passed,
        warnings_count=len(warnings),
        errors=errors,
        warnings=warnings,
        validation_details=validation_details,
    )
    
    output.data = validation_output.to_dict()
    
    if passed:
        output.add_log("VALIDATE_MOMENTS passed successfully")
    else:
        output.add_log("VALIDATE_MOMENTS FAILED - see errors above", "error")
    
    return output
