"""Fix NCAAB CBB team ID mappings with strict matching.

The original migration used substring matching which caused incorrect mappings
(e.g., "Florida International" matched to Florida's ID 87 instead of 89).

This migration:
1. Clears all cbb_team_id values
2. Re-matches with strict exact matching only
3. Reports unmatched teams for manual review

Revision ID: 20260129_000001
Revises: 20260128_000001
Create Date: 2026-01-29
"""

from __future__ import annotations

import json
import os
import re
import httpx
from alembic import op
from sqlalchemy import text

revision = "20260129_000001"
down_revision = "20260128_000001"
branch_labels = None
depends_on = None

CBB_API_BASE = "https://api.collegebasketballdata.com"
CBB_API_KEY = os.environ.get("CBB_STATS_API_KEY", "")


def _normalize_strict(name: str) -> str:
    """Normalize team name for strict matching.

    Only does case normalization, punctuation removal, and whitespace cleanup.
    NO abbreviation expansion to avoid false positives.
    """
    n = name.lower().strip()
    # Remove punctuation but keep spaces
    n = n.replace("'", "").replace(".", "").replace("-", " ").replace("&", "and")
    # Normalize whitespace
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


# Known manual mappings for teams that can't be auto-matched
# Format: DB team name (lowercase, normalized) -> CBB API team ID
MANUAL_MAPPINGS = {
    # FIU is "Florida International" in API, not just "Florida"
    "florida intl golden panthers": 89,
    "florida international golden panthers": 89,
    # Add more as needed
}


def upgrade() -> None:
    """Fix cbb_team_id mappings with strict matching."""
    conn = op.get_bind()

    # Get NCAAB league ID
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        print("NCAAB league not found")
        return
    league_id = row[0]

    # Clear existing cbb_team_id values
    print("Clearing existing cbb_team_id mappings...")
    conn.execute(text(
        "UPDATE sports_teams SET external_codes = external_codes - 'cbb_team_id' WHERE league_id = :lid"
    ), {"lid": league_id})

    # Fetch CBB teams from API
    print("Fetching CBB teams from API...")
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

    # Build lookup: normalized name -> CBB team (strict matching only)
    cbb_by_exact: dict[str, dict] = {}
    cbb_by_expanded: dict[str, dict] = {}

    for t in cbb_teams:
        team_id = t.get("id")
        display = t.get("displayName", "")
        school = t.get("school", "")
        mascot = t.get("mascot", "")
        full_name = f"{school} {mascot}".strip()

        # Index by all variations
        for name in [display, school, full_name]:
            if name:
                strict = _normalize_strict(name)
                expanded = _normalize_with_expansions(name)
                cbb_by_exact[strict] = t
                if expanded != strict:
                    cbb_by_expanded[expanded] = t

    # Get DB teams
    result = conn.execute(text(
        "SELECT id, name, external_codes FROM sports_teams WHERE league_id = :lid"
    ), {"lid": league_id})
    db_teams = result.fetchall()
    print(f"Found {len(db_teams)} DB teams")

    # Match and update
    matched, manual_matched, unmatched = 0, 0, []

    for team_id, team_name, ext_codes in db_teams:
        db_strict = _normalize_strict(team_name)
        db_expanded = _normalize_with_expansions(team_name)

        cbb_team_id = None
        # Priority 1: Manual mapping
        if db_strict in MANUAL_MAPPINGS:
            cbb_team_id = MANUAL_MAPPINGS[db_strict]
            manual_matched += 1

        # Priority 2: Exact match on strict normalized name
        elif db_strict in cbb_by_exact:
            cbb_team_id = cbb_by_exact[db_strict]["id"]

        # Priority 3: Exact match on expanded name (St -> State, etc.)
        elif db_expanded in cbb_by_exact:
            cbb_team_id = cbb_by_exact[db_expanded]["id"]
        elif db_expanded in cbb_by_expanded:
            cbb_team_id = cbb_by_expanded[db_expanded]["id"]

        # Priority 4: Try without mascot (last word)
        if not cbb_team_id:
            words = db_strict.split()
            if len(words) > 1:
                school_only = " ".join(words[:-1])
                if school_only in cbb_by_exact:
                    cbb_team_id = cbb_by_exact[school_only]["id"]

        # NO SUBSTRING MATCHING - this caused the original bug

        if cbb_team_id:
            codes = dict(ext_codes) if ext_codes else {}
            codes["cbb_team_id"] = cbb_team_id
            conn.execute(
                text("UPDATE sports_teams SET external_codes = :codes::jsonb WHERE id = :id"),
                {"codes": json.dumps(codes), "id": team_id}
            )
            matched += 1
        else:
            unmatched.append(team_name)

    print("\nResults:")
    print(f"  Matched: {matched} (including {manual_matched} manual)")
    print(f"  Unmatched: {len(unmatched)}")

    if unmatched:
        print("\nUnmatched teams (add to MANUAL_MAPPINGS if needed):")
        for name in sorted(unmatched):
            print(f"  - {name}")


def downgrade() -> None:
    """Remove cbb_team_id from NCAAB teams."""
    conn = op.get_bind()
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if row:
        conn.execute(text(
            "UPDATE sports_teams SET external_codes = external_codes - 'cbb_team_id' WHERE league_id = :lid"
        ), {"lid": row[0]})
