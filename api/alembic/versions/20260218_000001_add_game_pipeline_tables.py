"""Add game pipeline tracking tables.

This migration introduces the game pipeline infrastructure for decoupling
data scraping from moment generation. Each game can have multiple pipeline
runs, and each run tracks individual stage executions.

Pipeline Stages:
- NORMALIZE_PBP: Build normalized PBP events with phases
- DERIVE_SIGNALS: Compute lead ladder states and tier crossings
- GENERATE_MOMENTS: Partition game into narrative moments
- VALIDATE_MOMENTS: Run validation checks
- FINALIZE_MOMENTS: Persist final timeline artifact

Revision ID: 20260218_000001
Revises: 20260214_000001
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260218_000001"
down_revision = "20260214_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Create sports_game_pipeline_runs table
    if "sports_game_pipeline_runs" not in existing_tables:
        op.create_table(
            "sports_game_pipeline_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "run_uuid",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "game_id",
                sa.Integer(),
                sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "triggered_by",
                sa.String(length=20),
                nullable=False,
                comment="prod_auto, admin, manual, backfill",
            ),
            sa.Column(
                "auto_chain",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
                comment="Whether to automatically proceed to next stage",
            ),
            sa.Column(
                "current_stage",
                sa.String(length=30),
                nullable=True,
                comment="Current or last executed stage name",
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
                comment="pending, running, completed, failed, paused",
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index(
            "idx_pipeline_runs_game",
            "sports_game_pipeline_runs",
            ["game_id"],
        )
        op.create_index(
            "idx_pipeline_runs_status",
            "sports_game_pipeline_runs",
            ["status"],
        )
        op.create_index(
            "idx_pipeline_runs_uuid",
            "sports_game_pipeline_runs",
            ["run_uuid"],
            unique=True,
        )
        op.create_index(
            "idx_pipeline_runs_created",
            "sports_game_pipeline_runs",
            ["created_at"],
        )

    # Create sports_game_pipeline_stages table
    if "sports_game_pipeline_stages" not in existing_tables:
        op.create_table(
            "sports_game_pipeline_stages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "run_id",
                sa.Integer(),
                sa.ForeignKey("sports_game_pipeline_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "stage",
                sa.String(length=30),
                nullable=False,
                comment="NORMALIZE_PBP, DERIVE_SIGNALS, GENERATE_MOMENTS, VALIDATE_MOMENTS, FINALIZE_MOMENTS",
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
                comment="pending, running, success, failed, skipped",
            ),
            sa.Column(
                "output_json",
                postgresql.JSONB(),
                nullable=True,
                comment="Stage-specific output data",
            ),
            sa.Column(
                "logs_json",
                postgresql.JSONB(),
                nullable=True,
                server_default=sa.text("'[]'::jsonb"),
                comment="Array of log entries with timestamps",
            ),
            sa.Column(
                "error_details",
                sa.Text(),
                nullable=True,
                comment="Error message if stage failed",
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index(
            "idx_pipeline_stages_run",
            "sports_game_pipeline_stages",
            ["run_id"],
        )
        op.create_index(
            "idx_pipeline_stages_status",
            "sports_game_pipeline_stages",
            ["status"],
        )
        # Unique constraint: one stage per run
        op.create_unique_constraint(
            "uq_pipeline_stages_run_stage",
            "sports_game_pipeline_stages",
            ["run_id", "stage"],
        )


def downgrade() -> None:
    op.drop_table("sports_game_pipeline_stages")
    op.drop_table("sports_game_pipeline_runs")
