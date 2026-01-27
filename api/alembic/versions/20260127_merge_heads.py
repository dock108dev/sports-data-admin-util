"""Merge migration branches.

Revision ID: 20260127_merge_heads
Revises: 20260126_000001, 20260127_add_players
Create Date: 2026-01-27
"""

from alembic import op

revision = "20260127_merge_heads"
down_revision = ("20260126_000001", "20260127_add_players")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge point - no operations needed."""
    pass


def downgrade() -> None:
    """Merge point - no operations needed."""
    pass
