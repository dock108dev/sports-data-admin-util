"""Add OpenAI response cache table.

Revision ID: 20260127_000003
Revises: 20260127_000002
Create Date: 2026-01-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260127_000003"
down_revision = "20260127_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openai_response_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_key", sa.String(64), nullable=False),
        sa.Column("prompt_preview", sa.Text(), nullable=True),
        sa.Column("response_json", JSONB(), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_openai_cache_game_batch",
        "openai_response_cache",
        ["game_id", "batch_key"],
    )
    op.create_index(
        "idx_openai_cache_game_id",
        "openai_response_cache",
        ["game_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_openai_cache_game_id")
    op.drop_constraint("uq_openai_cache_game_batch", "openai_response_cache")
    op.drop_table("openai_response_cache")
