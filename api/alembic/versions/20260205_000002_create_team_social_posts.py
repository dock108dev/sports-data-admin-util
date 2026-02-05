"""Create team_social_posts table for team-centric social collection.

This table stores tweets collected per-team rather than per-game.
Tweets are collected first (mapping_status='unmapped'), then mapped to games
based on posted_at timestamps falling within game windows.

Revision ID: 20260205_000002
Revises: 20260205_000001
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260205_000002"
down_revision = "20260205_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create team_social_posts table and indexes."""
    op.create_table(
        "team_social_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("sports_teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.String(20),
            nullable=False,
            server_default="x",
        ),
        sa.Column(
            "external_post_id",
            sa.String(100),
            unique=True,
            nullable=True,
        ),
        sa.Column("post_url", sa.Text(), nullable=False),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("tweet_text", sa.Text(), nullable=True),
        sa.Column("likes_count", sa.Integer(), nullable=True),
        sa.Column("retweets_count", sa.Integer(), nullable=True),
        sa.Column("replies_count", sa.Integer(), nullable=True),
        sa.Column(
            "has_video",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("media_type", sa.String(20), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("source_handle", sa.String(100), nullable=True),
        # Mapping fields - game_id is NULL until mapped to a game
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("sports_games.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "mapping_status",
            sa.String(20),
            nullable=False,
            server_default="unmapped",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Create indexes for efficient queries
    op.create_index(
        "idx_team_social_posts_team",
        "team_social_posts",
        ["team_id"],
    )
    op.create_index(
        "idx_team_social_posts_posted_at",
        "team_social_posts",
        ["posted_at"],
    )
    op.create_index(
        "idx_team_social_posts_mapping_status",
        "team_social_posts",
        ["mapping_status"],
    )
    op.create_index(
        "idx_team_social_posts_game",
        "team_social_posts",
        ["game_id"],
    )
    # Composite index for efficient mapping queries (find unmapped posts by team)
    op.create_index(
        "idx_team_social_posts_team_status",
        "team_social_posts",
        ["team_id", "mapping_status"],
    )


def downgrade() -> None:
    """Drop team_social_posts table and indexes."""
    op.drop_index("idx_team_social_posts_team_status", table_name="team_social_posts")
    op.drop_index("idx_team_social_posts_game", table_name="team_social_posts")
    op.drop_index("idx_team_social_posts_mapping_status", table_name="team_social_posts")
    op.drop_index("idx_team_social_posts_posted_at", table_name="team_social_posts")
    op.drop_index("idx_team_social_posts_team", table_name="team_social_posts")
    op.drop_table("team_social_posts")
