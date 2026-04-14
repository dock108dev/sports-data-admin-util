"""Add game_state_log table and new canonical game states.

Revision ID: game_state_log_001
Revises: forecast_blend_cols_001
Create Date: 2026-04-13

Adds delayed/suspended/cancelled states to sports_games status column
and creates the game_state_log audit trail table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "game_state_log_001"
down_revision = "forecast_blend_cols_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_state_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("from_state", sa.String(20), nullable=False),
        sa.Column("to_state", sa.String(20), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "transitioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_state_log_game_time",
        "game_state_log",
        ["game_id", "transitioned_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_state_log_game_time", table_name="game_state_log")
    op.drop_table("game_state_log")
