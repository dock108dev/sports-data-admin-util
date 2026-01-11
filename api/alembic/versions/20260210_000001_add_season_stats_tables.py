"""Add season-level team and player stats tables.

Revision ID: 20260210_000001
Revises: 20260120_000001
Create Date: 2026-01-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260210_000001"
down_revision = "20260120_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_team_season_stats" not in existing_tables:
        op.create_table(
            "sports_team_season_stats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("season_type", sa.String(length=50), nullable=False),
            sa.Column("raw_stats_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("team_id", "season", "season_type", "source", name="uq_team_season_stat_identity"),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_season_stats_team_season ON sports_team_season_stats(team_id, season)"
    )

    if "sports_player_season_stats" not in existing_tables:
        op.create_table(
            "sports_player_season_stats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("league_id", sa.Integer(), sa.ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("sports_teams.id", ondelete="SET NULL"), nullable=True),
            sa.Column("team_abbreviation", sa.String(length=20), nullable=True),
            sa.Column("player_external_ref", sa.String(length=100), nullable=False),
            sa.Column("player_name", sa.String(length=200), nullable=False),
            sa.Column("position", sa.String(length=20), nullable=True),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("season_type", sa.String(length=50), nullable=False),
            sa.Column("raw_stats_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint(
                "league_id",
                "player_external_ref",
                "season",
                "season_type",
                "team_abbreviation",
                "source",
                name="uq_player_season_stat_identity",
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_season_stats_league_season ON sports_player_season_stats(league_id, season)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_player_season_stats_league_season")
    op.execute("DROP TABLE IF EXISTS sports_player_season_stats")
    op.execute("DROP INDEX IF EXISTS idx_team_season_stats_team_season")
    op.execute("DROP TABLE IF EXISTS sports_team_season_stats")
