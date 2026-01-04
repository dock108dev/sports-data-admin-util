"""Fix social media_type for video posts."""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260101_000002"
down_revision = "20250920_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Align media_type with has_video flag for existing rows
    op.execute(
        """
        UPDATE game_social_posts
        SET media_type = 'video'
        WHERE has_video = TRUE AND media_type = 'none';
        """
    )


def downgrade() -> None:
    # Revert to previous media_type for rows we touched
    op.execute(
        """
        UPDATE game_social_posts
        SET media_type = 'none'
        WHERE has_video = TRUE AND media_type = 'video';
        """
    )






