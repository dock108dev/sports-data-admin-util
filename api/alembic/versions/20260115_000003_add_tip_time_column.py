"""Add tip_time column to sports_games for actual game start times.

Revision ID: 20260115_000003
Revises: 20260214_000001
Create Date: 2026-01-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260115_000003"
down_revision = "20260214_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tip_time column for actual scheduled game start time
    # Separate from game_date which is often just midnight UTC
    op.add_column(
        "sports_games",
        sa.Column("tip_time", sa.DateTime(timezone=True), nullable=True),
    )
    
    # Add index for tip_time queries
    op.create_index(
        "ix_sports_games_tip_time",
        "sports_games",
        ["tip_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_sports_games_tip_time", table_name="sports_games")
    op.drop_column("sports_games", "tip_time")
