"""Fix NCAAB social handles for 66 teams with zero posts.

Prod investigation (2/14-2/16 2026) found 66 NCAAB teams that played games
but have 0 social posts. Of these:
- 8 teams have NULL handles (never seeded)
- 58 teams have handles that are wrong/stale (scraper collects 0 posts)

This migration upserts all 66 with corrected X handles using
ON CONFLICT (team_id, platform) DO UPDATE.

Revision ID: 20260218_fix_ncaab
Revises: 20260218_seed
Create Date: 2026-02-18
"""

from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "20260218_fix_ncaab"
down_revision = "20260218_seed"
branch_labels = None
depends_on = None

NCAAB_SOCIAL_HANDLES: dict[str, str] = {
    "Alcorn St Braves": "BRAVESMBB",
    "Arizona Wildcats": "ArizonaMBB",
    "Arkansas-Pine Bluff Golden Lions": "UAPBLionsMBB",
    "Austin Peay Governors": "GovsMBB",
    "BYU Cougars": "BYUMBB",
    "Bowling Green Falcons": "BGSUMBB",
    "Brown Bears": "BrownU_MBB",
    "Central Connecticut St Blue Devils": "CCSU_MBB",
    "Chicago St Cougars": "ChicagoStateMBB",
    "Cornell Big Red": "CornellMBB",
    "Dartmouth Big Green": "DartmouthMBB",
    "Denver Pioneers": "DU_MensHoops",
    "Detroit Mercy Titans": "DetroitMercyMBB",
    "Eastern Michigan Eagles": "EMU_MBB",
    "Fairfield Stags": "FairfieldMBB",
    "Fairleigh Dickinson Knights": "FDUKnightsMBB",
    "Florida Atlantic Owls": "FAUMBB",
    "Furman Paladins": "FurmanMBB",
    "Gardner-Webb Bulldogs": "GWU_MBK",
    "Georgia St Panthers": "GeorgiaStateMBB",
    "IUPUI Jaguars": "IUPUIMensBball",
    "Idaho State Bengals": "IdahoStateMBB",
    "Indiana St Sycamores": "IndStBasketball",
    "Jackson St Tigers": "GoJSUTigersMBB",
    "Le Moyne Dolphins": "LeMoyneMBB",
    "Lindenwood Lions": "LUMensBball",
    "Long Beach St 49ers": "LBSUMBB",
    "Loyola (MD) Greyhounds": "LoyolaMBB",
    "Maine Black Bears": "MaineMBB",
    "Manhattan Jaspers": "JaspersMBB",
    "Marshall Thundering Herd": "Herd_MBB",
    "Mercyhurst Lakers": "HurstMBBall",
    "Missouri St Bears": "MoStateMBB",
    "Morehead St Eagles": "MSUEaglesMBB",
    "Morgan St Bears": "MSUBearsMBB",
    "Nebraska Cornhuskers": "HuskerMBB",
    "New Haven Chargers": "UNewHavenMBB",
    "New Orleans Privateers": "PrivateersHoops",
    "North Alabama Lions": "UNA_Basketball",
    "North Florida Ospreys": "OspreyMBB",
    "Old Dominion Monarchs": "ODU_MBB",
    "Pennsylvania Quakers": "PennMBB",
    "Pepperdine Waves": "PepperdineMBB",
    "Presbyterian Blue Hose": "BlueHoseMBB",
    "Princeton Tigers": "PrincetonMBB",
    "Queens University Royals": "queensMBB",
    "Radford Highlanders": "RadfordHoops",
    "Rice Owls": "RiceMBB",
    "SE Louisiana Lions": "LionUpMBB",
    "Sacred Heart Pioneers": "SHU_MensHoops",
    "San José St Spartans": "SanJoseStateMBB",
    "South Alabama Jaguars": "SouthAlabamaMBB",
    "South Carolina St Bulldogs": "SCStateMBB",
    "South Carolina Upstate Spartans": "UpstateMBB",
    "Southern Indiana Screaming Eagles": "USI_Basketball",
    "Southern Jaguars": "JaguarHoops",
    "Stonehill Skyhawks": "StonehillMBB",
    "Tenn-Martin Skyhawks": "SkyhawkHoops",
    "Texas A&M-CC Islanders": "Islanders_MBB",
    "Toledo Rockets": "Toledo_MBB",
    "Tulsa Golden Hurricane": "TUMBasketball",
    "UIC Flames": "UIC_MBB",
    "UT Rio Grande Valley Vaqueros": "UTRGVmbb",
    "UT-Arlington Mavericks": "UTAMavsMBB",
    "UTEP Miners": "UTEPMBB",
    "West Georgia Wolves": "UWG_MBB",
}


def upgrade() -> None:
    conn = op.get_bind()

    upsert_sql = text("""
        INSERT INTO team_social_accounts (team_id, league_id, platform, handle, is_active)
        SELECT t.id, t.league_id, 'x', :handle, true
        FROM sports_teams t
        JOIN sports_leagues l ON t.league_id = l.id
        WHERE l.code = 'NCAAB'
          AND t.name = :team_name
        ON CONFLICT (team_id, platform) DO UPDATE
          SET handle = EXCLUDED.handle
    """)

    updated = 0
    for team_name, handle in NCAAB_SOCIAL_HANDLES.items():
        result = conn.execute(upsert_sql, {"team_name": team_name, "handle": handle})
        if result.rowcount:
            updated += 1
        else:
            print(f"  WARNING: team not found: {team_name}")

    print(f"Upserted {updated}/{len(NCAAB_SOCIAL_HANDLES)} NCAAB social handles")


def downgrade() -> None:
    pass
