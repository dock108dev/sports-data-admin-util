"""Re-populate NCAAB CBB team IDs after fixing docker-compose env.

Previous migrations failed because CBB_STATS_API_KEY wasn't passed to
the migrate container. Now that docker-compose.yml includes the key,
this migration re-runs the population.

Revision ID: 20260130_000001
Revises: 20260129_000001
Create Date: 2026-01-30
"""

from __future__ import annotations

import json
import os
import re
import httpx
from alembic import op
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260130_000001"
down_revision = "20260129_000001"
branch_labels = None
depends_on = None

CBB_API_BASE = "https://api.collegebasketballdata.com"
CBB_API_KEY = os.environ.get("CBB_STATS_API_KEY", "")


def _normalize_strict(name: str) -> str:
    """Normalize team name for strict matching."""
    n = name.lower().strip()
    n = n.replace("'", "").replace(".", "").replace("-", " ").replace("&", "and")
    return " ".join(n.split())


def _normalize_with_expansions(name: str) -> str:
    """Normalize with common abbreviation expansions."""
    n = _normalize_strict(name)
    subs = [
        (r"\bst\b", "state"),
        (r"\bmt\b", "mount"),
    ]
    for p, r in subs:
        n = re.sub(p, r, n)
    return n


MANUAL_MAPPINGS = {
    "florida intl golden panthers": 89,
    "florida international golden panthers": 89,
}


def upgrade() -> None:
    """Populate cbb_team_id for NCAAB teams."""
    conn = op.get_bind()

    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        print("NCAAB league not found")
        return
    league_id = row[0]

    # Check if already populated
    result = conn.execute(text(
        "SELECT COUNT(*) FROM sports_teams WHERE league_id = :lid AND external_codes ? 'cbb_team_id'"
    ), {"lid": league_id})
    existing = result.fetchone()[0]
    if existing > 100:
        print(f"Already have {existing} teams with cbb_team_id, skipping")
        return

    print(f"CBB_STATS_API_KEY present: {bool(CBB_API_KEY)}")
    if not CBB_API_KEY:
        print("WARNING: CBB_STATS_API_KEY not set - migration will fail!")
        return

    # Clear any partial mappings
    print("Clearing existing cbb_team_id mappings...")
    conn.execute(text(
        "UPDATE sports_teams SET external_codes = external_codes - 'cbb_team_id' WHERE league_id = :lid"
    ), {"lid": league_id})

    print("Fetching CBB teams from API...")
    headers = {"Authorization": f"Bearer {CBB_API_KEY}"}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{CBB_API_BASE}/teams", params={"season": 2026}, headers=headers)
            resp.raise_for_status()
            cbb_teams = resp.json()
        print(f"Fetched {len(cbb_teams)} CBB teams")
    except Exception as e:
        print(f"API fetch failed: {e}")
        raise  # Fail the migration so it can be retried

    cbb_by_exact: dict[str, dict] = {}
    cbb_by_expanded: dict[str, dict] = {}

    for t in cbb_teams:
        display = t.get("displayName", "")
        school = t.get("school", "")
        mascot = t.get("mascot", "")
        full_name = f"{school} {mascot}".strip()

        for name in [display, school, full_name]:
            if name:
                strict = _normalize_strict(name)
                expanded = _normalize_with_expansions(name)
                cbb_by_exact[strict] = t
                if expanded != strict:
                    cbb_by_expanded[expanded] = t

    result = conn.execute(text(
        "SELECT id, name, external_codes FROM sports_teams WHERE league_id = :lid"
    ), {"lid": league_id})
    db_teams = result.fetchall()
    print(f"Found {len(db_teams)} DB teams")

    matched, unmatched = 0, []

    # Prepare the update statement with proper JSONB type binding
    update_stmt = text(
        "UPDATE sports_teams SET external_codes = CAST(:codes AS jsonb) WHERE id = :id"
    )

    for team_id, team_name, ext_codes in db_teams:
        db_strict = _normalize_strict(team_name)
        db_expanded = _normalize_with_expansions(team_name)

        cbb_team_id = None

        if db_strict in MANUAL_MAPPINGS:
            cbb_team_id = MANUAL_MAPPINGS[db_strict]
        elif db_strict in cbb_by_exact:
            cbb_team_id = cbb_by_exact[db_strict]["id"]
        elif db_expanded in cbb_by_exact:
            cbb_team_id = cbb_by_exact[db_expanded]["id"]
        elif db_expanded in cbb_by_expanded:
            cbb_team_id = cbb_by_expanded[db_expanded]["id"]

        if not cbb_team_id:
            words = db_strict.split()
            if len(words) > 1:
                school_only = " ".join(words[:-1])
                if school_only in cbb_by_exact:
                    cbb_team_id = cbb_by_exact[school_only]["id"]

        if cbb_team_id:
            codes = dict(ext_codes) if ext_codes else {}
            codes["cbb_team_id"] = cbb_team_id
            conn.execute(update_stmt, {"codes": json.dumps(codes), "id": team_id})
            matched += 1
        else:
            unmatched.append(team_name)

    print(f"\nResults: Matched {matched}, Unmatched {len(unmatched)}")
    if unmatched and len(unmatched) <= 20:
        print(f"Unmatched: {unmatched}")


def downgrade() -> None:
    """Remove cbb_team_id from NCAAB teams."""
    conn = op.get_bind()
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if row:
        conn.execute(text(
            "UPDATE sports_teams SET external_codes = external_codes - 'cbb_team_id' WHERE league_id = :lid"
        ), {"lid": row[0]})
