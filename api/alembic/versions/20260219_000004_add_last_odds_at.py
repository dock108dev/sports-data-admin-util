"""Add last_odds_at timestamp to sports_games.

Adds a nullable timestamp column so the admin UI can determine
odds-specific staleness independently of last_scraped_at.

Revision ID: 20260219_last_odds_at
Revises: 20260218_fix_ncaab
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260219_last_odds_at"
down_revision = "20260218_fix_ncaab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sports_games",
        sa.Column("last_odds_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sports_games", "last_odds_at")
