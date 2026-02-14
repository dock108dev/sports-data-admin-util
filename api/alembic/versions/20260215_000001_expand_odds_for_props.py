"""Expand odds schema for props, multi-region, and EV calculation.

Changes to sports_game_odds:
- Widen market_type from VARCHAR(20) to VARCHAR(80) (for player_points_rebounds_assists)
- Widen side from VARCHAR(100) to VARCHAR(200)
- Add market_category VARCHAR(30) DEFAULT 'mainline' + index
- Add player_name VARCHAR(150) nullable
- Add description TEXT nullable

Changes to fairbet_game_odds_work:
- Widen market_key from VARCHAR(50) to VARCHAR(80)
- Add market_category VARCHAR(30) DEFAULT 'mainline' + index
- Add player_name VARCHAR(150) nullable

Revision ID: 20260215_000001
Revises: 20260211_000002
Create Date: 2026-02-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260215_000001"
down_revision = "20260211_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- sports_game_odds ---
    # Widen market_type for prop market keys like "player_points_rebounds_assists"
    op.alter_column(
        "sports_game_odds",
        "market_type",
        type_=sa.String(80),
        existing_type=sa.String(20),
        existing_nullable=False,
    )

    # Widen side for longer outcome descriptions
    op.alter_column(
        "sports_game_odds",
        "side",
        type_=sa.String(200),
        existing_type=sa.String(100),
        existing_nullable=True,
    )

    # Add new columns
    op.add_column(
        "sports_game_odds",
        sa.Column(
            "market_category",
            sa.String(30),
            nullable=False,
            server_default="mainline",
        ),
    )
    op.add_column(
        "sports_game_odds",
        sa.Column("player_name", sa.String(150), nullable=True),
    )
    op.add_column(
        "sports_game_odds",
        sa.Column("description", sa.Text(), nullable=True),
    )

    # Index on market_category for filtered queries
    op.create_index(
        "idx_game_odds_market_category",
        "sports_game_odds",
        ["market_category"],
    )

    # --- fairbet_game_odds_work ---
    # Widen market_key for prop market keys
    op.alter_column(
        "fairbet_game_odds_work",
        "market_key",
        type_=sa.String(80),
        existing_type=sa.String(50),
        existing_nullable=False,
    )

    # Add new columns
    op.add_column(
        "fairbet_game_odds_work",
        sa.Column(
            "market_category",
            sa.String(30),
            nullable=False,
            server_default="mainline",
        ),
    )
    op.add_column(
        "fairbet_game_odds_work",
        sa.Column("player_name", sa.String(150), nullable=True),
    )

    # Index on market_category
    op.create_index(
        "idx_fairbet_odds_market_category",
        "fairbet_game_odds_work",
        ["market_category"],
    )


def downgrade() -> None:
    # --- fairbet_game_odds_work ---
    op.drop_index("idx_fairbet_odds_market_category", table_name="fairbet_game_odds_work")
    op.drop_column("fairbet_game_odds_work", "player_name")
    op.drop_column("fairbet_game_odds_work", "market_category")
    op.alter_column(
        "fairbet_game_odds_work",
        "market_key",
        type_=sa.String(50),
        existing_type=sa.String(80),
        existing_nullable=False,
    )

    # --- sports_game_odds ---
    op.drop_index("idx_game_odds_market_category", table_name="sports_game_odds")
    op.drop_column("sports_game_odds", "description")
    op.drop_column("sports_game_odds", "player_name")
    op.drop_column("sports_game_odds", "market_category")
    op.alter_column(
        "sports_game_odds",
        "side",
        type_=sa.String(100),
        existing_type=sa.String(200),
        existing_nullable=True,
    )
    op.alter_column(
        "sports_game_odds",
        "market_type",
        type_=sa.String(20),
        existing_type=sa.String(80),
        existing_nullable=False,
    )
