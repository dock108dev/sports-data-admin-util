"""Add quality_score to sports_game_stories; create quality_review_queue table.

Revision ID: 20260419_000041
Revises: 20260419_000040
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260419_000041"
down_revision = "20260419_000040"
branch_labels = None
depends_on = None

_FLOW_TABLE = "sports_game_stories"
_REVIEW_TABLE = "quality_review_queue"


def upgrade() -> None:
    # Add quality_score column to existing flow table
    op.add_column(
        _FLOW_TABLE,
        sa.Column("quality_score", sa.Float(), nullable=True),
    )
    op.create_index(
        "idx_game_stories_quality_score",
        _FLOW_TABLE,
        ["quality_score"],
    )

    # Create quality_review_queue table for Tier 3 escalation
    op.create_table(
        _REVIEW_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "flow_id",
            sa.Integer(),
            sa.ForeignKey("sports_game_stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sport", sa.String(20), nullable=False),
        sa.Column("combined_score", sa.Float(), nullable=False),
        sa.Column("tier1_score", sa.Float(), nullable=False),
        sa.Column("tier2_score", sa.Float(), nullable=True),
        sa.Column(
            "tier_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_quality_review_queue_flow_id", _REVIEW_TABLE, ["flow_id"])
    op.create_index("idx_quality_review_queue_status", _REVIEW_TABLE, ["status"])
    op.create_index("idx_quality_review_queue_sport", _REVIEW_TABLE, ["sport"])


def downgrade() -> None:
    op.drop_index("idx_quality_review_queue_sport", table_name=_REVIEW_TABLE)
    op.drop_index("idx_quality_review_queue_status", table_name=_REVIEW_TABLE)
    op.drop_index("idx_quality_review_queue_flow_id", table_name=_REVIEW_TABLE)
    op.drop_table(_REVIEW_TABLE)
    op.drop_index("idx_game_stories_quality_score", table_name=_FLOW_TABLE)
    op.drop_column(_FLOW_TABLE, "quality_score")
