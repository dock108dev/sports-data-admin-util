"""add media_type check constraint on team_social_posts

Revision ID: 20260419_000039
Revises: 20260419_000038
Create Date: 2026-04-19
"""

from alembic import op

revision = "20260419_000039"
down_revision = "20260419_000038"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_team_social_posts_media_type"
_TABLE = "team_social_posts"


def upgrade() -> None:
    # Backfill any out-of-range values to NULL before adding the constraint.
    op.execute(
        f"UPDATE {_TABLE} SET media_type = NULL "
        "WHERE media_type IS NOT NULL AND media_type NOT IN ('video', 'image')"
    )
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "media_type IS NULL OR media_type IN ('video', 'image')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
