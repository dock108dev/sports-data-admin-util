"""Add entity resolution tracking table.

This table tracks how teams and players are resolved from source identifiers
to internal IDs, enabling:
- Debugging resolution failures
- Auditing resolution decisions
- Identifying ambiguous entities

Revision ID: 20260218_000003
Revises: 20260218_000002
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260218_000003"
down_revision = "20260218_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sports_entity_resolutions" not in existing_tables:
        op.create_table(
            "sports_entity_resolutions",
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
            ),
            sa.Column(
                "entity_type",
                sa.String(length=20),
                nullable=False,
                comment="team or player",
            ),
            # Source identifiers (what the data source provided)
            sa.Column(
                "source_identifier",
                sa.String(length=200),
                nullable=False,
                comment="Original identifier from source (e.g., team abbrev, player name)",
            ),
            sa.Column(
                "source_context",
                postgresql.JSONB(),
                nullable=True,
                comment="Additional source context (e.g., raw_data fields)",
            ),
            # Resolution result
            sa.Column(
                "resolved_id",
                sa.Integer(),
                nullable=True,
                comment="Internal ID if resolved (team_id or future player_id)",
            ),
            sa.Column(
                "resolved_name",
                sa.String(length=200),
                nullable=True,
                comment="Resolved entity name",
            ),
            sa.Column(
                "resolution_status",
                sa.String(length=20),
                nullable=False,
                comment="success, failed, ambiguous, partial",
            ),
            sa.Column(
                "resolution_method",
                sa.String(length=50),
                nullable=True,
                comment="How resolution was performed (exact_match, fuzzy, abbreviation, etc.)",
            ),
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=True,
                comment="Confidence score 0-1 if applicable",
            ),
            # Failure/ambiguity details
            sa.Column(
                "failure_reason",
                sa.String(length=200),
                nullable=True,
                comment="Why resolution failed",
            ),
            sa.Column(
                "candidates",
                postgresql.JSONB(),
                nullable=True,
                comment="Candidate matches if ambiguous",
            ),
            # Occurrence tracking
            sa.Column(
                "occurrence_count",
                sa.Integer(),
                nullable=False,
                default=1,
                comment="How many times this source identifier appeared",
            ),
            sa.Column(
                "first_play_index",
                sa.Integer(),
                nullable=True,
                comment="First play index where this entity appeared",
            ),
            sa.Column(
                "last_play_index",
                sa.Integer(),
                nullable=True,
                comment="Last play index where this entity appeared",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index(
            "idx_entity_resolutions_game",
            "sports_entity_resolutions",
            ["game_id"],
        )
        op.create_index(
            "idx_entity_resolutions_pipeline_run",
            "sports_entity_resolutions",
            ["pipeline_run_id"],
        )
        op.create_index(
            "idx_entity_resolutions_status",
            "sports_entity_resolutions",
            ["resolution_status"],
        )
        op.create_index(
            "idx_entity_resolutions_entity_type",
            "sports_entity_resolutions",
            ["entity_type"],
        )
        op.create_index(
            "idx_entity_resolutions_game_type",
            "sports_entity_resolutions",
            ["game_id", "entity_type"],
        )


def downgrade() -> None:
    op.drop_table("sports_entity_resolutions")
