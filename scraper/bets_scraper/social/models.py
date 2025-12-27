"""Models for social media post collection."""

from datetime import datetime
from pydantic import BaseModel, Field


class CollectedPost(BaseModel):
    """A post collected from a team's X timeline."""

    post_url: str = Field(..., description="Full URL to the X post")
    posted_at: datetime = Field(..., description="When the post was published")
    has_video: bool = Field(default=False, description="Whether post contains video")
    text: str | None = Field(default=None, description="Post text for spoiler filtering (not stored)")
    author_handle: str | None = Field(default=None, description="X handle of the author")


class PostCollectionJob(BaseModel):
    """Parameters for a post collection job."""

    game_id: int = Field(..., description="Database ID of the game")
    team_abbreviation: str = Field(..., description="Team abbreviation (e.g., 'GSW')")
    x_handle: str = Field(..., description="X handle to collect from")
    window_start: datetime = Field(..., description="Start of collection window")
    window_end: datetime = Field(..., description="End of collection window")


class PostCollectionResult(BaseModel):
    """Result of a post collection job."""

    job: PostCollectionJob
    posts_found: int = Field(default=0)
    posts_saved: int = Field(default=0)
    posts_filtered: int = Field(default=0, description="Posts removed by spoiler filter")
    errors: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None

