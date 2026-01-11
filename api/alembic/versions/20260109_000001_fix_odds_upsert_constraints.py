"""Fix odds upsert constraints (side length + unique index).

Revision ID: 20260109_000001
Revises: 20260120_000001
Create Date: 2026-01-09

Why:
- Scraper upsert uses ON CONFLICT(game_id, book, market_type, side, is_closing_line)
  but the DB had a UNIQUE index missing `side`, causing InvalidColumnReference.
- `side` was VARCHAR(20), too small for team names (e.g. "Golden State Warriors").
"""

from alembic import op
import sqlalchemy as sa


revision = "20260109_000001"
down_revision = "20260120_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Widen side so it can store team names / "Over" / "Under" safely.
    # Some baselines already have a wider column; keep it safe/idempotent.
    op.execute(
        """
        DO $$
        DECLARE
          current_len integer;
        BEGIN
          SELECT character_maximum_length
          INTO current_len
          FROM information_schema.columns
          WHERE table_name = 'sports_game_odds'
            AND column_name = 'side';

          -- If it's a varchar and smaller than 100, widen it.
          IF current_len IS NOT NULL AND current_len < 100 THEN
            ALTER TABLE sports_game_odds ALTER COLUMN side TYPE varchar(100);
          END IF;
        END $$;
        """
    )

    # 2) Align unique index with upsert ON CONFLICT target.
    # Drop/recreate safely; if it's already correct, CREATE INDEX IF NOT EXISTS is a no-op.
    op.execute("DROP INDEX IF EXISTS uq_sports_game_odds_identity")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sports_game_odds_identity ON sports_game_odds(game_id, book, market_type, side, is_closing_line)"
    )


def downgrade() -> None:
    # Best-effort downgrade (dev only): re-create the older index shape.
    op.execute("DROP INDEX IF EXISTS uq_sports_game_odds_identity")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sports_game_odds_identity ON sports_game_odds(game_id, book, market_type, is_closing_line)"
    )

