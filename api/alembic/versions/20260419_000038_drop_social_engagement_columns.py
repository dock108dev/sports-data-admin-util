"""drop social engagement columns

Revision ID: 20260419_000038
Revises: 20260418_000037
Create Date: 2026-04-19
"""

from alembic import op

revision = "20260419_000038"
down_revision = "cb_trip_events_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("team_social_posts", "likes_count")
    op.drop_column("team_social_posts", "retweets_count")
    op.drop_column("team_social_posts", "replies_count")


def downgrade() -> None:
    import sqlalchemy as sa

    op.add_column("team_social_posts", sa.Column("replies_count", sa.Integer(), nullable=True))
    op.add_column("team_social_posts", sa.Column("retweets_count", sa.Integer(), nullable=True))
    op.add_column("team_social_posts", sa.Column("likes_count", sa.Integer(), nullable=True))
