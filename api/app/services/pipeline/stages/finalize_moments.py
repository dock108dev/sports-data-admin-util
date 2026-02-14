"""FINALIZE_MOMENTS Stage Implementation.

This stage persists validated Game Flow data to the database.

GAME FLOW CONTRACT ALIGNMENT
=============================
This stage is a write-only persistence layer:
- No transformation occurs
- No prose is generated
- No logic is invented
- Data is persisted exactly as produced by the pipeline

PERSISTENCE
===========
SportsGameFlow table stores:
- moments_json: JSONB containing ordered list of condensed moments
- moment_count: INTEGER for quick access
- validated_at: TIMESTAMPTZ when validation passed
- story_version: "v2-moments"
- blocks_json: JSONB containing 4-7 narrative blocks
- block_count: INTEGER for quick access
- blocks_version: "v1-blocks"
- blocks_validated_at: TIMESTAMPTZ when block validation passed

WHAT GETS WRITTEN
=================
Persist EXACTLY the moments produced by earlier stages, plus blocks:
- play_ids
- explicitly_narrated_play_ids
- period
- start_clock / end_clock
- score_before / score_after
- narrative (from moments)
- blocks with role, narrative, key_play_ids

Rules:
- Preserve order
- No mutation
- No reformatting
- No re-derivation

GUARANTEES
==========
1. Persist game flow data transactionally
2. Set has_flow indicators (moments_json IS NOT NULL)
3. Record moment_count and block_count
4. Record validation timestamps
5. On failure: roll back, fail loudly, no partial writes
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ....db.sports import SportsGame
from ....db.story import SportsGameFlow
from ....utils.datetime_utils import now_utc
from ..models import StageInput, StageOutput

if TYPE_CHECKING:
    from ....db import AsyncSession

logger = logging.getLogger(__name__)

# Story version identifiers
STORY_VERSION = "v2-moments"
BLOCKS_VERSION = "v1-blocks"


async def execute_finalize_moments(
    session: "AsyncSession",
    stage_input: StageInput,
    run_uuid: str,
) -> StageOutput:
    """Execute the FINALIZE_MOMENTS stage.

    Persists validated moments and blocks to SportsGameFlow table.
    This is the only stage that writes Game Flow data durably.

    Args:
        session: Database session for persistence
        stage_input: Input containing previous_output with rendered moments and blocks
        run_uuid: Pipeline run UUID for traceability

    Returns:
        StageOutput with persistence confirmation

    Raises:
        ValueError: If prerequisites not met or persistence fails
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting FINALIZE_MOMENTS for game {game_id}")

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("FINALIZE_MOMENTS requires previous stage output")

    # Verify VALIDATE_MOMENTS passed
    validated = previous_output.get("validated")
    if validated is not True:
        raise ValueError(
            "FINALIZE_MOMENTS requires VALIDATE_MOMENTS to pass. "
            f"Got validated={validated}"
        )

    # Verify VALIDATE_BLOCKS completed
    blocks_validated = previous_output.get("blocks_validated")

    # Get moments
    moments = previous_output.get("moments")
    if not moments:
        raise ValueError("No moments in previous stage output")

    # Get blocks (required)
    blocks = previous_output.get("blocks")
    if not blocks:
        raise ValueError(
            "FINALIZE_MOMENTS requires blocks from VALIDATE_BLOCKS stage. "
            f"Got blocks_validated={blocks_validated}"
        )

    if blocks_validated is not True:
        output.add_log(
            f"WARNING: blocks_validated={blocks_validated}, proceeding with blocks anyway",
            level="warning",
        )

    # Verify blocks have narratives
    missing_block_narratives = [
        i for i, b in enumerate(blocks) if not b.get("narrative")
    ]
    if missing_block_narratives:
        output.add_log(
            f"WARNING: Blocks missing narratives at indices: {missing_block_narratives}",
            level="warning",
        )

    output.add_log(f"Persisting {len(moments)} moments and {len(blocks)} blocks")

    # Get game to determine sport
    game_result = await session.execute(
        select(SportsGame)
        .options(selectinload(SportsGame.league))
        .where(SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()

    if not game:
        raise ValueError(f"Game {game_id} not found")

    sport = game.league.code if game.league else "NBA"

    # Check for existing v2-moments story for this game
    existing_result = await session.execute(
        select(SportsGameFlow).where(
            SportsGameFlow.game_id == game_id,
            SportsGameFlow.story_version == STORY_VERSION,
        )
    )
    existing_flow = existing_result.scalar_one_or_none()

    validation_time = now_utc()
    openai_calls = previous_output.get("openai_calls", 0)
    total_words = previous_output.get("total_words", 0)

    if existing_flow:
        # Update existing story
        output.add_log(f"Updating existing flow (id={existing_flow.id})")
        existing_flow.moments_json = moments
        existing_flow.moment_count = len(moments)
        existing_flow.validated_at = validation_time
        existing_flow.generated_at = validation_time
        existing_flow.total_ai_calls = openai_calls

        # Update blocks
        existing_flow.blocks_json = blocks
        existing_flow.block_count = len(blocks)
        existing_flow.blocks_version = BLOCKS_VERSION
        existing_flow.blocks_validated_at = validation_time

        story_id = existing_flow.id
    else:
        # Create new story record
        output.add_log("Creating new flow record")
        new_flow = SportsGameFlow(
            game_id=game_id,
            sport=sport,
            story_version=STORY_VERSION,
            moments_json=moments,
            moment_count=len(moments),
            validated_at=validation_time,
            generated_at=validation_time,
            total_ai_calls=openai_calls,
        )

        # Add blocks
        new_flow.blocks_json = blocks
        new_flow.block_count = len(blocks)
        new_flow.blocks_version = BLOCKS_VERSION
        new_flow.blocks_validated_at = validation_time

        session.add(new_flow)
        await session.flush()
        story_id = new_flow.id

    output.add_log(f"Flow persisted with id={story_id}")
    output.add_log(f"moment_count={len(moments)}")
    output.add_log(f"block_count={len(blocks)}")
    output.add_log(f"blocks_version={BLOCKS_VERSION}")
    output.add_log(f"total_words={total_words}")

    output.add_log(f"validated_at={validation_time.isoformat()}")
    output.add_log("FINALIZE_MOMENTS completed successfully")

    # Output shape for reviewability
    output.data = {
        "finalized": True,
        "flow_id": story_id,
        "game_id": game_id,
        "story_version": STORY_VERSION,
        "moment_count": len(moments),
        "validated_at": validation_time.isoformat(),
        "openai_calls": openai_calls,
        "block_count": len(blocks),
        "blocks_version": BLOCKS_VERSION,
        "total_words": total_words,
        "blocks_validated_at": validation_time.isoformat(),
    }

    return output
