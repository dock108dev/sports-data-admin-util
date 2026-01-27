"""Add bulk_story_generation_jobs table.

This table persists bulk story generation job state so it survives
worker restarts and is consistent across multiple worker processes.

Revision ID: 20260127_000002
Revises: 20260127_000001
Create Date: 2026-01-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260127_000002"
down_revision = "20260127_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bulk_story_generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_uuid",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "leagues",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "force_regenerate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("total_games", sa.Integer(), nullable=False, default=0),
        sa.Column("current_game", sa.Integer(), nullable=False, default=0),
        sa.Column("successful", sa.Integer(), nullable=False, default=0),
        sa.Column("failed", sa.Integer(), nullable=False, default=0),
        sa.Column("skipped", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "errors_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("triggered_by", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )

    op.create_index(
        "idx_bulk_story_jobs_uuid",
        "bulk_story_generation_jobs",
        ["job_uuid"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_bulk_story_jobs_uuid", table_name="bulk_story_generation_jobs")
    op.drop_table("bulk_story_generation_jobs")
