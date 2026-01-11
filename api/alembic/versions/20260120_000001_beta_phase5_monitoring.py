"""Beta Phase 5 - Monitoring metadata and safety tables.

Revision ID: 20260120_000001
Revises: 20260115_000002
Create Date: 2026-01-10

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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    games_cols = {col["name"] for col in inspector.get_columns("sports_games")}
    if "last_ingested_at" not in games_cols:
        op.add_column(
            "sports_games",
            sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "last_pbp_at" not in games_cols:
        op.add_column(
            "sports_games",
            sa.Column("last_pbp_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "last_social_at" not in games_cols:
        op.add_column(
            "sports_games",
            sa.Column("last_social_at", sa.DateTime(timezone=True), nullable=True),
        )

    existing_tables = set(inspector.get_table_names())
    if "sports_job_runs" not in existing_tables:
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_phase_started ON sports_job_runs(phase, started_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sports_job_runs_phase ON sports_job_runs(phase)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sports_job_runs_status ON sports_job_runs(status)")

    if "sports_game_conflicts" not in existing_tables:
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_game_conflicts_league_created ON sports_game_conflicts(league_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sports_game_conflicts_game_id ON sports_game_conflicts(game_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sports_game_conflicts_conflict_game_id ON sports_game_conflicts(conflict_game_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sports_game_conflicts_league_id ON sports_game_conflicts(league_id)")

    if "sports_missing_pbp" not in existing_tables:
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_missing_pbp_league_status ON sports_missing_pbp(league_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sports_missing_pbp_game_id ON sports_missing_pbp(game_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sports_missing_pbp_league_id ON sports_missing_pbp(league_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sports_missing_pbp_league_id")
    op.execute("DROP INDEX IF EXISTS ix_sports_missing_pbp_game_id")
    op.execute("DROP INDEX IF EXISTS idx_missing_pbp_league_status")
    op.execute("DROP TABLE IF EXISTS sports_missing_pbp")

    op.execute("DROP INDEX IF EXISTS ix_sports_game_conflicts_league_id")
    op.execute("DROP INDEX IF EXISTS ix_sports_game_conflicts_conflict_game_id")
    op.execute("DROP INDEX IF EXISTS ix_sports_game_conflicts_game_id")
    op.execute("DROP INDEX IF EXISTS idx_game_conflicts_league_created")
    op.execute("DROP TABLE IF EXISTS sports_game_conflicts")

    op.execute("DROP INDEX IF EXISTS ix_sports_job_runs_status")
    op.execute("DROP INDEX IF EXISTS ix_sports_job_runs_phase")
    op.execute("DROP INDEX IF EXISTS idx_job_runs_phase_started")
    op.execute("DROP TABLE IF EXISTS sports_job_runs")

    op.execute("ALTER TABLE sports_games DROP COLUMN IF EXISTS last_social_at")
    op.execute("ALTER TABLE sports_games DROP COLUMN IF EXISTS last_pbp_at")
    op.execute("ALTER TABLE sports_games DROP COLUMN IF EXISTS last_ingested_at")
