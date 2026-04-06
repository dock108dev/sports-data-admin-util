"""Add score hide-list fields to user_preferences.

Revision ID: user_prefs_score_hide_001
Revises: fairbet_bet_key_001
Create Date: 2026-04-06
"""

from __future__ import annotations

from alembic import op

revision = "user_prefs_score_hide_001"
down_revision = "fairbet_bet_key_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_preferences
        ADD COLUMN IF NOT EXISTS score_reveal_mode VARCHAR(20) NOT NULL DEFAULT 'onMarkRead'
        """
    )
    op.execute(
        """
        ALTER TABLE user_preferences
        ADD COLUMN IF NOT EXISTS score_hide_leagues JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE user_preferences
        ADD COLUMN IF NOT EXISTS score_hide_teams JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    # Backfill existing rows defensively in case historical nulls exist.
    op.execute(
        """
        UPDATE user_preferences
        SET
            score_reveal_mode = COALESCE(NULLIF(score_reveal_mode, ''), 'onMarkRead'),
            score_hide_leagues = COALESCE(score_hide_leagues, '[]'::jsonb),
            score_hide_teams = COALESCE(score_hide_teams, '[]'::jsonb)
        """
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "score_hide_teams")
    op.drop_column("user_preferences", "score_hide_leagues")
    op.drop_column("user_preferences", "score_reveal_mode")
