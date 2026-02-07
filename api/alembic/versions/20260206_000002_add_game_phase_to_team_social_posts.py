"""Add game_phase column to team_social_posts.

Revision ID: 20260206_000002
Revises: 20260220_000001
Create Date: 2026-02-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260206_000002"
down_revision = "20260220_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_social_posts",
        sa.Column("game_phase", sa.String(20), nullable=True),
    )
    op.create_index(
        "idx_team_social_posts_game_phase",
        "team_social_posts",
        ["game_phase"],
    )


def downgrade() -> None:
    op.drop_index("idx_team_social_posts_game_phase", table_name="team_social_posts")
    op.drop_column("team_social_posts", "game_phase")
