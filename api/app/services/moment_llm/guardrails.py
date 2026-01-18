"""Task 6.4: LLM Safety & Regression Guards.

Validation functions to ensure LLM output doesn't violate constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .rewriting import MomentRewriteInput, MomentRewriteOutput


@dataclass
class ValidationResult:
    """Result of LLM output validation."""

    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.passed = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)


def validate_stat_preservation(
    original: str,
    rewritten: str,
    boxscore: dict[str, Any],
) -> ValidationResult:
    """Verify that all stats in original are preserved in rewrite."""
    result = ValidationResult()

    original_numbers = set(re.findall(r"\b\d+\b", original))
    rewrite_numbers = set(re.findall(r"\b\d+\b", rewritten))

    missing = original_numbers - rewrite_numbers
    if missing:
        result.add_error(f"Stats missing from rewrite: {missing}")

    common_numbers = {"1", "2", "3", "4"}
    new_numbers = rewrite_numbers - original_numbers - common_numbers

    boxscore_numbers = _extract_boxscore_numbers(boxscore)
    truly_new = new_numbers - boxscore_numbers

    if truly_new:
        result.add_error(f"New stats invented by LLM: {truly_new}")

    return result


def _extract_boxscore_numbers(boxscore: dict[str, Any]) -> set[str]:
    """Extract all numbers from boxscore for validation."""
    numbers: set[str] = set()

    if "points_by_player" in boxscore:
        for pts in boxscore["points_by_player"].values():
            numbers.add(str(pts))

    if "team_totals" in boxscore:
        for val in boxscore["team_totals"].values():
            if isinstance(val, (int, float)):
                numbers.add(str(int(val)))

    if "key_plays" in boxscore:
        for play_type in boxscore["key_plays"].values():
            if isinstance(play_type, dict):
                for count in play_type.values():
                    numbers.add(str(count))

    return numbers


def validate_player_mentions(
    rewritten: str,
    boxscore: dict[str, Any],
) -> ValidationResult:
    """Verify that only players from boxscore are mentioned."""
    result = ValidationResult()

    allowed_players: set[str] = set()
    if "points_by_player" in boxscore:
        allowed_players.update(boxscore["points_by_player"].keys())
    if "key_plays" in boxscore:
        for play_type in boxscore["key_plays"].values():
            if isinstance(play_type, dict):
                allowed_players.update(play_type.keys())
    if "top_assists" in boxscore:
        for assist in boxscore["top_assists"]:
            if isinstance(assist, dict):
                allowed_players.add(assist.get("from", ""))
                allowed_players.add(assist.get("to", ""))

    allowed_players.discard("")

    if not allowed_players:
        return result

    name_pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
    mentioned_names = set(re.findall(name_pattern, rewritten))

    for name in mentioned_names:
        if name not in allowed_players:
            if len(name.split()) >= 2:
                result.add_warning(f"Potentially unknown player: {name}")

    return result


def validate_sentence_count(
    rewritten: str,
    max_sentences: int,
) -> ValidationResult:
    """Verify sentence count is within limits."""
    result = ValidationResult()

    sentences = re.split(r"[.!?]+", rewritten)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) > max_sentences:
        result.add_error(f"Too many sentences: {len(sentences)} > {max_sentences}")

    return result


def validate_length(
    rewritten: str,
    original: str,
    max_ratio: float = 1.5,
) -> ValidationResult:
    """Verify rewrite isn't excessively longer than original."""
    result = ValidationResult()

    if len(original) == 0:
        return result

    ratio = len(rewritten) / len(original)
    if ratio > max_ratio:
        result.add_error(
            f"Rewrite too long: {ratio:.1f}x original (max {max_ratio}x)"
        )

    return result


def validate_llm_output(
    input_data: "MomentRewriteInput",
    output: "MomentRewriteOutput",
    confidence_threshold: float = 0.6,
) -> ValidationResult:
    """Run all validation checks on LLM output."""
    result = ValidationResult()

    if output.confidence < confidence_threshold:
        result.add_error(
            f"Low confidence: {output.confidence:.2f} < {confidence_threshold}"
        )

    stat_result = validate_stat_preservation(
        input_data.template_summary,
        output.rewritten_summary,
        input_data.moment_boxscore,
    )
    result.errors.extend(stat_result.errors)
    result.warnings.extend(stat_result.warnings)
    if not stat_result.passed:
        result.passed = False

    player_result = validate_player_mentions(
        output.rewritten_summary,
        input_data.moment_boxscore,
    )
    result.errors.extend(player_result.errors)
    result.warnings.extend(player_result.warnings)
    if not player_result.passed:
        result.passed = False

    max_sentences = input_data.constraints.get("max_sentences", 3)
    sentence_result = validate_sentence_count(output.rewritten_summary, max_sentences)
    result.errors.extend(sentence_result.errors)
    if not sentence_result.passed:
        result.passed = False

    length_result = validate_length(
        output.rewritten_summary, input_data.template_summary
    )
    result.errors.extend(length_result.errors)
    if not length_result.passed:
        result.passed = False

    return result
