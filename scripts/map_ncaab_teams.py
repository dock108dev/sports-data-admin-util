#!/usr/bin/env python3
"""Map NCAAB teams to CBB API team IDs."""

import json
import os
import re
import subprocess

import httpx

CBB_API_BASE = "https://api.collegebasketballdata.com"
CBB_API_KEY = os.environ.get("CBB_STATS_API_KEY", "")


def _normalize(name: str) -> str:
    """Normalize team name for matching."""
    n = name.lower().strip()
    n = n.replace("'", "").replace(".", "").replace("-", " ").replace("&", "and")
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


def run_sql(sql: str) -> str:
    """Run SQL via docker exec."""
    result = subprocess.run(
        ["docker", "exec", "sports-postgres", "psql", "-U", "dock108", "-d", "sports", "-t", "-c", sql],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main():
    # Fetch CBB teams
    print("Fetching CBB teams...")
    headers = {"Authorization": f"Bearer {CBB_API_KEY}"} if CBB_API_KEY else {}
    resp = httpx.get(f"{CBB_API_BASE}/teams", params={"season": 2026}, headers=headers, timeout=30)
    resp.raise_for_status()
    cbb_teams = resp.json()
    print(f"Fetched {len(cbb_teams)} CBB teams")

    # Build lookup
    cbb_lookup = {}
    for t in cbb_teams:
        for name in [
            t.get("displayName", ""),
            t.get("school", ""),
            f"{t.get('school', '')} {t.get('mascot', '')}".strip(),
        ]:
            if name:
                cbb_lookup[_normalize(name)] = t

    # Get DB teams via docker exec
    print("Getting DB teams...")
    output = run_sql("SELECT id, name, external_codes::text FROM sports_teams WHERE league_id = 9")
    db_teams = []
    for line in output.strip().split("\n"):
        if line.strip():
            parts = line.split("|")
            if len(parts) >= 3:
                team_id = int(parts[0].strip())
                team_name = parts[1].strip()
                ext_str = parts[2].strip()
                try:
                    ext_codes = json.loads(ext_str) if ext_str and ext_str != "{}" else {}
                except json.JSONDecodeError:
                    ext_codes = {}
                db_teams.append((team_id, team_name, ext_codes))

    print(f"Found {len(db_teams)} DB teams")

    # Match and update
    matched, unmatched = 0, []
    for team_id, team_name, ext_codes in db_teams:
        db_norm = _normalize(team_name)
        cbb = cbb_lookup.get(db_norm)

        if not cbb:
            db_words = db_norm.split()
            if len(db_words) > 1:
                cbb = cbb_lookup.get(" ".join(db_words[:-1]))

        if not cbb:
            for k, v in cbb_lookup.items():
                if db_norm in k or k in db_norm:
                    cbb = v
                    break

        if cbb:
            codes = dict(ext_codes) if ext_codes else {}
            codes["cbb_team_id"] = cbb["id"]
            codes_json = json.dumps(codes).replace("'", "''")
            sql = f"UPDATE sports_teams SET external_codes = '{codes_json}'::jsonb WHERE id = {team_id}"
            run_sql(sql)
            matched += 1
        else:
            unmatched.append(team_name)

    print(f"Matched: {matched}, Unmatched: {len(unmatched)}")
    if unmatched:
        print(f"Unmatched: {unmatched}")


if __name__ == "__main__":
    main()
