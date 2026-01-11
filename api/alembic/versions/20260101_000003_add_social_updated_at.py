"""Add updated_at to game_social_posts."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260101_000003"
down_revision = "20260101_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some "baseline" schemas already include this column. Keep the migration
    # idempotent so fresh Docker volumes can be initialized reliably.
    inspector = sa.inspect(op.get_bind())
    existing_cols = {col["name"] for col in inspector.get_columns("game_social_posts")}
    if "updated_at" not in existing_cols:
        op.add_column(
            "game_social_posts",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute(
        "UPDATE game_social_posts SET updated_at = '2025-12-26 00:00:00+00' WHERE updated_at IS NULL"
    )
    op.alter_column("game_social_posts", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("game_social_posts", "updated_at")






