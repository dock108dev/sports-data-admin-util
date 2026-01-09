"""Beta Phase 5 - Monitoring metadata and safety tables.

Revision ID: 20260120_000001
Revises: 20260115_000002
Create Date: 2026-01-20

Adds per-game update timestamps, job run tracking, conflict guards, and PBP gap records.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260120_000001"
down_revision = "20260115_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sports_games",
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sports_games",
        sa.Column("last_pbp_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sports_games",
        sa.Column("last_social_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "sports_job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phase", sa.String(length=50), nullable=False),
        sa.Column(
            "leagues",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_job_runs_phase_started", "sports_job_runs", ["phase", "started_at"])
    op.create_index("ix_sports_job_runs_phase", "sports_job_runs", ["phase"])
    op.create_index("ix_sports_job_runs_status", "sports_job_runs", ["status"])

    op.create_table(
        "sports_game_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conflict_game_id", sa.Integer(), sa.ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column(
            "conflict_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("game_id", "conflict_game_id", "external_id", "source", name="uq_game_conflict"),
    )
    op.create_index("idx_game_conflicts_league_created", "sports_game_conflicts", ["league_id", "created_at"])
    op.create_index("ix_sports_game_conflicts_game_id", "sports_game_conflicts", ["game_id"])
    op.create_index("ix_sports_game_conflicts_conflict_game_id", "sports_game_conflicts", ["conflict_game_id"])
    op.create_index("ix_sports_game_conflicts_league_id", "sports_game_conflicts", ["league_id"])

    op.create_table(
        "sports_missing_pbp",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("game_id", name="uq_missing_pbp_game"),
    )
    op.create_index("idx_missing_pbp_league_status", "sports_missing_pbp", ["league_id", "status"])
    op.create_index("ix_sports_missing_pbp_game_id", "sports_missing_pbp", ["game_id"])
    op.create_index("ix_sports_missing_pbp_league_id", "sports_missing_pbp", ["league_id"])


def downgrade() -> None:
    op.drop_index("ix_sports_missing_pbp_league_id", table_name="sports_missing_pbp")
    op.drop_index("ix_sports_missing_pbp_game_id", table_name="sports_missing_pbp")
    op.drop_index("idx_missing_pbp_league_status", table_name="sports_missing_pbp")
    op.drop_table("sports_missing_pbp")

    op.drop_index("ix_sports_game_conflicts_league_id", table_name="sports_game_conflicts")
    op.drop_index("ix_sports_game_conflicts_conflict_game_id", table_name="sports_game_conflicts")
    op.drop_index("ix_sports_game_conflicts_game_id", table_name="sports_game_conflicts")
    op.drop_index("idx_game_conflicts_league_created", table_name="sports_game_conflicts")
    op.drop_table("sports_game_conflicts")

    op.drop_index("ix_sports_job_runs_status", table_name="sports_job_runs")
    op.drop_index("ix_sports_job_runs_phase", table_name="sports_job_runs")
    op.drop_index("idx_job_runs_phase_started", table_name="sports_job_runs")
    op.drop_table("sports_job_runs")

    op.drop_column("sports_games", "last_social_at")
    op.drop_column("sports_games", "last_pbp_at")
    op.drop_column("sports_games", "last_ingested_at")
