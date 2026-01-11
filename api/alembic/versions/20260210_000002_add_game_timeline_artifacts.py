"""Add timeline artifact storage for games.

Revision ID: 20260210_000002
Revises: 20260210_000001
Create Date: 2026-02-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260210_000002"
down_revision = "20260210_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_game_timeline_artifacts" not in existing_tables:
        op.create_table(
            "sports_game_timeline_artifacts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("game_id", sa.Integer(), sa.ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sport", sa.String(length=20), nullable=False),
            sa.Column("timeline_version", sa.String(length=20), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("timeline_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("summary_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("game_id", "sport", "timeline_version", name="uq_game_timeline_artifact_version"),
        )
        op.create_index(
            "idx_game_timeline_artifacts_game",
            "sports_game_timeline_artifacts",
            ["game_id"],
        )
        op.create_index(
            "idx_game_timeline_artifacts_sport",
            "sports_game_timeline_artifacts",
            ["sport"],
        )


def downgrade() -> None:
    op.drop_index("idx_game_timeline_artifacts_sport", table_name="sports_game_timeline_artifacts")
    op.drop_index("idx_game_timeline_artifacts_game", table_name="sports_game_timeline_artifacts")
    op.drop_table("sports_game_timeline_artifacts")
