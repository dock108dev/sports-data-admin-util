"""Add updated_at to plays and backfill all tables to 2025-12-26.

Revision ID: 20260101_000004
Revises: 20260101_000003
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260101_000004"
down_revision = "20260101_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add updated_at to sports_game_plays
    op.add_column(
        "sports_game_plays",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill plays
    op.execute("UPDATE sports_game_plays SET updated_at = '2025-12-26 00:00:00+00' WHERE updated_at IS NULL")
    # Make non-nullable
    op.alter_column("sports_game_plays", "updated_at", nullable=False)

    # Backfill all other tables to 2025-12-26
    op.execute("UPDATE sports_games SET updated_at = '2025-12-26 00:00:00+00'")
    op.execute("UPDATE sports_team_boxscores SET updated_at = '2025-12-26 00:00:00+00'")
    op.execute("UPDATE sports_player_boxscores SET updated_at = '2025-12-26 00:00:00+00'")
    op.execute("UPDATE sports_game_odds SET updated_at = '2025-12-26 00:00:00+00'")
    # game_social_posts already backfilled in previous migration


def downgrade() -> None:
    op.drop_column("sports_game_plays", "updated_at")






