"""Add compact mode thresholds table and defaults.

Revision ID: 20260101_000005
Revises: 20260101_000004
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260101_000005"
down_revision = "20260101_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "compact_mode_thresholds" not in set(inspector.get_table_names()):
        op.create_table(
            "compact_mode_thresholds",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sport_id", sa.Integer(), sa.ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False),
            sa.Column("thresholds", postgresql.JSONB(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("sport_id", name="uq_compact_mode_thresholds_sport_id"),
        )
        op.create_index(
            "idx_compact_mode_thresholds_sport_id",
            "compact_mode_thresholds",
            ["sport_id"],
            unique=True,
        )

    op.execute(
        """
        INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
        SELECT id, '[1, 2, 3, 5]'::jsonb, 'Score-lead thresholds for compact mode moments.'
        FROM sports_leagues
        WHERE code = 'NFL'
        ON CONFLICT (sport_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
        SELECT id, '[1, 2, 3, 5]'::jsonb, 'Score-lead thresholds for compact mode moments.'
        FROM sports_leagues
        WHERE code = 'NCAAF'
        ON CONFLICT (sport_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
        SELECT id, '[3, 6, 10, 16]'::jsonb, 'Point-lead thresholds for compact mode moments.'
        FROM sports_leagues
        WHERE code = 'NBA'
        ON CONFLICT (sport_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
        SELECT id, '[3, 6, 10, 16]'::jsonb, 'Point-lead thresholds for compact mode moments.'
        FROM sports_leagues
        WHERE code = 'NCAAB'
        ON CONFLICT (sport_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
        SELECT id, '[1, 2, 3, 5]'::jsonb, 'Run-lead thresholds for compact mode moments.'
        FROM sports_leagues
        WHERE code = 'MLB'
        ON CONFLICT (sport_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
        SELECT id, '[1, 2, 3]'::jsonb, 'Goal-lead thresholds for compact mode moments.'
        FROM sports_leagues
        WHERE code = 'NHL'
        ON CONFLICT (sport_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_compact_mode_thresholds_sport_id", table_name="compact_mode_thresholds")
    op.drop_table("compact_mode_thresholds")
