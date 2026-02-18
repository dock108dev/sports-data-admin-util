"""Seed missing NCAAB teams and populate cbb_team_id.

Seven HBCU/mid-major teams were missing from _NCAAB_TEAM_DATA and the
sports_teams table, causing the Odds API ingestion pipeline to match
them to wrong Power conference teams (e.g., Alabama A&M -> Alabama).

This migration:
1. Inserts the 7 missing teams with correct external_codes.cbb_team_id
2. Backfills cbb_team_id for any existing rows that were created by
   odds ingestion before the team was properly seeded

Revision ID: 20260217_000002
Revises: 20260217_000001
Create Date: 2026-02-17
"""

from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text

revision = "20260217_000002"
down_revision = "20260217_000001"
branch_labels = None
depends_on = None

# (canonical_name, short_name, abbreviation, cbb_team_id)
MISSING_TEAMS = [
    ("Alabama A&M Bulldogs", "Alabama A&M", "AAMU", 4),
    ("Coppin St Eagles", "Coppin St", "COPP", 59),
    ("Grambling St Tigers", "Grambling St", "GRAM", 103),
    ("Howard Bison", "Howard", "HOW", 114),
    ("Maryland-Eastern Shore Hawks", "Maryland-Eastern Shore", "UMES", 159),
    ("North Carolina Central Eagles", "North Carolina Central", "NCCU", 199),
    ("Texas Southern Tigers", "Texas Southern", "TXSO", 296),
]


def upgrade() -> None:
    """Insert missing NCAAB teams and backfill cbb_team_id."""
    conn = op.get_bind()

    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        print("NCAAB league not found — skipping")
        return
    league_id = row[0]

    upsert_stmt = text("""
        INSERT INTO sports_teams (league_id, name, short_name, abbreviation, external_codes)
        VALUES (:lid, :name, :short_name, :abbr, CAST(:codes AS jsonb))
        ON CONFLICT (league_id, name) DO UPDATE SET
            short_name = EXCLUDED.short_name,
            abbreviation = EXCLUDED.abbreviation,
            external_codes = sports_teams.external_codes || EXCLUDED.external_codes
    """)

    for name, short_name, abbr, cbb_team_id in MISSING_TEAMS:
        codes = json.dumps({"cbb_team_id": cbb_team_id})
        conn.execute(upsert_stmt, {
            "lid": league_id,
            "name": name,
            "short_name": short_name,
            "abbr": abbr,
            "codes": codes,
        })
        print(f"  Upserted {name} (cbb_team_id={cbb_team_id})")

    print(f"Seeded/updated {len(MISSING_TEAMS)} missing NCAAB teams")


def downgrade() -> None:
    """Remove the 7 teams added by this migration."""
    conn = op.get_bind()

    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        return

    names = [t[0] for t in MISSING_TEAMS]
    conn.execute(
        text(
            "DELETE FROM sports_teams WHERE league_id = :lid AND name = ANY(:names)"
        ),
        {"lid": row[0], "names": names},
    )
