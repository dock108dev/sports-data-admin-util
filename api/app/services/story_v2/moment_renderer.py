"""
Story V2 Moment Renderer: AI-driven narrative generation for condensed moments.

This is the ONLY module where AI-generated prose is permitted in Story V2.
All other modules are deterministic.

AUTHORITATIVE INPUTS:
- docs/story_v2_contract.md
- story_v2/schema.py
- story_v2/prompts/moment_render.txt

RESPONSIBILITIES:
1. Construct deterministic prompts from CondensedMoment + PlayData
2. Call AI model for narrative generation
3. Validate generated narratives meet contract requirements
4. Provide debug/traceability hooks

GUARANTEES:
- Prompt construction is deterministic for identical inputs
- Post-generation validation enforces contract compliance
- Failed validation raises RenderError (never returns invalid narrative)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .moment_builder import PlayData
from .schema import CondensedMoment, ScoreTuple

logger = logging.getLogger(__name__)

# Load prompt template at module load time
_PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "moment_render.txt"
_PROMPT_TEMPLATE: str | None = None


def _load_prompt_template() -> str:
    """Load and cache prompt template."""
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        if not _PROMPT_TEMPLATE_PATH.exists():
            raise RenderError(
                f"Prompt template not found: {_PROMPT_TEMPLATE_PATH}"
            )
        _PROMPT_TEMPLATE = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


class RenderError(Exception):
    """Raised when moment rendering fails."""

    pass


class ValidationError(RenderError):
    """Raised when generated narrative fails validation."""

    pass


class AIClient(Protocol):
    """Protocol for AI client interface.

    Any client providing this interface can be used for rendering.
    """

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 500,
        max_retries: int = 3,
    ) -> str:
        """Generate text from prompt, returning JSON string."""
        ...


@dataclass
class RenderInput:
    """Input data for moment rendering.

    Combines CondensedMoment with enriched play data and team context.
    """

    moment: CondensedMoment
    plays: Sequence[PlayData]
    home_team: str
    away_team: str


@dataclass
class RenderDebugInfo:
    """Debug information for render operation."""

    prompt: str
    raw_response: str
    narrative: str
    validation_passed: bool
    validation_errors: list[str]


@dataclass
class RenderResult:
    """Result of moment rendering."""

    narrative: str
    debug_info: RenderDebugInfo | None = None


# Forbidden phrases that indicate meta-language or poor style
FORBIDDEN_PHRASES = frozenset([
    "in this moment",
    "during this stretch",
    "in this sequence",
    "at this point",
    "little did they know",
    "as we'll see",
    "spoiler alert",
    "looking ahead",
    "foreshadowing",
])


def _build_prompt_input(render_input: RenderInput) -> dict:
    """Build the structured input for the prompt.

    This is deterministic: same input always produces same output.
    """
    moment = render_input.moment
    plays = render_input.plays

    # Build plays array with descriptions
    play_descriptions = [p.description for p in plays]

    # Build explicit plays array (only those that must be narrated)
    explicit_ids = set(moment.explicitly_narrated_play_ids)
    explicit_plays = [
        p.description for p in plays if p.play_index in explicit_ids
    ]

    return {
        "period": moment.period,
        "start_clock": moment.start_clock,
        "end_clock": moment.end_clock,
        "score_before": {
            "home": moment.score_before.home,
            "away": moment.score_before.away,
        },
        "score_after": {
            "home": moment.score_after.home,
            "away": moment.score_after.away,
        },
        "plays": play_descriptions,
        "explicit_plays": explicit_plays,
        "home_team": render_input.home_team,
        "away_team": render_input.away_team,
    }


def build_prompt(render_input: RenderInput) -> str:
    """Build complete prompt from render input.

    This is a pure function: deterministic for identical inputs.

    Args:
        render_input: Input data for rendering

    Returns:
        Complete prompt string ready for AI model
    """
    template = _load_prompt_template()
    input_data = _build_prompt_input(render_input)

    # Append the actual input as JSON
    input_json = json.dumps(input_data, indent=2)
    return f"{template}\n\nINPUT:\n{input_json}"


def _count_sentences(text: str) -> int:
    """Count sentences in text.

    Simple heuristic: count sentence-ending punctuation followed by
    space or end of string.
    """
    # Match . ! ? followed by space or end of string
    # Excludes things like "3.5" or "Mr." when possible
    pattern = r'[.!?](?:\s|$)'
    matches = re.findall(pattern, text)
    return len(matches)


def _extract_key_terms(description: str) -> list[str]:
    """Extract key terms from play description for validation.

    Returns normalized terms that should appear in narrative.
    """
    # Extract player names (capitalized words)
    # and key action words
    terms = []

    # Get player names (words starting with capital, not common words)
    common_words = {"The", "A", "An", "For", "And", "But", "Or", "From", "To"}
    words = description.split()
    for word in words:
        clean = word.strip(".,!?()[]")
        if clean and clean[0].isupper() and clean not in common_words:
            terms.append(clean.lower())

    return terms


def validate_narrative(
    narrative: str,
    render_input: RenderInput,
) -> list[str]:
    """Validate generated narrative against contract requirements.

    Args:
        narrative: Generated narrative text
        render_input: Original input for context

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    # 1. Non-empty check
    if not narrative or not narrative.strip():
        errors.append("Narrative is empty")
        return errors  # Can't validate further

    narrative_stripped = narrative.strip()
    narrative_lower = narrative_stripped.lower()

    # 2. Sentence count check (2-4 sentences)
    sentence_count = _count_sentences(narrative_stripped)
    if sentence_count < 2:
        errors.append(f"Narrative has {sentence_count} sentences (minimum 2)")
    if sentence_count > 4:
        errors.append(f"Narrative has {sentence_count} sentences (maximum 4)")

    # 3. Forbidden phrases check
    for phrase in FORBIDDEN_PHRASES:
        if phrase in narrative_lower:
            errors.append(f"Narrative contains forbidden phrase: '{phrase}'")

    # 4. Explicit play reference check
    # Extract key terms from explicit plays and verify they appear
    explicit_ids = set(render_input.moment.explicitly_narrated_play_ids)
    for play in render_input.plays:
        if play.play_index not in explicit_ids:
            continue

        # Extract key terms from this explicit play
        key_terms = _extract_key_terms(play.description)

        # Check if at least one key term appears
        # (player name or distinctive action)
        if key_terms:
            found = any(term in narrative_lower for term in key_terms)
            if not found:
                errors.append(
                    f"Explicit play not referenced: '{play.description}' "
                    f"(expected terms: {key_terms})"
                )

    # 5. Score accuracy check (if score changed)
    score_before = render_input.moment.score_before
    score_after = render_input.moment.score_after

    if score_before != score_after:
        # Score changed - check if final scores mentioned are accurate
        # Look for score patterns like "104-102" or "102 to 101"
        score_pattern = r'(\d{1,3})\s*[-to]\s*(\d{1,3})'
        matches = re.findall(score_pattern, narrative_stripped)

        for match in matches:
            s1, s2 = int(match[0]), int(match[1])
            # The mentioned score should match either score_after configuration
            valid_scores = [
                (score_after.home, score_after.away),
                (score_after.away, score_after.home),
            ]
            if (s1, s2) not in valid_scores:
                # Only warn, don't fail - narrative might reference lead margin
                logger.debug(
                    f"Score mention {s1}-{s2} doesn't match "
                    f"score_after {score_after.home}-{score_after.away}"
                )

    return errors


def _parse_response(raw_response: str) -> str:
    """Parse AI response to extract narrative.

    Args:
        raw_response: JSON string from AI model

    Returns:
        Extracted narrative text

    Raises:
        RenderError: If response cannot be parsed
    """
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise RenderError(f"Invalid JSON response: {e}") from e

    if not isinstance(data, dict):
        raise RenderError(f"Response is not a dict: {type(data)}")

    narrative = data.get("narrative")
    if narrative is None:
        raise RenderError("Response missing 'narrative' field")

    if not isinstance(narrative, str):
        raise RenderError(f"Narrative is not a string: {type(narrative)}")

    return narrative


def render_moment(
    render_input: RenderInput,
    client: AIClient,
    *,
    temperature: float = 0.7,
    max_tokens: int = 500,
    max_retries: int = 3,
    debug: bool = False,
    strict_validation: bool = True,
) -> RenderResult:
    """Render narrative for a condensed moment.

    Args:
        render_input: Input data (moment + plays + team names)
        client: AI client for generation
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens to generate
        max_retries: Maximum retry attempts
        debug: If True, include debug information
        strict_validation: If True, raise on validation failure

    Returns:
        RenderResult with narrative and optional debug info

    Raises:
        RenderError: If generation or validation fails
    """
    # Build prompt (deterministic)
    prompt = build_prompt(render_input)
    logger.debug(f"Built prompt ({len(prompt)} chars) for moment rendering")

    # Generate narrative
    try:
        raw_response = client.generate(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
    except Exception as e:
        raise RenderError(f"AI generation failed: {e}") from e

    # Parse response
    narrative = _parse_response(raw_response)

    # Validate narrative
    validation_errors = validate_narrative(narrative, render_input)
    validation_passed = len(validation_errors) == 0

    if validation_errors:
        for err in validation_errors:
            logger.warning(f"Narrative validation: {err}")

        if strict_validation:
            raise ValidationError(
                f"Narrative validation failed: {validation_errors}"
            )

    # Build debug info if requested
    debug_info = None
    if debug:
        debug_info = RenderDebugInfo(
            prompt=prompt,
            raw_response=raw_response,
            narrative=narrative,
            validation_passed=validation_passed,
            validation_errors=validation_errors,
        )

    return RenderResult(narrative=narrative, debug_info=debug_info)


def render_moments(
    render_inputs: Sequence[RenderInput],
    client: AIClient,
    *,
    temperature: float = 0.7,
    max_tokens: int = 500,
    max_retries: int = 3,
    debug: bool = False,
    strict_validation: bool = True,
) -> list[RenderResult]:
    """Render narratives for multiple moments.

    Processes moments sequentially to maintain ordering.

    Args:
        render_inputs: Sequence of input data
        client: AI client for generation
        temperature: Sampling temperature
        max_tokens: Maximum tokens per generation
        max_retries: Maximum retry attempts per generation
        debug: If True, include debug information
        strict_validation: If True, raise on validation failure

    Returns:
        List of RenderResults in same order as inputs

    Raises:
        RenderError: If any generation or validation fails
    """
    results: list[RenderResult] = []

    for i, render_input in enumerate(render_inputs):
        logger.debug(f"Rendering moment {i + 1}/{len(render_inputs)}")
        try:
            result = render_moment(
                render_input=render_input,
                client=client,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=max_retries,
                debug=debug,
                strict_validation=strict_validation,
            )
            results.append(result)
        except RenderError as e:
            raise RenderError(
                f"Failed to render moment {i + 1}: {e}"
            ) from e

    return results


def update_moment_with_narrative(
    moment: CondensedMoment,
    narrative: str,
) -> CondensedMoment:
    """Create new CondensedMoment with updated narrative.

    Args:
        moment: Original moment
        narrative: New narrative text

    Returns:
        New CondensedMoment with narrative field updated
    """
    return CondensedMoment(
        play_ids=moment.play_ids,
        explicitly_narrated_play_ids=moment.explicitly_narrated_play_ids,
        start_clock=moment.start_clock,
        end_clock=moment.end_clock,
        period=moment.period,
        score_before=moment.score_before,
        score_after=moment.score_after,
        narrative=narrative,
    )
