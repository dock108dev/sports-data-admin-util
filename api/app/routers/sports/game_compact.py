"""Compact game moment endpoints for admin UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession, get_db
from ...services.moment_summaries import summarize_moment
from .common import (
    build_compact_hint,
    build_score_chips,
    dedupe_social_posts,
    find_compact_moment_bounds,
    get_compact_cache,
    post_contains_score,
    serialize_play_entry,
    store_compact_cache,
)
from .schemas import (
    CompactMoment,
    CompactMomentSummaryResponse,
    CompactMomentsResponse,
    CompactPbpResponse,
    CompactPostEntry,
    CompactPostsResponse,
)

router = APIRouter()


@router.get("/games/{game_id}/compact", response_model=CompactMomentsResponse)
async def get_game_compact(game_id: int, session: AsyncSession = Depends(get_db)) -> CompactMomentsResponse:
    cached = get_compact_cache(game_id)
    if cached:
        return cached

    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = plays_result.scalars().all()

    moments: list[CompactMoment] = []
    moment_types: list[str] = []

    for play in plays:
        moment_type = play.play_type or "unknown"
        if moment_type not in moment_types:
            moment_types.append(moment_type)
        moments.append(
            CompactMoment(
                playIndex=play.play_index,
                quarter=play.quarter,
                gameClock=play.game_clock,
                momentType=moment_type,
                hint=build_compact_hint(play, moment_type),
            )
        )

    score_chips = build_score_chips(plays)
    response = CompactMomentsResponse(moments=moments, momentTypes=moment_types, scoreChips=score_chips)
    store_compact_cache(game_id, response)
    return response


@router.get("/games/{game_id}/compact/{moment_id}/pbp", response_model=CompactPbpResponse)
async def get_game_compact_pbp(
    game_id: int,
    moment_id: int,
    session: AsyncSession = Depends(get_db),
) -> CompactPbpResponse:
    compact_response = get_compact_cache(game_id)
    if compact_response is None:
        compact_response = await get_game_compact(game_id, session)

    try:
        start_index, end_index = find_compact_moment_bounds(compact_response.moments, moment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if end_index is None:
        max_index_stmt = select(func.max(db_models.SportsGamePlay.play_index)).where(
            db_models.SportsGamePlay.game_id == game_id
        )
        end_index = (await session.execute(max_index_stmt)).scalar_one_or_none()

    if end_index is None or end_index < start_index:
        return CompactPbpResponse(plays=[])

    plays_stmt = (
        select(db_models.SportsGamePlay)
        .where(
            db_models.SportsGamePlay.game_id == game_id,
            db_models.SportsGamePlay.play_index >= start_index,
            db_models.SportsGamePlay.play_index <= end_index,
        )
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays_result = await session.execute(plays_stmt)
    plays = plays_result.scalars().all()
    plays_entries = [serialize_play_entry(play) for play in plays]
    return CompactPbpResponse(plays=plays_entries)


@router.get("/games/{game_id}/compact/{moment_id}/posts", response_model=CompactPostsResponse)
async def get_game_compact_posts(
    game_id: int,
    moment_id: int,
    session: AsyncSession = Depends(get_db),
) -> CompactPostsResponse:
    compact_response = get_compact_cache(game_id)
    if compact_response is None:
        compact_response = await get_game_compact(game_id, session)

    try:
        find_compact_moment_bounds(compact_response.moments, moment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    posts_stmt = (
        select(db_models.GameSocialPost)
        .options(selectinload(db_models.GameSocialPost.team))
        .where(
            db_models.GameSocialPost.game_id == game_id,
        )
        .order_by(db_models.GameSocialPost.posted_at)
    )
    posts_result = await session.execute(posts_stmt)
    posts = posts_result.scalars().all()
    deduped_posts = dedupe_social_posts(posts)

    entries: list[CompactPostEntry] = []
    for post in deduped_posts:
        team_abbr = post.team.abbreviation if post.team and post.team.abbreviation else "UNK"
        entries.append(
            CompactPostEntry(
                id=post.id,
                post_url=post.post_url,
                posted_at=post.posted_at,
                has_video=post.has_video,
                team_abbreviation=team_abbr,
                tweet_text=post.tweet_text,
                video_url=post.video_url,
                image_url=post.image_url,
                source_handle=post.source_handle,
                media_type=post.media_type,
                containsScore=post_contains_score(post.tweet_text),
            )
        )

    return CompactPostsResponse(posts=entries)


@router.get("/games/{game_id}/compact/{moment_id}/summary", response_model=CompactMomentSummaryResponse)
async def get_game_compact_summary(
    game_id: int,
    moment_id: int,
    session: AsyncSession = Depends(get_db),
) -> CompactMomentSummaryResponse:
    try:
        summary = await summarize_moment(game_id, moment_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CompactMomentSummaryResponse(summary=summary)
