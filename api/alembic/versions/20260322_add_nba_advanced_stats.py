"""Add nba_game_advanced_stats and nba_player_advanced_stats tables.

Revision ID: nba_adv_stats_001
Revises: 20260321_nfl_teams
Create Date: 2026-03-22
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "nba_adv_stats_001"
down_revision = "20260321_nfl_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # nba_game_advanced_stats (team-level, 2 rows per game)
    # ------------------------------------------------------------------
    op.create_table(
        "nba_game_advanced_stats",
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
        sa.Column("off_rating", sa.Float(), nullable=True),
        sa.Column("def_rating", sa.Float(), nullable=True),
        sa.Column("net_rating", sa.Float(), nullable=True),
        sa.Column("pace", sa.Float(), nullable=True),
        sa.Column("pie", sa.Float(), nullable=True),
        # Shooting
        sa.Column("efg_pct", sa.Float(), nullable=True),
        sa.Column("ts_pct", sa.Float(), nullable=True),
        sa.Column("fg_pct", sa.Float(), nullable=True),
        sa.Column("fg3_pct", sa.Float(), nullable=True),
        sa.Column("ft_pct", sa.Float(), nullable=True),
        # Rebounding
        sa.Column("orb_pct", sa.Float(), nullable=True),
        sa.Column("drb_pct", sa.Float(), nullable=True),
        sa.Column("reb_pct", sa.Float(), nullable=True),
        # Playmaking
        sa.Column("ast_pct", sa.Float(), nullable=True),
        sa.Column("ast_ratio", sa.Float(), nullable=True),
        sa.Column("ast_tov_ratio", sa.Float(), nullable=True),
        # Ball security
        sa.Column("tov_pct", sa.Float(), nullable=True),
        # Free throws
        sa.Column("ft_rate", sa.Float(), nullable=True),
        # Hustle (team totals)
        sa.Column("contested_shots", sa.Integer(), nullable=True),
        sa.Column("deflections", sa.Integer(), nullable=True),
        sa.Column("charges_drawn", sa.Integer(), nullable=True),
        sa.Column("loose_balls_recovered", sa.Integer(), nullable=True),
        # Paint / transition
        sa.Column("paint_points", sa.Integer(), nullable=True),
        sa.Column("fastbreak_points", sa.Integer(), nullable=True),
        sa.Column("second_chance_points", sa.Integer(), nullable=True),
        sa.Column("points_off_turnovers", sa.Integer(), nullable=True),
        sa.Column("bench_points", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("game_id", "team_id", name="uq_nba_advanced_game_team"),
    )
    op.create_index("idx_nba_advanced_game", "nba_game_advanced_stats", ["game_id"])
    op.create_index("idx_nba_advanced_team", "nba_game_advanced_stats", ["team_id"])

    # ------------------------------------------------------------------
    # nba_player_advanced_stats (player-level)
    # ------------------------------------------------------------------
    op.create_table(
        "nba_player_advanced_stats",
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
        sa.Column("def_rating", sa.Float(), nullable=True),
        sa.Column("net_rating", sa.Float(), nullable=True),
        sa.Column("usg_pct", sa.Float(), nullable=True),
        sa.Column("pie", sa.Float(), nullable=True),
        # Shooting efficiency
        sa.Column("ts_pct", sa.Float(), nullable=True),
        sa.Column("efg_pct", sa.Float(), nullable=True),
        # Shooting context
        sa.Column("contested_2pt_fga", sa.Integer(), nullable=True),
        sa.Column("contested_2pt_fgm", sa.Integer(), nullable=True),
        sa.Column("uncontested_2pt_fga", sa.Integer(), nullable=True),
        sa.Column("uncontested_2pt_fgm", sa.Integer(), nullable=True),
        sa.Column("contested_3pt_fga", sa.Integer(), nullable=True),
        sa.Column("contested_3pt_fgm", sa.Integer(), nullable=True),
        sa.Column("uncontested_3pt_fga", sa.Integer(), nullable=True),
        sa.Column("uncontested_3pt_fgm", sa.Integer(), nullable=True),
        # Pull-up / catch-and-shoot
        sa.Column("pull_up_fga", sa.Integer(), nullable=True),
        sa.Column("pull_up_fgm", sa.Integer(), nullable=True),
        sa.Column("catch_shoot_fga", sa.Integer(), nullable=True),
        sa.Column("catch_shoot_fgm", sa.Integer(), nullable=True),
        # Tracking
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column("touches", sa.Float(), nullable=True),
        sa.Column("time_of_possession", sa.Float(), nullable=True),
        # Hustle
        sa.Column("contested_shots", sa.Integer(), nullable=True),
        sa.Column("deflections", sa.Integer(), nullable=True),
        sa.Column("charges_drawn", sa.Integer(), nullable=True),
        sa.Column("loose_balls_recovered", sa.Integer(), nullable=True),
        sa.Column("screen_assists", sa.Integer(), nullable=True),
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
            name="uq_nba_player_advanced_game_team_player",
        ),
    )
    op.create_index("idx_nba_player_advanced_game", "nba_player_advanced_stats", ["game_id"])
    op.create_index("idx_nba_player_advanced_team", "nba_player_advanced_stats", ["team_id"])


def downgrade() -> None:
    op.drop_index("idx_nba_player_advanced_team", table_name="nba_player_advanced_stats")
    op.drop_index("idx_nba_player_advanced_game", table_name="nba_player_advanced_stats")
    op.drop_table("nba_player_advanced_stats")

    op.drop_index("idx_nba_advanced_team", table_name="nba_game_advanced_stats")
    op.drop_index("idx_nba_advanced_game", table_name="nba_game_advanced_stats")
    op.drop_table("nba_game_advanced_stats")
