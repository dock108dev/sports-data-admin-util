"""Task 6.2: Full-Game Narrative Stitching.

Generates transitions between moments for narrative flow.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .tone_profiles import ToneConfig, ToneProfile
from .rewriting import LLMCallFn
from .guardrails import ValidationResult

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class TransitionInput:
    """Input for narrative transition generation."""

    moment_summaries: list[str]
    act_labels: list[str]  # "opening", "middle", "closing"
    home_team: str = ""
    away_team: str = ""


@dataclass
class TransitionOutput:
    """Output from transition generation."""

    opening_sentence: str = ""
    act_transitions: dict[str, str] = field(default_factory=dict)
    closing_sentence: str = ""
    passed_validation: bool = True
    used_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "opening_sentence": self.opening_sentence,
            "act_transitions": self.act_transitions,
            "closing_sentence": self.closing_sentence,
            "passed_validation": self.passed_validation,
            "used_fallback": self.used_fallback,
        }


def build_transition_prompt(
    input_data: TransitionInput,
    tone_config: ToneConfig,
) -> str:
    """Build prompt for narrative transitions."""
    acts = set(input_data.act_labels)

    prompt = f"""Generate brief narrative transitions for a basketball game recap.

GAME: {input_data.away_team} @ {input_data.home_team}

You will write:
1. ONE opening sentence (if the game has an opening act)
2. ONE transition sentence for act changes (opening→middle, middle→closing)
3. ONE closing sentence (if the game has a closing act)

ACTS IN THIS GAME: {', '.join(sorted(acts))}

STYLE: {tone_config.to_prompt_instructions()}

STRICT RULES:
1. NO new facts or statistics
2. NO player names
3. NO specific scores
4. Each sentence must be ≤ 20 words
5. Sentences should be general transitions, not summaries

Return in this exact format:
OPENING: [sentence or NONE]
MIDDLE_TRANSITION: [sentence or NONE]
CLOSING: [sentence or NONE]"""

    return prompt


def parse_transition_response(response: str) -> TransitionOutput:
    """Parse LLM response into TransitionOutput."""
    output = TransitionOutput()

    lines = response.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("OPENING:"):
            value = line[8:].strip()
            if value.upper() != "NONE":
                output.opening_sentence = value
        elif line.startswith("MIDDLE_TRANSITION:"):
            value = line[18:].strip()
            if value.upper() != "NONE":
                output.act_transitions["middle"] = value
        elif line.startswith("CLOSING:"):
            value = line[8:].strip()
            if value.upper() != "NONE":
                output.closing_sentence = value

    return output


def validate_transitions(output: TransitionOutput) -> ValidationResult:
    """Validate transition output."""
    result = ValidationResult()

    all_text = " ".join(
        [
            output.opening_sentence,
            *output.act_transitions.values(),
            output.closing_sentence,
        ]
    )

    numbers = re.findall(r"\b\d+\b", all_text)
    if numbers:
        result.add_error(f"Transitions contain stats: {numbers}")

    for sentence in [output.opening_sentence, output.closing_sentence]:
        if sentence and len(sentence.split()) > 25:
            result.add_error(f"Transition too long: {len(sentence.split())} words")

    return result


def generate_transitions(
    moments: Sequence["Moment"],
    llm_call: LLMCallFn,
    home_team: str = "",
    away_team: str = "",
    tone_config: ToneConfig | None = None,
) -> TransitionOutput:
    """Generate narrative transitions for a full game.

    Args:
        moments: All moments in order
        llm_call: LLM call function
        home_team: Home team name
        away_team: Away team name
        tone_config: Tone configuration

    Returns:
        TransitionOutput with generated transitions
    """
    if tone_config is None:
        tone_config = ToneConfig.from_profile(ToneProfile.NEUTRAL)

    summaries = []
    act_labels = []

    for moment in moments:
        summary = ""
        if hasattr(moment, "narrative_summary") and moment.narrative_summary:
            summary = moment.narrative_summary.text
        summaries.append(summary)

        act = "middle"
        if moment.start_play < 100:
            act = "opening"
        elif moment.start_play >= 350:
            act = "closing"
        act_labels.append(act)

    input_data = TransitionInput(
        moment_summaries=summaries,
        act_labels=act_labels,
        home_team=home_team,
        away_team=away_team,
    )

    prompt = build_transition_prompt(input_data, tone_config)

    try:
        response, _ = llm_call(prompt)
        output = parse_transition_response(response)
    except Exception as e:
        logger.warning(f"Transition generation failed: {e}")
        return TransitionOutput(used_fallback=True)

    validation = validate_transitions(output)
    output.passed_validation = validation.passed

    if not validation.passed:
        logger.warning(f"Transition validation failed: {validation.errors}")
        return TransitionOutput(used_fallback=True)

    return output
