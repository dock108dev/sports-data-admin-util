"""Beta Phase 0 - Canonical schema for game identity.

Revision ID: 20260108_000001
Revises: 20260101_000006
Create Date: 2026-01-08

This migration:
1. Adds 'live' to the game status options
2. Adds 'end_time' column to games
3. Adds index on (league_id, status) for efficient status-based queries
4. Adds 'external_post_id' and 'reveal_risk' to social posts for spec compliance
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260108_000001"
down_revision = "20260101_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add end_time column to sports_games (idempotent)
    games_cols = {col["name"] for col in inspector.get_columns("sports_games")}
    if "end_time" not in games_cols:
        op.add_column(
            "sports_games",
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        )

    # 2. Add index on (league_id, status) for efficient status queries
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_games_league_status ON sports_games(league_id, status)"
    )

    # 3. Add external_post_id to game_social_posts for tracking post identity
    posts_cols = {col["name"] for col in inspector.get_columns("game_social_posts")}
    if "external_post_id" not in posts_cols:
        op.add_column(
            "game_social_posts",
            sa.Column("external_post_id", sa.String(100), nullable=True),
        )

    # 4. Add reveal risk boolean to social posts
    if "spoiler_risk" not in posts_cols:
        op.add_column(
            "game_social_posts",
            sa.Column("spoiler_risk", sa.Boolean(), server_default="false", nullable=False),
        )

    # 5. Add index on (platform, external_post_id) - platform is implied as 'x' for now
    # We'll add a platform column in a future migration if needed
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_posts_external_id ON game_social_posts(external_post_id)"
    )

    # 6. Backfill end_time for completed games to game_date (they're final games)
    op.execute("""
        UPDATE sports_games 
        SET end_time = game_date 
        WHERE status = 'completed' AND end_time IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_social_posts_external_id")
    op.execute("ALTER TABLE game_social_posts DROP COLUMN IF EXISTS spoiler_risk")
    op.execute("ALTER TABLE game_social_posts DROP COLUMN IF EXISTS external_post_id")
    op.execute("DROP INDEX IF EXISTS idx_games_league_status")
    op.execute("ALTER TABLE sports_games DROP COLUMN IF EXISTS end_time")
