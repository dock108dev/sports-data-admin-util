#!/usr/bin/env python3
"""Harvest NCAAB team abbreviations from CBB API and reconcile with DB.

This script:
1. Fetches all teams from the CBB API /teams endpoint
2. Extracts the abbreviation field for each team
3. Compares CBB API teams against our DB teams by cbb_team_id
4. Reports: missing from DB, in DB but not API, name mismatches

Usage:
    # Requires CBB_STATS_API_KEY env var and running postgres container
    CBB_STATS_API_KEY=... python scripts/harvest_cbb_abbreviations.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import httpx

CBB_API_BASE = "https://api.collegebasketballdata.com"
CBB_API_KEY = os.environ.get("CBB_STATS_API_KEY", "")


def run_sql(sql: str) -> str:
    """Run SQL via docker exec."""
    result = subprocess.run(
        [
            "docker", "exec", "sports-postgres",
            "psql", "-U", "dock108", "-d", "sports", "-t", "-c", sql,
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def fetch_cbb_teams(season: int = 2026) -> list[dict]:
    """Fetch all teams from CBB API."""
    headers = {"Authorization": f"Bearer {CBB_API_KEY}"} if CBB_API_KEY else {}
    resp = httpx.get(
        f"{CBB_API_BASE}/teams",
        params={"season": season},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_db_teams() -> list[tuple[int, str, str, dict]]:
    """Get all NCAAB teams from DB with their abbreviations."""
    output = run_sql(
        "SELECT id, name, abbreviation, external_codes::text "
        "FROM sports_teams WHERE league_id = "
        "(SELECT id FROM sports_leagues WHERE code = 'NCAAB')"
    )
    teams: list[tuple[int, str, str, dict]] = []
    for line in output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) >= 4:
            team_id = int(parts[0].strip())
            name = parts[1].strip()
            abbr = parts[2].strip()
            ext_str = parts[3].strip()
            try:
                ext_codes = json.loads(ext_str) if ext_str and ext_str != "{}" else {}
            except json.JSONDecodeError:
                ext_codes = {}
            teams.append((team_id, name, abbr, ext_codes))
    return teams


def main() -> None:
    if not CBB_API_KEY:
        print("ERROR: CBB_STATS_API_KEY env var not set")
        sys.exit(1)

    # Fetch CBB API teams
    print("Fetching CBB API teams...")
    cbb_teams = fetch_cbb_teams()
    print(f"  Fetched {len(cbb_teams)} CBB teams")

    # Build CBB lookup by team ID
    cbb_by_id: dict[int, dict] = {}
    for t in cbb_teams:
        cbb_by_id[t["id"]] = t

    # Print abbreviation data for review
    print("\n=== CBB API Abbreviations ===")
    print("cbb_team_id | abbreviation | displayName")
    print("-" * 60)
    for t in sorted(cbb_teams, key=lambda x: x.get("id", 0)):
        abbr = t.get("abbreviation", "N/A")
        display = t.get("displayName", t.get("school", "???"))
        print(f"  {t['id']:>4} | {abbr:<12} | {display}")

    # Get DB teams
    print("\nGetting DB teams...")
    db_teams = get_db_teams()
    print(f"  Found {len(db_teams)} DB teams")

    # Build DB lookup by cbb_team_id
    db_by_cbb_id: dict[int, tuple[int, str, str]] = {}
    db_without_cbb_id: list[tuple[int, str, str]] = []
    for team_id, name, abbr, ext_codes in db_teams:
        cbb_id = ext_codes.get("cbb_team_id")
        if cbb_id is not None:
            db_by_cbb_id[int(cbb_id)] = (team_id, name, abbr)
        else:
            db_without_cbb_id.append((team_id, name, abbr))

    # Reconcile
    cbb_ids_in_api = set(cbb_by_id.keys())
    cbb_ids_in_db = set(db_by_cbb_id.keys())

    missing_from_db = cbb_ids_in_api - cbb_ids_in_db
    in_db_not_api = cbb_ids_in_db - cbb_ids_in_api

    print(f"\n=== Reconciliation ===")
    print(f"CBB API teams: {len(cbb_ids_in_api)}")
    print(f"DB teams with cbb_team_id: {len(cbb_ids_in_db)}")
    print(f"DB teams without cbb_team_id: {len(db_without_cbb_id)}")

    if missing_from_db:
        print(f"\n--- Missing from DB ({len(missing_from_db)} teams) ---")
        for cbb_id in sorted(missing_from_db):
            t = cbb_by_id[cbb_id]
            abbr = t.get("abbreviation", "N/A")
            display = t.get("displayName", t.get("school", "???"))
            mascot = t.get("mascot", "")
            print(f"  cbb_id={cbb_id}: {display} ({mascot}) [abbr={abbr}]")

    if in_db_not_api:
        print(f"\n--- In DB but NOT in API ({len(in_db_not_api)} teams) ---")
        for cbb_id in sorted(in_db_not_api):
            db_id, db_name, db_abbr = db_by_cbb_id[cbb_id]
            print(f"  cbb_id={cbb_id}: DB name='{db_name}' (abbr={db_abbr})")

    # Name mismatches
    print(f"\n--- Name Mismatches ---")
    mismatches = 0
    for cbb_id in sorted(cbb_ids_in_api & cbb_ids_in_db):
        t = cbb_by_id[cbb_id]
        db_id, db_name, db_abbr = db_by_cbb_id[cbb_id]
        api_display = t.get("displayName", "")
        api_school = t.get("school", "")
        api_mascot = t.get("mascot", "")
        api_full = f"{api_school} {api_mascot}".strip()

        if db_name != api_display and db_name != api_full:
            mismatches += 1
            print(f"  cbb_id={cbb_id}:")
            print(f"    DB:  '{db_name}' (abbr={db_abbr})")
            print(f"    API: '{api_display}' / '{api_full}'")

    if mismatches == 0:
        print("  (none)")

    # Output Python dict for SSOT
    print(f"\n=== Python Dict Output (for ncaab_teams.py) ===")
    print("# Paste into NCAAB_TEAM_ABBREVIATIONS:")
    for cbb_id in sorted(cbb_ids_in_api & cbb_ids_in_db):
        t = cbb_by_id[cbb_id]
        db_id, db_name, db_abbr = db_by_cbb_id[cbb_id]
        api_abbr = t.get("abbreviation", "")
        print(f'    "{db_name}": ("{db_name}", "{api_abbr}", {cbb_id}),')

    if db_without_cbb_id:
        print(f"\n--- DB teams without cbb_team_id ({len(db_without_cbb_id)}) ---")
        for team_id, name, abbr in db_without_cbb_id:
            print(f"  id={team_id}: '{name}' (abbr={abbr})")


if __name__ == "__main__":
    main()
