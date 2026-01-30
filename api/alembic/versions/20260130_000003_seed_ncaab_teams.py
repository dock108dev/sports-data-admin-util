"""Seed NCAAB teams with cbb_team_id mappings.

Production has 0 NCAAB teams after data cleanup. This migration seeds
all 358 NCAAB teams with their cbb_team_id pre-populated.

Revision ID: 20260130_000003
Revises: 20260130_000002
Create Date: 2026-01-30
"""

from __future__ import annotations

import json
from alembic import op
from sqlalchemy import text

revision = "20260130_000003"
down_revision = "20260130_000002"
branch_labels = None
depends_on = None

# All 358 NCAAB teams with their CBB API team IDs
NCAAB_TEAMS = [
    ("Abilene Christian Wildcats", "ACW", 1),
    ("Air Force Falcons", "AFF", 2),
    ("Akron Zips", "AZI", 3),
    ("Alabama Crimson Tide", "ACT", 5),
    ("Alabama St Hornets", "ASH", 6),
    ("Albany Great Danes", "AGD", 306),
    ("Alcorn St Braves", "ASB", 7),
    ("American Eagles", "AEA", 8),
    ("Appalachian St Mountaineers", "ASM", 9),
    ("Arizona St Sun Devils", "ASSD", 10),
    ("Arizona Wildcats", "AWI", 11),
    ("Arkansas Razorbacks", "ARA", 12),
    ("Arkansas St Red Wolves", "ASRW", 13),
    ("Arkansas-Little Rock Trojans", "ALRT", 144),
    ("Arkansas-Pine Bluff Golden Lions", "APBGL", 14),
    ("Army Knights", "AKN", 15),
    ("Auburn Tigers", "ATI", 16),
    ("Austin Peay Governors", "APG", 17),
    ("BYU Cougars", "BCO", 18),
    ("Ball State Cardinals", "BSC", 19),
    ("Baylor Bears", "BBE", 20),
    ("Bellarmine Knights", "BKN", 21),
    ("Belmont Bruins", "BBR", 22),
    ("Bethune-Cookman Wildcats", "BCW", 23),
    ("Binghamton Bearcats", "BBE", 24),
    ("Boise State Broncos", "BSB", 25),
    ("Boston College Eagles", "BCE", 26),
    ("Boston Univ. Terriers", "BUT", 27),
    ("Bowling Green Falcons", "BGF", 28),
    ("Bradley Braves", "BBR", 29),
    ("Brown Bears", "BBE", 30),
    ("Bryant Bulldogs", "BBU", 31),
    ("Bucknell Bison", "BBI", 32),
    ("Buffalo Bulls", "BBU", 33),
    ("Butler Bulldogs", "BBU", 34),
    ("CSU Bakersfield Roadrunners", "CBR", 36),
    ("CSU Fullerton Titans", "CFT", 37),
    ("CSU Northridge Matadors", "CNM", 38),
    ("Cal Baptist Lancers", "CBL", 39),
    ("Cal Poly Mustangs", "CPM", 35),
    ("California Golden Bears", "CGB", 40),
    ("Campbell Fighting Camels", "CFC", 41),
    ("Canisius Golden Griffins", "CGG", 42),
    ("Central Arkansas Bears", "CAB", 43),
    ("Central Connecticut St Blue Devils", "CCSBD", 44),
    ("Central Michigan Chippewas", "CMC", 45),
    ("Charleston Cougars", "CCO", 46),
    ("Charleston Southern Buccaneers", "CSB", 47),
    ("Charlotte 49ers", "C49", 48),
    ("Chattanooga Mocs", "CMO", 49),
    ("Chicago St Cougars", "CSC", 50),
    ("Cincinnati Bearcats", "CBE", 51),
    ("Clemson Tigers", "CTI", 52),
    ("Cleveland St Vikings", "CSV", 53),
    ("Coastal Carolina Chanticleers", "CCC", 54),
    ("Colgate Raiders", "CRA", 55),
    ("Colorado Buffaloes", "CBU", 56),
    ("Colorado St Rams", "CSR", 57),
    ("Columbia Lions", "CLI", 58),
    ("Cornell Big Red", "CBR", 60),
    ("Creighton Bluejays", "CBL", 61),
    ("Dartmouth Big Green", "DBG", 62),
    ("Davidson Wildcats", "DWI", 63),
    ("Dayton Flyers", "DFL", 64),
    ("DePaul Blue Demons", "DBD", 65),
    ("Delaware Blue Hens", "DBH", 66),
    ("Delaware St Hornets", "DSH", 67),
    ("Denver Pioneers", "DPI", 68),
    ("Detroit Mercy Titans", "DMT", 69),
    ("Drake Bulldogs", "DBU", 70),
    ("Drexel Dragons", "DDR", 71),
    ("Duke Blue Devils", "DBD", 72),
    ("Duquesne Dukes", "DDU", 73),
    ("East Carolina Pirates", "ECP", 74),
    ("East Tennessee St Buccaneers", "ETSB", 75),
    ("East Texas A&M Lions", "ETAML", 76),
    ("Eastern Illinois Panthers", "EIP", 77),
    ("Eastern Kentucky Colonels", "EKC", 78),
    ("Eastern Michigan Eagles", "EME", 79),
    ("Eastern Washington Eagles", "EWE", 80),
    ("Elon Phoenix", "EPH", 81),
    ("Evansville Purple Aces", "EPA", 82),
    ("Fairfield Stags", "FST", 83),
    ("Fairleigh Dickinson Knights", "FDK", 84),
    ("Florida A&M Rattlers", "FAMR", 85),
    ("Florida Atlantic Owls", "FAO", 86),
    ("Florida Gators", "FGA", 87),
    ("Florida Gulf Coast Eagles", "FGCE", 88),
    ("Florida Int'l Golden Panthers", "FILGP", 89),
    ("Florida St Seminoles", "FSS", 90),
    ("Fordham Rams", "FRA", 91),
    ("Fort Wayne Mastodons", "FWM", 237),
    ("Fresno St Bulldogs", "FSB", 92),
    ("Furman Paladins", "FPA", 93),
    ("GW Revolutionaries", "GRE", 96),
    ("Gardner-Webb Bulldogs", "GWB", 94),
    ("George Mason Patriots", "GMP", 95),
    ("Georgetown Hoyas", "GHO", 97),
    ("Georgia Bulldogs", "GBU", 98),
    ("Georgia Southern Eagles", "GSE", 99),
    ("Georgia St Panthers", "GSP", 100),
    ("Georgia Tech Yellow Jackets", "GTYJ", 101),
    ("Gonzaga Bulldogs", "GBU", 102),
    ("Grand Canyon Antelopes", "GCA", 104),
    ("Green Bay Phoenix", "GBP", 105),
    ("Hampton Pirates", "HPI", 106),
    ("Harvard Crimson", "HCR", 107),
    ("Hawai'i Rainbow Warriors", "HIRW", 108),
    ("High Point Panthers", "HPP", 109),
    ("Hofstra Pride", "HPR", 110),
    ("Holy Cross Crusaders", "HCC", 111),
    ("Houston Christian Huskies", "HCH", 112),
    ("Houston Cougars", "HCO", 113),
    ("IUPUI Jaguars", "IJA", 115),
    ("Idaho State Bengals", "ISB", 116),
    ("Idaho Vandals", "IVA", 117),
    ("Illinois Fighting Illini", "IFI", 118),
    ("Illinois St Redbirds", "ISR", 119),
    ("Incarnate Word Cardinals", "IWC", 120),
    ("Indiana Hoosiers", "IHO", 121),
    ("Indiana St Sycamores", "ISS", 122),
    ("Iona Gaels", "IGA", 123),
    ("Iowa Hawkeyes", "IHA", 124),
    ("Iowa State Cyclones", "ISC", 125),
    ("Jackson St Tigers", "JST", 126),
    ("Jacksonville Dolphins", "JDO", 127),
    ("Jacksonville St Gamecocks", "JSG", 128),
    ("James Madison Dukes", "JMD", 129),
    ("Kansas Jayhawks", "KJA", 131),
    ("Kansas St Wildcats", "KSW", 132),
    ("Kennesaw St Owls", "KSO", 133),
    ("Kent State Golden Flashes", "KSGF", 134),
    ("Kentucky Wildcats", "KWI", 135),
    ("LIU Sharks", "LSH", 146),
    ("LSU Tigers", "LTI", 136),
    ("La Salle Explorers", "LSE", 137),
    ("Lafayette Leopards", "LLE", 138),
    ("Lamar Cardinals", "LCA", 139),
    ("Le Moyne Dolphins", "LMD", 140),
    ("Lehigh Mountain Hawks", "LMH", 141),
    ("Liberty Flames", "LFL", 142),
    ("Lindenwood Lions", "LLI", 366),
    ("Lipscomb Bisons", "LBI", 143),
    ("Long Beach St 49ers", "LBS4", 145),
    ("Longwood Lancers", "LLA", 147),
    ("Louisiana Ragin' Cajuns", "LRC", 148),
    ("Louisiana Tech Bulldogs", "LTB", 149),
    ("Louisville Cardinals", "LCA", 150),
    ("Loyola (Chi) Ramblers", "LCR", 151),
    ("Loyola (MD) Greyhounds", "LMG", 152),
    ("Loyola Marymount Lions", "LML", 153),
    ("Maine Black Bears", "MBB", 154),
    ("Manhattan Jaspers", "MJA", 155),
    ("Marist Red Foxes", "MRF", 156),
    ("Marquette Golden Eagles", "MGE", 157),
    ("Marshall Thundering Herd", "MTH", 158),
    ("Maryland Terrapins", "MTE", 160),
    ("Massachusetts Minutemen", "MMI", 161),
    ("McNeese Cowboys", "MCO", 162),
    ("Memphis Tigers", "MTI", 163),
    ("Mercer Bears", "MBE", 164),
    ("Mercyhurst Lakers", "MLA", 165),
    ("Merrimack Warriors", "MWA", 166),
    ("Miami (OH) RedHawks", "MOR", 167),
    ("Miami Hurricanes", "MHU", 168),
    ("Michigan St Spartans", "MSS", 169),
    ("Michigan Wolverines", "MWO", 170),
    ("Middle Tennessee Blue Raiders", "MTBR", 171),
    ("Milwaukee Panthers", "MPA", 172),
    ("Minnesota Golden Gophers", "MGG", 173),
    ("Miss Valley St Delta Devils", "MVSDD", 175),
    ("Mississippi St Bulldogs", "MSB", 174),
    ("Missouri St Bears", "MSB", 176),
    ("Missouri Tigers", "MTI", 177),
    ("Monmouth Hawks", "MHA", 178),
    ("Montana Grizzlies", "MGR", 179),
    ("Montana St Bobcats", "MSB", 180),
    ("Morehead St Eagles", "MSE", 181),
    ("Morgan St Bears", "MSB", 182),
    ("Mt. St. Mary's Mountaineers", "MSMSM", 183),
    ("Murray St Racers", "MSR", 184),
    ("N Colorado Bears", "NCB", 207),
    ("NC State Wolfpack", "NSW", 185),
    ("NJIT Highlanders", "NHI", 186),
    ("Navy Midshipmen", "NMI", 187),
    ("Nebraska Cornhuskers", "NCO", 188),
    ("Nevada Wolf Pack", "NWP", 189),
    ("New Hampshire Wildcats", "NHW", 190),
    ("New Haven Chargers", "NHC", 1507),
    ("New Mexico Lobos", "NML", 191),
    ("New Mexico St Aggies", "NMSA", 192),
    ("New Orleans Privateers", "NOP", 193),
    ("Niagara Purple Eagles", "NPE", 194),
    ("Nicholls St Colonels", "NSC", 195),
    ("Norfolk St Spartans", "NSS", 196),
    ("North Alabama Lions", "NAL", 197),
    ("North Carolina A&T Aggies", "NCATA", 198),
    ("North Carolina Tar Heels", "NCTH", 200),
    ("North Dakota Fighting Hawks", "NDFH", 201),
    ("North Dakota St Bison", "NDSB", 202),
    ("North Florida Ospreys", "NFO", 203),
    ("North Texas Mean Green", "NTMG", 204),
    ("Northeastern Huskies", "NHU", 205),
    ("Northern Arizona Lumberjacks", "NAL", 206),
    ("Northern Illinois Huskies", "NIH", 208),
    ("Northern Iowa Panthers", "NIP", 209),
    ("Northern Kentucky Norse", "NKN", 210),
    ("Northwestern St Demons", "NSD", 211),
    ("Northwestern Wildcats", "NWI", 212),
    ("Notre Dame Fighting Irish", "NDFI", 213),
    ("Oakland Golden Grizzlies", "OGG", 214),
    ("Ohio Bobcats", "OBO", 215),
    ("Ohio State Buckeyes", "OSB", 216),
    ("Oklahoma Sooners", "OSO", 217),
    ("Oklahoma St Cowboys", "OSC", 218),
    ("Old Dominion Monarchs", "ODM", 219),
    ("Ole Miss Rebels", "OMR", 220),
    ("Omaha Mavericks", "OMA", 221),
    ("Oral Roberts Golden Eagles", "ORGE", 222),
    ("Oregon Ducks", "ODU", 223),
    ("Oregon St Beavers", "OSB", 224),
    ("Pacific Tigers", "PTI", 225),
    ("Penn State Nittany Lions", "PSNL", 226),
    ("Pennsylvania Quakers", "PQU", 227),
    ("Pepperdine Waves", "PWA", 228),
    ("Pittsburgh Panthers", "PPA", 229),
    ("Portland Pilots", "PPI", 230),
    ("Portland St Vikings", "PSV", 231),
    ("Prairie View Panthers", "PVP", 232),
    ("Presbyterian Blue Hose", "PBH", 233),
    ("Princeton Tigers", "PTI", 234),
    ("Providence Friars", "PFR", 235),
    ("Purdue Boilermakers", "PBO", 236),
    ("Queens University Royals", "QUR", 362),
    ("Quinnipiac Bobcats", "QBO", 238),
    ("Radford Highlanders", "RHI", 239),
    ("Rhode Island Rams", "RIR", 240),
    ("Rice Owls", "ROW", 241),
    ("Richmond Spiders", "RSP", 242),
    ("Rider Broncs", "RBR", 243),
    ("Robert Morris Colonials", "RMC", 244),
    ("Rutgers Scarlet Knights", "RSK", 245),
    ("SE Louisiana Lions", "SLL", 246),
    ("SE Missouri St Redhawks", "SMSR", 272),
    ("SIU-Edwardsville Cougars", "SEC", 247),
    ("SMU Mustangs", "SMU", 248),
    ("Sacramento St Hornets", "SSH", 249),
    ("Sacred Heart Pioneers", "SHP", 250),
    ("Saint Joseph's Hawks", "SJSH", 251),
    ("Saint Louis Billikens", "SLB", 252),
    ("Saint Mary's Gaels", "SMSG", 253),
    ("Saint Peter's Peacocks", "SPSP", 254),
    ("Sam Houston St Bearkats", "SHSB", 255),
    ("Samford Bulldogs", "SBU", 256),
    ("San Diego St Aztecs", "SDSA", 257),
    ("San Diego Toreros", "SDT", 258),
    ("San Francisco Dons", "SFD", 259),
    ("San José St Spartans", "SJSS", 260),
    ("Santa Clara Broncos", "SCB", 261),
    ("Seattle Redhawks", "SRE", 262),
    ("Seton Hall Pirates", "SHP", 263),
    ("Siena Saints", "SSA", 264),
    ("South Alabama Jaguars", "SAJ", 265),
    ("South Carolina Gamecocks", "SCG", 266),
    ("South Carolina St Bulldogs", "SCSB", 267),
    ("South Carolina Upstate Spartans", "SCUS", 268),
    ("South Dakota Coyotes", "SDC", 269),
    ("South Dakota St Jackrabbits", "SDSJ", 270),
    ("South Florida Bulls", "SFB", 271),
    ("Southern Illinois Salukis", "SIS", 273),
    ("Southern Indiana Screaming Eagles", "SISE", 365),
    ("Southern Jaguars", "SJA", 274),
    ("Southern Miss Golden Eagles", "SMGE", 275),
    ("Southern Utah Thunderbirds", "SUT", 276),
    ("St. Bonaventure Bonnies", "SBB", 277),
    ("St. Francis (PA) Red Flash", "SFPRF", 278),
    ("St. John's Red Storm", "SJSRS", 279),
    ("St. Thomas (MN) Tommies", "STMT", 280),
    ("Stanford Cardinal", "SCA", 281),
    ("Stephen F. Austin Lumberjacks", "SFAL", 282),
    ("Stetson Hatters", "SHA", 283),
    ("Stonehill Skyhawks", "SSK", 284),
    ("Stony Brook Seawolves", "SBS", 285),
    ("Syracuse Orange", "SOR", 286),
    ("TCU Horned Frogs", "THF", 287),
    ("Tarleton State Texans", "TST", 288),
    ("Temple Owls", "TOW", 289),
    ("Tenn-Martin Skyhawks", "TMS", 325),
    ("Tennessee St Tigers", "TST", 290),
    ("Tennessee Tech Golden Eagles", "TTGE", 291),
    ("Tennessee Volunteers", "TVO", 292),
    ("Texas A&M Aggies", "TAMA", 293),
    ("Texas A&M-CC Islanders", "TAMCI", 294),
    ("Texas Longhorns", "TLO", 295),
    ("Texas State Bobcats", "TSB", 297),
    ("Texas Tech Red Raiders", "TTRR", 298),
    ("The Citadel Bulldogs", "CBU", 299),
    ("Toledo Rockets", "TRO", 300),
    ("Towson Tigers", "TTI", 301),
    ("Troy Trojans", "TTR", 302),
    ("Tulane Green Wave", "TGW", 303),
    ("Tulsa Golden Hurricane", "TGH", 304),
    ("UAB Blazers", "UBL", 305),
    ("UC Davis Aggies", "UCDA", 307),
    ("UC Irvine Anteaters", "UCIR", 308),
    ("UC Riverside Highlanders", "UCRI", 309),
    ("UC San Diego Tritons", "UCSA", 310),
    ("UC Santa Barbara Gauchos", "UCSA", 311),
    ("UCF Knights", "UKN", 312),
    ("UCLA Bruins", "UBR", 313),
    ("UConn Huskies", "UHU", 314),
    ("UIC Flames", "UFL", 315),
    ("UL Monroe Warhawks", "UMW", 316),
    ("UMBC Retrievers", "URE", 317),
    ("UMKC Kangaroos", "UKA", 130),
    ("UMass Lowell River Hawks", "ULRH", 318),
    ("UNC Asheville Bulldogs", "UNCAS", 319),
    ("UNC Greensboro Spartans", "UNCGR", 320),
    ("UNC Wilmington Seahawks", "UNCWI", 321),
    ("UNLV Rebels", "URE", 322),
    ("USC Trojans", "UTR", 323),
    ("UT Rio Grande Valley Vaqueros", "URGVV", 326),
    ("UT-Arlington Mavericks", "UAM", 324),
    ("UTEP Miners", "UMI", 327),
    ("UTSA Roadrunners", "URO", 328),
    ("Utah State Aggies", "USA", 329),
    ("Utah Tech Trailblazers", "UTT", 330),
    ("Utah Utes", "UUT", 331),
    ("Utah Valley Wolverines", "UVW", 332),
    ("VCU Rams", "VRA", 333),
    ("VMI Keydets", "VKE", 334),
    ("Valparaiso Beacons", "VBE", 335),
    ("Vanderbilt Commodores", "VCO", 336),
    ("Vermont Catamounts", "VCA", 337),
    ("Villanova Wildcats", "VWI", 338),
    ("Virginia Cavaliers", "VCA", 339),
    ("Virginia Tech Hokies", "VTH", 340),
    ("Wagner Seahawks", "WSE", 341),
    ("Wake Forest Demon Deacons", "WFDD", 342),
    ("Washington Huskies", "WHU", 343),
    ("Washington St Cougars", "WSC", 344),
    ("Weber State Wildcats", "WSW", 345),
    ("West Georgia Wolves", "WGW", 346),
    ("West Virginia Mountaineers", "WVM", 347),
    ("Western Carolina Catamounts", "WCC", 348),
    ("Western Illinois Leathernecks", "WIL", 349),
    ("Western Kentucky Hilltoppers", "WKH", 350),
    ("Western Michigan Broncos", "WMB", 351),
    ("Wichita St Shockers", "WSS", 352),
    ("William & Mary Tribe", "WMT", 353),
    ("Winthrop Eagles", "WEA", 354),
    ("Wisconsin Badgers", "WBA", 355),
    ("Wofford Terriers", "WTE", 356),
    ("Wright St Raiders", "WSR", 357),
    ("Wyoming Cowboys", "WCO", 358),
    ("Xavier Musketeers", "XMU", 359),
    ("Yale Bulldogs", "YBU", 360),
    ("Youngstown St Penguins", "YSP", 361),
]


def upgrade() -> None:
    """Seed NCAAB teams with cbb_team_id mappings."""
    conn = op.get_bind()

    # Get NCAAB league ID
    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        print("NCAAB league not found - skipping team seed")
        return
    league_id = row[0]

    # Check if teams already exist
    result = conn.execute(text(
        "SELECT COUNT(*) FROM sports_teams WHERE league_id = :lid"
    ), {"lid": league_id})
    existing_count = result.fetchone()[0]

    if existing_count >= 350:
        print(f"Already have {existing_count} NCAAB teams, skipping seed")
        return

    if existing_count > 0:
        print(f"Found {existing_count} existing NCAAB teams - clearing before seed")
        conn.execute(text("DELETE FROM sports_teams WHERE league_id = :lid"), {"lid": league_id})

    print(f"Seeding {len(NCAAB_TEAMS)} NCAAB teams...")

    insert_stmt = text("""
        INSERT INTO sports_teams (league_id, name, short_name, abbreviation, external_codes)
        VALUES (:lid, :name, :short_name, :abbr, CAST(:codes AS jsonb))
    """)

    for name, abbr, cbb_team_id in NCAAB_TEAMS:
        # Derive short_name by removing the mascot (last word)
        # e.g., "Abilene Christian Wildcats" -> "Abilene Christian"
        parts = name.rsplit(" ", 1)
        short_name = parts[0] if len(parts) > 1 else name

        codes = json.dumps({"cbb_team_id": cbb_team_id})
        conn.execute(insert_stmt, {
            "lid": league_id,
            "name": name,
            "short_name": short_name,
            "abbr": abbr,
            "codes": codes,
        })

    print(f"Seeded {len(NCAAB_TEAMS)} NCAAB teams with cbb_team_id mappings")


def downgrade() -> None:
    """Remove seeded NCAAB teams."""
    conn = op.get_bind()

    result = conn.execute(text("SELECT id FROM sports_leagues WHERE code = 'NCAAB'"))
    row = result.fetchone()
    if not row:
        return

    # Only delete teams that were seeded by this migration
    # (teams with cbb_team_id matching our list)
    cbb_ids = [t[2] for t in NCAAB_TEAMS]

    conn.execute(text("""
        DELETE FROM sports_teams
        WHERE league_id = :lid
        AND (external_codes->>'cbb_team_id')::int = ANY(:cbb_ids)
    """), {"lid": row[0], "cbb_ids": cbb_ids})
