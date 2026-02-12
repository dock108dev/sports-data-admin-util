"""Add team color columns and seed with color data from GameTheme.swift.

Adds color_light_hex and color_dark_hex VARCHAR(7) columns to sports_teams
and populates them for 408 teams across NBA, NHL, and NCAAB.

Revision ID: 20260211_000002
Revises: 20260211_000001
Create Date: 2026-02-11
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "20260211_000002"
down_revision = "20260211_000001"
branch_labels = None
depends_on = None

# Add scripts/ to path so we can import the color data module
_scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def upgrade() -> None:
    """Add color columns and populate with team color data."""
    # 1. Add columns
    op.add_column(
        "sports_teams",
        sa.Column("color_light_hex", sa.String(7), nullable=True),
    )
    op.add_column(
        "sports_teams",
        sa.Column("color_dark_hex", sa.String(7), nullable=True),
    )

    # 2. Populate from color data
    from _team_color_data import TEAM_COLORS

    conn = op.get_bind()

    # Get league IDs
    leagues = {}
    for row in conn.execute(text("SELECT id, code FROM sports_leagues")):
        leagues[row[1]] = row[0]

    # NBA/NHL: match by league_code + exact name
    nba_nhl_update = text("""
        UPDATE sports_teams
        SET color_light_hex = :light, color_dark_hex = :dark
        WHERE league_id = :lid AND name = :name
    """)

    # NCAAB: match by league_code + name prefix (LIKE)
    ncaab_update = text("""
        UPDATE sports_teams
        SET color_light_hex = :light, color_dark_hex = :dark
        WHERE league_id = :lid AND name LIKE :pattern
          AND color_light_hex IS NULL
    """)

    updated = 0
    missed = 0

    # Sort NCAAB keys by length DESC so longest prefixes match first
    # (e.g., "Alabama A&M" before "Alabama")
    sorted_keys = sorted(
        TEAM_COLORS.keys(),
        key=lambda k: (TEAM_COLORS[k]["league"] != "NCAAB", -len(k)),
    )

    for name in sorted_keys:
        data = TEAM_COLORS[name]
        league_code = data["league"]
        league_id = leagues.get(league_code)

        if not league_id:
            print(f"  SKIP: league {league_code} not found for {name}")
            missed += 1
            continue

        if league_code in ("NBA", "NHL"):
            result = conn.execute(nba_nhl_update, {
                "light": data["light"],
                "dark": data["dark"],
                "lid": league_id,
                "name": name,
            })
            if result.rowcount > 0:
                updated += result.rowcount
            else:
                missed += 1
                print(f"  MISS: {league_code} exact name='{name}' — not found in DB")
        else:
            # NCAAB prefix match — only update rows that don't already have colors
            # (prevents shorter prefix from overwriting longer match)
            pattern = f"{name}%"
            result = conn.execute(ncaab_update, {
                "light": data["light"],
                "dark": data["dark"],
                "lid": league_id,
                "pattern": pattern,
            })
            if result.rowcount > 0:
                updated += result.rowcount
            else:
                missed += 1
                print(f"  MISS: NCAAB prefix='{name}%' — no uncolored match in DB")

    print(f"Updated {updated} team colors ({missed} keys not matched)")


def downgrade() -> None:
    """Remove color columns."""
    op.drop_column("sports_teams", "color_dark_hex")
    op.drop_column("sports_teams", "color_light_hex")
