"""VALIDATE_MOMENTS Stage Implementation.

This stage runs validation checks on the generated moments to ensure
they meet quality requirements before finalization.

Input: GeneratedMomentsOutput from GENERATE_MOMENTS stage
Output: ValidationOutput with passed status and any errors/warnings

PHASE 0 ENHANCEMENTS (Guardrails & Observability)
=================================================
- Score continuity failures can now block validation (strict mode)
- Quality status (PASSED/DEGRADED/FAILED/OVERRIDDEN) provides clear signal
- Score continuity issues are captured with full detail
- Override mechanism allows manual override with audit trail
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ....config import settings
from ..models import (
    QualityStatus,
    ScoreContinuityOverride,
    ValidationOutput,
    StageInput,
    StageOutput,
)

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


def _validate_score_continuity_detailed(
    moments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate score is continuous between moments.
    
    Returns detailed issue records instead of just warning strings.
    Each issue includes:
    - prev_moment_id: ID of the moment ending before the gap
    - curr_moment_id: ID of the moment starting after the gap
    - prev_score_after: Score at end of previous moment
    - curr_score_before: Score at start of current moment
    - delta: The unexpected score change
    - position_in_sequence: Which boundary (1-indexed)
    """
    issues: list[dict[str, Any]] = []
    
    for i in range(1, len(moments)):
        prev = moments[i - 1]
        curr = moments[i]
        
        prev_end = prev.get("score_after", (0, 0))
        curr_start = curr.get("score_before", (0, 0))
        
        # Normalize to tuple
        if isinstance(prev_end, list):
            prev_end = tuple(prev_end)
        if isinstance(curr_start, list):
            curr_start = tuple(curr_start)
        
        # Handle tuple or list format
        if isinstance(prev_end, tuple) and isinstance(curr_start, tuple):
            if len(prev_end) >= 2 and len(curr_start) >= 2:
                if prev_end[0] != curr_start[0] or prev_end[1] != curr_start[1]:
                    # Calculate the delta
                    home_delta = curr_start[0] - prev_end[0]
                    away_delta = curr_start[1] - prev_end[1]
                    
                    issues.append({
                        "prev_moment_id": prev.get("id"),
                        "curr_moment_id": curr.get("id"),
                        "prev_score_after": list(prev_end),
                        "curr_score_before": list(curr_start),
                        "delta": {"home": home_delta, "away": away_delta},
                        "position_in_sequence": i,
                        "prev_end_play": prev.get("end_play"),
                        "curr_start_play": curr.get("start_play"),
                    })
    
    return issues


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
    override_score_continuity: bool = False,
    override_reason: str | None = None,
    override_by: str | None = None,
) -> StageOutput:
    """Execute the VALIDATE_MOMENTS stage.
    
    Runs validation checks on the generated moments:
    - Structure validation (required fields)
    - Ordering validation (chronological)
    - Overlap detection
    - Score continuity (can be blocking in strict mode)
    - Budget compliance
    - Reason presence
    
    Args:
        stage_input: Input containing previous_output from GENERATE_MOMENTS
        override_score_continuity: If True, allows score discontinuities to pass
        override_reason: Required reason when override is enabled
        override_by: Identifier of who/what requested the override
        
    Returns:
        StageOutput with ValidationOutput data including quality_status
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id
    
    output.add_log(f"Starting VALIDATE_MOMENTS for game {game_id}")
    
    # Log configuration state
    strict_mode = settings.strict_score_continuity
    output.add_log(f"Strict score continuity mode: {strict_mode}")
    
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
    
    # Run structural validations (always critical)
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
    
    # Score continuity validation - detailed capture
    output.add_log("Checking score continuity...")
    score_continuity_issues = _validate_score_continuity_detailed(moments)
    validation_details["score_discontinuities"] = len(score_continuity_issues)
    
    # Handle score continuity based on mode and override
    score_continuity_override: ScoreContinuityOverride | None = None
    has_score_issues = len(score_continuity_issues) > 0
    
    if has_score_issues:
        if override_score_continuity:
            # Override requested - record it
            if not override_reason:
                override_reason = "No reason provided"
            
            score_continuity_override = ScoreContinuityOverride(
                enabled=True,
                reason=override_reason,
                overridden_by=override_by or "unknown",
                overridden_at=datetime.now(timezone.utc).isoformat(),
            )
            output.add_log(
                f"Score continuity override enabled: {override_reason}",
                "warning"
            )
        elif strict_mode:
            # Strict mode - score issues are errors
            for issue in score_continuity_issues:
                errors.append(
                    f"STRICT: Score discontinuity between {issue['prev_moment_id']} and "
                    f"{issue['curr_moment_id']}: {issue['prev_score_after']} -> {issue['curr_score_before']}"
                )
            validation_details["score_continuity_blocking"] = True
            output.add_log(
                f"Score continuity check FAILED (strict mode): {len(score_continuity_issues)} discontinuities",
                "error"
            )
        else:
            # Non-strict mode - score issues are warnings but mark as DEGRADED
            for issue in score_continuity_issues:
                warnings.append(
                    f"Score discontinuity between {issue['prev_moment_id']} and "
                    f"{issue['curr_moment_id']}: {issue['prev_score_after']} -> {issue['curr_score_before']}"
                )
            output.add_log(
                f"Score continuity issues detected: {len(score_continuity_issues)} (non-blocking, DEGRADED status)",
                "warning"
            )
    
    # Budget and reason checks
    output.add_log("Checking budget compliance...")
    budget_warnings = _validate_budget(moments, budget)
    warnings.extend(budget_warnings)
    validation_details["budget_exceeded"] = len(budget_warnings) > 0
    
    output.add_log("Checking reason presence...")
    reason_warnings = _validate_reason_present(moments)
    warnings.extend(reason_warnings)
    validation_details["missing_reasons"] = len(reason_warnings)
    
    # Determine pass/fail and quality status
    # Critical errors: structure, ordering, overlaps, and score continuity in strict mode
    critical_passed = len(errors) == 0
    passed = critical_passed
    
    # Determine quality status
    if not critical_passed:
        quality_status = QualityStatus.FAILED
    elif has_score_issues:
        if override_score_continuity:
            quality_status = QualityStatus.OVERRIDDEN
        else:
            # Non-strict mode with issues = DEGRADED
            quality_status = QualityStatus.DEGRADED
    else:
        quality_status = QualityStatus.PASSED
    
    output.add_log(f"Validation complete: {len(errors)} errors, {len(warnings)} warnings")
    output.add_log(f"Quality status: {quality_status.value}")
    
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
        quality_status=quality_status,
        score_continuity_issues=score_continuity_issues,
        score_continuity_override=score_continuity_override,
    )
    
    output.data = validation_output.to_dict()
    
    if passed:
        if quality_status == QualityStatus.DEGRADED:
            output.add_log(
                "VALIDATE_MOMENTS passed with DEGRADED status - score continuity issues present",
                "warning"
            )
        elif quality_status == QualityStatus.OVERRIDDEN:
            output.add_log(
                "VALIDATE_MOMENTS passed with OVERRIDDEN status - manual override applied",
                "warning"
            )
        else:
            output.add_log("VALIDATE_MOMENTS passed successfully")
    else:
        output.add_log("VALIDATE_MOMENTS FAILED - see errors above", "error")
    
    return output
