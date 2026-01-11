"""Add game analysis JSON to timeline artifacts.

Revision ID: 20260210_000003
Revises: 20260210_000002
Create Date: 2026-02-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260210_000003"
down_revision = "20260210_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_game_timeline_artifacts" not in existing_tables:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("sports_game_timeline_artifacts")}
    if "game_analysis_json" not in existing_columns:
        op.add_column(
            "sports_game_timeline_artifacts",
            sa.Column("game_analysis_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_game_timeline_artifacts" not in existing_tables:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("sports_game_timeline_artifacts")}
    if "game_analysis_json" in existing_columns:
        op.drop_column("sports_game_timeline_artifacts", "game_analysis_json")
