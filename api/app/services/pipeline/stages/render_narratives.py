"""RENDER_NARRATIVES Stage Implementation.

This stage generates narrative text for each validated moment using OpenAI.
It is the ONLY AI-driven step in the Story pipeline.

STORY CONTRACT ALIGNMENT
========================
This implementation adheres to the Story contract:
- AI is a renderer, not an author
- One OpenAI call per moment
- Narrative is grounded strictly in backing plays
- No story-level prose or summaries
- Narrative is traceable to explicit plays

RENDERING RULES
===============
The prompt REQUIRES:
- Direct reference to at least one explicitly narrated play
- Concrete actions only (shots, fouls, turnovers, scores)
- Chronological order
- Neutral, factual language

The prompt FORBIDS:
- Momentum, flow, turning points
- Summaries or retrospection
- "Earlier/later in the game"
- Speculation or interpretation
- Referencing plays not provided

POST-GENERATION VALIDATION
==========================
After receiving AI output, we validate:
1. Narrative is non-empty
2. No forbidden abstraction language
3. Response is well-formed JSON

If validation fails, the stage fails. No retries with weaker rules.
No auto-editing of text. AI output is untrusted until validated.

GUARANTEES
==========
1. One OpenAI call per moment (no more)
2. All narratives pass validation
3. Broken narratives fail loudly
4. Output includes narrative per moment
5. Human can audit text → plays deterministically
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..models import StageInput, StageOutput
from ...openai_client import get_openai_client

logger = logging.getLogger(__name__)

# Forbidden phrases that indicate abstraction beyond the moment
FORBIDDEN_PHRASES = [
    # Momentum/flow language
    r"\bmomentum\b",
    r"\bturning point\b",
    r"\bshift(ed|ing)?\b",
    r"\bswing\b",
    r"\btide\b",
    # Temporal references outside the moment
    r"\bearlier in the game\b",
    r"\blater in the game\b",
    r"\bpreviously\b",
    r"\bwould (later|eventually)\b",
    r"\bforeshadow\b",
    # Summary/retrospective language
    r"\bin summary\b",
    r"\boverall\b",
    r"\bultimately\b",
    r"\bin the end\b",
    r"\bkey moment\b",
    r"\bcrucial\b",
    r"\bpivotal\b",
    # Speculation
    r"\bcould have\b",
    r"\bmight have\b",
    r"\bwould have\b",
    r"\bshould have\b",
    r"\bseemed to\b",
    r"\bappeared to\b",
]

# Compile patterns for efficiency
FORBIDDEN_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PHRASES]


def _build_moment_prompt(
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    game_context: dict[str, str],
    moment_index: int,
) -> str:
    """Build the OpenAI prompt for a single moment.

    The prompt is strict and includes:
    - Clear requirements
    - Explicit prohibitions
    - Positive and negative examples
    - Statement that violations invalidate output

    Args:
        moment: The moment data (play_ids, scores, etc.)
        moment_plays: Full PBP records for plays in this moment
        game_context: Team names and sport info
        moment_index: Index of this moment in the sequence

    Returns:
        Prompt string for OpenAI
    """
    # Extract context
    home_team = game_context.get("home_team_name", "Home Team")
    away_team = game_context.get("away_team_name", "Away Team")
    sport = game_context.get("sport", "basketball")

    # Extract moment data
    period = moment.get("period", 1)
    start_clock = moment.get("start_clock", "")
    end_clock = moment.get("end_clock", "")
    score_before = moment.get("score_before", [0, 0])
    score_after = moment.get("score_after", [0, 0])
    explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))

    # Format plays for the prompt
    plays_text = []
    for play in moment_plays:
        play_index = play.get("play_index")
        is_explicit = play_index in explicitly_narrated
        marker = "[MUST NARRATE]" if is_explicit else ""

        # Build play description
        clock = play.get("game_clock", "")
        description = play.get("description", "")
        play_type = play.get("play_type", "")
        home_score = play.get("home_score", 0)
        away_score = play.get("away_score", 0)

        play_line = (
            f"- Play {play_index} {marker}: {clock} | {play_type} | "
            f"{description} | Score: {away_team} {away_score} - {home_team} {home_score}"
        )
        plays_text.append(play_line)

    plays_block = "\n".join(plays_text)

    prompt = f"""Generate a brief narrative (1-3 sentences) for this {sport} game moment.

CONTEXT:
- Teams: {away_team} vs {home_team}
- Period: {period}
- Time: {start_clock} to {end_clock}
- Score before: {away_team} {score_before[0]} - {home_team} {score_before[1]}
- Score after: {away_team} {score_after[0]} - {home_team} {score_after[1]}

PLAYS IN THIS MOMENT:
{plays_block}

REQUIREMENTS (MANDATORY):
1. You MUST describe at least one play marked [MUST NARRATE]
2. Only describe actions from the plays provided above
3. Use concrete actions: shots made/missed, fouls, turnovers, scores
4. Use chronological order if describing multiple plays
5. Use neutral, factual language

FORBIDDEN (WILL INVALIDATE YOUR RESPONSE):
- Do NOT use words like: momentum, turning point, shift, swing, tide, crucial, pivotal
- Do NOT reference "earlier in the game" or "later in the game"
- Do NOT speculate about what "could have" or "might have" happened
- Do NOT summarize the game or moment's importance
- Do NOT reference any plays not listed above

GOOD EXAMPLE:
"Brown drove baseline and finished with a layup, giving the Celtics a 45-42 lead."

BAD EXAMPLE (FORBIDDEN):
"This was a crucial turning point as the momentum shifted toward the Celtics who would go on to dominate."

Respond with JSON in this exact format:
{{"narrative": "Your 1-3 sentence narrative here"}}"""

    return prompt


def _validate_narrative(
    narrative: str,
    moment: dict[str, Any],
    moment_index: int,
) -> list[str]:
    """Validate the generated narrative against Story contract rules.

    Args:
        narrative: The generated narrative text
        moment: The moment data
        moment_index: Index for error reporting

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Rule 1: Narrative must be non-empty
    if not narrative or not narrative.strip():
        errors.append(f"Moment {moment_index}: Narrative is empty")
        return errors  # Can't validate further if empty

    # Rule 2: Check for forbidden phrases
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(narrative)
        if match:
            errors.append(
                f"Moment {moment_index}: Contains forbidden phrase '{match.group()}'"
            )

    return errors


async def execute_render_narratives(stage_input: StageInput) -> StageOutput:
    """Execute the RENDER_NARRATIVES stage.

    Generates narrative text for each validated moment using OpenAI.
    One OpenAI call per moment. Validates all narratives before returning.

    Args:
        stage_input: Input containing previous_output with validated moments

    Returns:
        StageOutput with moments enriched with narrative field

    Raises:
        ValueError: If OpenAI is not configured or validation fails
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting RENDER_NARRATIVES for game {game_id}")

    # Get OpenAI client
    openai_client = get_openai_client()
    if openai_client is None:
        raise ValueError(
            "OpenAI API key not configured - cannot render narratives. "
            "Set OPENAI_API_KEY environment variable."
        )

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("RENDER_NARRATIVES requires previous stage output")

    # Verify validation passed
    validated = previous_output.get("validated")
    if validated is not True:
        raise ValueError(
            "RENDER_NARRATIVES requires VALIDATE_MOMENTS to pass. "
            f"Got validated={validated}"
        )

    # Get moments and PBP data
    moments = previous_output.get("moments")
    if not moments:
        raise ValueError("No moments in previous stage output")

    pbp_events = previous_output.get("pbp_events")
    if not pbp_events:
        raise ValueError("No pbp_events in previous stage output")

    # Build play_index -> event lookup
    play_lookup: dict[int, dict[str, Any]] = {}
    for event in pbp_events:
        play_index = event.get("play_index")
        if play_index is not None:
            play_lookup[play_index] = event

    game_context = stage_input.game_context

    output.add_log(f"Rendering narratives for {len(moments)} moments")

    # Process each moment
    enriched_moments: list[dict[str, Any]] = []
    all_validation_errors: list[str] = []
    successful_renders = 0
    total_openai_calls = 0

    for i, moment in enumerate(moments):
        # Get plays for this moment
        play_ids = moment.get("play_ids", [])
        moment_plays = [play_lookup[pid] for pid in play_ids if pid in play_lookup]

        if not moment_plays:
            all_validation_errors.append(
                f"Moment {i}: No plays found for play_ids {play_ids}"
            )
            continue

        # Build prompt
        prompt = _build_moment_prompt(moment, moment_plays, game_context, i)

        # Call OpenAI (one call per moment)
        try:
            total_openai_calls += 1
            response_json = openai_client.generate(
                prompt=prompt,
                temperature=0.3,  # Lower temperature for factual consistency
                max_tokens=200,  # Short narratives only
            )

            # Parse response
            response_data = json.loads(response_json)
            narrative = response_data.get("narrative", "")

            # Validate narrative
            validation_errors = _validate_narrative(narrative, moment, i)
            if validation_errors:
                all_validation_errors.extend(validation_errors)
                output.add_log(
                    f"Moment {i}: Narrative validation failed", level="error"
                )
            else:
                successful_renders += 1

            # Create enriched moment (include narrative even if validation failed
            # so errors are inspectable)
            enriched_moment = {**moment, "narrative": narrative}
            enriched_moments.append(enriched_moment)

        except json.JSONDecodeError as e:
            all_validation_errors.append(
                f"Moment {i}: OpenAI returned invalid JSON: {e}"
            )
            # Still add moment without narrative for inspection
            enriched_moments.append({**moment, "narrative": ""})

        except Exception as e:
            all_validation_errors.append(
                f"Moment {i}: OpenAI call failed: {e}"
            )
            enriched_moments.append({**moment, "narrative": ""})

    output.add_log(f"OpenAI calls made: {total_openai_calls}")
    output.add_log(f"Successful renders: {successful_renders}/{len(moments)}")

    # Check if any validation errors occurred
    if all_validation_errors:
        output.add_log(
            f"Narrative validation failed with {len(all_validation_errors)} errors",
            level="error",
        )

        # Log to Python logger for visibility
        logger.error(
            "Narrative rendering failed",
            extra={
                "game_id": game_id,
                "error_count": len(all_validation_errors),
                "errors": all_validation_errors,
            },
        )

        # Build structured error output
        error_output = {
            "rendered": False,
            "moments": enriched_moments,
            "errors": all_validation_errors,
            "openai_calls": total_openai_calls,
            "successful_renders": successful_renders,
        }

        # Raise with structured JSON for reviewability
        raise ValueError(json.dumps(error_output))

    # All narratives passed validation
    output.add_log(f"All {len(moments)} narratives passed validation")
    output.add_log("RENDER_NARRATIVES completed successfully")

    # Output shape: moments with narrative field added
    output.data = {
        "rendered": True,
        "moments": enriched_moments,
        "errors": [],
        "openai_calls": total_openai_calls,
        "successful_renders": successful_renders,
    }

    return output
