"""Fix source_game_key constraint to be per-league unique.

Revision ID: 20260125_000001
Revises: 20260124_000001
Create Date: 2026-01-25

Why:
- The original constraint was UNIQUE(source_game_key) globally
- This caused collisions between leagues that share team abbreviations
- Example: NBA Minnesota Timberwolves (MIN) vs NHL Minnesota Wild (MIN)
  both generate source_game_key "202601220MIN" for games on the same date
- The fix makes source_game_key unique per league: UNIQUE(league_id, source_game_key)

Affected abbreviations across leagues:
- MIN: Timberwolves (NBA), Wild (NHL), Twins (MLB)
- ARI: Diamondbacks (MLB), Cardinals (NFL)
- DEN: Nuggets (NBA), Broncos (NFL)
- LAC: Clippers (NBA), Chargers (NFL)
- PHI: 76ers (NBA), Eagles (NFL), Phillies (MLB), Flyers (NHL)
"""

from alembic import op


revision = "20260125_000001"
down_revision = "20260124_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the global unique constraint on source_game_key
    op.execute("ALTER TABLE sports_games DROP CONSTRAINT IF EXISTS uq_sports_game_source_key")

    # Create composite unique constraint (per-league uniqueness)
    # This allows the same source_game_key in different leagues
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_sports_game_league_source_key'
            ) THEN
                ALTER TABLE sports_games
                ADD CONSTRAINT uq_sports_game_league_source_key
                UNIQUE (league_id, source_game_key);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Revert to global unique constraint (may fail if duplicates exist)
    op.execute("ALTER TABLE sports_games DROP CONSTRAINT IF EXISTS uq_sports_game_league_source_key")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_sports_game_source_key'
            ) THEN
                ALTER TABLE sports_games
                ADD CONSTRAINT uq_sports_game_source_key
                UNIQUE (source_game_key);
            END IF;
        END $$;
        """
    )
