"""4-stage content validation pipeline for Flow narratives.

Orchestrates the full validation pipeline:
  Stage 1: Structural validation (existing validate_blocks + render_validation)
  Stage 2: Factual validation (stat claims, training-data bleed)
  Stage 3: Quality scoring (repetition, vocabulary, readability, clichés)
  Stage 4: Decision engine (publish / regenerate / fallback)

Tracks monitoring metrics: factual error rate, regenerate rate,
fallback rate, per-sport quality score distribution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .content_decision import (
    ContentDecision,
    DecisionResult,
    generate_template_fallback,
    run_decision_engine,
)
from .factual_validation import FactualValidationResult, run_factual_validation
from .quality_scoring import QualityScoreResult, compute_quality_score
from .render_validation import validate_all_blocks

logger = logging.getLogger(__name__)


@dataclass
class ContentPipelineResult:
    """Full result of the 4-stage content validation pipeline."""

    decision: ContentDecision
    structural_passed: bool
    factual_result: FactualValidationResult
    quality_result: QualityScoreResult
    decision_result: DecisionResult
    blocks: list[dict[str, Any]]
    is_fallback: bool = False
    structural_errors: list[str] = field(default_factory=list)
    structural_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "structural_passed": self.structural_passed,
            "structural_errors": self.structural_errors,
            "structural_warnings": self.structural_warnings,
            "factual": self.factual_result.to_dict(),
            "quality": self.quality_result.to_dict(),
            "decision_engine": self.decision_result.to_dict(),
            "is_fallback": self.is_fallback,
        }


@dataclass
class PipelineMetrics:
    """Monitoring metrics for the content pipeline."""

    sport: str
    factual_error_rate: float = 0.0
    regenerate_count: int = 0
    is_fallback: bool = False
    quality_score: float = 0.0
    claims_checked: int = 0
    claims_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sport": self.sport,
            "factual_error_rate": round(self.factual_error_rate, 3),
            "regenerate_count": self.regenerate_count,
            "is_fallback": self.is_fallback,
            "quality_score": round(self.quality_score, 1),
            "claims_checked": self.claims_checked,
            "claims_failed": self.claims_failed,
        }


def run_content_pipeline(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    sport: str,
    retry_count: int = 0,
) -> ContentPipelineResult:
    """Run the full 4-stage content validation pipeline.

    Stage 1: Structural — block narrative length, forbidden words, format
    Stage 2: Factual — stat claims, training-data bleed, entity allowlist
    Stage 3: Quality — repetition, vocabulary, readability, clichés
    Stage 4: Decision — publish / regenerate / fallback

    If decision is FALLBACK, replaces blocks with template-based content.
    """
    # Stage 1: Structural validation
    structural_errors, structural_warnings = validate_all_blocks(blocks)
    structural_passed = len(structural_errors) == 0

    # Stage 2: Factual validation
    factual_result = run_factual_validation(blocks, game_context, sport)

    # Stage 3: Quality scoring
    quality_result = compute_quality_score(blocks)

    # Stage 4: Decision engine
    all_errors = structural_errors + factual_result.errors
    all_warnings = structural_warnings + factual_result.warnings

    decision_result = run_decision_engine(
        quality_score=quality_result.composite_score,
        factual_passed=factual_result.passed,
        structural_passed=structural_passed,
        retry_count=retry_count,
        all_errors=all_errors,
        all_warnings=all_warnings,
    )

    is_fallback = decision_result.decision == ContentDecision.FALLBACK
    output_blocks = blocks

    if is_fallback:
        output_blocks = generate_template_fallback(blocks, game_context, sport)

    # Log metrics
    metrics = PipelineMetrics(
        sport=sport,
        factual_error_rate=(
            factual_result.claims_failed / factual_result.claims_checked
            if factual_result.claims_checked > 0
            else 0.0
        ),
        regenerate_count=retry_count,
        is_fallback=is_fallback,
        quality_score=quality_result.composite_score,
        claims_checked=factual_result.claims_checked,
        claims_failed=factual_result.claims_failed,
    )

    logger.info(
        "content_pipeline_complete",
        extra=metrics.to_dict(),
    )

    return ContentPipelineResult(
        decision=decision_result.decision,
        structural_passed=structural_passed,
        factual_result=factual_result,
        quality_result=quality_result,
        decision_result=decision_result,
        blocks=output_blocks,
        is_fallback=is_fallback,
        structural_errors=structural_errors,
        structural_warnings=structural_warnings,
    )
