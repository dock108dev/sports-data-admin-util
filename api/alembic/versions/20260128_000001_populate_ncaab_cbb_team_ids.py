"""Populate NCAAB teams with CBB API team IDs.

This data migration fetches teams from the College Basketball Data API
and maps them to existing NCAAB teams in our database. The CBB team ID
is stored in external_codes['cbb_team_id'].

Revision ID: 20260128_000001
Revises: 20260218_000005
Create Date: 2026-01-28
"""

from __future__ import annotations

import json
import os
import re
import httpx
from alembic import op
from sqlalchemy import text

revision = "20260128_000001"
down_revision = "20260127_merge_heads"
branch_labels = None
depends_on = None

CBB_API_BASE = "https://api.collegebasketballdata.com"
CBB_API_KEY = os.environ.get("CBB_STATS_API_KEY", "")


def _normalize(name: str) -> str:
    """Normalize team name for matching."""
    n = name.lower().strip()
    n = n.replace("'", "").replace(".", "").replace("-", " ").replace("&", "and")
    # Expand abbreviations
    subs = [
        (r"\bunc\b", "north carolina"),
        (r"\buniv\b", "university"),
        (r"\bu\b", "university"),
        (r"\bst\b", "state"),
        (r"\bvmi\b", "virginia military institute"),
    ]
    for p, r in subs:
        n = re.sub(p, r, n)
    return " ".join(n.split())


def upgrade() -> None:
    """Populate cbb_team_id for NCAAB teams."""
    conn = op.get_bind()

    # Get NCAAB league ID
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        print("NCAAB league not found")
        return
    league_id = row[0]

    # Fetch CBB teams from API
    print("Fetching CBB teams...")
    headers = {"Authorization": f"Bearer {CBB_API_KEY}"} if CBB_API_KEY else {}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{CBB_API_BASE}/teams", params={"season": 2026}, headers=headers)
            resp.raise_for_status()
            cbb_teams = resp.json()
        print(f"Fetched {len(cbb_teams)} CBB teams")
    except Exception as e:
        print(f"API fetch failed: {e} - skipping migration")
        return

    # Build lookup: normalized name -> CBB team
    cbb_lookup: dict[str, dict] = {}
    for t in cbb_teams:
        for name in [t.get("displayName", ""), t.get("school", ""), f"{t.get('school', '')} {t.get('mascot', '')}".strip()]:
            if name:
                cbb_lookup[_normalize(name)] = t

    # Get DB teams
    result = conn.execute(text(
        "SELECT id, name, external_codes FROM sports_teams WHERE league_id = :lid"
    ), {"lid": league_id})
    db_teams = result.fetchall()
    print(f"Found {len(db_teams)} DB teams")

    # Match and update
    matched, unmatched = 0, []
    for team_id, team_name, ext_codes in db_teams:
        db_norm = _normalize(team_name)
        cbb = cbb_lookup.get(db_norm)

        # Try partial match if no exact
        if not cbb:
            db_words = db_norm.split()
            if len(db_words) > 1:
                school = " ".join(db_words[:-1])  # Remove mascot
                cbb = cbb_lookup.get(school)

        # Try substring
        if not cbb:
            for k, v in cbb_lookup.items():
                if db_norm in k or k in db_norm:
                    cbb = v
                    break

        if cbb:
            codes = dict(ext_codes) if ext_codes else {}
            codes["cbb_team_id"] = cbb["id"]
            conn.execute(
                text("UPDATE sports_teams SET external_codes = :codes::jsonb WHERE id = :id"),
                {"codes": json.dumps(codes), "id": team_id}
            )
            matched += 1
        else:
            unmatched.append(team_name)

    print(f"Matched: {matched}, Unmatched: {len(unmatched)}")
    if unmatched[:10]:
        print(f"Sample unmatched: {unmatched[:10]}")


def downgrade() -> None:
    """Remove cbb_team_id from NCAAB teams."""
    conn = op.get_bind()
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if row:
        conn.execute(text(
            "UPDATE sports_teams SET external_codes = external_codes - 'cbb_team_id' WHERE league_id = :lid"
        ), {"lid": row[0]})
