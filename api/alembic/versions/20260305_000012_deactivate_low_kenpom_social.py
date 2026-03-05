"""Deactivate social scraping for NCAAB teams ranked 200-365 in KenPom.

These low-ranked teams consume Playwright budget without contributing
meaningful social data. With 358 active NCAAB social accounts, the
30-min collect_game_social task can't finish in time, leaving higher-value
games (NBA, top NCAAB) without social data.

This deactivates 166 teams, leaving ~199 active (top ~200 KenPom).
Handles are preserved — set is_active = true to re-enable.

Revision ID: 20260305_deactivate_social
Revises: 20260305_closing_lines
Create Date: 2026-03-05
"""

from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "20260305_deactivate_social"
down_revision = "20260305_closing_lines"
branch_labels = None
depends_on = None

# NCAAB teams ranked 200-365 in KenPom (2025-26 season)
TEAMS_TO_DEACTIVATE = [
    "Abilene Christian Wildcats",
    "Air Force Falcons",
    "Alabama A&M Bulldogs",
    "Alabama St Hornets",
    "Albany Great Danes",
    "Alcorn St Braves",
    "American Eagles",
    "Arkansas-Little Rock Trojans",
    "Arkansas-Pine Bluff Golden Lions",
    "Army Knights",
    "Ball State Cardinals",
    "Bellarmine Knights",
    "Bethune-Cookman Wildcats",
    "Binghamton Bearcats",
    "Boston Univ. Terriers",
    "Brown Bears",
    "Bryant Bulldogs",
    "Bucknell Bison",
    "CSU Bakersfield Roadrunners",
    "Cal Poly Mustangs",
    "Canisius Golden Griffins",
    "Central Connecticut St Blue Devils",
    "Central Michigan Chippewas",
    "Charleston Southern Buccaneers",
    "Chattanooga Mocs",
    "Chicago St Cougars",
    "Cleveland St Vikings",
    "Coastal Carolina Chanticleers",
    "Colgate Raiders",
    "Coppin St Eagles",
    "Dartmouth Big Green",
    "Delaware Blue Hens",
    "Delaware St Hornets",
    "Denver Pioneers",
    "Detroit Mercy Titans",
    "Drake Bulldogs",
    "Drexel Dragons",
    "East Carolina Pirates",
    "East Texas A&M Lions",
    "Eastern Illinois Panthers",
    "Eastern Kentucky Colonels",
    "Eastern Michigan Eagles",
    "Elon Phoenix",
    "Evansville Purple Aces",
    "Fairfield Stags",
    "Fairleigh Dickinson Knights",
    "Florida A&M Rattlers",
    "Florida Gulf Coast Eagles",
    "Fort Wayne Mastodons",
    "Furman Paladins",
    "Gardner-Webb Bulldogs",
    "Georgia Southern Eagles",
    "Georgia St Panthers",
    "Grambling St Tigers",
    "Hampton Pirates",
    "Holy Cross Crusaders",
    "Houston Christian Huskies",
    "Howard Bison",
    "IUPUI Jaguars",
    "Idaho State Bengals",
    "Incarnate Word Cardinals",
    "Indiana St Sycamores",
    "Iona Gaels",
    "Jackson St Tigers",
    "Jacksonville Dolphins",
    "Jacksonville St Gamecocks",
    "James Madison Dukes",
    "LIU Sharks",
    "La Salle Explorers",
    "Lafayette Leopards",
    "Lamar Cardinals",
    "Le Moyne Dolphins",
    "Lehigh Mountain Hawks",
    "Lindenwood Lions",
    "Long Beach St 49ers",
    "Longwood Lancers",
    "Louisiana Ragin' Cajuns",
    "Louisiana Tech Bulldogs",
    "Loyola (Chi) Ramblers",
    "Loyola (MD) Greyhounds",
    "Maine Black Bears",
    "Manhattan Jaspers",
    "Marist Red Foxes",
    "Maryland-Eastern Shore Hawks",
    "Mercyhurst Lakers",
    "Milwaukee Panthers",
    "Miss Valley St Delta Devils",
    "Missouri St Bears",
    "Morehead St Eagles",
    "Morgan St Bears",
    "Mt. St. Mary's Mountaineers",
    "NJIT Highlanders",
    "New Hampshire Wildcats",
    "New Haven Chargers",
    "Niagara Purple Eagles",
    "Nicholls St Colonels",
    "Norfolk St Spartans",
    "North Alabama Lions",
    "North Carolina A&T Aggies",
    "North Carolina Central Eagles",
    "North Dakota Fighting Hawks",
    "North Florida Ospreys",
    "Northeastern Huskies",
    "Northern Arizona Lumberjacks",
    "Northern Illinois Huskies",
    "Northwestern St Demons",
    "Ohio Bobcats",
    "Old Dominion Monarchs",
    "Omaha Mavericks",
    "Oral Roberts Golden Eagles",
    "Pepperdine Waves",
    "Portland Pilots",
    "Prairie View Panthers",
    "Presbyterian Blue Hose",
    "Princeton Tigers",
    "Quinnipiac Bobcats",
    "Radford Highlanders",
    "Rice Owls",
    "Rider Broncs",
    "SE Louisiana Lions",
    "SE Missouri St Redhawks",
    "SIU-Edwardsville Cougars",
    "Sacramento St Hornets",
    "Sacred Heart Pioneers",
    "Saint Peter's Peacocks",
    "Samford Bulldogs",
    "San Diego Toreros",
    "San José St Spartans",
    "Siena Saints",
    "South Carolina St Bulldogs",
    "South Carolina Upstate Spartans",
    "South Dakota Coyotes",
    "South Dakota St Jackrabbits",
    "Southern Indiana Screaming Eagles",
    "Southern Jaguars",
    "Southern Miss Golden Eagles",
    "Southern Utah Thunderbirds",
    "St. Francis (PA) Red Flash",
    "Stetson Hatters",
    "Stonehill Skyhawks",
    "Stony Brook Seawolves",
    "Tarleton State Texans",
    "Tenn-Martin Skyhawks",
    "Tennessee St Tigers",
    "Tennessee Tech Golden Eagles",
    "Texas Southern Tigers",
    "Texas State Bobcats",
    "The Citadel Bulldogs",
    "UC Riverside Highlanders",
    "UL Monroe Warhawks",
    "UMBC Retrievers",
    "UMKC Kangaroos",
    "UMass Lowell River Hawks",
    "UNC Asheville Bulldogs",
    "UNC Greensboro Spartans",
    "UTEP Miners",
    "UTSA Roadrunners",
    "VMI Keydets",
    "Vermont Catamounts",
    "Wagner Seahawks",
    "West Georgia Wolves",
    "Western Carolina Catamounts",
    "Western Illinois Leathernecks",
    "Western Michigan Broncos",
    "Wofford Terriers",
    "Youngstown St Penguins",
]


def upgrade() -> None:
    conn = op.get_bind()

    deactivate_sql = text("""
        UPDATE team_social_accounts
        SET is_active = false, updated_at = NOW()
        WHERE team_id IN (
            SELECT t.id FROM sports_teams t
            JOIN sports_leagues l ON t.league_id = l.id
            WHERE l.code = 'NCAAB'
            AND t.name = :team_name
        )
        AND platform = 'x'
        AND is_active = true
    """)

    deactivated = 0
    for team_name in TEAMS_TO_DEACTIVATE:
        result = conn.execute(deactivate_sql, {"team_name": team_name})
        if result.rowcount:
            deactivated += 1

    print(f"Deactivated {deactivated}/{len(TEAMS_TO_DEACTIVATE)} NCAAB social accounts")


def downgrade() -> None:
    conn = op.get_bind()

    reactivate_sql = text("""
        UPDATE team_social_accounts
        SET is_active = true, updated_at = NOW()
        WHERE team_id IN (
            SELECT t.id FROM sports_teams t
            JOIN sports_leagues l ON t.league_id = l.id
            WHERE l.code = 'NCAAB'
            AND t.name = :team_name
        )
        AND platform = 'x'
        AND is_active = false
    """)

    reactivated = 0
    for team_name in TEAMS_TO_DEACTIVATE:
        result = conn.execute(reactivate_sql, {"team_name": team_name})
        if result.rowcount:
            reactivated += 1

    print(f"Reactivated {reactivated}/{len(TEAMS_TO_DEACTIVATE)} NCAAB social accounts")
