"""Seed NCAAB team social handles for X/Twitter.

Covers 350 of 358 NCAAB teams in the database. The 8 omitted teams are
recent D-I transitional programs without verified MBB-specific handles:
Le Moyne, Mercyhurst, Stonehill, Queens, Southern Indiana, Lindenwood,
New Haven, West Georgia.

Matches teams by cbb_team_id in external_codes JSONB rather than abbreviation,
since NCAAB abbreviations have duplicates (e.g. BBE = Baylor, Binghamton, Brown).

Revision ID: 20260208_000001
Revises: 20260220_000001
Create Date: 2026-02-08
"""

from alembic import op
from sqlalchemy import text


revision = "20260208_000001"
down_revision = "20260220_000001"
branch_labels = None
depends_on = None


# cbb_team_id → X handle mapping (350 teams, sorted by cbb_team_id)
NCAAB_SOCIAL_HANDLES: dict[int, str] = {
    1: "ACU_MBB",              # Abilene Christian Wildcats
    2: "AF_MBB",               # Air Force Falcons
    3: "ZipsMBB",              # Akron Zips
    5: "AlabamaMBB",           # Alabama Crimson Tide
    6: "BamaStateMBB",         # Alabama St Hornets
    7: "BRAVESMBB",            # Alcorn St Braves
    8: "AU_Mbasketball",       # American Eagles
    9: "AppStateMBB",          # Appalachian St Mountaineers
    10: "SunDevilHoops",       # Arizona St Sun Devils
    11: "APlayersProgram",     # Arizona Wildcats
    12: "RazorbackMBB",        # Arkansas Razorbacks
    13: "AStateMB",            # Arkansas St Red Wolves
    14: "UAPBLionsRoar",       # Arkansas-Pine Bluff Golden Lions
    15: "ArmyWP_MBB",         # Army Knights
    16: "AuburnMBB",           # Auburn Tigers
    17: "AustinPeayMBB",       # Austin Peay Governors
    18: "BYUBasketball",       # BYU Cougars
    19: "BallStateMBB",        # Ball State Cardinals
    20: "BaylorMBB",           # Baylor Bears
    21: "BUKnightsMBB",        # Bellarmine Knights
    22: "BelmontMBB",          # Belmont Bruins
    23: "BCUHoops",            # Bethune-Cookman Wildcats
    24: "BinghamtonMBB",       # Binghamton Bearcats
    25: "BroncoSportsMBB",     # Boise State Broncos
    26: "BCMBB",               # Boston College Eagles
    27: "TerrierMBB",          # Boston Univ. Terriers
    28: "BGSUMHoops",          # Bowling Green Falcons
    29: "BradleyUMBB",         # Bradley Braves
    30: "BrownBasketball",     # Brown Bears
    31: "BryantHoops",         # Bryant Bulldogs
    32: "Bucknell_MBB",        # Bucknell Bison
    33: "UBMensHoops",         # Buffalo Bulls
    34: "ButlerMBB",           # Butler Bulldogs
    35: "CalPolyMBB",          # Cal Poly Mustangs
    36: "CSUB_MBB",            # CSU Bakersfield Roadrunners
    37: "FullertonMBB",        # CSU Fullerton Titans
    38: "CSUNMBB",             # CSU Northridge Matadors
    39: "CBUmbb",              # Cal Baptist Lancers
    40: "CalMBBall",           # California Golden Bears
    41: "GoCamelsMBB",         # Campbell Fighting Camels
    42: "Griffs_MBB",          # Canisius Golden Griffins
    43: "UCAMBB",              # Central Arkansas Bears
    44: "CCSU_MBB",            # Central Connecticut St Blue Devils
    45: "CMUMensBBall",        # Central Michigan Chippewas
    46: "CofCBasketball",      # Charleston Cougars
    47: "CSU_MBBall",          # Charleston Southern Buccaneers
    48: "CharlotteMBB",        # Charlotte 49ers
    49: "GoMocsMBB",           # Chattanooga Mocs
    50: "ChicagoStateMBB",     # Chicago St Cougars
    51: "GoBearcatsMBB",       # Cincinnati Bearcats
    52: "ClemsonMBB",          # Clemson Tigers
    53: "CSU_Basketball",      # Cleveland St Vikings
    54: "CoastalMBB",          # Coastal Carolina Chanticleers
    55: "ColgateMBB",          # Colgate Raiders
    56: "CUBuffsMBB",          # Colorado Buffaloes
    57: "CSUMBasketball",      # Colorado St Rams
    58: "CULionsMBB",          # Columbia Lions
    60: "CUBigRedHoops",       # Cornell Big Red
    61: "BluejayMBB",          # Creighton Bluejays
    62: "DartmouthMBK",        # Dartmouth Big Green
    63: "DavidsonMBB",         # Davidson Wildcats
    64: "DaytonMBB",           # Dayton Flyers
    65: "DePaulHoops",         # DePaul Blue Demons
    66: "DelawareMBB",         # Delaware Blue Hens
    67: "DSUMBB",              # Delaware St Hornets
    68: "DU_Mhoops",           # Denver Pioneers
    69: "DetroitMBB",          # Detroit Mercy Titans
    70: "DrakeBulldogsMB",     # Drake Bulldogs
    71: "DrexelMBB",           # Drexel Dragons
    72: "DukeMBB",             # Duke Blue Devils
    73: "DuqMBB",              # Duquesne Dukes
    74: "ECUBasketball",       # East Carolina Pirates
    75: "ETSU_MBB",            # East Tennessee St Buccaneers
    76: "Lion_MBB",            # East Texas A&M Lions (fka Texas A&M-Commerce)
    77: "EIUBasketball",       # Eastern Illinois Panthers
    78: "EKUHoops",            # Eastern Kentucky Colonels
    79: "EMUHoops",            # Eastern Michigan Eagles
    80: "EWUMBB",              # Eastern Washington Eagles
    81: "ElonMBasketball",     # Elon Phoenix
    82: "UEAthletics_MBB",    # Evansville Purple Aces
    83: "StagsMensBBall",      # Fairfield Stags
    84: "FDU_MBB",             # Fairleigh Dickinson Knights
    85: "FAMUAthletics",       # Florida A&M Rattlers
    86: "FAU_Hoops",           # Florida Atlantic Owls
    87: "GatorsMBK",           # Florida Gators
    88: "FGCU_MBB",            # Florida Gulf Coast Eagles
    89: "FIUHoops",            # Florida Int'l Golden Panthers
    90: "FSUHoops",            # Florida St Seminoles
    91: "FordhamMBB",          # Fordham Rams
    92: "FresnoStateMBB",      # Fresno St Bulldogs
    93: "FurmanHoops",         # Furman Paladins
    94: "GWU_MBK",             # Gardner-Webb Bulldogs
    95: "MasonMBB",            # George Mason Patriots
    96: "GW_MBB",              # GW Revolutionaries
    97: "GeorgetownHoops",     # Georgetown Hoyas
    98: "UGABasketball",       # Georgia Bulldogs
    99: "GSAthletics_MBB",     # Georgia Southern Eagles
    100: "GeorgiaStateMBB",    # Georgia St Panthers
    101: "GTMBB",              # Georgia Tech Yellow Jackets
    102: "ZagMBB",             # Gonzaga Bulldogs
    104: "GCU_MBB",            # Grand Canyon Antelopes
    105: "GBPhoenixMBB",       # Green Bay Phoenix
    106: "Hampton_MBB",        # Hampton Pirates
    107: "HarvardMBB",         # Harvard Crimson
    108: "HawaiiMBB",          # Hawai'i Rainbow Warriors
    109: "HPUMBB",             # High Point Panthers
    110: "HofstraMBB",         # Hofstra Pride
    111: "HCrossMBB",          # Holy Cross Crusaders
    112: "HCUHoops",           # Houston Christian Huskies
    113: "UHCougarMBK",        # Houston Cougars
    115: "IUPUIMensBBall",     # IUPUI Jaguars
    116: "IdahoStateBBall",    # Idaho State Bengals
    117: "VandalHoops",        # Idaho Vandals
    118: "IlliniMBB",          # Illinois Fighting Illini
    119: "Redbird_MBB",        # Illinois St Redbirds
    120: "UIWMBB",             # Incarnate Word Cardinals
    121: "IndianaMBB",         # Indiana Hoosiers
    122: "IndStMBB",           # Indiana St Sycamores
    123: "IonaGaelsMBB",       # Iona Gaels
    124: "IowaHoops",          # Iowa Hawkeyes
    125: "CycloneMBB",         # Iowa State Cyclones
    126: "GoJSUTigersMBB",     # Jackson St Tigers
    127: "JAX_MBB",            # Jacksonville Dolphins
    128: "JSU_MBB",            # Jacksonville St Gamecocks
    129: "JMUMBasketball",     # James Madison Dukes
    130: "KCRoosMBB",          # UMKC Kangaroos
    131: "KUHoops",            # Kansas Jayhawks
    132: "KStateMBB",          # Kansas St Wildcats
    133: "KSUOwlsMBB",         # Kennesaw St Owls
    134: "KentStMBB",          # Kent State Golden Flashes
    135: "KentuckyMBB",        # Kentucky Wildcats
    136: "LSUBasketball",      # LSU Tigers
    137: "LaSalleMBB",         # La Salle Explorers
    138: "LafayetteMBB",       # Lafayette Leopards
    139: "LamarMBB",           # Lamar Cardinals
    141: "LehighMBB",          # Lehigh Mountain Hawks
    142: "LibertyMBB",         # Liberty Flames
    143: "LipscombMBB",        # Lipscomb Bisons
    144: "LittleRockMBB",      # Arkansas-Little Rock Trojans
    145: "LBSUhoops",          # Long Beach St 49ers
    146: "LIUBasketball",      # LIU Sharks
    147: "LongwoodMBB",        # Longwood Lancers
    148: "RaginCajunsMBB",     # Louisiana Ragin' Cajuns
    149: "LATechHoops",        # Louisiana Tech Bulldogs
    150: "LouisvilleMBB",      # Louisville Cardinals
    151: "RamblersMBB",        # Loyola (Chi) Ramblers
    152: "LoyolaMBB",          # Loyola (MD) Greyhounds
    153: "LMULionsMBB",        # Loyola Marymount Lions
    154: "BlackBearsMBB",      # Maine Black Bears
    155: "JaspersMBB",         # Manhattan Jaspers
    156: "MaristMBB",          # Marist Red Foxes
    157: "MarquetteMBB",       # Marquette Golden Eagles
    158: "HerdMBB",            # Marshall Thundering Herd
    160: "TerrapinHoops",      # Maryland Terrapins
    161: "UMassBasketball",    # Massachusetts Minutemen
    162: "McNeeseMBB",         # McNeese Cowboys
    163: "Memphis_MBB",        # Memphis Tigers
    164: "MercerMBB",          # Mercer Bears
    166: "MerrimackMBB",       # Merrimack Warriors
    167: "MiamiOH_Bball",      # Miami (OH) RedHawks
    168: "CanesHoops",         # Miami Hurricanes
    169: "MSU_Basketball",     # Michigan St Spartans
    170: "UMichBBall",         # Michigan Wolverines
    171: "MT_MBB",             # Middle Tennessee Blue Raiders
    172: "MKE_MBB",            # Milwaukee Panthers
    173: "GopherMBB",          # Minnesota Golden Gophers
    174: "HailStateMBK",       # Mississippi St Bulldogs
    175: "MVSUDevilSports",    # Miss Valley St Delta Devils
    176: "MSUBearsHoops",      # Missouri St Bears
    177: "MizzouHoops",        # Missouri Tigers
    178: "MonmouthBBall",      # Monmouth Hawks
    179: "MontanaGrizBB",      # Montana Grizzlies
    180: "MSUBobcatsMBB",      # Montana St Bobcats
    181: "MSUEaglesMBB",       # Morehead St Eagles
    182: "MSUBearsMBB",        # Morgan St Bears
    183: "MountHoops",         # Mt. St. Mary's Mountaineers
    184: "RacersHoops",        # Murray St Racers
    185: "PackMensBball",      # NC State Wolfpack
    186: "NJITHoops",          # NJIT Highlanders
    187: "NavyBasketball",     # Navy Midshipmen
    188: "HuskerHoops",        # Nebraska Cornhuskers
    189: "NevadaHoops",        # Nevada Wolf Pack
    190: "UNHMBB",             # New Hampshire Wildcats
    191: "UNMLoboMBB",         # New Mexico Lobos
    192: "NMStateMBB",         # New Mexico St Aggies
    193: "PrivateersMBB",      # New Orleans Privateers
    194: "NiagaraMBB",         # Niagara Purple Eagles
    195: "Nicholls_MBB",       # Nicholls St Colonels
    196: "NSU_Bball",          # Norfolk St Spartans
    197: "UNA_MBB",            # North Alabama Lions
    198: "NCATBasketball",     # North Carolina A&T Aggies
    200: "UNC_Basketball",     # North Carolina Tar Heels
    201: "UNDMBasketball",     # North Dakota Fighting Hawks
    202: "NDSUmbb",            # North Dakota St Bison
    203: "OspreysMBB",         # North Florida Ospreys
    204: "MeanGreenMBB",       # North Texas Mean Green
    205: "GoNUmbasketball",    # Northeastern Huskies
    206: "NAUBasketball",      # Northern Arizona Lumberjacks
    207: "UNC_Bears",          # N Colorado Bears
    208: "GoHuskiesMBB",       # Northern Illinois Huskies
    209: "UNImbb",             # Northern Iowa Panthers
    210: "NKUNorseMBB",        # Northern Kentucky Norse
    211: "NSUDemonsMBB",       # Northwestern St Demons
    212: "NUMensBball",        # Northwestern Wildcats
    213: "NDMBB",              # Notre Dame Fighting Irish
    214: "OaklandMBB",         # Oakland Golden Grizzlies
    215: "OhioMBasketball",    # Ohio Bobcats
    216: "OhioStateHoops",     # Ohio State Buckeyes
    217: "OU_MBBall",          # Oklahoma Sooners
    218: "OSUMBB",             # Oklahoma St Cowboys
    219: "ODUMBB",             # Old Dominion Monarchs
    220: "OleMissMBB",         # Ole Miss Rebels
    221: "OmahaMBB",           # Omaha Mavericks
    222: "ORUMBB",             # Oral Roberts Golden Eagles
    223: "OregonMBB",          # Oregon Ducks
    224: "BeaverMBB",          # Oregon St Beavers
    225: "PacificMensBB",      # Pacific Tigers
    226: "PennStateMBB",       # Penn State Nittany Lions
    227: "PennBasketball",     # Pennsylvania Quakers
    228: "PeppBasketball",     # Pepperdine Waves
    229: "Pitt_MBB",           # Pittsburgh Panthers
    230: "PilotHoops",         # Portland Pilots
    231: "PSUViksMBB",         # Portland St Vikings
    232: "PVAMU_MBB",          # Prairie View Panthers
    233: "BlueHoseHoops",      # Presbyterian Blue Hose
    234: "Princeton_Hoops",    # Princeton Tigers
    235: "PCFriarsMBB",        # Providence Friars
    236: "BoilerBall",         # Purdue Boilermakers
    237: "MastodonMBB",        # Fort Wayne Mastodons
    238: "QU_MBB",             # Quinnipiac Bobcats
    239: "RadfordMBB",         # Radford Highlanders
    240: "RhodyMBB",           # Rhode Island Rams
    241: "RiceBasketball",     # Rice Owls
    242: "SpiderMBB",          # Richmond Spiders
    243: "RiderMBB",           # Rider Broncs
    244: "RMUMBasketball",     # Robert Morris Colonials
    245: "RutgersMBB",         # Rutgers Scarlet Knights
    246: "SLU_Hoops",          # SE Louisiana Lions
    247: "SIUEMBB",            # SIU-Edwardsville Cougars
    248: "SMUBasketball",      # SMU Mustangs
    249: "SacHornetsMBB",      # Sacramento St Hornets
    250: "SHU_MensHoops",      # Sacred Heart Pioneers
    251: "SJUHawks_MBB",       # Saint Joseph's Hawks
    252: "SaintLouisMBB",      # Saint Louis Billikens
    253: "SaintMarysHoops",    # Saint Mary's Gaels
    254: "PeacocksMBB",        # Saint Peter's Peacocks
    255: "BearkatsMBB",        # Sam Houston St Bearkats
    256: "SamfordMBB",         # Samford Bulldogs
    257: "Aztec_MBB",          # San Diego St Aztecs
    258: "USDMBB",             # San Diego Toreros
    259: "USFDonsMBB",         # San Francisco Dons
    260: "SJSUMBB",            # San José St Spartans
    261: "SantaClaraHoops",    # Santa Clara Broncos
    262: "SeattleUMBB",        # Seattle Redhawks
    263: "SetonHallMBB",       # Seton Hall Pirates
    264: "SienaMBB",           # Siena Saints
    265: "WeAreSouth_MBB",     # South Alabama Jaguars
    266: "GamecockMBB",        # South Carolina Gamecocks
    267: "SCStateAthletic",    # South Carolina St Bulldogs
    268: "UpstateMB",          # South Carolina Upstate Spartans
    269: "SDCoyotesMBB",       # South Dakota Coyotes
    270: "GoJacksMBB",         # South Dakota St Jackrabbits
    271: "USFMBB",             # South Florida Bulls
    272: "SEMOMBB",            # SE Missouri St Redhawks
    273: "SIU_Basketball",     # Southern Illinois Salukis
    274: "JaguarHoops",        # Southern Jaguars
    275: "SouthernMissMBB",    # Southern Miss Golden Eagles
    276: "SUUBasketball",      # Southern Utah Thunderbirds
    277: "BonniesMBB",         # St. Bonaventure Bonnies
    278: "RedFlashMBB",        # St. Francis (PA) Red Flash
    279: "StJohnsBBall",       # St. John's Red Storm
    280: "TommieMBBall",       # St. Thomas (MN) Tommies
    281: "StanfordMBB",        # Stanford Cardinal
    282: "SFA_MBB",            # Stephen F. Austin Lumberjacks
    283: "StetsonMBB",         # Stetson Hatters
    285: "StonyBrookMBB",      # Stony Brook Seawolves
    286: "Cuse_MBB",           # Syracuse Orange
    287: "TCUBasketball",      # TCU Horned Frogs
    288: "TarletonMBB",        # Tarleton State Texans
    289: "TUMBBHoops",         # Temple Owls
    290: "TSUTigersMBB",       # Tennessee St Tigers
    291: "TTU_Basketball",     # Tennessee Tech Golden Eagles
    292: "Vol_Hoops",          # Tennessee Volunteers
    293: "AggieMBK",           # Texas A&M Aggies
    294: "IslandersMBB",       # Texas A&M-CC Islanders
    295: "TexasMBB",           # Texas Longhorns
    297: "TXStateMBB",         # Texas State Bobcats
    298: "TexasTechMBB",       # Texas Tech Red Raiders
    299: "CitadelHoops",       # The Citadel Bulldogs
    300: "ToledoMBB",          # Toledo Rockets
    301: "Towson_MBB",         # Towson Tigers
    302: "TroyTrojansMBB",     # Troy Trojans
    303: "GreenWaveMBB",       # Tulane Green Wave
    304: "TUMBasketball",      # Tulsa Golden Hurricane
    305: "UAB_MBB",            # UAB Blazers
    306: "UAlbanyMBB",         # Albany Great Danes
    307: "UCDavisMBB",         # UC Davis Aggies
    308: "UCImbb",             # UC Irvine Anteaters
    309: "UCRMBB",             # UC Riverside Highlanders
    310: "UCSDmbb",            # UC San Diego Tritons
    311: "UCSBbasketball",     # UC Santa Barbara Gauchos
    312: "UCF_MBB",            # UCF Knights
    313: "UCLAMBB",            # UCLA Bruins
    314: "UConnMBB",           # UConn Huskies
    315: "UICFlamesMBB",       # UIC Flames
    316: "ULM_MBB",            # UL Monroe Warhawks
    317: "UMBC_MBB",           # UMBC Retrievers
    318: "RiverHawkMBB",       # UMass Lowell River Hawks
    319: "UNCAvlMBB",          # UNC Asheville Bulldogs
    320: "UNCGBasketball",     # UNC Greensboro Spartans
    321: "UNCWMensHoops",      # UNC Wilmington Seahawks
    322: "TheRunninRebels",    # UNLV Rebels
    323: "USC_Hoops",          # USC Trojans
    324: "UTA_MBB",            # UT-Arlington Mavericks
    325: "SkyhawkHoops",       # Tenn-Martin Skyhawks
    326: "UTRGMBB",            # UT Rio Grande Valley Vaqueros
    327: "UTEP_MBB",           # UTEP Miners
    328: "UTSAMBB",            # UTSA Roadrunners
    329: "USUBasketball",      # Utah State Aggies
    330: "UtahTechMBB",        # Utah Tech Trailblazers
    331: "UtahMBB",            # Utah Utes
    332: "UVUMBB",             # Utah Valley Wolverines
    333: "VCU_Hoops",          # VCU Rams
    334: "VMI_Basketball",     # VMI Keydets
    335: "ValpoBasketball",    # Valparaiso Beacons
    336: "VandyMBB",           # Vanderbilt Commodores
    337: "UVMmbb",             # Vermont Catamounts
    338: "NovaMBB",            # Villanova Wildcats
    339: "UVAMensHoops",       # Virginia Cavaliers
    340: "HokiesMBB",          # Virginia Tech Hokies
    341: "Wagner_MBB",         # Wagner Seahawks
    342: "WakeMBB",            # Wake Forest Demon Deacons
    343: "UW_MBB",             # Washington Huskies
    344: "WSUMensHoops",       # Washington St Cougars
    345: "WeberStateMBB",      # Weber State Wildcats
    347: "WVUHoops",           # West Virginia Mountaineers
    348: "WCU_MBB",            # Western Carolina Catamounts
    349: "WIUMensHoops",       # Western Illinois Leathernecks
    350: "WKUBasketball",      # Western Kentucky Hilltoppers
    351: "WMUMBB",             # Western Michigan Broncos
    352: "GoShockersMBB",      # Wichita St Shockers
    353: "WMTribeMBB",         # William & Mary Tribe
    354: "Winthrop_MBB",       # Winthrop Eagles
    355: "BadgerMBB",          # Wisconsin Badgers
    356: "WoffordMBB",         # Wofford Terriers
    357: "WSU_MBB",            # Wright St Raiders
    358: "Wyo_MBB",            # Wyoming Cowboys
    359: "XavierMBB",          # Xavier Musketeers
    360: "Yale_Basketball",    # Yale Bulldogs
    361: "YSUMensHoops",       # Youngstown St Penguins
}


def upgrade() -> None:
    """Insert NCAAB team social handles.

    Inserts each team's handle individually using parameterized queries.
    Matches by cbb_team_id in external_codes JSONB (not abbreviation).
    Only inserts for teams that exist and don't already have a handle.
    """
    conn = op.get_bind()

    insert_sql = text("""
        INSERT INTO team_social_accounts (team_id, league_id, platform, handle, is_active)
        SELECT t.id, t.league_id, 'x', :handle, true
        FROM sports_teams t
        JOIN sports_leagues l ON t.league_id = l.id
        WHERE l.code = 'NCAAB'
          AND (t.external_codes->>'cbb_team_id')::int = :cbb_team_id
        ON CONFLICT (team_id, platform) DO NOTHING
    """)

    for cbb_team_id, handle in NCAAB_SOCIAL_HANDLES.items():
        conn.execute(insert_sql, {"cbb_team_id": cbb_team_id, "handle": handle})


def downgrade() -> None:
    """Remove NCAAB team social handles."""
    conn = op.get_bind()

    sql = """
    DELETE FROM team_social_accounts
    WHERE platform = 'x'
      AND league_id = (SELECT id FROM sports_leagues WHERE code = 'NCAAB')
    """
    conn.execute(text(sql))
