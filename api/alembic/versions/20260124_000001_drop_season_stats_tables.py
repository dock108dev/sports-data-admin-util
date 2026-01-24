"""Drop unused season stats tables.

Revision ID: 20260124_000001
Revises: 20260218_000005
Create Date: 2026-01-24

Season-level team and player stats were unused infrastructure.
This migration removes the tables entirely.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260124_000001"
down_revision = "20260122_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_player_season_stats_league_season")
    op.execute("DROP INDEX IF EXISTS idx_team_season_stats_team_season")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS sports_player_season_stats CASCADE")
    op.execute("DROP TABLE IF EXISTS sports_team_season_stats CASCADE")


def downgrade() -> None:
    # We don't recreate the tables on downgrade - they were unused
    pass
