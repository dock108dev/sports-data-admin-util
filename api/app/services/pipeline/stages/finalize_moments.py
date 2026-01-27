"""FINALIZE_MOMENTS Stage Implementation.

This stage persists validated Story data to the database.

STORY CONTRACT ALIGNMENT
========================
This stage is a write-only persistence layer:
- No transformation occurs
- No prose is generated
- No logic is invented
- Data is persisted exactly as produced by the pipeline

PERSISTENCE
===========
SportsGameStory table stores:
- moments_json: JSONB containing ordered list of condensed moments
- moment_count: INTEGER for quick access
- validated_at: TIMESTAMPTZ when validation passed
- story_version: "v2-moments"

WHAT GETS WRITTEN
=================
Persist EXACTLY the moments produced by RENDER_NARRATIVES:
- play_ids
- explicitly_narrated_play_ids
- period
- start_clock / end_clock
- score_before / score_after
- narrative

Rules:
- Preserve order
- No mutation
- No reformatting
- No re-derivation

GUARANTEES
==========
1. Persist story data transactionally
2. Set has_story indicators (moments_json IS NOT NULL)
3. Record moment_count
4. Record validation timestamp
5. On failure: roll back, fail loudly, no partial writes
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .... import db_models
from ....utils.datetime_utils import now_utc
from ..models import StageInput, StageOutput

if TYPE_CHECKING:
    from ....db import AsyncSession

logger = logging.getLogger(__name__)

# Story version identifier for v2 moments format
STORY_VERSION_V2_MOMENTS = "v2-moments"


async def execute_finalize_moments(
    session: "AsyncSession",
    stage_input: StageInput,
    run_uuid: str,
) -> StageOutput:
    """Execute the FINALIZE_MOMENTS stage.

    Persists validated moments with narratives to SportsGameStory table.
    This is the only stage that writes Story data durably.

    Args:
        session: Database session for persistence
        stage_input: Input containing previous_output with rendered moments
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

    # Verify RENDER_NARRATIVES completed
    rendered = previous_output.get("rendered")
    if rendered is not True:
        raise ValueError(
            "FINALIZE_MOMENTS requires RENDER_NARRATIVES to complete. "
            f"Got rendered={rendered}"
        )

    # Get rendered moments
    moments = previous_output.get("moments")
    if not moments:
        raise ValueError("No moments in previous stage output")

    # Verify all moments have narratives
    missing_narratives = [
        i for i, m in enumerate(moments) if not m.get("narrative")
    ]
    if missing_narratives:
        raise ValueError(
            f"Moments missing narratives at indices: {missing_narratives}"
        )

    output.add_log(f"Persisting {len(moments)} moments with narratives")

    # Get game to determine sport
    game_result = await session.execute(
        select(db_models.SportsGame)
        .options(selectinload(db_models.SportsGame.league))
        .where(db_models.SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()

    if not game:
        raise ValueError(f"Game {game_id} not found")

    sport = game.league.code if game.league else "NBA"

    # Check for existing v2-moments story for this game
    existing_result = await session.execute(
        select(db_models.SportsGameStory).where(
            db_models.SportsGameStory.game_id == game_id,
            db_models.SportsGameStory.story_version == STORY_VERSION_V2_MOMENTS,
        )
    )
    existing_story = existing_result.scalar_one_or_none()

    validation_time = now_utc()
    openai_calls = previous_output.get("openai_calls", 0)

    if existing_story:
        # Update existing story
        output.add_log(f"Updating existing story (id={existing_story.id})")
        existing_story.moments_json = moments
        existing_story.moment_count = len(moments)
        existing_story.validated_at = validation_time
        existing_story.generated_at = validation_time
        existing_story.total_ai_calls = openai_calls
        story_id = existing_story.id
    else:
        # Create new story record
        output.add_log("Creating new story record")
        new_story = db_models.SportsGameStory(
            game_id=game_id,
            sport=sport,
            story_version=STORY_VERSION_V2_MOMENTS,
            moments_json=moments,
            moment_count=len(moments),
            validated_at=validation_time,
            generated_at=validation_time,
            total_ai_calls=openai_calls,
        )
        session.add(new_story)
        await session.flush()
        story_id = new_story.id

    output.add_log(f"Story persisted with id={story_id}")
    output.add_log(f"moment_count={len(moments)}")
    output.add_log(f"validated_at={validation_time.isoformat()}")
    output.add_log("FINALIZE_MOMENTS completed successfully")

    # Output shape for reviewability
    output.data = {
        "finalized": True,
        "story_id": story_id,
        "game_id": game_id,
        "story_version": STORY_VERSION_V2_MOMENTS,
        "moment_count": len(moments),
        "validated_at": validation_time.isoformat(),
        "openai_calls": openai_calls,
    }

    return output
