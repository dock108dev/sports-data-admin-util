"""Initial schema baseline."""

from __future__ import annotations

from alembic import op

from app.db_models import Base

# revision identifiers, used by Alembic.
revision = "20250920_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema from SQLAlchemy metadata."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all tables from SQLAlchemy metadata."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
