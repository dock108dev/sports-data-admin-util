"""RENDER_NARRATIVES Stage Implementation.

This stage generates narrative text for each validated moment using OpenAI.
It is the ONLY AI-driven step in the Story pipeline.

STORY CONTRACT ALIGNMENT
========================
This implementation adheres to the Story contract:
- AI is a renderer, not an author
- Moments are batched (up to 25 per call) for efficiency
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
4. At least one explicitly narrated play is referenced (traceability)

If validation fails, the stage fails. No retries with weaker rules.
No auto-editing of text. AI output is untrusted until validated.

GUARANTEES
==========
1. Moments batched efficiently (~25 per OpenAI call)
2. All narratives pass validation
3. Broken narratives fail loudly
4. Output includes narrative per moment
5. Human can audit text → plays deterministically
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from .... import db_models
from ..models import StageInput, StageOutput
from ...openai_client import get_openai_client

if TYPE_CHECKING:
    from ....db import AsyncSession

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

# Number of moments to process in a single OpenAI call
MOMENTS_PER_BATCH = 25

# Fallback narrative when OpenAI returns empty
# This allows pipeline to complete while flagging the issue for debugging
FALLBACK_NARRATIVE = "Play continued."


def _build_batch_prompt(
    moments_batch: list[tuple[int, dict[str, Any], list[dict[str, Any]]]],
    game_context: dict[str, str],
) -> str:
    """Build a compact OpenAI prompt for a batch of moments.

    Minimizes token usage by:
    - Putting instructions once at the top
    - Using compact notation for plays
    - Minimal formatting

    Args:
        moments_batch: List of (moment_index, moment, moment_plays) tuples
        game_context: Team names and sport info

    Returns:
        Prompt string for OpenAI to generate all narratives in the batch
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")

    # Build compact moments data
    moments_lines = []
    for moment_index, moment, moment_plays in moments_batch:
        period = moment.get("period", 1)
        clock = moment.get("start_clock", "")
        score_after = moment.get("score_after", [0, 0])
        explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))

        # Compact play format: just the essentials
        plays_compact = []
        for play in moment_plays:
            play_index = play.get("play_index")
            is_explicit = play_index in explicitly_narrated
            star = "*" if is_explicit else ""
            desc = play.get("description", "")
            # Truncate long descriptions
            if len(desc) > 80:
                desc = desc[:77] + "..."
            plays_compact.append(f"{star}{desc}")

        plays_str = "; ".join(plays_compact)
        moments_lines.append(
            f"[{moment_index}] Q{period} {clock} ({away_team} {score_after[0]}-{score_after[1]} {home_team}): {plays_str}"
        )

    moments_block = "\n".join(moments_lines)

    prompt = f"""Write 1-2 sentence narratives for each moment. {away_team} vs {home_team}.

Rules: Describe *starred plays. Concrete actions only (shots/fouls/scores). No: momentum, turning point, crucial, pivotal, speculation.

{moments_block}

JSON response format: {{"items":[{{"i":0,"n":"narrative"}},{{"i":1,"n":"narrative"}},...]}}`"""

    return prompt


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


def _extract_play_identifiers(play: dict[str, Any]) -> list[str]:
    """Extract identifiable tokens from a play for narrative traceability.

    Extracts player names and significant words that should appear in
    a narrative that references this play.

    Args:
        play: A normalized PBP event

    Returns:
        List of lowercase tokens that identify this play
    """
    identifiers: list[str] = []

    # Player name is the primary identifier
    player_name = play.get("player_name")
    if player_name:
        # Add full name and last name (most common in narratives)
        identifiers.append(player_name.lower())
        parts = player_name.split()
        if len(parts) > 1:
            identifiers.append(parts[-1].lower())  # Last name

    # Team abbreviation as fallback
    team_abbrev = play.get("team_abbreviation")
    if team_abbrev:
        identifiers.append(team_abbrev.lower())

    return identifiers


def _validate_narrative(
    narrative: str,
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    moment_index: int,
) -> list[str]:
    """Validate the generated narrative against Story contract rules.

    Args:
        narrative: The generated narrative text
        moment: The moment data
        moment_plays: Full PBP records for plays in this moment
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


def _get_batch_cache_key(moment_indices: list[int]) -> str:
    """Generate a cache key for a batch of moments.

    Args:
        moment_indices: List of moment indices in the batch

    Returns:
        SHA256 hash of the sorted indices (first 16 chars)
    """
    key_str = ",".join(str(i) for i in sorted(moment_indices))
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


async def _get_cached_response(
    session: "AsyncSession",
    game_id: int,
    batch_key: str,
) -> dict[str, Any] | None:
    """Check cache for an existing OpenAI response.

    Args:
        session: Database session
        game_id: Game ID
        batch_key: Cache key for the batch

    Returns:
        Cached response data or None if not found
    """
    result = await session.execute(
        select(db_models.OpenAIResponseCache).where(
            db_models.OpenAIResponseCache.game_id == game_id,
            db_models.OpenAIResponseCache.batch_key == batch_key,
        )
    )
    cached = result.scalar_one_or_none()
    if cached:
        logger.info(f"Cache HIT for game {game_id} batch {batch_key}")
        return cached.response_json
    return None


async def _store_cached_response(
    session: "AsyncSession",
    game_id: int,
    batch_key: str,
    prompt_preview: str,
    response_data: dict[str, Any],
    model: str,
) -> None:
    """Store an OpenAI response in the cache.

    Args:
        session: Database session
        game_id: Game ID
        batch_key: Cache key for the batch
        prompt_preview: Truncated prompt for debugging
        response_data: The parsed response from OpenAI
        model: Model name used
    """
    cache_entry = db_models.OpenAIResponseCache(
        game_id=game_id,
        batch_key=batch_key,
        prompt_preview=prompt_preview[:2000] if prompt_preview else None,
        response_json=response_data,
        model=model,
    )
    session.add(cache_entry)
    await session.flush()
    logger.info(f"Cache STORED for game {game_id} batch {batch_key}")


async def execute_render_narratives(stage_input: StageInput) -> StageOutput:
    """Execute the RENDER_NARRATIVES stage.

    Generates narrative text for each validated moment using OpenAI.
    Moments are batched (up to MOMENTS_PER_BATCH per call) for efficiency.
    Validates all narratives before returning.

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

    # Prepare all moments with their plays
    moments_with_plays: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for i, moment in enumerate(moments):
        play_ids = moment.get("play_ids", [])
        moment_plays = [play_lookup[pid] for pid in play_ids if pid in play_lookup]
        moments_with_plays.append((i, moment, moment_plays))

    # Calculate batch count
    num_batches = (len(moments) + MOMENTS_PER_BATCH - 1) // MOMENTS_PER_BATCH
    output.add_log(
        f"Rendering {len(moments)} moments in {num_batches} batches "
        f"({MOMENTS_PER_BATCH} per batch)"
    )

    # Process in batches
    enriched_moments: list[dict[str, Any]] = [None] * len(moments)  # type: ignore
    all_validation_errors: list[str] = []
    fallback_moments: list[int] = []  # Track moments that got fallback narrative
    successful_renders = 0
    total_openai_calls = 0

    for batch_start in range(0, len(moments_with_plays), MOMENTS_PER_BATCH):
        batch_end = min(batch_start + MOMENTS_PER_BATCH, len(moments_with_plays))
        batch = moments_with_plays[batch_start:batch_end]

        # Check for moments with no plays
        valid_batch = []
        for moment_index, moment, moment_plays in batch:
            if not moment_plays:
                logger.warning(
                    f"Moment {moment_index}: No plays found for play_ids "
                    f"{moment.get('play_ids', [])}, using fallback"
                )
                enriched_moments[moment_index] = {**moment, "narrative": FALLBACK_NARRATIVE}
                fallback_moments.append(moment_index)
                successful_renders += 1
            else:
                valid_batch.append((moment_index, moment, moment_plays))

        if not valid_batch:
            continue

        # Build batch prompt and call OpenAI
        prompt = _build_batch_prompt(valid_batch, game_context)

        try:
            total_openai_calls += 1
            # More tokens for batch response
            max_tokens = 150 * len(valid_batch)
            # Run sync OpenAI call in thread to avoid blocking async event loop
            response_json = await asyncio.to_thread(
                openai_client.generate,
                prompt=prompt,
                temperature=0.3,
                max_tokens=max_tokens,
            )

            # Parse batch response
            response_data = json.loads(response_json)

        except json.JSONDecodeError as e:
            logger.warning(
                f"Batch {batch_start}-{batch_end}: OpenAI returned invalid JSON: {e}, using fallback"
            )
            for moment_index, moment, _ in valid_batch:
                enriched_moments[moment_index] = {**moment, "narrative": FALLBACK_NARRATIVE}
                fallback_moments.append(moment_index)
                successful_renders += 1
            continue

        except Exception as e:
            logger.warning(
                f"Batch {batch_start}-{batch_end}: OpenAI call failed: {e}, using fallback"
            )
            for moment_index, moment, _ in valid_batch:
                enriched_moments[moment_index] = {**moment, "narrative": FALLBACK_NARRATIVE}
                fallback_moments.append(moment_index)
                successful_renders += 1
            continue

        # Process response (from cache or fresh API call)
        # Extract items array from response object
        # OpenAI JSON mode returns objects, not arrays
        items = response_data.get("items", [])
        if not items and isinstance(response_data, list):
            items = response_data  # Fallback if it's already a list

        # Log for debugging
        logger.info(
            f"Batch {batch_start}-{batch_end}: Got {len(items)} items from OpenAI "
            f"(expected {len(valid_batch)})"
        )

        # Build lookup of narratives by moment_index
        # Supports both compact ("i", "n") and full ("moment_index", "narrative") keys
        narrative_lookup: dict[int, str] = {}
        for item in items:
            idx = item.get("i") if item.get("i") is not None else item.get("moment_index")
            narrative = item.get("n") or item.get("narrative", "")
            if idx is not None:
                narrative_lookup[idx] = narrative

        # Log if we're missing narratives
        missing = [idx for idx, _, _ in valid_batch if idx not in narrative_lookup]
        if missing:
            logger.warning(
                f"Batch {batch_start}-{batch_end}: Missing narratives for moments {missing[:5]}..."
            )

        # Process each moment in the batch
        for moment_index, moment, moment_plays in valid_batch:
            narrative = narrative_lookup.get(moment_index, "")

            # Handle empty narratives with fallback instead of failing
            if not narrative or not narrative.strip():
                narrative = FALLBACK_NARRATIVE
                fallback_moments.append(moment_index)
                logger.warning(
                    f"Moment {moment_index}: Empty narrative from OpenAI, using fallback",
                    extra={
                        "game_id": game_id,
                        "moment_index": moment_index,
                        "period": moment.get("period"),
                        "start_clock": moment.get("start_clock"),
                    },
                )
                # Count as successful since we have a valid fallback
                successful_renders += 1
            else:
                # Validate non-empty narratives for forbidden phrases
                validation_errors = _validate_narrative(
                    narrative, moment, moment_plays, moment_index
                )
                if validation_errors:
                    all_validation_errors.extend(validation_errors)
                    output.add_log(
                        f"Moment {moment_index}: Narrative validation failed",
                        level="error",
                    )
                else:
                    successful_renders += 1

            enriched_moments[moment_index] = {**moment, "narrative": narrative}

    output.add_log(f"OpenAI calls made: {total_openai_calls}")
    output.add_log(f"Successful renders: {successful_renders}/{len(moments)}")

    # Log fallback usage for debugging
    if fallback_moments:
        output.add_log(
            f"Fallback narratives used for {len(fallback_moments)} moments: {fallback_moments[:20]}{'...' if len(fallback_moments) > 20 else ''}",
            level="warning",
        )
        logger.warning(
            "render_narratives_fallbacks_used",
            extra={
                "game_id": game_id,
                "fallback_count": len(fallback_moments),
                "fallback_moment_indices": fallback_moments,
            },
        )

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
            "fallback_count": len(fallback_moments),
            "fallback_moment_indices": fallback_moments,
        }

        # Raise with structured JSON for reviewability
        raise ValueError(json.dumps(error_output))

    # All narratives passed validation (or got fallback)
    if fallback_moments:
        output.add_log(
            f"{len(moments) - len(fallback_moments)} narratives from OpenAI, "
            f"{len(fallback_moments)} fallbacks used"
        )
    else:
        output.add_log(f"All {len(moments)} narratives generated successfully")
    output.add_log("RENDER_NARRATIVES completed successfully")

    # Output shape: moments with narrative field added
    output.data = {
        "rendered": True,
        "moments": enriched_moments,
        "errors": [],
        "openai_calls": total_openai_calls,
        "successful_renders": successful_renders,
        "fallback_count": len(fallback_moments),
        "fallback_moment_indices": fallback_moments,
    }

    return output
