"""Merge pipeline heads.

Revision ID: 20260218_000005
Revises: 20260115_000004, 20260218_000004
Create Date: 2026-02-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20260218_000005"
down_revision = ("20260115_000004", "20260218_000004")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge heads - no schema changes needed."""
    pass


def downgrade() -> None:
    """Merge heads - no schema changes needed."""
    pass
