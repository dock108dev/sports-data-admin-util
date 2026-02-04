"""Add max_games to bulk_story_generation_jobs.

Revision ID: 20260131_000002
Revises: 20260131_000001
Create Date: 2026-01-31

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260131_000002"
down_revision: Union[str, None] = "20260131_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add max_games column to bulk_story_generation_jobs."""
    # Check if column already exists (created by initial schema baseline)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col["name"] for col in inspector.get_columns("bulk_story_generation_jobs")}
    if "max_games" in existing_cols:
        return  # Column already exists

    op.add_column(
        "bulk_story_generation_jobs",
        sa.Column("max_games", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Remove max_games column from bulk_story_generation_jobs."""
    op.drop_column("bulk_story_generation_jobs", "max_games")
