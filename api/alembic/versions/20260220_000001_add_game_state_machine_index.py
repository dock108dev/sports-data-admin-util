"""Merge heads + add index for game-state-machine resolver and backfill archived.

Revision ID: 20260220_000001
Revises: 20260206_000003, 20260218_000005
Create Date: 2026-02-20
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260220_000001"
down_revision = ("20260206_000003", "20260218_000005")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add composite index for ActiveGamesResolver queries.
    # The status column is VARCHAR(20), so pregame/archived need no ALTER TYPE.
    op.create_index(
        "idx_games_status_tip_time",
        "sports_games",
        ["status", "tip_time"],
    )

    # Backfill: mark old final games as archived.
    # Criteria: status='final', end_time > 7 days ago, AND has timeline artifacts.
    op.execute("""
        UPDATE sports_games
        SET status = 'archived', updated_at = now()
        WHERE status = 'final'
          AND end_time < now() - interval '7 days'
          AND id IN (
              SELECT DISTINCT game_id
              FROM sports_game_timeline_artifacts
          )
    """)


def downgrade() -> None:
    # Revert archived games back to final
    op.execute("""
        UPDATE sports_games
        SET status = 'final', updated_at = now()
        WHERE status = 'archived'
    """)

    op.drop_index("idx_games_status_tip_time", table_name="sports_games")
