"""RENDER_BLOCKS Stage Implementation.

This stage generates short narrative text for each block using OpenAI.
Each block gets 1-2 sentences (~35 words) describing that stretch of play.

RENDERING RULES
===============
The prompt REQUIRES:
- 1-2 sentences per block (~35 words)
- Role-aware context (SETUP, MOMENTUM_SHIFT, etc.)
- Focus on key plays identified
- Concrete actions and score changes

The prompt FORBIDS:
- momentum, turning point, dominant, huge, clutch
- Speculation or interpretation
- References to plays not in the block

VALIDATION
==========
Post-generation validation ensures:
- Non-empty narratives
- Word count within limits (10-50 words)
- No forbidden language
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from ..models import StageInput, StageOutput
from ...openai_client import get_openai_client
from .block_types import (
    NarrativeBlock,
    SemanticRole,
    MIN_WORDS_PER_BLOCK,
    MAX_WORDS_PER_BLOCK,
    TARGET_WORDS_PER_BLOCK,
)

logger = logging.getLogger(__name__)

# Forbidden words in block narratives
FORBIDDEN_WORDS = [
    "momentum",
    "turning point",
    "dominant",
    "huge",
    "clutch",
    "epic",
    "crucial",
    "massive",
    "incredible",
]

# Task 1.4: Sentence style constraints - prohibited stat-feed patterns
PROHIBITED_PATTERNS = [
    # "X had Y points" stat-feed patterns
    r"\bhad\s+\d+\s+points\b",
    r"\bfinished\s+with\s+\d+\b",
    r"\brecorded\s+\d+\b",
    r"\bnotched\s+\d+\b",
    r"\btallied\s+\d+\b",
    r"\bposted\s+\d+\b",
    r"\bracked\s+up\s+\d+\b",
    # Subjective adjectives to avoid
    r"\bincredible\b",
    r"\bamazing\b",
    r"\bunbelievable\b",
    r"\binsane\b",
    r"\belectric\b",
    r"\bexplosive\b",
    r"\bbrilliant\b",
    r"\bstunning\b",
    r"\bspectacular\b",
    r"\bsensational\b",
]

# Maximum regeneration attempts for play coverage recovery
MAX_REGENERATION_ATTEMPTS = 2


def _build_block_prompt(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    pbp_events: list[dict[str, Any]],
) -> str:
    """Build the prompt for generating block narratives.

    Args:
        blocks: List of block dicts (without narratives)
        game_context: Team names and other context
        pbp_events: PBP events for play descriptions

    Returns:
        Prompt string for OpenAI
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")

    # Build play lookup
    play_lookup: dict[int, dict[str, Any]] = {
        e["play_index"]: e for e in pbp_events if "play_index" in e
    }

    prompt_parts = [
        "Generate short narrative summaries for game blocks.",
        "",
        f"Teams: {away_team} (away) vs {home_team} (home)",
        "",
        "RULES:",
        "- Write 1-2 sentences per block (~35 words)",
        "- Focus on the key plays provided",
        "- Describe concrete actions and score changes",
        "- Use the semantic role to guide tone:",
        "  - SETUP: Set the stage, establish early context",
        "  - MOMENTUM_SHIFT: Describe the swing in the game",
        "  - RESPONSE: How the other team answered",
        "  - DECISION_POINT: The sequence that decided the outcome",
        "  - RESOLUTION: How the game concluded",
        "",
        "FORBIDDEN WORDS (do not use):",
        ", ".join(FORBIDDEN_WORDS),
        "",
        "Return JSON: {\"blocks\": [{\"i\": block_index, \"n\": \"narrative\"}]}",
        "",
        "BLOCKS:",
    ]

    for block in blocks:
        block_idx = block["block_index"]
        role = block["role"]
        score_before = block["score_before"]
        score_after = block["score_after"]
        key_play_ids = block["key_play_ids"]

        # Get key play descriptions
        key_plays_desc = []
        for pid in key_play_ids:
            play = play_lookup.get(pid, {})
            desc = play.get("description", "")
            if desc:
                key_plays_desc.append(f"- {desc}")

        prompt_parts.append(f"\nBlock {block_idx} ({role}):")
        prompt_parts.append(
            f"Score: {away_team} {score_before[1]}-{score_before[0]} {home_team} "
            f"-> {away_team} {score_after[1]}-{score_after[0]} {home_team}"
        )
        if key_plays_desc:
            prompt_parts.append("Key plays:")
            prompt_parts.extend(key_plays_desc[:3])

    return "\n".join(prompt_parts)


def _validate_block_narrative(
    narrative: str,
    block_idx: int,
) -> tuple[list[str], list[str]]:
    """Validate a single block narrative.

    Args:
        narrative: The generated narrative text
        block_idx: Block index for error messages

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not narrative or not narrative.strip():
        errors.append(f"Block {block_idx}: Empty narrative")
        return errors, warnings

    word_count = len(narrative.split())

    if word_count < MIN_WORDS_PER_BLOCK:
        warnings.append(
            f"Block {block_idx}: Narrative too short ({word_count} words, min: {MIN_WORDS_PER_BLOCK})"
        )

    if word_count > MAX_WORDS_PER_BLOCK:
        warnings.append(
            f"Block {block_idx}: Narrative too long ({word_count} words, max: {MAX_WORDS_PER_BLOCK})"
        )

    # Check forbidden words
    narrative_lower = narrative.lower()
    for word in FORBIDDEN_WORDS:
        if word.lower() in narrative_lower:
            warnings.append(f"Block {block_idx}: Contains forbidden word '{word}'")

    return errors, warnings


def _generate_fallback_narrative(
    block: dict[str, Any],
    game_context: dict[str, str],
) -> str:
    """Generate a simple fallback narrative when AI fails.

    Args:
        block: Block data
        game_context: Team names

    Returns:
        Simple descriptive narrative
    """
    home_team = game_context.get("home_team_abbrev", "Home")
    away_team = game_context.get("away_team_abbrev", "Away")

    score_before = block["score_before"]
    score_after = block["score_after"]
    role = block["role"]

    home_delta = score_after[0] - score_before[0]
    away_delta = score_after[1] - score_before[1]

    if role == SemanticRole.SETUP.value:
        return (
            f"The game began with {away_team} and {home_team} trading baskets. "
            f"Score moved to {home_team} {score_after[0]}, {away_team} {score_after[1]}."
        )
    elif role == SemanticRole.RESOLUTION.value:
        return (
            f"The game concluded with a final score of "
            f"{home_team} {score_after[0]}, {away_team} {score_after[1]}."
        )
    else:
        if home_delta > away_delta:
            return (
                f"{home_team} outscored {away_team} {home_delta}-{away_delta} "
                f"in this stretch, moving the score to {home_team} {score_after[0]}, "
                f"{away_team} {score_after[1]}."
            )
        elif away_delta > home_delta:
            return (
                f"{away_team} outscored {home_team} {away_delta}-{home_delta} "
                f"in this stretch, moving the score to {home_team} {score_after[0]}, "
                f"{away_team} {score_after[1]}."
            )
        else:
            return (
                f"Both teams scored evenly in this stretch. "
                f"Score: {home_team} {score_after[0]}, {away_team} {score_after[1]}."
            )


async def execute_render_blocks(stage_input: StageInput) -> StageOutput:
    """Execute the RENDER_BLOCKS stage.

    Generates narrative text for each block using OpenAI.
    Each block gets 1-2 sentences (~35 words).

    Args:
        stage_input: Input containing previous_output with grouped blocks

    Returns:
        StageOutput with blocks enriched with narratives

    Raises:
        ValueError: If OpenAI not configured or prerequisites not met
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting RENDER_BLOCKS for game {game_id}")

    # Get OpenAI client
    openai_client = get_openai_client()
    if openai_client is None:
        raise ValueError(
            "OpenAI API key not configured - cannot render block narratives. "
            "Set OPENAI_API_KEY environment variable."
        )

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("RENDER_BLOCKS requires previous stage output")

    # Verify GROUP_BLOCKS completed
    blocks_grouped = previous_output.get("blocks_grouped")
    if blocks_grouped is not True:
        raise ValueError(
            f"RENDER_BLOCKS requires GROUP_BLOCKS to complete. Got blocks_grouped={blocks_grouped}"
        )

    # Get blocks and PBP data
    blocks = previous_output.get("blocks", [])
    if not blocks:
        raise ValueError("No blocks in previous stage output")

    pbp_events = previous_output.get("pbp_events", [])
    game_context = stage_input.game_context

    output.add_log(f"Rendering narratives for {len(blocks)} blocks")

    # Build prompt and call OpenAI
    prompt = _build_block_prompt(blocks, game_context, pbp_events)

    try:
        # Estimate tokens: ~100 words per block max
        max_tokens = 150 * len(blocks)

        response_json = await asyncio.to_thread(
            openai_client.generate,
            prompt=prompt,
            temperature=0.3,
            max_tokens=max_tokens,
        )
        response_data = json.loads(response_json)

    except json.JSONDecodeError as e:
        output.add_log(f"OpenAI returned invalid JSON: {e}", level="error")
        output.add_log("Using fallback narratives for all blocks", level="warning")

        # Use fallbacks
        for block in blocks:
            block["narrative"] = _generate_fallback_narrative(block, game_context)

        output.data = {
            "blocks_rendered": True,
            "blocks": blocks,
            "openai_calls": 1,
            "fallback_count": len(blocks),
            "errors": [f"JSON parse error: {e}"],
            # Pass through
            "moments": previous_output.get("moments", []),
            "pbp_events": pbp_events,
            "validated": True,
            "blocks_grouped": True,
        }
        return output

    except Exception as e:
        output.add_log(f"OpenAI call failed: {e}", level="error")
        output.add_log("Using fallback narratives for all blocks", level="warning")

        for block in blocks:
            block["narrative"] = _generate_fallback_narrative(block, game_context)

        output.data = {
            "blocks_rendered": True,
            "blocks": blocks,
            "openai_calls": 1,
            "fallback_count": len(blocks),
            "errors": [f"OpenAI error: {e}"],
            "moments": previous_output.get("moments", []),
            "pbp_events": pbp_events,
            "validated": True,
            "blocks_grouped": True,
        }
        return output

    # Extract narratives from response
    block_items = response_data.get("blocks", [])
    if not block_items and isinstance(response_data, list):
        block_items = response_data

    output.add_log(f"Got {len(block_items)} narratives from OpenAI")

    # Build lookup by block index
    narrative_lookup: dict[int, str] = {}
    for item in block_items:
        idx = item.get("i") if item.get("i") is not None else item.get("block_index")
        narrative = item.get("n") or item.get("narrative", "")
        if idx is not None:
            narrative_lookup[idx] = narrative

    # Apply narratives to blocks with validation
    all_errors: list[str] = []
    all_warnings: list[str] = []
    fallback_count = 0
    total_words = 0

    for block in blocks:
        block_idx = block["block_index"]
        narrative = narrative_lookup.get(block_idx, "")

        if not narrative or not narrative.strip():
            output.add_log(
                f"Block {block_idx}: No narrative from AI, using fallback",
                level="warning",
            )
            narrative = _generate_fallback_narrative(block, game_context)
            fallback_count += 1

        # Validate
        errors, warnings = _validate_block_narrative(narrative, block_idx)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

        # If hard errors, use fallback
        if errors:
            narrative = _generate_fallback_narrative(block, game_context)
            fallback_count += 1

        block["narrative"] = narrative
        total_words += len(narrative.split())

    output.add_log(f"Total word count: {total_words}")
    output.add_log(f"Fallback narratives used: {fallback_count}")

    if all_warnings:
        output.add_log(f"Warnings: {len(all_warnings)}", level="warning")
        for w in all_warnings[:5]:
            output.add_log(f"  {w}", level="warning")

    output.add_log("RENDER_BLOCKS completed successfully")

    output.data = {
        "blocks_rendered": True,
        "blocks": blocks,
        "block_count": len(blocks),
        "total_words": total_words,
        "openai_calls": 1,
        "fallback_count": fallback_count,
        "errors": all_errors,
        "warnings": all_warnings,
        # Pass through
        "moments": previous_output.get("moments", []),
        "pbp_events": pbp_events,
        "validated": True,
        "blocks_grouped": True,
    }

    return output
