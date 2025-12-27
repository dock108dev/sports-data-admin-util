"""API endpoints for game social posts (X/Twitter embeds)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from .. import db_models
from ..db import AsyncSession, get_db

router = APIRouter(prefix="/api/social", tags=["social"])


# ────────────────────────────────────────────────────────────────────────────────
# Response Models
# ────────────────────────────────────────────────────────────────────────────────


class SocialPostResponse(BaseModel):
    """Single social post for timeline display."""

    id: int
    game_id: int
    team_id: str  # Team abbreviation for frontend
    post_url: str
    posted_at: datetime
    has_video: bool


class SocialPostListResponse(BaseModel):
    """List of social posts."""

    posts: list[SocialPostResponse]
    total: int


class SocialPostCreateRequest(BaseModel):
    """Request to create a new social post."""

    game_id: int = Field(..., alias="gameId")
    team_abbreviation: str = Field(..., alias="teamAbbreviation")
    post_url: str = Field(..., alias="postUrl")
    posted_at: datetime = Field(..., alias="postedAt")
    has_video: bool = Field(False, alias="hasVideo")


class SocialPostBulkCreateRequest(BaseModel):
    """Bulk create social posts."""

    posts: list[SocialPostCreateRequest]


# ────────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────────


def _serialize_post(post: db_models.GameSocialPost) -> SocialPostResponse:
    """Serialize a social post to API response."""
    return SocialPostResponse(
        id=post.id,
        game_id=post.game_id,
        team_id=post.team.abbreviation if post.team else "UNK",
        post_url=post.post_url,
        posted_at=post.posted_at,
        has_video=post.has_video,
    )


@router.get("/posts", response_model=SocialPostListResponse)
async def list_social_posts(
    game_id: int | None = Query(None, alias="game_id"),
    team_id: str | None = Query(None, alias="team_id"),
    start_date: datetime | None = Query(None, alias="start_date"),
    end_date: datetime | None = Query(None, alias="end_date"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> SocialPostListResponse:
    """
    List social posts with optional filters.
    
    - game_id: Filter by specific game
    - team_id: Filter by team abbreviation (e.g., "GSW", "LAL")
    - start_date/end_date: Filter by posted_at timestamp
    """
    stmt = select(db_models.GameSocialPost).options(
        selectinload(db_models.GameSocialPost.team)
    )

    if game_id is not None:
        stmt = stmt.where(db_models.GameSocialPost.game_id == game_id)

    if team_id is not None:
        # Join to team and filter by abbreviation
        stmt = stmt.where(
            db_models.GameSocialPost.team.has(
                db_models.SportsTeam.abbreviation.ilike(team_id)
            )
        )

    if start_date is not None:
        stmt = stmt.where(db_models.GameSocialPost.posted_at >= start_date)

    if end_date is not None:
        stmt = stmt.where(db_models.GameSocialPost.posted_at <= end_date)

    # Count total before pagination
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # Apply ordering and pagination
    stmt = stmt.order_by(db_models.GameSocialPost.posted_at.asc()).offset(offset).limit(limit)

    result = await session.execute(stmt)
    posts = result.scalars().all()

    return SocialPostListResponse(
        posts=[_serialize_post(post) for post in posts],
        total=total,
    )


@router.get("/posts/game/{game_id}", response_model=SocialPostListResponse)
async def get_posts_for_game(
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> SocialPostListResponse:
    """Get all social posts for a specific game, sorted by posted_at."""
    stmt = (
        select(db_models.GameSocialPost)
        .options(selectinload(db_models.GameSocialPost.team))
        .where(db_models.GameSocialPost.game_id == game_id)
        .order_by(db_models.GameSocialPost.posted_at.asc())
    )

    result = await session.execute(stmt)
    posts = result.scalars().all()

    return SocialPostListResponse(
        posts=[_serialize_post(post) for post in posts],
        total=len(posts),
    )


@router.post("/posts", response_model=SocialPostResponse, status_code=status.HTTP_201_CREATED)
async def create_social_post(
    payload: SocialPostCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> SocialPostResponse:
    """Create a new social post linked to a game."""
    # Verify game exists
    game = await session.get(db_models.SportsGame, payload.game_id)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {payload.game_id} not found",
        )

    # Find team by abbreviation
    team_stmt = select(db_models.SportsTeam).where(
        db_models.SportsTeam.abbreviation.ilike(payload.team_abbreviation)
    )
    result = await session.execute(team_stmt)
    team = result.scalar_one_or_none()
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with abbreviation '{payload.team_abbreviation}' not found",
        )

    # Check for duplicate URL
    existing_stmt = select(db_models.GameSocialPost).where(
        db_models.GameSocialPost.post_url == payload.post_url
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post URL already exists",
        )

    post = db_models.GameSocialPost(
        game_id=payload.game_id,
        team_id=team.id,
        post_url=payload.post_url,
        posted_at=payload.posted_at,
        has_video=payload.has_video,
    )
    session.add(post)
    await session.flush()
    await session.refresh(post, attribute_names=["team"])

    return _serialize_post(post)


@router.post("/posts/bulk", response_model=SocialPostListResponse, status_code=status.HTTP_201_CREATED)
async def bulk_create_social_posts(
    payload: SocialPostBulkCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> SocialPostListResponse:
    """Bulk create social posts. Skips duplicates by tweet_url."""
    created_posts: list[db_models.GameSocialPost] = []
    
    # Pre-fetch all teams by abbreviation
    abbrevs = list({p.team_abbreviation.upper() for p in payload.posts})
    team_stmt = select(db_models.SportsTeam).where(
        db_models.SportsTeam.abbreviation.in_(abbrevs)
    )
    team_result = await session.execute(team_stmt)
    teams_by_abbrev = {t.abbreviation.upper(): t for t in team_result.scalars()}

    # Pre-fetch existing URLs to skip
    urls = [p.post_url for p in payload.posts]
    existing_stmt = select(db_models.GameSocialPost.post_url).where(
        db_models.GameSocialPost.post_url.in_(urls)
    )
    existing_urls = set((await session.execute(existing_stmt)).scalars())

    for post_data in payload.posts:
        if post_data.post_url in existing_urls:
            continue  # Skip duplicate

        team = teams_by_abbrev.get(post_data.team_abbreviation.upper())
        if not team:
            continue  # Skip unknown team

        post = db_models.GameSocialPost(
            game_id=post_data.game_id,
            team_id=team.id,
            post_url=post_data.post_url,
            posted_at=post_data.posted_at,
            has_video=post_data.has_video,
        )
        session.add(post)
        created_posts.append(post)

    await session.flush()
    
    # Refresh to load team relationships
    for post in created_posts:
        await session.refresh(post, attribute_names=["team"])

    return SocialPostListResponse(
        posts=[_serialize_post(post) for post in created_posts],
        total=len(created_posts),
    )


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_social_post(
    post_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a social post."""
    post = await session.get(db_models.GameSocialPost, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    
    await session.delete(post)

