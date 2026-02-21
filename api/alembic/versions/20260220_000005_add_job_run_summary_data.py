"""Add summary_data JSONB column to sports_job_runs.

Stores structured summary data (counts, stats) from recurring task
executions, enabling richer monitoring in the web admin UI.

Revision ID: 20260220_job_run_summary
Revises: 20260219_last_odds_at
Create Date: 2026-02-20
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260220_job_run_summary"
down_revision = "20260219_last_odds_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sports_job_runs",
        sa.Column("summary_data", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sports_job_runs", "summary_data")
