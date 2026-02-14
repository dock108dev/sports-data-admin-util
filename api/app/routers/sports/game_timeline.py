"""Timeline and game flow endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...db import AsyncSession, get_db
from ...db.sports import SportsGame, SportsGamePlay
from ...db.flow import SportsGameFlow, SportsGameTimelineArtifact
from ...services.team_colors import get_matchup_colors
from ...services.timeline_generator import (
    TimelineGenerationError,
    generate_timeline_artifact,
)
from ...services.timeline_types import DEFAULT_TIMELINE_VERSION
from .schemas import (
    GameFlowBlock,
    GameFlowContent,
    GameFlowMoment,
    GameFlowPlay,
    GameFlowResponse,
    TimelineArtifactResponse,
)

router = APIRouter()

# Flow version identifier (DB filter value — "v2-moments")
FLOW_VERSION = "v2-moments"


@router.get("/games/{game_id}/timeline", response_model=TimelineArtifactResponse)
async def get_game_timeline(
    game_id: int,
    timeline_version: str = Query(DEFAULT_TIMELINE_VERSION),
    session: AsyncSession = Depends(get_db),
) -> TimelineArtifactResponse:
    """Retrieve a persisted timeline artifact for a game.

    Returns the timeline exactly as persisted. Use the POST generate
    endpoint to create or regenerate a timeline.
    """
    result = await session.execute(
        select(SportsGameTimelineArtifact).where(
            SportsGameTimelineArtifact.game_id == game_id,
            SportsGameTimelineArtifact.timeline_version == timeline_version,
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No timeline artifact found for game {game_id} (version={timeline_version})",
        )

    return TimelineArtifactResponse(
        game_id=artifact.game_id,
        sport=artifact.sport,
        timeline_version=artifact.timeline_version,
        generated_at=artifact.generated_at,
        timeline=artifact.timeline_json,
        summary=artifact.summary_json,
        game_analysis=artifact.game_analysis_json,
    )


@router.post(
    "/games/{game_id}/timeline/generate", response_model=TimelineArtifactResponse
)
async def generate_game_timeline(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> TimelineArtifactResponse:
    """Generate and store a finalized timeline artifact for any league.

    Social data is optional and gracefully degrades to empty for leagues
    without social scraping configured (NHL, NCAAB).
    """
    try:
        artifact = await generate_timeline_artifact(session, game_id)
    except TimelineGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    await session.commit()
    return TimelineArtifactResponse(
        game_id=artifact.game_id,
        sport=artifact.sport,
        timeline_version=artifact.timeline_version,
        generated_at=artifact.generated_at,
        timeline=artifact.timeline,
        summary=artifact.summary,
        game_analysis=artifact.game_analysis,
    )


@router.get("/games/{game_id}/flow", response_model=GameFlowResponse)
async def get_game_flow(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> GameFlowResponse:
    """Get the persisted Game Flow for a game.

    Returns the Game Flow exactly as persisted - no transformation, no aggregation.

    Game Flow Contract:
    - moments: Ordered list of condensed moments with narratives
    - plays: Only plays referenced by moments
    - validation_passed: Whether validation passed
    - validation_errors: Any validation errors (empty if passed)
    - blocks: 4-7 narrative blocks (Phase 1, consumer-facing output)
    - total_words: Total word count across all block narratives

    Returns:
        GameFlowResponse with moments, plays, blocks, and validation status

    Raises:
        HTTPException 404: If no Game Flow exists for this game
    """
    flow_result = await session.execute(
        select(SportsGameFlow).where(
            SportsGameFlow.game_id == game_id,
            SportsGameFlow.story_version == FLOW_VERSION,
            SportsGameFlow.moments_json.isnot(None),
        )
    )
    flow_record = flow_result.scalar_one_or_none()

    if not flow_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Game Flow found for game {game_id}",
        )

    # Load game with teams and league for color/metadata fields
    game_result = await session.execute(
        select(SportsGame).options(
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
            selectinload(SportsGame.league),
        ).where(SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()

    matchup_colors = get_matchup_colors(
        game.home_team.color_light_hex if game and game.home_team else None,
        game.home_team.color_dark_hex if game and game.home_team else None,
        game.away_team.color_light_hex if game and game.away_team else None,
        game.away_team.color_dark_hex if game and game.away_team else None,
    )

    # Get moments from persisted data (no transformation)
    moments_data = flow_record.moments_json or []

    # Collect all play_ids referenced by moments
    all_play_ids: set[int] = set()
    for moment in moments_data:
        all_play_ids.update(moment.get("play_ids", []))

    # Load plays by play_ids
    plays_result = await session.execute(
        select(SportsGamePlay).where(
            SportsGamePlay.game_id == game_id,
            SportsGamePlay.play_index.in_(all_play_ids),
        )
    )
    plays_records = plays_result.scalars().all()

    # Build play lookup for ordering
    play_lookup = {p.play_index: p for p in plays_records}

    # Build response moments (exact data, no transformation)
    response_moments = [
        GameFlowMoment(
            playIds=moment["play_ids"],
            explicitlyNarratedPlayIds=moment["explicitly_narrated_play_ids"],
            period=moment["period"],
            startClock=moment.get("start_clock"),
            endClock=moment.get("end_clock"),
            # Internal format is [home, away], API contract is [away, home]
            scoreBefore=[moment["score_before"][1], moment["score_before"][0]],
            scoreAfter=[moment["score_after"][1], moment["score_after"][0]],
            narrative=moment.get("narrative"),
            cumulativeBoxScore=moment.get("cumulative_box_score"),
        )
        for moment in moments_data
    ]

    # Build response plays (only those referenced by moments, ordered by play_index)
    # NOTE: playId uses play_index (not DB id) to match moment.playIds contract
    response_plays = [
        GameFlowPlay(
            playId=play.play_index,
            playIndex=play.play_index,
            period=play.quarter or 1,
            clock=play.game_clock,
            playType=play.play_type,
            description=play.description,
            homeScore=play.home_score,
            awayScore=play.away_score,
        )
        for play_index in sorted(all_play_ids)
        if (play := play_lookup.get(play_index))
    ]

    # Build response blocks if present (Phase 1)
    response_blocks: list[GameFlowBlock] | None = None
    total_words: int | None = None

    blocks_data = flow_record.blocks_json
    if blocks_data:
        response_blocks = [
            GameFlowBlock(
                blockIndex=block["block_index"],
                role=block["role"],
                momentIndices=block["moment_indices"],
                periodStart=block["period_start"],
                periodEnd=block["period_end"],
                # Internal format is [home, away], API contract is [away, home]
                scoreBefore=[block["score_before"][1], block["score_before"][0]],
                scoreAfter=[block["score_after"][1], block["score_after"][0]],
                playIds=block["play_ids"],
                keyPlayIds=block["key_play_ids"],
                narrative=block.get("narrative"),
                miniBox=block.get("mini_box"),
                embeddedSocialPostId=block.get("embedded_social_post_id"),
            )
            for block in blocks_data
        ]
        # Calculate total words from block narratives
        total_words = sum(
            len((block.get("narrative") or "").split())
            for block in blocks_data
        )

    # Validation status from persisted data
    validation_passed = flow_record.validated_at is not None

    return GameFlowResponse(
        gameId=game_id,
        flow=GameFlowContent(moments=response_moments),
        plays=response_plays,
        validationPassed=validation_passed,
        validationErrors=[],
        blocks=response_blocks,
        totalWords=total_words,
        homeTeam=game.home_team.name if game and game.home_team else None,
        awayTeam=game.away_team.name if game and game.away_team else None,
        homeTeamAbbr=game.home_team.abbreviation if game and game.home_team else None,
        awayTeamAbbr=game.away_team.abbreviation if game and game.away_team else None,
        homeTeamColorLight=matchup_colors["homeLightHex"],
        homeTeamColorDark=matchup_colors["homeDarkHex"],
        awayTeamColorLight=matchup_colors["awayLightHex"],
        awayTeamColorDark=matchup_colors["awayDarkHex"],
        leagueCode=game.league.code if game and game.league else None,
    )
