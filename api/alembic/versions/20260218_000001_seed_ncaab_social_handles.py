"""Fix NCAAB social handles for 66 teams with zero posts.

Prod investigation (2/14-2/16 2026) found 66 NCAAB teams that played games
but have 0 social posts. Of these:
- 8 teams have NULL handles (never seeded)
- 58 teams have handles that are wrong/stale (scraper collects 0 posts)

This migration upserts all 66 with corrected X handles using
ON CONFLICT (team_id, platform) DO UPDATE.

Revision ID: 20260218_000001
Revises: 20260217_000002
Create Date: 2026-02-18
"""

from alembic import op
from sqlalchemy import text


revision = "20260218_000001"
down_revision = "20260217_000002"
branch_labels = None
depends_on = None


# team_name → corrected x_handle (all 66 teams)
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

# Previous handles for downgrade (58 teams that had stale handles).
# The 8 teams with NULL handles are not listed here — downgrade deletes them.
_OLD_HANDLES: dict[str, str] = {
    "Alcorn St Braves": "BRAVESMBB",
    "Arizona Wildcats": "APlayersProgram",
    "Arkansas-Pine Bluff Golden Lions": "UAPBLionsRoar",
    "Austin Peay Governors": "AustinPeayMBB",
    "BYU Cougars": "BYUBasketball",
    "Bowling Green Falcons": "BGSUMHoops",
    "Brown Bears": "BrownBasketball",
    "Central Connecticut St Blue Devils": "CCSU_MBB",
    "Chicago St Cougars": "ChicagoStateMBB",
    "Cornell Big Red": "CUBigRedHoops",
    "Dartmouth Big Green": "DartmouthMBK",
    "Denver Pioneers": "DU_Mhoops",
    "Detroit Mercy Titans": "DetroitMBB",
    "Eastern Michigan Eagles": "EMUHoops",
    "Fairfield Stags": "StagsMensBBall",
    "Fairleigh Dickinson Knights": "FDU_MBB",
    "Florida Atlantic Owls": "FAU_Hoops",
    "Furman Paladins": "FurmanHoops",
    "Gardner-Webb Bulldogs": "GWU_MBK",
    "Georgia St Panthers": "GeorgiaStateMBB",
    "IUPUI Jaguars": "IUPUIMensBBall",
    "Idaho State Bengals": "IdahoStateBBall",
    "Indiana St Sycamores": "IndStMBB",
    "Jackson St Tigers": "GoJSUTigersMBB",
    "Long Beach St 49ers": "LBSUhoops",
    "Loyola (MD) Greyhounds": "LoyolaMBB",
    "Maine Black Bears": "BlackBearsMBB",
    "Manhattan Jaspers": "JaspersMBB",
    "Marshall Thundering Herd": "HerdMBB",
    "Missouri St Bears": "MSUBearsHoops",
    "Morehead St Eagles": "MSUEaglesMBB",
    "Morgan St Bears": "MSUBearsMBB",
    "Nebraska Cornhuskers": "HuskerHoops",
    "New Orleans Privateers": "PrivateersMBB",
    "North Alabama Lions": "UNA_MBB",
    "North Florida Ospreys": "OspreysMBB",
    "Old Dominion Monarchs": "ODUMBB",
    "Pennsylvania Quakers": "PennBasketball",
    "Pepperdine Waves": "PeppBasketball",
    "Presbyterian Blue Hose": "BlueHoseHoops",
    "Princeton Tigers": "Princeton_Hoops",
    "Radford Highlanders": "RadfordMBB",
    "Rice Owls": "RiceBasketball",
    "SE Louisiana Lions": "SLU_Hoops",
    "Sacred Heart Pioneers": "SHU_MensHoops",
    "San José St Spartans": "SJSUMBB",
    "South Alabama Jaguars": "WeAreSouth_MBB",
    "South Carolina St Bulldogs": "SCStateAthletic",
    "South Carolina Upstate Spartans": "UpstateMB",
    "Southern Jaguars": "JaguarHoops",
    "Tenn-Martin Skyhawks": "SkyhawkHoops",
    "Texas A&M-CC Islanders": "IslandersMBB",
    "Toledo Rockets": "ToledoMBB",
    "Tulsa Golden Hurricane": "TUMBasketball",
    "UIC Flames": "UICFlamesMBB",
    "UT Rio Grande Valley Vaqueros": "UTRGMBB",
    "UT-Arlington Mavericks": "UTA_MBB",
    "UTEP Miners": "UTEP_MBB",
}

# Teams that had no social handle before (NULL) — downgrade deletes them.
_NULL_TEAMS: list[str] = [
    "Le Moyne Dolphins",
    "Lindenwood Lions",
    "Mercyhurst Lakers",
    "New Haven Chargers",
    "Queens University Royals",
    "Southern Indiana Screaming Eagles",
    "Stonehill Skyhawks",
    "West Georgia Wolves",
]


def upgrade() -> None:
    """Upsert corrected X handles for 66 NCAAB teams.

    Matches teams by name within the NCAAB league.
    Uses ON CONFLICT DO UPDATE to fix stale handles and insert new ones.
    """
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
    """Restore previous handles for the 58 stale teams, delete the 8 NULL teams."""
    conn = op.get_bind()

    # Restore old handles for teams that previously had one
    restore_sql = text("""
        UPDATE team_social_accounts
        SET handle = :old_handle
        WHERE platform = 'x'
          AND team_id = (
              SELECT t.id FROM sports_teams t
              JOIN sports_leagues l ON t.league_id = l.id
              WHERE l.code = 'NCAAB' AND t.name = :team_name
          )
    """)

    for team_name, old_handle in _OLD_HANDLES.items():
        conn.execute(restore_sql, {"team_name": team_name, "old_handle": old_handle})

    # Delete rows for teams that had no handle before this migration
    delete_sql = text("""
        DELETE FROM team_social_accounts
        WHERE platform = 'x'
          AND team_id IN (
              SELECT t.id FROM sports_teams t
              JOIN sports_leagues l ON t.league_id = l.id
              WHERE l.code = 'NCAAB' AND t.name = ANY(:names)
          )
    """)

    conn.execute(delete_sql, {"names": _NULL_TEAMS})
