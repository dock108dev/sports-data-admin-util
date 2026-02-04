"""Add fairbet_game_odds_work table.

FairBet work table: derived, disposable, upserted odds for cross-book comparison.
One row per (bet x book) for non-completed games.

Bet identity: (game_id, market_key, selection_key, line_value)
Books are variants, not schema - each book is a separate row.

This table is NOT historical - rows are overwritten per book per bet.
Only populated for non-final games (scheduled, live).

Revision ID: 20260131_000001
Revises: 20260130_000003
Create Date: 2026-01-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260131_000001"
down_revision = "20260130_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if table already exists (created by initial schema baseline)
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'fairbet_game_odds_work')"
    ))
    if result.scalar():
        return  # Table already exists

    op.create_table(
        "fairbet_game_odds_work",
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("market_key", sa.String(50), nullable=False, primary_key=True),
        sa.Column("selection_key", sa.Text(), nullable=False, primary_key=True),
        sa.Column(
            "line_value",
            sa.Float(),
            nullable=False,
            primary_key=True,
            server_default="0",
        ),
        sa.Column("book", sa.String(50), nullable=False, primary_key=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "idx_fairbet_odds_game",
        "fairbet_game_odds_work",
        ["game_id"],
    )

    op.create_index(
        "idx_fairbet_odds_observed",
        "fairbet_game_odds_work",
        ["observed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_fairbet_odds_observed", table_name="fairbet_game_odds_work")
    op.drop_index("idx_fairbet_odds_game", table_name="fairbet_game_odds_work")
    op.drop_table("fairbet_game_odds_work")
