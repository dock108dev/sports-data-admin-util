"""Beta Phase 0 - Canonical schema for game identity.

Revision ID: 20260108_000001
Revises: 20260101_000006
Create Date: 2026-01-08

This migration:
1. Adds 'live' to the game status options
2. Adds 'end_time' column to games
3. Adds index on (league_id, status) for efficient status-based queries
4. Adds 'external_post_id' and 'spoiler_risk' to social posts for spec compliance
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260108_000001"
down_revision = "20260101_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add end_time column to sports_games
    op.add_column(
        "sports_games",
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True)
    )

    # 2. Add index on (league_id, status) for efficient status queries
    op.create_index(
        "idx_games_league_status",
        "sports_games",
        ["league_id", "status"]
    )

    # 3. Add external_post_id to game_social_posts for tracking post identity
    op.add_column(
        "game_social_posts",
        sa.Column("external_post_id", sa.String(100), nullable=True)
    )

    # 4. Add spoiler_risk boolean to social posts
    op.add_column(
        "game_social_posts",
        sa.Column("spoiler_risk", sa.Boolean(), server_default="false", nullable=False)
    )

    # 5. Add index on (platform, external_post_id) - platform is implied as 'x' for now
    # We'll add a platform column in a future migration if needed
    op.create_index(
        "idx_social_posts_external_id",
        "game_social_posts",
        ["external_post_id"],
        unique=False
    )

    # 6. Backfill end_time for completed games to game_date (they're final games)
    op.execute("""
        UPDATE sports_games 
        SET end_time = game_date 
        WHERE status = 'completed' AND end_time IS NULL
    """)


def downgrade() -> None:
    op.drop_index("idx_social_posts_external_id", table_name="game_social_posts")
    op.drop_column("game_social_posts", "spoiler_risk")
    op.drop_column("game_social_posts", "external_post_id")
    op.drop_index("idx_games_league_status", table_name="sports_games")
    op.drop_column("sports_games", "end_time")
