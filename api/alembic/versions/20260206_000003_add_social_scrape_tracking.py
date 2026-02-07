"""Add social_scrape_1_at, social_scrape_2_at, closed_at to sports_games.

Revision ID: 20260206_000003
Revises: 20260206_000002
Create Date: 2026-02-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260206_000003"
down_revision = "20260206_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sports_games",
        sa.Column("social_scrape_1_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sports_games",
        sa.Column("social_scrape_2_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sports_games",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sports_games", "closed_at")
    op.drop_column("sports_games", "social_scrape_2_at")
    op.drop_column("sports_games", "social_scrape_1_at")
