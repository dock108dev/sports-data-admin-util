"""Beta Phase 3 - Social account registry and reveal metadata.

Revision ID: 20260115_000001
Revises: 20260108_000001
Create Date: 2026-01-10

This migration:
1. Adds platform to game_social_posts
2. Adds unique constraint on (platform, external_post_id)
3. Creates team_social_accounts registry table
4. Creates social_account_polls cache table
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260115_000001"
down_revision = "20260108_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    posts_cols = {col["name"] for col in inspector.get_columns("game_social_posts")}
    if "platform" not in posts_cols:
        op.add_column(
            "game_social_posts",
            sa.Column("platform", sa.String(length=20), server_default="x", nullable=False),
        )

    # Unique constraint may already exist (baseline schema uses a unique index).
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_social_posts_platform_external_id'
          ) THEN
            ALTER TABLE game_social_posts
              ADD CONSTRAINT uq_social_posts_platform_external_id UNIQUE (platform, external_post_id);
          END IF;
        END $$;
        """
    )

    existing_tables = set(inspector.get_table_names())
    if "team_social_accounts" not in existing_tables:
        op.create_table(
            "team_social_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("league_id", sa.Integer(), nullable=False),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("handle", sa.String(length=100), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["team_id"], ["sports_teams.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["league_id"], ["sports_leagues.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("platform", "handle", name="uq_team_social_accounts_platform_handle"),
            sa.UniqueConstraint("team_id", "platform", name="uq_team_social_accounts_team_platform"),
        )
        op.execute("CREATE INDEX IF NOT EXISTS idx_team_social_accounts_league ON team_social_accounts(league_id)")
        op.execute("CREATE INDEX IF NOT EXISTS idx_team_social_accounts_team_id ON team_social_accounts(team_id)")

    if "social_account_polls" not in existing_tables:
        op.create_table(
            "social_account_polls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("handle", sa.String(length=100), nullable=False),
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("posts_found", sa.Integer(), server_default="0", nullable=False),
            sa.Column("rate_limited_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "platform",
                "handle",
                "window_start",
                "window_end",
                name="uq_social_account_poll_window",
            ),
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_social_account_polls_handle_window ON social_account_polls(handle, window_start, window_end)"
        )
        op.execute("CREATE INDEX IF NOT EXISTS idx_social_account_polls_platform ON social_account_polls(platform)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_social_account_polls_platform")
    op.execute("DROP INDEX IF EXISTS idx_social_account_polls_handle_window")
    op.execute("DROP TABLE IF EXISTS social_account_polls")
    op.execute("DROP INDEX IF EXISTS idx_team_social_accounts_team_id")
    op.execute("DROP INDEX IF EXISTS idx_team_social_accounts_league")
    op.execute("DROP TABLE IF EXISTS team_social_accounts")
    op.execute("ALTER TABLE game_social_posts DROP CONSTRAINT IF EXISTS uq_social_posts_platform_external_id")
    op.execute("ALTER TABLE game_social_posts DROP COLUMN IF EXISTS platform")
