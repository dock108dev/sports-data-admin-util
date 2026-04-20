"""Add flow_source column to sports_game_stories.

Revision ID: 20260419_000042
Revises: 20260419_000041
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260419_000042"
down_revision = "20260419_000041"
branch_labels = None
depends_on = None

_TABLE = "sports_game_stories"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "flow_source",
            sa.String(20),
            nullable=True,
            server_default="LLM",
        ),
    )
    op.create_index("idx_game_stories_flow_source", _TABLE, ["flow_source"])


def downgrade() -> None:
    op.drop_index("idx_game_stories_flow_source", table_name=_TABLE)
    op.drop_column(_TABLE, "flow_source")
