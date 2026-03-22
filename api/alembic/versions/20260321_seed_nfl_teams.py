"""Seed 32 NFL teams into sports_teams.

Adds all 32 NFL franchises (league_id=2) with official colors,
abbreviations, and short names matching the normalization dict.

Revision ID: 20260321_nfl_teams
Revises: sim_obs_001
Create Date: 2026-03-21
"""

from __future__ import annotations

from alembic import op

revision = "20260321_nfl_teams"
down_revision = "sim_obs_001"
branch_labels = None
depends_on = None

# (name, short_name, abbreviation, color_light_hex, color_dark_hex)
NFL_TEAMS = [
    ("Arizona Cardinals", "Cardinals", "ARI", "#97233F", "#000000"),
    ("Atlanta Falcons", "Falcons", "ATL", "#A71930", "#000000"),
    ("Baltimore Ravens", "Ravens", "BAL", "#241773", "#000000"),
    ("Buffalo Bills", "Bills", "BUF", "#00338D", "#C60C30"),
    ("Carolina Panthers", "Panthers", "CAR", "#0085CA", "#101820"),
    ("Chicago Bears", "Bears", "CHI", "#0B162A", "#C83803"),
    ("Cincinnati Bengals", "Bengals", "CIN", "#FB4F14", "#000000"),
    ("Cleveland Browns", "Browns", "CLE", "#311D00", "#FF3C00"),
    ("Dallas Cowboys", "Cowboys", "DAL", "#003594", "#869397"),
    ("Denver Broncos", "Broncos", "DEN", "#FB4F14", "#002244"),
    ("Detroit Lions", "Lions", "DET", "#0076B6", "#B0B7BC"),
    ("Green Bay Packers", "Packers", "GB", "#203731", "#FFB612"),
    ("Houston Texans", "Texans", "HOU", "#03202F", "#A71930"),
    ("Indianapolis Colts", "Colts", "IND", "#002C5F", "#A2AAAD"),
    ("Jacksonville Jaguars", "Jaguars", "JAX", "#006778", "#9F792C"),
    ("Kansas City Chiefs", "Chiefs", "KC", "#E31837", "#FFB81C"),
    ("Las Vegas Raiders", "Raiders", "LV", "#000000", "#A5ACAF"),
    ("Los Angeles Chargers", "Chargers", "LAC", "#0080C6", "#FFC20E"),
    ("Los Angeles Rams", "Rams", "LAR", "#003594", "#FFA300"),
    ("Miami Dolphins", "Dolphins", "MIA", "#008E97", "#FC4C02"),
    ("Minnesota Vikings", "Vikings", "MIN", "#4F2683", "#FFC62F"),
    ("New England Patriots", "Patriots", "NE", "#002244", "#C60C30"),
    ("New Orleans Saints", "Saints", "NO", "#D3BC8D", "#101820"),
    ("New York Giants", "Giants", "NYG", "#0B2265", "#A71930"),
    ("New York Jets", "Jets", "NYJ", "#125740", "#000000"),
    ("Philadelphia Eagles", "Eagles", "PHI", "#004C54", "#A5ACAF"),
    ("Pittsburgh Steelers", "Steelers", "PIT", "#FFB612", "#101820"),
    ("San Francisco 49ers", "49ers", "SF", "#AA0000", "#B3995D"),
    ("Seattle Seahawks", "Seahawks", "SEA", "#002244", "#69BE28"),
    ("Tampa Bay Buccaneers", "Buccaneers", "TB", "#D50A0A", "#34302B"),
    ("Tennessee Titans", "Titans", "TEN", "#0C2340", "#4B92DB"),
    ("Washington Commanders", "Commanders", "WAS", "#5A1414", "#FFB612"),
]


def upgrade() -> None:
    for name, short_name, abbr, color_light, color_dark in NFL_TEAMS:
        esc_name = name.replace("'", "''")
        esc_short = short_name.replace("'", "''")
        op.execute(
            f"INSERT INTO sports_teams "
            f"(id, league_id, external_ref, name, short_name, abbreviation, "
            f"location, external_codes, created_at, updated_at, x_handle, "
            f"color_light_hex, color_dark_hex) "
            f"VALUES (nextval('sports_teams_id_seq'), 2, NULL, '{esc_name}', "
            f"'{esc_short}', '{abbr}', NULL, '{{}}', now(), now(), NULL, "
            f"'{color_light}', '{color_dark}') "
            f"ON CONFLICT (league_id, name) DO NOTHING"
        )


def downgrade() -> None:
    op.execute("DELETE FROM sports_teams WHERE league_id = 2")
