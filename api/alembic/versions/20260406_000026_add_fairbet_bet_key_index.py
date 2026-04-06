"""Add composite bet-key index for FairBet keyset pagination.

Revision ID: fairbet_bet_key_001
Revises: game_ingest_errors_001
Create Date: 2026-04-06
"""

from __future__ import annotations

from alembic import op

revision = "fairbet_bet_key_001"
down_revision = "game_ingest_errors_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_fairbet_odds_bet_key",
            "fairbet_game_odds_work",
            ["game_id", "market_key", "selection_key", "line_value"],
            if_not_exists=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    op.drop_index("idx_fairbet_odds_bet_key", table_name="fairbet_game_odds_work")
