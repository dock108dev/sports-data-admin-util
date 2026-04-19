"""Add pipeline_coverage_reports table.

Revision ID: 20260419_000040
Revises: 20260419_000039
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260419_000040"
down_revision = "20260419_000039"
branch_labels = None
depends_on = None

_TABLE = "pipeline_coverage_reports"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sport_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("total_finals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_flows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_missing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_fallbacks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_quality_score", sa.Float(), nullable=True),
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
        sa.UniqueConstraint("report_date", name="uq_pipeline_coverage_reports_date"),
    )
    op.create_index(
        "idx_pipeline_coverage_reports_date", _TABLE, ["report_date"], unique=True
    )


def downgrade() -> None:
    op.drop_index("idx_pipeline_coverage_reports_date", table_name=_TABLE)
    op.drop_table(_TABLE)
