"""Models for social media post collection."""

from datetime import datetime
from pydantic import BaseModel, Field


class CollectedPost(BaseModel):
    """A post collected from a team's X timeline."""

    post_url: str = Field(..., description="Full URL to the X post")
    external_post_id: str | None = Field(default=None, description="Platform-specific post ID")
    platform: str = Field(default="x", description="Social platform identifier")
    posted_at: datetime = Field(..., description="When the post was published")
    has_video: bool = Field(default=False, description="Whether post contains video")
    text: str | None = Field(default=None, description="Post text/caption")
    author_handle: str | None = Field(default=None, description="X handle of the author")
    # Media content fields for custom embed display
    video_url: str | None = Field(default=None, description="Direct video URL if available")
    image_url: str | None = Field(default=None, description="Thumbnail or image URL")
    media_type: str | None = Field(default=None, description="video, image, or none")


class PostCollectionJob(BaseModel):
    """Parameters for a post collection job."""

    game_id: int = Field(..., description="Database ID of the game")
    team_abbreviation: str = Field(..., description="Team abbreviation (e.g., 'GSW')")
    x_handle: str = Field(..., description="X handle to collect from")
    window_start: datetime = Field(..., description="Start of collection window")
    window_end: datetime = Field(..., description="End of collection window")
    game_start: datetime = Field(..., description="Game start time for attachment rules")
    game_end: datetime | None = Field(default=None, description="Game end time for attachment rules")
    is_backfill: bool = Field(default=False, description="Skip poll interval for historical data")


class PostCollectionResult(BaseModel):
    """Result of a post collection job."""

    job: PostCollectionJob
    posts_found: int = Field(default=0)
    posts_saved: int = Field(default=0)
    errors: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
