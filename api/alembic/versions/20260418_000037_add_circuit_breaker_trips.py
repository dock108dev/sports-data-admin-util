"""Add circuit_breaker_trip_events table.

Revision ID: cb_trip_events_001
Revises: embedded_social_post_fk_001
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "cb_trip_events_001"
down_revision = "embedded_social_post_fk_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "circuit_breaker_trip_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("breaker_name", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "tripped_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_circuit_breaker_trip_events_breaker_name",
        "circuit_breaker_trip_events",
        ["breaker_name"],
    )
    op.create_index(
        "ix_circuit_breaker_trip_events_tripped_at",
        "circuit_breaker_trip_events",
        ["tripped_at"],
    )
    op.create_index(
        "ix_cb_trip_events_name_tripped",
        "circuit_breaker_trip_events",
        ["breaker_name", "tripped_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cb_trip_events_name_tripped", table_name="circuit_breaker_trip_events"
    )
    op.drop_index(
        "ix_circuit_breaker_trip_events_tripped_at",
        table_name="circuit_breaker_trip_events",
    )
    op.drop_index(
        "ix_circuit_breaker_trip_events_breaker_name",
        table_name="circuit_breaker_trip_events",
    )
    op.drop_table("circuit_breaker_trip_events")
