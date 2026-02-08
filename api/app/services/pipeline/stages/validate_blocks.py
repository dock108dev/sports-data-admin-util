"""VALIDATE_BLOCKS Stage Implementation.

This stage validates the rendered blocks to ensure they meet all constraints.

VALIDATION RULES
================
1. Block count in range [4, 7]
2. No role appears more than twice
3. Each narrative >= 30 words (meaningful content, 2+ sentences)
4. Each narrative <= 100 words (up to 4 sentences)
5. First block role = SETUP
6. Last block role = RESOLUTION
7. Score continuity across block boundaries
8. Total word count <= 500 (~90-second read target)
9. Each narrative has 2-4 sentences

GUARANTEES
==========
- All constraints validated before returning success
- Detailed error messages for each violation
- Warnings for soft limit violations
"""

from __future__ import annotations

import logging
import re
from datetime import timezone
from typing import Any

from sqlalchemy import select

from ....db import AsyncSession
from ....db.sports import SportsGame
from ....db.social import TeamSocialPost
from ..models import StageInput, StageOutput
from .block_types import (
    SemanticRole,
    MIN_BLOCKS,
    MAX_BLOCKS,
    MIN_WORDS_PER_BLOCK,
    MAX_WORDS_PER_BLOCK,
    MAX_TOTAL_WORDS,
)
from .embedded_tweets import select_and_assign_embedded_tweets

logger = logging.getLogger(__name__)

# Sentence count constraints
MIN_SENTENCES_PER_BLOCK = 2
MAX_SENTENCES_PER_BLOCK = 4

# Common abbreviations that contain periods but don't end sentences
# Used to avoid false sentence breaks in _count_sentences
COMMON_ABBREVIATIONS = [
    "Mr.", "Mrs.", "Ms.", "Dr.", "Jr.", "Sr.", "vs.", "etc.", "e.g.", "i.e.",
    "St.", "Ave.", "Blvd.", "Rd.", "Mt.", "Ft.",  # Addresses
    "Jan.", "Feb.", "Mar.", "Apr.", "Aug.", "Sept.", "Oct.", "Nov.", "Dec.",
]


def _count_sentences(text: str) -> int:
    """Count the number of sentences in text.

    Uses sentence-ending punctuation (. ! ?) to split, with handling for
    common abbreviations to avoid false positives.

    Known limitations:
    - May not handle all abbreviations (only common ones are protected)
    - Single-letter initials like "J. Smith" may cause false splits
    - Decimal numbers like "3.5" are not specially handled

    Since this is used for soft validation warnings (not hard failures),
    approximate counts are acceptable.
    """
    if not text:
        return 0

    # Protect common abbreviations by temporarily replacing their periods
    # Use a marker that won't be split by [.!?]
    protected = text
    for abbrev in COMMON_ABBREVIATIONS:
        # Case-insensitive replacement
        pattern = re.escape(abbrev)
        protected = re.sub(pattern, abbrev.replace(".", "\x00"), protected, flags=re.IGNORECASE)

    # Collapse ellipsis to single marker (not a sentence break)
    protected = re.sub(r"\.{2,}", "\x00", protected)

    # Split on sentence-ending punctuation
    sentences = re.split(r"[.!?]+", protected)

    # Count non-empty segments
    return len([s for s in sentences if s.strip()])


def _validate_block_count(blocks: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Validate block count is in range [4, 7]."""
    errors: list[str] = []
    warnings: list[str] = []

    count = len(blocks)

    if count < MIN_BLOCKS:
        errors.append(f"Too few blocks: {count} (minimum: {MIN_BLOCKS})")
    elif count > MAX_BLOCKS:
        errors.append(f"Too many blocks: {count} (maximum: {MAX_BLOCKS})")

    return errors, warnings


def _validate_role_constraints(blocks: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Validate role constraints.

    - No role appears more than twice
    - First block is SETUP
    - Last block is RESOLUTION
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not blocks:
        return errors, warnings

    # Check first block is SETUP
    first_role = blocks[0].get("role")
    if first_role != SemanticRole.SETUP.value:
        errors.append(f"First block must be SETUP, got: {first_role}")

    # Check last block is RESOLUTION
    last_role = blocks[-1].get("role")
    if last_role != SemanticRole.RESOLUTION.value:
        errors.append(f"Last block must be RESOLUTION, got: {last_role}")

    # Count role occurrences
    role_counts: dict[str, int] = {}
    for block in blocks:
        role = block.get("role", "")
        role_counts[role] = role_counts.get(role, 0) + 1

    # Check no role appears more than twice
    for role, count in role_counts.items():
        if count > 2:
            errors.append(f"Role {role} appears {count} times (maximum: 2)")

    return errors, warnings


def _validate_word_counts(blocks: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Validate word counts and sentence counts for each block and total."""
    errors: list[str] = []
    warnings: list[str] = []

    total_words = 0

    for block in blocks:
        block_idx = block.get("block_index", "?")
        narrative = block.get("narrative", "")

        if not narrative:
            errors.append(f"Block {block_idx}: Missing narrative")
            continue

        word_count = len(narrative.split())
        total_words += word_count

        if word_count < MIN_WORDS_PER_BLOCK:
            warnings.append(
                f"Block {block_idx}: Too short ({word_count} words, min: {MIN_WORDS_PER_BLOCK})"
            )

        if word_count > MAX_WORDS_PER_BLOCK:
            warnings.append(
                f"Block {block_idx}: Too long ({word_count} words, max: {MAX_WORDS_PER_BLOCK})"
            )

        # Validate sentence count
        sentence_count = _count_sentences(narrative)
        if sentence_count < MIN_SENTENCES_PER_BLOCK:
            warnings.append(
                f"Block {block_idx}: Too few sentences ({sentence_count}, min: {MIN_SENTENCES_PER_BLOCK})"
            )

        if sentence_count > MAX_SENTENCES_PER_BLOCK:
            warnings.append(
                f"Block {block_idx}: Too many sentences ({sentence_count}, max: {MAX_SENTENCES_PER_BLOCK})"
            )

    if total_words > MAX_TOTAL_WORDS:
        warnings.append(
            f"Total word count too high: {total_words} (target max: {MAX_TOTAL_WORDS})"
        )

    return errors, warnings


def _validate_score_continuity(blocks: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Validate score continuity across block boundaries.

    Each block's score_after should equal the next block's score_before.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for i in range(len(blocks) - 1):
        current_block = blocks[i]
        next_block = blocks[i + 1]

        current_after = current_block.get("score_after", [0, 0])
        next_before = next_block.get("score_before", [0, 0])

        if list(current_after) != list(next_before):
            errors.append(
                f"Score discontinuity between blocks {i} and {i + 1}: "
                f"{current_after} -> {next_before}"
            )

    return errors, warnings


def _validate_moment_coverage(
    blocks: list[dict[str, Any]],
    total_moments: int,
) -> tuple[list[str], list[str]]:
    """Validate that all moments are covered by blocks."""
    errors: list[str] = []
    warnings: list[str] = []

    covered_moments: set[int] = set()
    for block in blocks:
        moment_indices = block.get("moment_indices", [])
        for idx in moment_indices:
            if idx in covered_moments:
                errors.append(f"Moment {idx} is in multiple blocks")
            covered_moments.add(idx)

    expected_moments = set(range(total_moments))
    missing = expected_moments - covered_moments
    extra = covered_moments - expected_moments

    if missing:
        errors.append(f"Moments not covered by any block: {sorted(missing)}")

    if extra:
        warnings.append(f"Blocks reference non-existent moments: {sorted(extra)}")

    return errors, warnings


def _validate_key_plays(blocks: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Validate that each block has key plays and they are valid."""
    errors: list[str] = []
    warnings: list[str] = []

    for block in blocks:
        block_idx = block.get("block_index", "?")
        key_play_ids = block.get("key_play_ids", [])
        play_ids = block.get("play_ids", [])

        if not key_play_ids:
            warnings.append(f"Block {block_idx}: No key plays selected")
            continue

        if len(key_play_ids) > 3:
            warnings.append(
                f"Block {block_idx}: Too many key plays ({len(key_play_ids)}, max: 3)"
            )

        # Verify key plays are subset of play_ids
        play_id_set = set(play_ids)
        for key_id in key_play_ids:
            if key_id not in play_id_set:
                errors.append(
                    f"Block {block_idx}: Key play {key_id} not in block's play_ids"
                )

    return errors, warnings


async def _attach_embedded_tweets(
    session: AsyncSession,
    game_id: int,
    blocks: list[dict[str, Any]],
    output: StageOutput,
) -> tuple[list[dict[str, Any]], Any]:
    """Load social posts and attach embedded tweets to blocks.

    This is called after validation passes to enhance blocks with social content.
    Embedded tweets are optional and do not affect story structure.

    Args:
        session: Database session
        game_id: Game ID to load social posts for
        blocks: Validated blocks to attach tweets to
        output: StageOutput to add logs to

    Returns:
        Tuple of (updated blocks, EmbeddedTweetSelection or None)
    """
    # Load game to get tip_time for position classification
    game_result = await session.execute(
        select(SportsGame).where(SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()

    if not game:
        output.add_log(f"Game {game_id} not found, skipping embedded tweets")
        return blocks, None

    # Get game start time (tip_time or game_date as fallback)
    game_start = game.tip_time or game.game_date
    if game_start and game_start.tzinfo is None:
        game_start = game_start.replace(tzinfo=timezone.utc)

    # Load social posts for this game
    social_result = await session.execute(
        select(TeamSocialPost)
        .where(
            TeamSocialPost.game_id == game_id,
            TeamSocialPost.mapping_status == "mapped",
        )
        .order_by(TeamSocialPost.posted_at)
    )
    social_posts = social_result.scalars().all()

    if not social_posts:
        output.add_log("No social posts found for game, skipping embedded tweets")
        return blocks, None

    output.add_log(f"Found {len(social_posts)} social posts for embedded tweet selection")

    # Convert to dict format expected by embedded_tweets module
    tweets: list[dict[str, Any]] = []
    for post in social_posts:
        if not post.tweet_text:
            continue

        tweets.append({
            "id": post.id,
            "posted_at": post.posted_at,
            "text": post.tweet_text,
            "author": post.source_handle or "",
            "phase": post.game_phase or "in_game",
            "has_media": post.has_video or bool(post.image_url),
            "media_type": post.media_type,
            "post_url": post.post_url,
            # Team account detection based on having a source handle
            "is_team_account": bool(post.source_handle),
        })

    # Only in-game tweets belong in narrative blocks;
    # pregame/postgame are surfaced separately by consuming apps
    tweets = [t for t in tweets if t["phase"] == "in_game"]

    if not tweets:
        output.add_log("No tweets with text found, skipping embedded tweets")
        return blocks, None

    output.add_log(f"Processing {len(tweets)} tweet candidates for embedding")

    # Select and assign embedded tweets to blocks
    updated_blocks, selection = select_and_assign_embedded_tweets(
        tweets=tweets,
        blocks=blocks,
        game_start=game_start,
    )

    # Log selection results
    assigned_count = sum(1 for b in updated_blocks if b.get("embedded_tweet"))
    output.add_log(
        f"Embedded tweets: selected {len(selection.tweets)} from {selection.total_candidates} "
        f"candidates, assigned to {assigned_count} blocks"
    )

    return updated_blocks, selection


async def execute_validate_blocks(
    session: AsyncSession,
    stage_input: StageInput,
) -> StageOutput:
    """Execute the VALIDATE_BLOCKS stage.

    Validates all block constraints before finalization. After validation passes,
    loads social posts and attaches embedded tweets to blocks.

    Args:
        session: Async database session for loading social posts
        stage_input: Input containing previous_output with rendered blocks

    Returns:
        StageOutput with validation results and embedded tweets

    Raises:
        ValueError: If prerequisites not met
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting VALIDATE_BLOCKS for game {game_id}")

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("VALIDATE_BLOCKS requires previous stage output")

    # Verify RENDER_BLOCKS completed
    blocks_rendered = previous_output.get("blocks_rendered")
    if blocks_rendered is not True:
        raise ValueError(
            f"VALIDATE_BLOCKS requires RENDER_BLOCKS to complete. Got blocks_rendered={blocks_rendered}"
        )

    # Get blocks
    blocks = previous_output.get("blocks", [])
    if not blocks:
        raise ValueError("No blocks in previous stage output")

    total_moments = previous_output.get("total_moments", 0)
    if not total_moments:
        moments = previous_output.get("moments", [])
        total_moments = len(moments)

    output.add_log(f"Validating {len(blocks)} blocks covering {total_moments} moments")

    # Run all validations
    all_errors: list[str] = []
    all_warnings: list[str] = []

    # 1. Block count
    output.add_log("Checking Rule 1: Block count in range [4, 7]")
    errors, warnings = _validate_block_count(blocks)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    if errors:
        output.add_log(f"Rule 1 FAILED: {errors}", level="error")
    else:
        output.add_log("Rule 1 PASSED")

    # 2. Role constraints
    output.add_log("Checking Rule 2: Role constraints")
    errors, warnings = _validate_role_constraints(blocks)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    if errors:
        output.add_log(f"Rule 2 FAILED: {errors}", level="error")
    else:
        output.add_log("Rule 2 PASSED")

    # 3. Word counts
    output.add_log("Checking Rule 3: Word count limits")
    errors, warnings = _validate_word_counts(blocks)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    if errors:
        output.add_log(f"Rule 3 FAILED: {errors}", level="error")
    else:
        output.add_log("Rule 3 PASSED")

    # 4. Score continuity
    output.add_log("Checking Rule 4: Score continuity")
    errors, warnings = _validate_score_continuity(blocks)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    if errors:
        output.add_log(f"Rule 4 FAILED: {errors}", level="error")
    else:
        output.add_log("Rule 4 PASSED")

    # 5. Moment coverage
    output.add_log("Checking Rule 5: Moment coverage")
    errors, warnings = _validate_moment_coverage(blocks, total_moments)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    if errors:
        output.add_log(f"Rule 5 FAILED: {errors}", level="error")
    else:
        output.add_log("Rule 5 PASSED")

    # 6. Key plays
    output.add_log("Checking Rule 6: Key plays")
    errors, warnings = _validate_key_plays(blocks)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    if errors:
        output.add_log(f"Rule 6 FAILED: {errors}", level="error")
    else:
        output.add_log("Rule 6 PASSED")

    # Calculate total words
    total_words = sum(len(b.get("narrative", "").split()) for b in blocks)

    # Determine pass/fail
    # Errors are hard failures, warnings are acceptable
    passed = len(all_errors) == 0

    if passed:
        output.add_log(f"VALIDATE_BLOCKS PASSED with {len(all_warnings)} warnings")
    else:
        output.add_log(
            f"VALIDATE_BLOCKS FAILED with {len(all_errors)} errors, {len(all_warnings)} warnings",
            level="error",
        )

    output.add_log(f"Total word count: {total_words}")

    # After validation passes, attach embedded tweets (social enhancement)
    embedded_tweet_selection = None
    if passed:
        blocks, embedded_tweet_selection = await _attach_embedded_tweets(
            session, game_id, blocks, output
        )

    output.data = {
        "blocks_validated": passed,
        "blocks": blocks,
        "block_count": len(blocks),
        "total_words": total_words,
        "errors": all_errors,
        "warnings": all_warnings,
        # Embedded tweet metadata
        "embedded_tweet_selection": (
            embedded_tweet_selection.to_dict() if embedded_tweet_selection else None
        ),
        # Pass through
        "moments": previous_output.get("moments", []),
        "pbp_events": previous_output.get("pbp_events", []),
        "validated": previous_output.get("validated", True),
        "blocks_grouped": True,
        "blocks_rendered": True,
        # From earlier stages
        "rendered": previous_output.get("rendered"),
    }

    return output
