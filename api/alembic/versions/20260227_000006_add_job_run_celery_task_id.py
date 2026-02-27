"""Add celery_task_id column to sports_job_runs.

Stores the Celery task ID so running jobs can be revoked/canceled
from the admin UI.

Revision ID: 20260227_celery_task_id
Revises: 20260220_job_run_summary
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260227_celery_task_id"
down_revision = "20260220_job_run_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sports_job_runs",
        sa.Column("celery_task_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sports_job_runs", "celery_task_id")
