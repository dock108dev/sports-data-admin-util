"""Set SQL-level DEFAULT 'unknown' on team_social_posts.game_phase.

Revision ID: 20260420_000056
Revises: 20260420_000055
Create Date: 2026-04-20

The SQLAlchemy model declares `server_default="unknown"` on
TeamSocialPost.game_phase, but the earlier NOT NULL migration
(game_phase_not_null_001) never issued ALTER COLUMN ... SET DEFAULT,
so the deployed column has NOT NULL + CHECK but no default. Any INSERT
that omitted the column hit a NotNullViolation. This migration installs
the default to match the model declaration.
"""

from __future__ import annotations

from alembic import op


revision = "20260420_000056"
down_revision = "20260420_000055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE team_social_posts "
        "ALTER COLUMN game_phase SET DEFAULT 'unknown'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE team_social_posts "
        "ALTER COLUMN game_phase DROP DEFAULT"
    )
