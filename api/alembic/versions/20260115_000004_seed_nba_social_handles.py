"""Seed NBA team social handles for X/Twitter.

Revision ID: 20260115_000004
Revises: 20260214_000001
Create Date: 2026-01-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260115_000004"
down_revision = "20260214_000001"
branch_labels = None
depends_on = None


# NBA team abbreviations to X handles mapping
NBA_SOCIAL_HANDLES = {
    "ATL": "ATLHawks",
    "BKN": "BrooklynNets",
    "BOS": "celtics",
    "CHA": "hornets",
    "CHI": "chicagobulls",
    "CLE": "cavs",
    "DAL": "dallasmavs",
    "DEN": "nuggets",
    "DET": "DetroitPistons",
    "GSW": "warriors",
    "HOU": "HoustonRockets",
    "IND": "Pacers",
    "LAC": "LAClippers",
    "LAL": "Lakers",
    "MEM": "memgrizz",
    "MIA": "MiamiHEAT",
    "MIL": "Bucks",
    "MIN": "Timberwolves",
    "NOP": "PelicansNBA",
    "NYK": "nyknicks",
    "OKC": "OKCThunder",
    "ORL": "OrlandoMagic",
    "PHI": "sixers",
    "PHX": "Suns",
    "POR": "trailblazers",
    "SAC": "SacramentoKings",
    "SAS": "spurs",
    "TOR": "Raptors",
    "UTA": "utahjazz",
    "WAS": "WashWizards",
}


def upgrade() -> None:
    """Insert NBA team social handles.
    
    Uses raw SQL to handle the case-when mapping from team abbreviation to handle.
    Only inserts for teams that exist and don't already have a handle.
    """
    conn = op.get_bind()
    
    # Build CASE statement for handle mapping
    case_parts = [f"WHEN t.abbreviation = '{abbr}' THEN '{handle}'" 
                  for abbr, handle in NBA_SOCIAL_HANDLES.items()]
    case_stmt = " ".join(case_parts)
    
    sql = f"""
    INSERT INTO team_social_accounts (team_id, league_id, platform, handle, is_active)
    SELECT t.id, t.league_id, 'x',
        CASE {case_stmt} END,
        true
    FROM sports_teams t
    JOIN sports_leagues l ON t.league_id = l.id
    WHERE l.code = 'NBA'
      AND t.abbreviation IN ({", ".join(f"'{a}'" for a in NBA_SOCIAL_HANDLES.keys())})
    ON CONFLICT (team_id, platform) DO NOTHING
    """
    
    conn.execute(text(sql))


def downgrade() -> None:
    """Remove NBA team social handles."""
    conn = op.get_bind()
    
    sql = """
    DELETE FROM team_social_accounts
    WHERE platform = 'x'
      AND league_id = (SELECT id FROM sports_leagues WHERE code = 'NBA')
    """
    conn.execute(text(sql))
