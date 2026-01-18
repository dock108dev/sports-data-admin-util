"""Task 6.1: Constrained LLM Rewrite (per-moment).

Per-moment LLM rewriting with strict constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from .tone_profiles import ToneConfig, ToneProfile

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


# Type alias for LLM call function
LLMCallFn = Callable[[str], tuple[str, float]]


@dataclass
class MomentRewriteInput:
    """Input contract for per-moment LLM rewrite.

    STRICT: The LLM only sees this, nothing else.
    """

    moment_type: str  # "FLIP", "LEAD_BUILD", etc.
    quarter: str  # "Q2"
    time_range: str  # "7:32–4:10"
    template_summary: str
    moment_boxscore: dict[str, Any]
    constraints: dict[str, Any] = field(
        default_factory=lambda: {
            "no_new_stats": True,
            "no_reordering": True,
            "max_sentences": 3,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_type": self.moment_type,
            "quarter": self.quarter,
            "time_range": self.time_range,
            "template_summary": self.template_summary,
            "moment_boxscore": self.moment_boxscore,
            "constraints": self.constraints,
        }


@dataclass
class MomentRewriteOutput:
    """Output contract for per-moment LLM rewrite."""

    rewritten_summary: str
    players_mentioned: list[str] = field(default_factory=list)
    confidence: float = 0.0
    passed_validation: bool = True
    validation_errors: list[str] = field(default_factory=list)
    used_fallback: bool = False
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rewritten_summary": self.rewritten_summary,
            "players_mentioned": self.players_mentioned,
            "confidence": self.confidence,
            "passed_validation": self.passed_validation,
            "validation_errors": self.validation_errors,
            "used_fallback": self.used_fallback,
            "fallback_reason": self.fallback_reason,
        }


def build_moment_rewrite_prompt(
    input_data: MomentRewriteInput,
    tone_config: ToneConfig,
) -> str:
    """Build the LLM prompt for moment rewriting."""
    tone_instructions = tone_config.to_prompt_instructions()
    max_sentences = input_data.constraints.get("max_sentences", 3)

    allowed_players = list(
        input_data.moment_boxscore.get("points_by_player", {}).keys()
    )

    prompt = f"""Rewrite the following game moment summary to improve flow and readability.

ORIGINAL SUMMARY:
{input_data.template_summary}

MOMENT CONTEXT:
- Type: {input_data.moment_type}
- Quarter: {input_data.quarter}
- Time: {input_data.time_range}

ALLOWED PLAYERS: {', '.join(allowed_players) if allowed_players else 'No specific players'}

BOXSCORE DATA:
{_format_boxscore_for_prompt(input_data.moment_boxscore)}

STYLE INSTRUCTIONS:
{tone_instructions}

STRICT RULES (VIOLATIONS WILL BE REJECTED):
1. Keep ALL stats exactly as they appear in the original
2. Only mention players from the ALLOWED PLAYERS list
3. Maximum {max_sentences} sentences
4. Do not add new facts or statistics
5. Do not speculate about intent or strategy
6. Do not add drama not supported by the data
7. Do not change the meaning of the summary

Return ONLY the rewritten summary text, nothing else."""

    return prompt


def _format_boxscore_for_prompt(boxscore: dict[str, Any]) -> str:
    """Format boxscore data for inclusion in prompt."""
    lines = []

    if "points_by_player" in boxscore:
        lines.append("Points:")
        for player, pts in boxscore["points_by_player"].items():
            lines.append(f"  - {player}: {pts}")

    if "team_totals" in boxscore:
        tt = boxscore["team_totals"]
        lines.append(f"Team totals: Home {tt.get('home', 0)}, Away {tt.get('away', 0)}")

    if "key_plays" in boxscore:
        kp = boxscore["key_plays"]
        if kp.get("blocks"):
            for player, count in kp["blocks"].items():
                lines.append(f"  - {player}: {count} block(s)")
        if kp.get("steals"):
            for player, count in kp["steals"].items():
                lines.append(f"  - {player}: {count} steal(s)")

    return "\n".join(lines) if lines else "No detailed stats available"


def _estimate_quarter(moment: "Moment") -> int:
    """Estimate quarter from moment's play range."""
    return min(4, max(1, (moment.start_play // 100) + 1))


def _extract_players_from_text(text: str, boxscore: dict[str, Any]) -> list[str]:
    """Extract player names mentioned in text that exist in boxscore."""
    allowed_players: set[str] = set()
    if "points_by_player" in boxscore:
        allowed_players.update(boxscore["points_by_player"].keys())
    if "key_plays" in boxscore:
        for play_type in boxscore["key_plays"].values():
            if isinstance(play_type, dict):
                allowed_players.update(play_type.keys())

    mentioned = []
    for player in allowed_players:
        if player in text:
            mentioned.append(player)

    return mentioned


def rewrite_moment_with_llm(
    moment: "Moment",
    llm_call: LLMCallFn,
    tone_config: ToneConfig | None = None,
    confidence_threshold: float = 0.6,
) -> MomentRewriteOutput:
    """Rewrite a single moment's summary using LLM.

    Args:
        moment: The moment to rewrite
        llm_call: Function that takes prompt and returns (response, confidence)
        tone_config: Optional tone configuration
        confidence_threshold: Minimum confidence to accept rewrite

    Returns:
        MomentRewriteOutput with rewritten summary or fallback
    """
    from .guardrails import validate_llm_output

    if tone_config is None:
        tone_config = ToneConfig.from_profile(ToneProfile.NEUTRAL)

    template_summary = ""
    if hasattr(moment, "narrative_summary") and moment.narrative_summary:
        template_summary = moment.narrative_summary.text

    if not template_summary:
        return MomentRewriteOutput(
            rewritten_summary="",
            used_fallback=True,
            fallback_reason="No template summary available",
        )

    boxscore: dict[str, Any] = {}
    if hasattr(moment, "moment_boxscore") and moment.moment_boxscore:
        boxscore = moment.moment_boxscore.to_dict()

    input_data = MomentRewriteInput(
        moment_type=(
            moment.type.value if hasattr(moment.type, "value") else str(moment.type)
        ),
        quarter=f"Q{_estimate_quarter(moment)}",
        time_range=moment.clock if hasattr(moment, "clock") else "",
        template_summary=template_summary,
        moment_boxscore=boxscore,
    )

    prompt = build_moment_rewrite_prompt(input_data, tone_config)

    try:
        response, confidence = llm_call(prompt)
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        return MomentRewriteOutput(
            rewritten_summary=template_summary,
            used_fallback=True,
            fallback_reason=f"LLM call failed: {str(e)}",
        )

    output = MomentRewriteOutput(
        rewritten_summary=response.strip(),
        confidence=confidence,
        players_mentioned=_extract_players_from_text(response, boxscore),
    )

    validation = validate_llm_output(input_data, output, confidence_threshold)
    output.passed_validation = validation.passed
    output.validation_errors = validation.errors

    if not validation.passed:
        logger.warning(
            f"LLM rewrite failed validation for {moment.id}: {validation.errors}"
        )
        output.rewritten_summary = template_summary
        output.used_fallback = True
        output.fallback_reason = f"Validation failed: {'; '.join(validation.errors)}"

    return output


def create_mock_llm(
    confidence: float = 0.8,
    should_fail: bool = False,
) -> LLMCallFn:
    """Create a mock LLM for testing.

    Args:
        confidence: Confidence to return
        should_fail: Whether to raise an exception

    Returns:
        LLM call function
    """

    def mock_llm(prompt: str) -> tuple[str, float]:
        if should_fail:
            raise RuntimeError("Mock LLM failure")

        lines = prompt.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("ORIGINAL SUMMARY:"):
                if i + 1 < len(lines):
                    original = lines[i + 1].strip()
                    return original, confidence

        return "Mock rewrite.", confidence

    return mock_llm
