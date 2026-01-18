"""Add PBP snapshots table for inspectable ingestion.

This table stores snapshots of play-by-play data at different stages:
- Raw PBP as received from the data source
- Normalized PBP after processing
- Tied to pipeline runs for auditability

Revision ID: 20260218_000002
Revises: 20260218_000001
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260218_000002"
down_revision = "20260218_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_pbp_snapshots" not in existing_tables:
        op.create_table(
            "sports_pbp_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "game_id",
                sa.Integer(),
                sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "pipeline_run_id",
                sa.Integer(),
                sa.ForeignKey("sports_game_pipeline_runs.id", ondelete="SET NULL"),
                nullable=True,
                comment="Pipeline run that created this snapshot (null for scrape-time snapshots)",
            ),
            sa.Column(
                "scrape_run_id",
                sa.Integer(),
                sa.ForeignKey("sports_scrape_runs.id", ondelete="SET NULL"),
                nullable=True,
                comment="Scrape run that created this snapshot (for raw PBP)",
            ),
            sa.Column(
                "snapshot_type",
                sa.String(length=20),
                nullable=False,
                comment="raw, normalized, or resolved",
            ),
            sa.Column(
                "source",
                sa.String(length=50),
                nullable=True,
                comment="Data source (e.g., nba_live, nhl_api, sportsref)",
            ),
            sa.Column(
                "play_count",
                sa.Integer(),
                nullable=False,
                default=0,
            ),
            sa.Column(
                "plays_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
                comment="Array of play objects",
            ),
            sa.Column(
                "metadata_json",
                postgresql.JSONB(),
                nullable=True,
                server_default=sa.text("'{}'::jsonb"),
                comment="Snapshot metadata (game timing, resolution stats, etc.)",
            ),
            sa.Column(
                "resolution_stats",
                postgresql.JSONB(),
                nullable=True,
                comment="Stats on team/player/score resolution",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index(
            "idx_pbp_snapshots_game",
            "sports_pbp_snapshots",
            ["game_id"],
        )
        op.create_index(
            "idx_pbp_snapshots_pipeline_run",
            "sports_pbp_snapshots",
            ["pipeline_run_id"],
        )
        op.create_index(
            "idx_pbp_snapshots_type",
            "sports_pbp_snapshots",
            ["snapshot_type"],
        )
        op.create_index(
            "idx_pbp_snapshots_game_type",
            "sports_pbp_snapshots",
            ["game_id", "snapshot_type"],
        )


def downgrade() -> None:
    op.drop_table("sports_pbp_snapshots")
