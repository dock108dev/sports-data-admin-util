"""Add ncaab_game_advanced_stats and ncaab_player_advanced_stats tables.

Revision ID: ncaab_adv_stats_001
Revises: sim_obs_001
Create Date: 2026-03-22
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "ncaab_adv_stats_001"
down_revision = "nfl_adv_stats_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Team-level four-factor advanced stats ----
    op.create_table(
        "ncaab_game_advanced_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("sports_teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        # Efficiency
        sa.Column("possessions", sa.Float(), nullable=True),
        sa.Column("off_rating", sa.Float(), nullable=True),
        sa.Column("def_rating", sa.Float(), nullable=True),
        sa.Column("net_rating", sa.Float(), nullable=True),
        sa.Column("pace", sa.Float(), nullable=True),
        # Four factors (offense)
        sa.Column("off_efg_pct", sa.Float(), nullable=True),
        sa.Column("off_tov_pct", sa.Float(), nullable=True),
        sa.Column("off_orb_pct", sa.Float(), nullable=True),
        sa.Column("off_ft_rate", sa.Float(), nullable=True),
        # Four factors (defense)
        sa.Column("def_efg_pct", sa.Float(), nullable=True),
        sa.Column("def_tov_pct", sa.Float(), nullable=True),
        sa.Column("def_orb_pct", sa.Float(), nullable=True),
        sa.Column("def_ft_rate", sa.Float(), nullable=True),
        # Shooting splits
        sa.Column("fg_pct", sa.Float(), nullable=True),
        sa.Column("three_pt_pct", sa.Float(), nullable=True),
        sa.Column("ft_pct", sa.Float(), nullable=True),
        sa.Column("three_pt_rate", sa.Float(), nullable=True),
        # Extensibility
        sa.Column(
            "raw_extras",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("game_id", "team_id", name="uq_ncaab_advanced_game_team"),
    )
    op.create_index("idx_ncaab_advanced_game", "ncaab_game_advanced_stats", ["game_id"])
    op.create_index("idx_ncaab_advanced_team", "ncaab_game_advanced_stats", ["team_id"])

    # ---- Player-level advanced stats ----
    op.create_table(
        "ncaab_player_advanced_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("sports_games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("sports_teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("player_external_ref", sa.String(100), nullable=False),
        sa.Column("player_name", sa.String(200), nullable=False),
        # Minutes
        sa.Column("minutes", sa.Float(), nullable=True),
        # Efficiency
        sa.Column("off_rating", sa.Float(), nullable=True),
        sa.Column("usg_pct", sa.Float(), nullable=True),
        # Shooting
        sa.Column("ts_pct", sa.Float(), nullable=True),
        sa.Column("efg_pct", sa.Float(), nullable=True),
        # Impact
        sa.Column("game_score", sa.Float(), nullable=True),
        # Volume
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("rebounds", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("steals", sa.Integer(), nullable=True),
        sa.Column("blocks", sa.Integer(), nullable=True),
        sa.Column("turnovers", sa.Integer(), nullable=True),
        # Extensibility
        sa.Column(
            "raw_extras",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "game_id", "team_id", "player_external_ref",
            name="uq_ncaab_player_advanced_game_team_player",
        ),
    )
    op.create_index("idx_ncaab_player_advanced_game", "ncaab_player_advanced_stats", ["game_id"])
    op.create_index("idx_ncaab_player_advanced_team", "ncaab_player_advanced_stats", ["team_id"])


def downgrade() -> None:
    op.drop_index("idx_ncaab_player_advanced_team", table_name="ncaab_player_advanced_stats")
    op.drop_index("idx_ncaab_player_advanced_game", table_name="ncaab_player_advanced_stats")
    op.drop_table("ncaab_player_advanced_stats")
    op.drop_index("idx_ncaab_advanced_team", table_name="ncaab_game_advanced_stats")
    op.drop_index("idx_ncaab_advanced_game", table_name="ncaab_game_advanced_stats")
    op.drop_table("ncaab_game_advanced_stats")
