"""Drop legacy chapter-based story columns.

Revision ID: 20260126_000001
Revises: 20260127_000001
Create Date: 2026-01-26

The story system now uses moments-based format exclusively.
Drop legacy chapter-based columns that are no longer used.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20260126_000001"
down_revision = "20260127_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop legacy story columns."""
    # Drop legacy chapter-based columns
    op.drop_column("sports_game_stories", "chapters_json")
    op.drop_column("sports_game_stories", "chapter_count")
    op.drop_column("sports_game_stories", "chapters_fingerprint")
    op.drop_column("sports_game_stories", "summaries_json")
    op.drop_column("sports_game_stories", "titles_json")
    op.drop_column("sports_game_stories", "compact_story")
    op.drop_column("sports_game_stories", "reading_time_minutes")
    op.drop_column("sports_game_stories", "has_summaries")
    op.drop_column("sports_game_stories", "has_titles")
    op.drop_column("sports_game_stories", "has_compact_story")


def downgrade() -> None:
    """Restore legacy story columns (empty defaults)."""
    op.add_column(
        "sports_game_stories",
        sa.Column("has_compact_story", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("has_titles", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("has_summaries", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("reading_time_minutes", sa.Float(), nullable=True),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("compact_story", sa.Text(), nullable=True),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("titles_json", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("summaries_json", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("chapters_fingerprint", sa.String(64), nullable=True),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("chapter_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("chapters_json", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
