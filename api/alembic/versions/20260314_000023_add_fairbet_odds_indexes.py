"""Add missing indexes to fairbet_game_odds_work for DELETE and query performance.

The stale-odds DELETE query joins on (game_id, book, market_category) but only
a single-column index on game_id existed. The updated_at column used in the
WHERE clause had no index at all. These missing indexes caused full table scans
on a 1.5M-row table, producing 34-37 second response times.

Revision ID: 20260314_fairbet_indexes
Revises: 20260313_mlb_player_level
Create Date: 2026-03-14
"""

from alembic import op

revision = "20260314_fairbet_indexes"
down_revision = "20260313_mlb_player_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_fairbet_odds_game_book_cat",
        "fairbet_game_odds_work",
        ["game_id", "book", "market_category"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_fairbet_odds_updated_at",
        "fairbet_game_odds_work",
        ["updated_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_fairbet_odds_updated_at", table_name="fairbet_game_odds_work")
    op.drop_index("idx_fairbet_odds_game_book_cat", table_name="fairbet_game_odds_work")
