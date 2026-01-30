"""Add missing NCAAB team cbb_team_id mappings.

28 teams were not matched by the automated migration due to naming
differences between our database and the CBB API. This migration
adds manual mappings for these teams.

Revision ID: 20260130_000002
Revises: 20260130_000001
Create Date: 2026-01-30
"""

from __future__ import annotations

import json
from alembic import op
from sqlalchemy import text

revision = "20260130_000002"
down_revision = "20260130_000001"
branch_labels = None
depends_on = None

# Manual mappings: DB team name (normalized) -> CBB API team ID
# These teams have naming differences between our database and the CBB API
MANUAL_MAPPINGS = {
    # University abbreviations
    "albany great danes": 306,  # UAlbany Great Danes
    "american eagles": 8,  # American University Eagles
    "boston univ terriers": 27,  # Boston University Terriers

    # State/school name variations
    "appalachian st mountaineers": 9,  # App State Mountaineers
    "arkansas little rock trojans": 144,  # Little Rock Trojans
    "fort wayne mastodons": 237,  # Purdue Fort Wayne Mastodons
    "long beach st 49ers": 145,  # Long Beach State Beach (mascot changed)
    "sam houston st bearkats": 255,  # Sam Houston Bearkats
    "se missouri st redhawks": 272,  # Southeast Missouri State Redhawks
    "n colorado bears": 207,  # Northern Colorado Bears
    "nicholls st colonels": 195,  # Nicholls Colonels
    "tenn martin skyhawks": 325,  # UT Martin Skyhawks
    "miss valley st delta devils": 175,  # Mississippi Valley State Delta Devils

    # CSU variations
    "csu bakersfield roadrunners": 36,  # Cal State Bakersfield Roadrunners
    "csu fullerton titans": 37,  # Cal State Fullerton Titans
    "csu northridge matadors": 38,  # Cal State Northridge Matadors

    # School name changes/abbreviations
    "cal baptist lancers": 39,  # California Baptist Lancers
    "central connecticut st blue devils": 44,  # Central Connecticut Blue Devils
    "gw revolutionaries": 96,  # George Washington Revolutionaries
    "iupui jaguars": 115,  # IU Indianapolis Jaguars (IUPUI became IU Indianapolis)
    "liu sharks": 146,  # Long Island University Sharks
    "umkc kangaroos": 130,  # Kansas City Roos (name changed)
    "texas a m cc islanders": 294,  # Texas A&M-Corpus Christi Islanders
    "prairie view panthers": 232,  # Prairie View A&M Panthers

    # Loyola campuses
    "loyola chi ramblers": 151,  # Loyola Chicago Ramblers
    "loyola md greyhounds": 152,  # Loyola Maryland Greyhounds

    # Other
    "seattle redhawks": 262,  # Seattle U Redhawks
    "st thomas mn tommies": 280,  # St. Thomas-Minnesota Tommies
}


def _normalize(name: str) -> str:
    """Normalize team name for matching."""
    n = name.lower().strip()
    # Remove punctuation
    n = n.replace("'", "").replace(".", "").replace("-", " ").replace("&", " ").replace("(", " ").replace(")", " ")
    # Collapse whitespace
    return " ".join(n.split())


def upgrade() -> None:
    """Add cbb_team_id for teams missing it."""
    conn = op.get_bind()

    # Get NCAAB league
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        print("NCAAB league not found")
        return
    league_id = row[0]

    # Get teams without cbb_team_id
    result = conn.execute(text("""
        SELECT id, name, external_codes
        FROM sports_teams
        WHERE league_id = :lid
        AND (external_codes IS NULL OR NOT external_codes ? 'cbb_team_id')
    """), {"lid": league_id})

    teams_without_mapping = result.fetchall()
    print(f"Found {len(teams_without_mapping)} teams without cbb_team_id")

    update_stmt = text(
        "UPDATE sports_teams SET external_codes = CAST(:codes AS jsonb) WHERE id = :id"
    )

    updated = 0
    unmatched = []

    for team_id, team_name, ext_codes in teams_without_mapping:
        normalized = _normalize(team_name)

        if normalized in MANUAL_MAPPINGS:
            cbb_team_id = MANUAL_MAPPINGS[normalized]
            codes = dict(ext_codes) if ext_codes else {}
            codes["cbb_team_id"] = cbb_team_id
            conn.execute(update_stmt, {"codes": json.dumps(codes), "id": team_id})
            updated += 1
            print(f"  Mapped: {team_name} -> {cbb_team_id}")
        else:
            unmatched.append((team_name, normalized))

    print(f"\nUpdated {updated} teams")
    if unmatched:
        print(f"Still unmatched ({len(unmatched)}):")
        for name, norm in unmatched:
            print(f"  {name} -> '{norm}'")


def downgrade() -> None:
    """Remove cbb_team_id from manually mapped teams."""
    conn = op.get_bind()
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        return

    # Get all manually mapped team IDs
    cbb_ids = list(MANUAL_MAPPINGS.values())

    # Remove cbb_team_id where it matches our manual mappings
    conn.execute(text("""
        UPDATE sports_teams
        SET external_codes = external_codes - 'cbb_team_id'
        WHERE league_id = :lid
        AND (external_codes->>'cbb_team_id')::int = ANY(:cbb_ids)
    """), {"lid": row[0], "cbb_ids": cbb_ids})
