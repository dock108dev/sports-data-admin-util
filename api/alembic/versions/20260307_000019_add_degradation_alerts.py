"""Add analytics_degradation_alerts table.

Revision ID: 20260307_degradation_alerts
Revises: 20260307_prediction_outcomes
Create Date: 2026-03-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260307_degradation_alerts"
down_revision = "20260307_prediction_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_degradation_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(50), nullable=False),
        sa.Column(
            "alert_type",
            sa.String(50),
            nullable=False,
            server_default="brier_degradation",
        ),
        sa.Column("baseline_brier", sa.Float(), nullable=False),
        sa.Column("recent_brier", sa.Float(), nullable=False),
        sa.Column("baseline_accuracy", sa.Float(), nullable=False),
        sa.Column("recent_accuracy", sa.Float(), nullable=False),
        sa.Column("baseline_count", sa.Integer(), nullable=False),
        sa.Column("recent_count", sa.Integer(), nullable=False),
        sa.Column("delta_brier", sa.Float(), nullable=False),
        sa.Column("delta_accuracy", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("analytics_degradation_alerts")
