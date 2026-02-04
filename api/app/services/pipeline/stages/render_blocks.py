"""RENDER_BLOCKS Stage Implementation.

This stage generates narrative text for each block using OpenAI.
Each block gets 2-4 sentences (~65 words) describing that stretch of play.

TWO-PASS RENDERING
==================
1. Initial render: Per-block narrative generation with role-aware prompting
2. Game-level flow pass: Single call that sees all blocks and smooths transitions

RENDERING RULES
===============
The prompt REQUIRES:
- 2-4 sentences per block (~50-80 words)
- Role-aware context (SETUP, MOMENTUM_SHIFT, etc.)
- Focus on key plays identified
- Concrete actions and score changes
- SportsCenter-style prose describing stretches of play

The prompt FORBIDS:
- momentum, turning point, dominant, huge, clutch
- Speculation or interpretation
- References to plays not in the block
- Raw PBP artifacts (initials like "j. smith")

GAME-LEVEL FLOW PASS
====================
After initial narratives are generated, a second OpenAI call smooths
the entire game flow:
- Acknowledges time progression (early → middle → late)
- Reduces repetition across blocks
- Preserves all facts, scores, and structure
- Uses low temperature (0.2) for consistency
- Safe fallback: if output count != input count, uses originals

VALIDATION
==========
Post-generation validation ensures:
- Non-empty narratives
- Word count within limits (30-100 words)
- Sentence count within limits (2-4 sentences)
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
    SemanticRole,
    MIN_WORDS_PER_BLOCK,
    MAX_WORDS_PER_BLOCK,
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


def _check_play_coverage(
    narrative: str,
    key_play_ids: list[int],
    pbp_events: list[dict[str, Any]],
) -> tuple[list[int], list[dict[str, Any]]]:
    """Check if key plays are referenced in the narrative.

    Task 1.3: Explicit play coverage invariant.

    Args:
        narrative: The generated narrative text
        key_play_ids: IDs of plays that must be referenced
        pbp_events: PBP events with play descriptions

    Returns:
        Tuple of (missing_play_ids, missing_play_events)
    """
    if not narrative or not key_play_ids:
        return [], []

    # Build play lookup
    play_lookup: dict[int, dict[str, Any]] = {
        e.get("play_index", e.get("play_id")): e
        for e in pbp_events
        if e.get("play_index") is not None or e.get("play_id") is not None
    }

    narrative_lower = narrative.lower()
    missing_ids: list[int] = []
    missing_events: list[dict[str, Any]] = []

    for play_id in key_play_ids:
        event = play_lookup.get(play_id, {})
        if not event:
            continue

        # Check if play is referenced in narrative
        # Look for player name, action keywords from description
        description = event.get("description", "")
        player_name = event.get("player_name", "")

        # Extract keywords from description
        found = False

        # Check for player name (first or last name)
        if player_name:
            name_parts = player_name.lower().split()
            for part in name_parts:
                if len(part) > 2 and part in narrative_lower:
                    found = True
                    break

        # Check for key action words from description
        if not found and description:
            # Look for key action words (3-pointer, dunk, layup, etc.)
            # Map both description keywords and their narrative equivalents
            action_keyword_pairs = [
                (["three", "3-point", "3pt", "3-pointer"], ["three", "3-point", "three-pointer"]),
                (["dunk"], ["dunk"]),
                (["layup"], ["layup"]),
                (["jumper", "jump shot"], ["jumper", "jump shot"]),
                (["free throw"], ["free throw"]),
                (["steal"], ["steal"]),
                (["block"], ["block"]),
                (["rebound"], ["rebound"]),
                (["assist"], ["assist"]),
            ]
            desc_lower = description.lower()
            for desc_keywords, narr_keywords in action_keyword_pairs:
                desc_has_keyword = any(kw in desc_lower for kw in desc_keywords)
                narr_has_keyword = any(kw in narrative_lower for kw in narr_keywords)
                if desc_has_keyword and narr_has_keyword:
                    found = True
                    break

        if not found:
            missing_ids.append(play_id)
            missing_events.append(event)

    return missing_ids, missing_events


# Natural language mappings for play types
PLAY_TYPE_VERBS = {
    "2pt": "scored inside",
    "3pt": "hit a three-pointer",
    "dunk": "threw down a dunk",
    "layup": "finished at the rim",
    "freethrow": "converted from the line",
    "free throw": "converted from the line",
    "steal": "came up with a steal",
    "block": "rejected the shot",
    "rebound": "grabbed the rebound",
    "assist": "delivered the assist",
    "jump shot": "knocked down a jumper",
    "jumper": "knocked down a jumper",
    "hook": "hit a hook shot",
    "tip": "tipped one in",
    "alley oop": "finished the alley-oop",
    "putback": "scored on the putback",
}


def _normalize_player_name(name: str) -> str:
    """Convert 'j. smith' or 'J. Smith' to 'Smith'.

    Handles initial-style names from PBP data to produce cleaner narratives.
    Supports international names with diacritical marks (e.g., Dončić, Schröder).
    """
    if not name:
        return ""
    # Match patterns like "j. smith" or "J. Dončić" - use \S+ for Unicode support
    if re.match(r"^[A-Za-z]\.\s+\S+", name):
        return name.split()[-1].title()
    return name.title() if name.islower() else name


def _generate_play_injection_sentence(
    event: dict[str, Any],
    game_context: dict[str, str],
) -> str:
    """Generate a natural language sentence for a missing play.

    Task 1.3: Recovery strategy when a key play is not referenced.
    Produces SportsCenter-style prose instead of raw PBP artifacts.

    Args:
        event: The PBP event that needs to be mentioned
        game_context: Team abbreviations

    Returns:
        A natural, broadcast-style sentence describing the play
    """
    player_name = _normalize_player_name(event.get("player_name", ""))
    play_type = (event.get("play_type") or "").lower()
    description = (event.get("description") or "").lower()

    # Try to find a matching verb from play type
    verb = PLAY_TYPE_VERBS.get(play_type)

    # If no direct match, try to extract from description
    if not verb and description:
        for key, val in PLAY_TYPE_VERBS.items():
            if key in description:
                verb = val
                break

    # Fallback verb
    if not verb:
        verb = "scored"

    if player_name:
        return f"{player_name} {verb}."
    return ""


def _validate_style_constraints(
    narrative: str,
    block_idx: int,
) -> tuple[list[str], list[str]]:
    """Validate narrative against style constraints.

    Task 1.4: Sentence style constraints.
    - No stat-feed prose patterns
    - No subjective adjectives
    - Broadcast tone

    Args:
        narrative: The generated narrative text
        block_idx: Block index for error messages

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not narrative:
        return errors, warnings

    narrative_lower = narrative.lower()

    # Check for prohibited patterns
    for pattern in PROHIBITED_PATTERNS:
        if re.search(pattern, narrative_lower, re.IGNORECASE):
            warnings.append(
                f"Block {block_idx}: Style violation - matches prohibited pattern '{pattern}'"
            )

    # Check for overly long sentences (stat-feed indicator)
    sentences = re.split(r'[.!?]+', narrative)
    for sentence in sentences:
        words = sentence.split()
        if len(words) > 40:
            warnings.append(
                f"Block {block_idx}: Sentence too long ({len(words)} words) - may be stat-feed style"
            )

    # Check for too many numbers (stat-feed indicator)
    numbers_in_narrative = re.findall(r'\b\d+\b', narrative)
    if len(numbers_in_narrative) > 6:
        warnings.append(
            f"Block {block_idx}: Too many numbers ({len(numbers_in_narrative)}) - may be stat-feed style"
        )

    return errors, warnings


# Patterns to clean up raw PBP artifacts from narratives
# Use \S+ for name matching to support international names (e.g., Dončić, Schröder)
# Order matters: more specific patterns (like "tip to") must come before general patterns
PBP_ARTIFACT_PATTERNS = [
    # Jump ball tip patterns like "tip to j. smith" - must come before general initial removal
    (r"tip to [a-zA-Z]\.\s*\S+", "won the tip"),
    # "j. smith" style initials - match single letter followed by period and name
    (r"\b[a-zA-Z]\.\s+\S+(?=\s|[.,!?]|$)", ""),
    # Score artifacts like ": 45-42"
    (r"\s*:\s*\d+-\d+", ""),
    # Raw PBP colons followed by lowercase play text
    (r":\s+[a-zA-Z]", lambda m: ". " + m.group(0)[-1].upper()),
]


def _cleanup_pbp_artifacts(narrative: str) -> str:
    """Remove raw PBP artifacts from narrative text.

    Cleans up patterns like:
    - "j. smith" initials → removed (should use full names)
    - "tip to j. smith" → "won the tip"
    - ": 45-42" score artifacts → removed

    Args:
        narrative: The generated narrative text

    Returns:
        Cleaned narrative without raw PBP artifacts
    """
    if not narrative:
        return narrative

    cleaned = narrative
    for pattern, replacement in PBP_ARTIFACT_PATTERNS:
        if callable(replacement):
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        else:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# Game-level flow pass prompt - intentionally tight and low-token
GAME_FLOW_PASS_PROMPT = """You are given the full Game Flow for a single game as a sequence of blocks.

Each block is already correct and final in structure, timing, and scoring.
Your job is to lightly rewrite the narrative text so the blocks flow naturally
as a single game recap, while keeping each block as its own paragraph.

Rules:
- Preserve block order and boundaries
- Do not add or remove events
- Do not change scores, players, or periods
- Each block should be 2-4 sentences in one paragraph
- Improve flow, reduce repetition, and acknowledge the passage of time across blocks
- No hype, no speculation, no raw play-by-play

If a block already flows well, make minimal changes.

Return JSON: {"blocks": [{"i": block_index, "n": "revised narrative"}]}"""


def _build_game_flow_pass_prompt(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
) -> str:
    """Build prompt for game-level flow pass.

    This is a single call that receives all blocks and smooths transitions
    while preserving facts, scores, and structure.

    Args:
        blocks: List of block dicts with narratives already generated
        game_context: Team names and context

    Returns:
        Prompt string for the flow pass
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")

    prompt_parts = [
        GAME_FLOW_PASS_PROMPT,
        "",
        f"Game: {away_team} at {home_team}",
        "",
        "BLOCKS:",
    ]

    for block in blocks:
        block_idx = block["block_index"]
        role = block.get("role", "")
        period_start = block.get("period_start", 1)
        period_end = block.get("period_end", period_start)
        score_before = block.get("score_before", [0, 0])
        score_after = block.get("score_after", [0, 0])
        narrative = block.get("narrative", "")

        # Period label
        if period_start == period_end:
            period_label = f"Q{period_start}" if period_start <= 4 else f"OT{period_start - 4}"
        else:
            period_label = f"Q{period_start}-Q{period_end}"

        prompt_parts.append(f"\nBlock {block_idx} ({role}, {period_label}):")
        prompt_parts.append(
            f"Score: {away_team} {score_before[1]}-{score_before[0]} {home_team} "
            f"-> {away_team} {score_after[1]}-{score_after[0]} {home_team}"
        )
        prompt_parts.append(f"Current narrative: {narrative}")

    return "\n".join(prompt_parts)


async def _apply_game_level_flow_pass(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    openai_client: Any,
    output: StageOutput,
) -> list[dict[str, Any]]:
    """Apply game-level flow pass to smooth transitions across blocks.

    This is a single OpenAI call that sees all blocks and rewrites narratives
    so they flow naturally as one coherent recap while preserving all facts.

    Args:
        blocks: List of block dicts with initial narratives
        game_context: Team names and context
        openai_client: OpenAI client instance
        output: StageOutput for logging

    Returns:
        Blocks with smoothed narratives (or original if pass fails)
    """
    if len(blocks) < 2:
        output.add_log("Skipping flow pass: fewer than 2 blocks")
        return blocks

    output.add_log(f"Applying game-level flow pass to {len(blocks)} blocks")

    prompt = _build_game_flow_pass_prompt(blocks, game_context)

    try:
        # Low temperature for consistency, ~100 tokens per block
        max_tokens = 100 * len(blocks)

        response_json = await asyncio.to_thread(
            openai_client.generate,
            prompt=prompt,
            temperature=0.2,  # Low for consistency
            max_tokens=max_tokens,
        )
        response_data = json.loads(response_json)

    except json.JSONDecodeError as e:
        output.add_log(f"Flow pass returned invalid JSON, using originals: {e}", level="warning")
        return blocks

    except Exception as e:
        output.add_log(f"Flow pass failed, using originals: {e}", level="warning")
        return blocks

    # Extract revised narratives
    block_items = response_data.get("blocks", [])
    if not block_items and isinstance(response_data, list):
        block_items = response_data

    # Safety check: output count must match input count
    if len(block_items) != len(blocks):
        output.add_log(
            f"Flow pass output count mismatch ({len(block_items)} vs {len(blocks)}), using originals",
            level="warning",
        )
        return blocks

    # Build lookup by block index
    narrative_lookup: dict[int, str] = {}
    for item in block_items:
        idx = item.get("i") if item.get("i") is not None else item.get("block_index")
        narrative = item.get("n") or item.get("narrative", "")
        if idx is not None and narrative:
            narrative_lookup[idx] = narrative

    # Apply revised narratives
    revised_count = 0
    for block in blocks:
        block_idx = block["block_index"]
        if block_idx in narrative_lookup:
            new_narrative = narrative_lookup[block_idx].strip()
            if new_narrative and new_narrative != block.get("narrative", ""):
                block["narrative"] = new_narrative
                revised_count += 1

    output.add_log(f"Flow pass revised {revised_count}/{len(blocks)} block narratives")
    return blocks


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
        "Generate broadcast-quality narrative blocks for a game recap.",
        "",
        f"Teams: {away_team} (away) vs {home_team} (home)",
        "",
        "NARRATIVE STRUCTURE:",
        "- Write 2-4 sentences per block (~50-80 words)",
        "- Each block describes a STRETCH of play, not isolated events",
        "- Connect plays with cause-and-effect",
        "- Vary sentence openings",
        "- Focus on the key plays provided - EVERY key play must be referenced",
        "",
        "CONNECTING PHRASES TO USE:",
        "- 'building on that', 'in response', 'shortly after'",
        "- 'over the next several possessions', 'as the quarter progressed'",
        "- 'trading baskets', 'the teams exchanged leads'",
        "",
        "ROLE-SPECIFIC GUIDANCE:",
        "- SETUP: Opening tone, early pace, how the game began",
        "- MOMENTUM_SHIFT: What triggered the change, how it unfolded over several plays",
        "- RESPONSE: How the trailing team fought back, the adjustment they made",
        "- DECISION_POINT: The pivotal stretch that determined the outcome",
        "- RESOLUTION: How the game concluded, the final sequence",
        "",
        "PLAYER NAMES (CRITICAL):",
        "- Use FULL NAME on first mention (e.g., 'Donovan Mitchell', 'Brandon Miller')",
        "- NEVER use initials like 'D. Mitchell' or 'B. Miller' - always spell out first names",
        "- After first mention, use LAST NAME only (e.g., 'Mitchell', 'Miller')",
        "- Common names are fine abbreviated after first mention (Williams, Smith, Jones)",
        "",
        "TEAM ATTRIBUTION (CRITICAL):",
        "- On FIRST mention of each player, tie them to their team naturally:",
        f"  * \"{home_team}'s [Player Name]\" or \"{away_team}'s [Player Name]\" (possessive)",
        f"  * \"[Player Name] for {home_team}\" or \"[Player Name] for {away_team}\" (scoring context)",
        "- After first mention, just use last name without team",
        "- Do NOT use parenthetical abbreviations like '(CHA)' or '(NOP)'",
        "",
        "STYLE REQUIREMENTS:",
        "- Use broadcast tone, not stat-feed prose",
        "- NO stat-listing patterns like 'X had Y points' or 'X finished with Y'",
        "- NO subjective adjectives (incredible, amazing, unbelievable, insane)",
        "- Describe ACTIONS, not statistics",
        "- Keep individual sentences concise (under 30 words each)",
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

    # Task 1.4: Check style constraints
    style_errors, style_warnings = _validate_style_constraints(narrative, block_idx)
    errors.extend(style_errors)
    warnings.extend(style_warnings)

    return errors, warnings


async def execute_render_blocks(stage_input: StageInput) -> StageOutput:
    """Execute the RENDER_BLOCKS stage.

    Generates narrative text for each block using OpenAI.
    Each block gets 2-4 sentences (~65 words).

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

    # Task 1.5: Get blowout metrics from previous stage
    is_blowout = previous_output.get("is_blowout", False)
    garbage_time_start_idx = previous_output.get("garbage_time_start_idx")

    if is_blowout:
        output.add_log("Processing blowout game with compressed narratives")

    # Build prompt and call OpenAI
    prompt = _build_block_prompt(blocks, game_context, pbp_events)

    try:
        # Estimate tokens: ~200 per block for 2-4 sentences
        max_tokens = 200 * len(blocks)

        response_json = await asyncio.to_thread(
            openai_client.generate,
            prompt=prompt,
            temperature=0.5,  # Higher for more natural prose variation
            max_tokens=max_tokens,
        )
        response_data = json.loads(response_json)

    except json.JSONDecodeError as e:
        # Fail fast - no fallback narratives
        raise ValueError(f"OpenAI returned invalid JSON: {e}") from e

    except Exception as e:
        # Fail fast - no fallback narratives
        raise ValueError(f"OpenAI call failed: {e}") from e

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
    total_words = 0
    play_injections = 0

    for block in blocks:
        block_idx = block["block_index"]
        narrative = narrative_lookup.get(block_idx, "")

        if not narrative or not narrative.strip():
            # Fail fast - no fallback narratives
            raise ValueError(f"Block {block_idx}: No narrative from AI")

        # Clean up any raw PBP artifacts from the narrative
        narrative = _cleanup_pbp_artifacts(narrative)

        # Validate
        errors, warnings = _validate_block_narrative(narrative, block_idx)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

        # If hard errors, fail fast
        if errors:
            raise ValueError(f"Block {block_idx} validation failed: {errors}")

        # Task 1.3: Check play coverage - ensure key plays are mentioned
        key_play_ids = block.get("key_play_ids", [])
        if key_play_ids:
            missing_ids, missing_events = _check_play_coverage(
                narrative, key_play_ids, pbp_events
            )

            if missing_events:
                output.add_log(
                    f"Block {block_idx}: {len(missing_events)} key plays not referenced, injecting sentences",
                    level="warning",
                )

                # Recovery strategy: inject deterministic sentences for missing plays
                for event in missing_events:
                    injection = _generate_play_injection_sentence(event, game_context)
                    if injection:
                        narrative = narrative.rstrip()
                        if not narrative.endswith("."):
                            narrative += "."
                        narrative = f"{narrative} {injection}"
                        play_injections += 1

                all_warnings.append(
                    f"Block {block_idx}: Injected {len(missing_events)} play references"
                )

        block["narrative"] = narrative
        total_words += len(narrative.split())

    output.add_log(f"Total word count: {total_words}")
    if play_injections > 0:
        output.add_log(f"Play injection sentences added: {play_injections}")

    if all_warnings:
        output.add_log(f"Warnings: {len(all_warnings)}", level="warning")
        for w in all_warnings[:5]:
            output.add_log(f"  {w}", level="warning")

    # Game-level flow pass: smooth transitions across all blocks
    # This is a second OpenAI call that sees all blocks at once
    blocks = await _apply_game_level_flow_pass(
        blocks, game_context, openai_client, output
    )

    # Recalculate total words after flow pass
    total_words = sum(len(b.get("narrative", "").split()) for b in blocks)
    output.add_log(f"Final word count after flow pass: {total_words}")

    output.add_log("RENDER_BLOCKS completed successfully")

    output.data = {
        "blocks_rendered": True,
        "blocks": blocks,
        "block_count": len(blocks),
        "total_words": total_words,
        "openai_calls": 2,  # Initial render + flow pass
        "play_injections": play_injections,
        "errors": all_errors,
        "warnings": all_warnings,
        # Pass through
        "moments": previous_output.get("moments", []),
        "pbp_events": pbp_events,
        "validated": True,
        "blocks_grouped": True,
    }

    return output
