"""Seed NHL team social handles for X/Twitter.

Revision ID: 20260205_000001
Revises: 2a6236c3c8c4
Create Date: 2026-02-05
"""

from alembic import op
from sqlalchemy import text


revision = "20260205_000001"
down_revision = "2a6236c3c8c4"
branch_labels = None
depends_on = None


# NHL team abbreviations to X handles mapping
# Source: sql/006_seed_nhl_x_handles.sql
NHL_SOCIAL_HANDLES = {
    "ANA": "AnaheimDucks",
    "ARI": "ArizonaCoyotes",
    "BOS": "NHLBruins",
    "BUF": "BuffaloSabres",
    "CGY": "NHLFlames",
    "CAR": "Canes",
    "CHI": "NHLBlackhawks",
    "COL": "Avalanche",
    "CBJ": "BlueJacketsNHL",
    "DAL": "DallasStars",
    "DET": "DetroitRedWings",
    "EDM": "EdmontonOilers",
    "FLA": "FlaPanthers",
    "LAK": "LAKings",
    "MIN": "mnwild",
    "MTL": "CanadiensMTL",
    "NSH": "PredsNHL",
    "NJD": "NJDevils",
    "NYI": "NYIslanders",
    "NYR": "NYRangers",
    "OTT": "Senators",
    "PHI": "NHLFlyers",
    "PIT": "penguins",
    "SJS": "SanJoseSharks",
    "SEA": "SeattleKraken",
    "STL": "StLouisBlues",
    "TBL": "TampaBayLightning",
    "TOR": "MapleLeafs",
    "VAN": "Canucks",
    "VGK": "GoldenKnights",
    "WSH": "Capitals",
    "WPG": "NHLJets",
}


def upgrade() -> None:
    """Insert NHL team social handles.

    Inserts each team's handle individually using parameterized queries.
    Only inserts for teams that exist and don't already have a handle.
    """
    conn = op.get_bind()

    # Insert each team's handle using parameterized query
    insert_sql = text("""
        INSERT INTO team_social_accounts (team_id, league_id, platform, handle, is_active)
        SELECT t.id, t.league_id, 'x', :handle, true
        FROM sports_teams t
        JOIN sports_leagues l ON t.league_id = l.id
        WHERE l.code = 'NHL'
          AND t.abbreviation = :abbreviation
        ON CONFLICT (team_id, platform) DO NOTHING
    """)

    for abbreviation, handle in NHL_SOCIAL_HANDLES.items():
        conn.execute(insert_sql, {"abbreviation": abbreviation, "handle": handle})


def downgrade() -> None:
    """Remove NHL team social handles."""
    conn = op.get_bind()

    sql = """
    DELETE FROM team_social_accounts
    WHERE platform = 'x'
      AND league_id = (SELECT id FROM sports_leagues WHERE code = 'NHL')
    """
    conn.execute(text(sql))
