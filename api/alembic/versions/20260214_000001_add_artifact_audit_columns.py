"""Add audit columns to timeline artifacts for tracking generation source.

Revision ID: 20260214_000001
Revises: 20260213_000001
Create Date: 2026-01-14

Adds:
- generated_by: Source of generation (backfill, api, scheduled, etc.)
- generation_reason: Why it was generated (initial_rollout, regeneration, etc.)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260214_000001"
down_revision = "20260213_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_game_timeline_artifacts" not in existing_tables:
        return

    existing_columns = {
        col["name"] for col in inspector.get_columns("sports_game_timeline_artifacts")
    }

    if "generated_by" not in existing_columns:
        op.add_column(
            "sports_game_timeline_artifacts",
            sa.Column("generated_by", sa.String(50), nullable=True),
        )

    if "generation_reason" not in existing_columns:
        op.add_column(
            "sports_game_timeline_artifacts",
            sa.Column("generation_reason", sa.String(100), nullable=True),
        )

    # Mark all existing artifacts as backfill/initial_rollout
    op.execute("""
        UPDATE sports_game_timeline_artifacts 
        SET generated_by = 'backfill', 
            generation_reason = 'initial_rollout'
        WHERE generated_by IS NULL
    """)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_game_timeline_artifacts" not in existing_tables:
        return

    existing_columns = {
        col["name"] for col in inspector.get_columns("sports_game_timeline_artifacts")
    }

    if "generation_reason" in existing_columns:
        op.drop_column("sports_game_timeline_artifacts", "generation_reason")

    if "generated_by" in existing_columns:
        op.drop_column("sports_game_timeline_artifacts", "generated_by")
