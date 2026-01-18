"""Add immutable frontend payload versions table.

This table stores immutable snapshots of what the frontend receives.
Each pipeline run creates a NEW version - payloads are NEVER mutated.

Key design principles:
1. IMMUTABILITY - Once created, a payload version is never modified
2. TRACEABILITY - Every payload links to its pipeline run
3. HISTORY - All historical payloads are preserved for debugging
4. ACTIVE FLAG - Only one version is "active" at a time per game

Revision ID: 20260218_000004
Revises: 20260218_000003
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260218_000004"
down_revision = "20260218_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_frontend_payload_versions" not in existing_tables:
        op.create_table(
            "sports_frontend_payload_versions",
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
                comment="Pipeline run that created this version",
            ),
            # Version tracking
            sa.Column(
                "version_number",
                sa.Integer(),
                nullable=False,
                comment="Auto-incrementing version number per game",
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default="false",
                comment="True if this is the currently active version for the frontend",
            ),
            # Payload content (IMMUTABLE once created)
            sa.Column(
                "payload_hash",
                sa.String(length=64),
                nullable=False,
                comment="SHA-256 hash of payload for change detection",
            ),
            sa.Column(
                "timeline_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
                comment="Timeline events (PBP + social)",
            ),
            sa.Column(
                "moments_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
                comment="Generated moments",
            ),
            sa.Column(
                "summary_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
                comment="Game summary for frontend",
            ),
            # Metadata
            sa.Column(
                "event_count",
                sa.Integer(),
                nullable=False,
                default=0,
            ),
            sa.Column(
                "moment_count",
                sa.Integer(),
                nullable=False,
                default=0,
            ),
            sa.Column(
                "generation_source",
                sa.String(length=50),
                nullable=True,
                comment="pipeline, manual, backfill, etc.",
            ),
            sa.Column(
                "generation_notes",
                sa.Text(),
                nullable=True,
                comment="Any notes about this generation",
            ),
            # Change tracking
            sa.Column(
                "diff_from_previous",
                postgresql.JSONB(),
                nullable=True,
                comment="Summary of changes from previous version",
            ),
            # Timestamps
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            # NOTE: No updated_at - payloads are IMMUTABLE
        )
        op.create_index(
            "idx_frontend_payload_game",
            "sports_frontend_payload_versions",
            ["game_id"],
        )
        op.create_index(
            "idx_frontend_payload_pipeline_run",
            "sports_frontend_payload_versions",
            ["pipeline_run_id"],
        )
        op.create_index(
            "idx_frontend_payload_active",
            "sports_frontend_payload_versions",
            ["game_id", "is_active"],
            postgresql_where=sa.text("is_active = true"),
        )
        op.create_index(
            "idx_frontend_payload_version",
            "sports_frontend_payload_versions",
            ["game_id", "version_number"],
        )
        # Unique constraint: only one active version per game
        op.create_index(
            "idx_frontend_payload_unique_active",
            "sports_frontend_payload_versions",
            ["game_id"],
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        )


def downgrade() -> None:
    op.drop_table("sports_frontend_payload_versions")
