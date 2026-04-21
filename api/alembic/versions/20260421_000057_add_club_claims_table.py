"""Add club_claims table for public 'claim your club' onboarding submissions.

Revision ID: 20260421_000057
Revises: 20260420_000056
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260421_000057"
down_revision = "20260420_000056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "club_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.String(length=32), nullable=False),
        sa.Column("club_name", sa.String(length=200), nullable=False),
        sa.Column("contact_email", sa.String(length=320), nullable=False),
        sa.Column("expected_entries", sa.Integer(), nullable=True),
        sa.Column(
            "notes", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'new'"),
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source_ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_club_claims_claim_id",
        "club_claims",
        ["claim_id"],
        unique=True,
    )
    op.create_index(
        "ix_club_claims_contact_email",
        "club_claims",
        ["contact_email"],
    )
    op.create_index(
        "ix_club_claims_received_at",
        "club_claims",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_club_claims_received_at", table_name="club_claims")
    op.drop_index("ix_club_claims_contact_email", table_name="club_claims")
    op.drop_index("ix_club_claims_claim_id", table_name="club_claims")
    op.drop_table("club_claims")
