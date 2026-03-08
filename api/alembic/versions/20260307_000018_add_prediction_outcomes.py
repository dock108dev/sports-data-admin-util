"""Add analytics_prediction_outcomes table.

Revision ID: 20260307_prediction_outcomes
Revises: 20260307_batch_sim_jobs
Create Date: 2026-03-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260307_prediction_outcomes"
down_revision = "20260307_batch_sim_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_prediction_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("sport", sa.String(50), nullable=False),
        sa.Column("batch_sim_job_id", sa.Integer(), nullable=True),
        sa.Column("home_team", sa.String(100), nullable=False),
        sa.Column("away_team", sa.String(100), nullable=False),
        sa.Column("predicted_home_wp", sa.Float(), nullable=False),
        sa.Column("predicted_away_wp", sa.Float(), nullable=False),
        sa.Column("predicted_home_score", sa.Float(), nullable=True),
        sa.Column("predicted_away_score", sa.Float(), nullable=True),
        sa.Column("probability_mode", sa.String(50), nullable=True),
        sa.Column("game_date", sa.String(20), nullable=True),
        sa.Column("actual_home_score", sa.Integer(), nullable=True),
        sa.Column("actual_away_score", sa.Integer(), nullable=True),
        sa.Column("home_win_actual", sa.Boolean(), nullable=True),
        sa.Column("correct_winner", sa.Boolean(), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column(
            "outcome_recorded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_prediction_outcomes_game_id",
        "analytics_prediction_outcomes",
        ["game_id"],
    )
    op.create_index(
        "idx_prediction_outcomes_batch_sim_job_id",
        "analytics_prediction_outcomes",
        ["batch_sim_job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_prediction_outcomes_batch_sim_job_id",
        table_name="analytics_prediction_outcomes",
    )
    op.drop_index(
        "idx_prediction_outcomes_game_id",
        table_name="analytics_prediction_outcomes",
    )
    op.drop_table("analytics_prediction_outcomes")
