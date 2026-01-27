"""Add moments_json and related fields to sports_game_stories.

This migration extends the SportsGameStory table to support the new
condensed moments-based Story format (v2-moments).

New fields:
- moments_json: JSONB containing ordered list of condensed moments
- moment_count: INTEGER for quick access to moment count
- validated_at: TIMESTAMPTZ when validation passed

The story_version field will use "v2-moments" to distinguish from legacy
chapter-based stories. Legacy data (chapters, summaries, compact_story)
remains untouched for coexistence.

Revision ID: 20260127_000001
Revises: 20260218_000005
Create Date: 2026-01-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
# This migration merges the two heads and adds the moments fields
revision = "20260127_000001"
down_revision = ("20260218_000005", "20260125_000001")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        col["name"] for col in inspector.get_columns("sports_game_stories")
    }

    # Add moments_json column
    if "moments_json" not in existing_columns:
        op.add_column(
            "sports_game_stories",
            sa.Column(
                "moments_json",
                postgresql.JSONB(),
                nullable=True,
                comment="Ordered list of condensed moments (v2 Story format)",
            ),
        )

    # Add moment_count column
    if "moment_count" not in existing_columns:
        op.add_column(
            "sports_game_stories",
            sa.Column(
                "moment_count",
                sa.Integer(),
                nullable=True,
                comment="Number of moments in moments_json",
            ),
        )

    # Add validated_at column
    if "validated_at" not in existing_columns:
        op.add_column(
            "sports_game_stories",
            sa.Column(
                "validated_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="When moment validation passed",
            ),
        )

    # Create index for efficient story discovery queries
    op.create_index(
        "idx_game_stories_moments",
        "sports_game_stories",
        ["game_id"],
        postgresql_where=sa.text("moments_json IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_game_stories_moments", table_name="sports_game_stories")
    op.drop_column("sports_game_stories", "validated_at")
    op.drop_column("sports_game_stories", "moment_count")
    op.drop_column("sports_game_stories", "moments_json")
