"""Add game reading positions table.

Revision ID: 20260101_000006
Revises: 20260101_000005
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260101_000006"
down_revision = "20260101_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_reading_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("moment", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("scroll_hint", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "game_id", name="uq_reading_position_user_game"),
    )
    op.create_index(
        "idx_reading_positions_user_game",
        "game_reading_positions",
        ["user_id", "game_id"],
        unique=False,
    )
    op.create_index(
        "idx_reading_positions_user_id",
        "game_reading_positions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "idx_reading_positions_game_id",
        "game_reading_positions",
        ["game_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_reading_positions_game_id", table_name="game_reading_positions")
    op.drop_index("idx_reading_positions_user_id", table_name="game_reading_positions")
    op.drop_index("idx_reading_positions_user_game", table_name="game_reading_positions")
    op.drop_table("game_reading_positions")
