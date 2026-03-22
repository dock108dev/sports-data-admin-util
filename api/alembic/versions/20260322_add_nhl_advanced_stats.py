"""Add NHL advanced stats tables (team, skater, goalie).

Revision ID: nhl_adv_stats_001
Revises: sim_obs_001
Create Date: 2026-03-22
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "nhl_adv_stats_001"
down_revision = "nba_adv_stats_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- nhl_game_advanced_stats (team-level, 2 rows per game) ----
    op.create_table(
        "nhl_game_advanced_stats",
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
        # Shot quality (xGoals)
        sa.Column("xgoals_for", sa.Float(), nullable=True),
        sa.Column("xgoals_against", sa.Float(), nullable=True),
        sa.Column("xgoals_pct", sa.Float(), nullable=True),
        # Possession (Corsi)
        sa.Column("corsi_for", sa.Integer(), nullable=True),
        sa.Column("corsi_against", sa.Integer(), nullable=True),
        sa.Column("corsi_pct", sa.Float(), nullable=True),
        # Possession (Fenwick)
        sa.Column("fenwick_for", sa.Integer(), nullable=True),
        sa.Column("fenwick_against", sa.Integer(), nullable=True),
        sa.Column("fenwick_pct", sa.Float(), nullable=True),
        # Shooting
        sa.Column("shots_for", sa.Integer(), nullable=True),
        sa.Column("shots_against", sa.Integer(), nullable=True),
        sa.Column("shooting_pct", sa.Float(), nullable=True),
        sa.Column("save_pct", sa.Float(), nullable=True),
        sa.Column("pdo", sa.Float(), nullable=True),
        # Danger zones
        sa.Column("high_danger_shots_for", sa.Integer(), nullable=True),
        sa.Column("high_danger_goals_for", sa.Integer(), nullable=True),
        sa.Column("high_danger_shots_against", sa.Integer(), nullable=True),
        sa.Column("high_danger_goals_against", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("game_id", "team_id", name="uq_nhl_advanced_game_team"),
    )
    op.create_index("idx_nhl_advanced_game", "nhl_game_advanced_stats", ["game_id"])
    op.create_index("idx_nhl_advanced_team", "nhl_game_advanced_stats", ["team_id"])

    # ---- nhl_skater_advanced_stats (skater-level) ----
    op.create_table(
        "nhl_skater_advanced_stats",
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
        # xGoals
        sa.Column("xgoals_for", sa.Float(), nullable=True),
        sa.Column("xgoals_against", sa.Float(), nullable=True),
        sa.Column("on_ice_xgoals_pct", sa.Float(), nullable=True),
        # Shots
        sa.Column("shots", sa.Integer(), nullable=True),
        sa.Column("goals", sa.Integer(), nullable=True),
        sa.Column("shooting_pct", sa.Float(), nullable=True),
        # Per-60 rates
        sa.Column("goals_per_60", sa.Float(), nullable=True),
        sa.Column("assists_per_60", sa.Float(), nullable=True),
        sa.Column("points_per_60", sa.Float(), nullable=True),
        sa.Column("shots_per_60", sa.Float(), nullable=True),
        # Impact
        sa.Column("game_score", sa.Float(), nullable=True),
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
            name="uq_nhl_skater_advanced_game_team_player",
        ),
    )
    op.create_index("idx_nhl_skater_advanced_game", "nhl_skater_advanced_stats", ["game_id"])
    op.create_index("idx_nhl_skater_advanced_team", "nhl_skater_advanced_stats", ["team_id"])

    # ---- nhl_goalie_advanced_stats (goalie-level) ----
    op.create_table(
        "nhl_goalie_advanced_stats",
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
        # Core
        sa.Column("xgoals_against", sa.Float(), nullable=True),
        sa.Column("goals_against", sa.Integer(), nullable=True),
        sa.Column("goals_saved_above_expected", sa.Float(), nullable=True),
        sa.Column("save_pct", sa.Float(), nullable=True),
        # Danger zone saves
        sa.Column("high_danger_save_pct", sa.Float(), nullable=True),
        sa.Column("medium_danger_save_pct", sa.Float(), nullable=True),
        sa.Column("low_danger_save_pct", sa.Float(), nullable=True),
        sa.Column("shots_against", sa.Integer(), nullable=True),
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
            "game_id", "player_external_ref",
            name="uq_nhl_goalie_advanced_game_player",
        ),
    )
    op.create_index("idx_nhl_goalie_advanced_game", "nhl_goalie_advanced_stats", ["game_id"])
    op.create_index("idx_nhl_goalie_advanced_player", "nhl_goalie_advanced_stats", ["player_external_ref"])


def downgrade() -> None:
    op.drop_index("idx_nhl_goalie_advanced_player", table_name="nhl_goalie_advanced_stats")
    op.drop_index("idx_nhl_goalie_advanced_game", table_name="nhl_goalie_advanced_stats")
    op.drop_table("nhl_goalie_advanced_stats")

    op.drop_index("idx_nhl_skater_advanced_team", table_name="nhl_skater_advanced_stats")
    op.drop_index("idx_nhl_skater_advanced_game", table_name="nhl_skater_advanced_stats")
    op.drop_table("nhl_skater_advanced_stats")

    op.drop_index("idx_nhl_advanced_team", table_name="nhl_game_advanced_stats")
    op.drop_index("idx_nhl_advanced_game", table_name="nhl_game_advanced_stats")
    op.drop_table("nhl_game_advanced_stats")
