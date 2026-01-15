"""Merge all Alembic heads.

Revision ID: 20260213_000001
Revises: 20260110_000002, 20260210_000003
Create Date: 2026-01-13

Why:
The previous merge at 20260110_000002 merged too early, before 20260210_000002
and 20260210_000003 were created. This merge unifies all heads so
`alembic upgrade head` works correctly.
"""

from __future__ import annotations

# alembic requires `op` to be importable even for no-op merge revisions
from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20260213_000001"
down_revision = ("20260110_000002", "20260210_000003")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op merge revision.
    pass


def downgrade() -> None:
    # Downgrade is a no-op; it simply re-splits the heads.
    pass
