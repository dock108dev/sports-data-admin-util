"""Merge Alembic heads after parallel migrations.

Revision ID: 20260110_000002
Revises: 20260109_000001, 20260210_000001
Create Date: 2026-01-10

Why:
Two migrations branched off `20260120_000001`, creating multiple Alembic heads.
This merge revision restores a single linear head so `alembic upgrade head` works
predictably in Docker and CI.
"""

from __future__ import annotations

# alembic requires `op` to be importable even for no-op merge revisions
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260110_000002"
down_revision = ("20260109_000001", "20260210_000001")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op merge revision.
    pass


def downgrade() -> None:
    # Downgrade is a no-op; it simply re-splits the heads.
    pass

