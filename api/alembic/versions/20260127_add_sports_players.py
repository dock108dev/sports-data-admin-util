"""Add sports_players master table.

Revision ID: 20260127_add_players
Revises: 20260126_000001
Create Date: 2026-01-27

Creates a master players table to link PBP events and boxscores to players.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260127_add_players"
down_revision = "20260127_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create sports_players table and add FK to plays."""
    conn = op.get_bind()

    # Check if table already exists (created by initial schema baseline)
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sports_players')"
    ))
    table_exists = result.scalar()

    if not table_exists:
        # Create master players table
        op.create_table(
        "sports_players",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("position", sa.String(10), nullable=True),
        sa.Column("sweater_number", sa.Integer(), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),  # Current team
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["league_id"], ["sports_leagues.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["sports_teams.id"]),
        sa.UniqueConstraint("league_id", "external_id", name="uq_player_identity"),
    )
        op.create_index("idx_players_external_id", "sports_players", ["external_id"])
        op.create_index("idx_players_name", "sports_players", ["name"])

    # Check if column already exists
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'sports_game_plays' AND column_name = 'player_ref_id')"
    ))
    if result.scalar():
        return  # Column already exists

    # Add FK column to plays (nullable for now, will backfill)
    op.add_column(
        "sports_game_plays",
        sa.Column("player_ref_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_plays_player",
        "sports_game_plays",
        "sports_players",
        ["player_ref_id"],
        ["id"],
    )
    op.create_index("idx_plays_player_ref", "sports_game_plays", ["player_ref_id"])


def downgrade() -> None:
    """Remove sports_players table and FK from plays."""
    op.drop_index("idx_plays_player_ref", table_name="sports_game_plays")
    op.drop_constraint("fk_plays_player", "sports_game_plays", type_="foreignkey")
    op.drop_column("sports_game_plays", "player_ref_id")
    op.drop_index("idx_players_name", table_name="sports_players")
    op.drop_index("idx_players_external_id", table_name="sports_players")
    op.drop_table("sports_players")
