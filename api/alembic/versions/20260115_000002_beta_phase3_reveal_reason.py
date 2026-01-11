"""Beta Phase 3 - Reveal reason metadata.

Revision ID: 20260115_000002
Revises: 20260115_000001
Create Date: 2026-01-10

This migration adds reveal_reason to game_social_posts for debug visibility.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260115_000002"
down_revision = "20260115_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("game_social_posts")}
    if "spoiler_reason" not in existing_cols:
        op.add_column(
            "game_social_posts",
            sa.Column("spoiler_reason", sa.String(length=200), nullable=True),
        )


def downgrade() -> None:
    op.execute("ALTER TABLE game_social_posts DROP COLUMN IF EXISTS spoiler_reason")
