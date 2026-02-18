"""Add last_boxscore_at to sports_games.

Revision ID: 20260217_000001
Revises: 20260215_000001
Create Date: 2026-02-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260217_000001"
down_revision = "20260215_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sports_games",
        sa.Column("last_boxscore_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sports_games", "last_boxscore_at")
