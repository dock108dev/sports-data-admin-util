"""Add blocks columns to sports_game_stories.

Adds support for 4-7 narrative blocks per game story:
- blocks_json: JSONB containing the narrative blocks
- block_count: Number of blocks
- blocks_version: Version identifier (e.g., "v1-blocks")
- blocks_validated_at: When block validation passed
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20260203_000003"
down_revision = "20260101_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if columns already exist (created by initial schema baseline)
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'sports_game_stories' AND column_name = 'blocks_json')"
    ))
    column_exists = result.scalar()
    if column_exists:
        return  # Columns already created by Base.metadata.create_all() in initial migration

    # Add blocks columns to sports_game_stories
    op.add_column(
        "sports_game_stories",
        sa.Column("blocks_json", JSONB, nullable=True),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("block_count", sa.Integer, nullable=True),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column("blocks_version", sa.String(20), nullable=True),
    )
    op.add_column(
        "sports_game_stories",
        sa.Column(
            "blocks_validated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Remove blocks columns from sports_game_stories
    op.drop_column("sports_game_stories", "blocks_validated_at")
    op.drop_column("sports_game_stories", "blocks_version")
    op.drop_column("sports_game_stories", "block_count")
    op.drop_column("sports_game_stories", "blocks_json")
