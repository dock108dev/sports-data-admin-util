"""Initial schema baseline.

NOTE: This is a no-op migration that serves as the baseline.
The actual schema is created by subsequent migrations.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250920_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op baseline migration.

    The schema is built incrementally by subsequent migrations.
    """
    pass


def downgrade() -> None:
    """No-op downgrade."""
    pass
