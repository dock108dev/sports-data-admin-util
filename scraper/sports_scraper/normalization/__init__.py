"""Team name normalization for matching across data sources.

Handles variations in team names between Basketball Reference, The Odds API, and other sources.
"""

from __future__ import annotations

import re
from typing import Literal

SportCode = Literal["NBA", "NFL", "NCAAF", "NCAAB", "MLB", "NHL"]

# Canonical team data: (canonical_name, abbreviation, common_variations)
# Abbreviations match Basketball Reference standards
NBA_TEAMS = {
    "Atlanta Hawks": ("Atlanta Hawks", "ATL", ["Atlanta", "Hawks"]),
    "Boston Celtics": ("Boston Celtics", "BOS", ["Boston", "Celtics"]),
    "Brooklyn Nets": ("Brooklyn Nets", "BKN", ["Brooklyn", "Nets", "New Jersey Nets", "NJ Nets"]),
    "Charlotte Hornets": ("Charlotte Hornets", "CHA", ["Charlotte", "Hornets"]),
    "Chicago Bulls": ("Chicago Bulls", "CHI", ["Chicago", "Bulls"]),
    "Cleveland Cavaliers": ("Cleveland Cavaliers", "CLE", ["Cleveland", "Cavaliers", "Cavs"]),
    "Dallas Mavericks": ("Dallas Mavericks", "DAL", ["Dallas", "Mavericks", "Mavs"]),
    "Denver Nuggets": ("Denver Nuggets", "DEN", ["Denver", "Nuggets"]),
    "Detroit Pistons": ("Detroit Pistons", "DET", ["Detroit", "Pistons"]),
    "Golden State Warriors": ("Golden State Warriors", "GSW", ["Golden State", "Warriors", "GS Warriors", "Golden State Warriors"]),
    "Houston Rockets": ("Houston Rockets", "HOU", ["Houston", "Rockets"]),
    "Indiana Pacers": ("Indiana Pacers", "IND", ["Indiana", "Pacers"]),
    "LA Clippers": ("LA Clippers", "LAC", ["Los Angeles Clippers", "L.A. Clippers", "Clippers", "LA Clippers"]),
    "LA Lakers": ("LA Lakers", "LAL", ["Los Angeles Lakers", "L.A. Lakers", "Lakers", "LA Lakers"]),
    "Memphis Grizzlies": ("Memphis Grizzlies", "MEM", ["Memphis", "Grizzlies"]),
    "Miami Heat": ("Miami Heat", "MIA", ["Miami", "Heat"]),
    "Milwaukee Bucks": ("Milwaukee Bucks", "MIL", ["Milwaukee", "Bucks"]),
    "Minnesota Timberwolves": ("Minnesota Timberwolves", "MIN", ["Minnesota", "Timberwolves", "Wolves"]),
    "New Orleans Pelicans": ("New Orleans Pelicans", "NOP", ["New Orleans", "Pelicans", "NO Pelicans", "New Orleans Pelicans"]),
    "New York Knicks": ("New York Knicks", "NYK", ["New York", "Knicks", "NY Knicks", "New York Knicks"]),
    "Oklahoma City Thunder": ("Oklahoma City Thunder", "OKC", ["Oklahoma City", "Thunder", "OKC Thunder", "Oklahoma City Thunder"]),
    "Orlando Magic": ("Orlando Magic", "ORL", ["Orlando", "Magic"]),
    "Philadelphia 76ers": ("Philadelphia 76ers", "PHI", ["Philadelphia", "76ers", "Sixers", "Philadelphia 76ers"]),
    "Phoenix Suns": ("Phoenix Suns", "PHX", ["Phoenix", "Suns"]),
    "Portland Trail Blazers": ("Portland Trail Blazers", "POR", ["Portland", "Trail Blazers", "Blazers", "Portland Trail Blazers"]),
    "Sacramento Kings": ("Sacramento Kings", "SAC", ["Sacramento", "Kings"]),
    "San Antonio Spurs": ("San Antonio Spurs", "SAS", ["San Antonio", "Spurs"]),
    "Toronto Raptors": ("Toronto Raptors", "TOR", ["Toronto", "Raptors"]),
    "Utah Jazz": ("Utah Jazz", "UTA", ["Utah", "Jazz"]),
    "Washington Wizards": ("Washington Wizards", "WAS", ["Washington", "Wizards"]),
}

# NFL teams - using Pro Football Reference abbreviations
NFL_TEAMS = {
    "Arizona Cardinals": ("Arizona Cardinals", "ARI", ["Arizona", "Cardinals"]),
    "Atlanta Falcons": ("Atlanta Falcons", "ATL", ["Atlanta", "Falcons"]),
    "Baltimore Ravens": ("Baltimore Ravens", "BAL", ["Baltimore", "Ravens"]),
    "Buffalo Bills": ("Buffalo Bills", "BUF", ["Buffalo", "Bills"]),
    "Carolina Panthers": ("Carolina Panthers", "CAR", ["Carolina", "Panthers"]),
    "Chicago Bears": ("Chicago Bears", "CHI", ["Chicago", "Bears"]),
    "Cincinnati Bengals": ("Cincinnati Bengals", "CIN", ["Cincinnati", "Bengals"]),
    "Cleveland Browns": ("Cleveland Browns", "CLE", ["Cleveland", "Browns"]),
    "Dallas Cowboys": ("Dallas Cowboys", "DAL", ["Dallas", "Cowboys"]),
    "Denver Broncos": ("Denver Broncos", "DEN", ["Denver", "Broncos"]),
    "Detroit Lions": ("Detroit Lions", "DET", ["Detroit", "Lions"]),
    "Green Bay Packers": ("Green Bay Packers", "GB", ["Green Bay", "Packers"]),
    "Houston Texans": ("Houston Texans", "HOU", ["Houston", "Texans"]),
    "Indianapolis Colts": ("Indianapolis Colts", "IND", ["Indianapolis", "Colts"]),
    "Jacksonville Jaguars": ("Jacksonville Jaguars", "JAX", ["Jacksonville", "Jaguars"]),
    "Kansas City Chiefs": ("Kansas City Chiefs", "KC", ["Kansas City", "Chiefs"]),
    "Las Vegas Raiders": ("Las Vegas Raiders", "LV", ["Las Vegas", "Raiders", "Oakland Raiders"]),
    "Los Angeles Chargers": ("Los Angeles Chargers", "LAC", ["LA Chargers", "L.A. Chargers", "Chargers"]),
    "Los Angeles Rams": ("Los Angeles Rams", "LAR", ["LA Rams", "L.A. Rams", "Rams"]),
    "Miami Dolphins": ("Miami Dolphins", "MIA", ["Miami", "Dolphins"]),
    "Minnesota Vikings": ("Minnesota Vikings", "MIN", ["Minnesota", "Vikings"]),
    "New England Patriots": ("New England Patriots", "NE", ["New England", "Patriots"]),
    "New Orleans Saints": ("New Orleans Saints", "NO", ["New Orleans", "Saints"]),
    "New York Giants": ("New York Giants", "NYG", ["NY Giants", "Giants"]),
    "New York Jets": ("New York Jets", "NYJ", ["NY Jets", "Jets"]),
    "Philadelphia Eagles": ("Philadelphia Eagles", "PHI", ["Philadelphia", "Eagles"]),
    "Pittsburgh Steelers": ("Pittsburgh Steelers", "PIT", ["Pittsburgh", "Steelers"]),
    "San Francisco 49ers": ("San Francisco 49ers", "SF", ["San Francisco", "49ers"]),
    "Seattle Seahawks": ("Seattle Seahawks", "SEA", ["Seattle", "Seahawks"]),
    "Tampa Bay Buccaneers": ("Tampa Bay Buccaneers", "TB", ["Tampa Bay", "Buccaneers"]),
    "Tennessee Titans": ("Tennessee Titans", "TEN", ["Tennessee", "Titans"]),
    "Washington Commanders": ("Washington Commanders", "WAS", ["Washington", "Commanders", "Washington Football Team"]),
}

# MLB teams - using Baseball Reference abbreviations
MLB_TEAMS = {
    "Arizona Diamondbacks": ("Arizona Diamondbacks", "ARI", ["Arizona", "Diamondbacks", "D-backs"]),
    "Atlanta Braves": ("Atlanta Braves", "ATL", ["Atlanta", "Braves"]),
    "Baltimore Orioles": ("Baltimore Orioles", "BAL", ["Baltimore", "Orioles"]),
    "Boston Red Sox": ("Boston Red Sox", "BOS", ["Boston", "Red Sox"]),
    "Chicago Cubs": ("Chicago Cubs", "CHC", ["Chicago Cubs", "Cubs"]),
    "Chicago White Sox": ("Chicago White Sox", "CWS", ["Chicago White Sox", "White Sox"]),
    "Cincinnati Reds": ("Cincinnati Reds", "CIN", ["Cincinnati", "Reds"]),
    "Cleveland Guardians": ("Cleveland Guardians", "CLE", ["Cleveland", "Guardians", "Cleveland Indians"]),
    "Colorado Rockies": ("Colorado Rockies", "COL", ["Colorado", "Rockies"]),
    "Detroit Tigers": ("Detroit Tigers", "DET", ["Detroit", "Tigers"]),
    "Houston Astros": ("Houston Astros", "HOU", ["Houston", "Astros"]),
    "Kansas City Royals": ("Kansas City Royals", "KC", ["Kansas City", "Royals"]),
    "Los Angeles Angels": ("Los Angeles Angels", "LAA", ["LA Angels", "L.A. Angels", "Angels"]),
    "Los Angeles Dodgers": ("Los Angeles Dodgers", "LAD", ["LA Dodgers", "L.A. Dodgers", "Dodgers"]),
    "Miami Marlins": ("Miami Marlins", "MIA", ["Miami", "Marlins"]),
    "Milwaukee Brewers": ("Milwaukee Brewers", "MIL", ["Milwaukee", "Brewers"]),
    "Minnesota Twins": ("Minnesota Twins", "MIN", ["Minnesota", "Twins"]),
    "New York Mets": ("New York Mets", "NYM", ["NY Mets", "Mets"]),
    "New York Yankees": ("New York Yankees", "NYY", ["NY Yankees", "Yankees"]),
    "Oakland Athletics": ("Oakland Athletics", "OAK", ["Oakland", "Athletics", "A's"]),
    "Philadelphia Phillies": ("Philadelphia Phillies", "PHI", ["Philadelphia", "Phillies"]),
    "Pittsburgh Pirates": ("Pittsburgh Pirates", "PIT", ["Pittsburgh", "Pirates"]),
    "San Diego Padres": ("San Diego Padres", "SD", ["San Diego", "Padres"]),
    "San Francisco Giants": ("San Francisco Giants", "SF", ["San Francisco", "Giants"]),
    "Seattle Mariners": ("Seattle Mariners", "SEA", ["Seattle", "Mariners"]),
    "St. Louis Cardinals": ("St. Louis Cardinals", "STL", ["St. Louis", "Cardinals"]),
    "Tampa Bay Rays": ("Tampa Bay Rays", "TB", ["Tampa Bay", "Rays"]),
    "Texas Rangers": ("Texas Rangers", "TEX", ["Texas", "Rangers"]),
    "Toronto Blue Jays": ("Toronto Blue Jays", "TOR", ["Toronto", "Blue Jays"]),
    "Washington Nationals": ("Washington Nationals", "WSH", ["Washington", "Nationals"]),
}

# NHL teams - using Hockey Reference abbreviations
NHL_TEAMS = {
    "Anaheim Ducks": ("Anaheim Ducks", "ANA", ["Anaheim", "Ducks"]),
    "Arizona Coyotes": ("Arizona Coyotes", "ARI", ["Arizona", "Coyotes"]),
    # Utah Hockey Club (relocated from Arizona in 2024)
    "Utah Hockey Club": ("Utah Hockey Club", "UTA", ["Utah", "Utah HC", "Utah Mammoth"]),
    "Boston Bruins": ("Boston Bruins", "BOS", ["Boston", "Bruins"]),
    "Buffalo Sabres": ("Buffalo Sabres", "BUF", ["Buffalo", "Sabres"]),
    "Calgary Flames": ("Calgary Flames", "CGY", ["Calgary", "Flames"]),
    "Carolina Hurricanes": ("Carolina Hurricanes", "CAR", ["Carolina", "Hurricanes"]),
    "Chicago Blackhawks": ("Chicago Blackhawks", "CHI", ["Chicago", "Blackhawks"]),
    "Colorado Avalanche": ("Colorado Avalanche", "COL", ["Colorado", "Avalanche"]),
    "Columbus Blue Jackets": ("Columbus Blue Jackets", "CBJ", ["Columbus", "Blue Jackets"]),
    "Dallas Stars": ("Dallas Stars", "DAL", ["Dallas", "Stars"]),
    "Detroit Red Wings": ("Detroit Red Wings", "DET", ["Detroit", "Red Wings"]),
    "Edmonton Oilers": ("Edmonton Oilers", "EDM", ["Edmonton", "Oilers"]),
    "Florida Panthers": ("Florida Panthers", "FLA", ["Florida", "Panthers"]),
    "Los Angeles Kings": ("Los Angeles Kings", "LAK", ["LA Kings", "L.A. Kings", "Kings"]),
    "Minnesota Wild": ("Minnesota Wild", "MIN", ["Minnesota", "Wild"]),
    "Montreal Canadiens": ("Montreal Canadiens", "MTL", ["Montreal", "Canadiens", "Montréal Canadiens", "Montréal"]),
    "Nashville Predators": ("Nashville Predators", "NSH", ["Nashville", "Predators"]),
    "New Jersey Devils": ("New Jersey Devils", "NJD", ["New Jersey", "Devils"]),
    "New York Islanders": ("New York Islanders", "NYI", ["NY Islanders", "Islanders"]),
    "New York Rangers": ("New York Rangers", "NYR", ["NY Rangers", "Rangers"]),
    "Ottawa Senators": ("Ottawa Senators", "OTT", ["Ottawa", "Senators"]),
    "Philadelphia Flyers": ("Philadelphia Flyers", "PHI", ["Philadelphia", "Flyers"]),
    "Pittsburgh Penguins": ("Pittsburgh Penguins", "PIT", ["Pittsburgh", "Penguins"]),
    "San Jose Sharks": ("San Jose Sharks", "SJS", ["San Jose", "Sharks"]),
    "Seattle Kraken": ("Seattle Kraken", "SEA", ["Seattle", "Kraken"]),
    "St. Louis Blues": ("St. Louis Blues", "STL", ["St. Louis", "Blues"]),
    "Tampa Bay Lightning": ("Tampa Bay Lightning", "TBL", ["Tampa Bay", "Lightning"]),
    "Toronto Maple Leafs": ("Toronto Maple Leafs", "TOR", ["Toronto", "Maple Leafs"]),
    "Vancouver Canucks": ("Vancouver Canucks", "VAN", ["Vancouver", "Canucks"]),
    "Vegas Golden Knights": ("Vegas Golden Knights", "VGK", ["Vegas", "Golden Knights"]),
    "Washington Capitals": ("Washington Capitals", "WSH", ["Washington", "Capitals"]),
    "Winnipeg Jets": ("Winnipeg Jets", "WPG", ["Winnipeg", "Jets"]),
}

# Build lookup dictionaries: variation -> (canonical_name, abbreviation)
TEAM_MAPPINGS: dict[SportCode, dict[str, tuple[str, str]]] = {
    "NBA": {},
    "NFL": {},
    "MLB": {},
    "NHL": {},
    "NCAAF": {},  # College teams are too numerous to map exhaustively
    "NCAAB": {},  # Populated below from ncaab_teams.py
}

# Populate NBA mappings
for canonical, abbr, variations in NBA_TEAMS.values():
    # Add canonical name
    TEAM_MAPPINGS["NBA"][canonical] = (canonical, abbr)
    # Add all variations
    for variation in variations:
        TEAM_MAPPINGS["NBA"][variation] = (canonical, abbr)
        # Also add lowercase versions
        TEAM_MAPPINGS["NBA"][variation.lower()] = (canonical, abbr)
    # Add abbreviation as a key
    TEAM_MAPPINGS["NBA"][abbr] = (canonical, abbr)
    TEAM_MAPPINGS["NBA"][abbr.lower()] = (canonical, abbr)

# Populate NFL mappings
for canonical, abbr, variations in NFL_TEAMS.values():
    TEAM_MAPPINGS["NFL"][canonical] = (canonical, abbr)
    for variation in variations:
        TEAM_MAPPINGS["NFL"][variation] = (canonical, abbr)
        TEAM_MAPPINGS["NFL"][variation.lower()] = (canonical, abbr)
    TEAM_MAPPINGS["NFL"][abbr] = (canonical, abbr)
    TEAM_MAPPINGS["NFL"][abbr.lower()] = (canonical, abbr)

# Populate MLB mappings
for canonical, abbr, variations in MLB_TEAMS.values():
    TEAM_MAPPINGS["MLB"][canonical] = (canonical, abbr)
    for variation in variations:
        TEAM_MAPPINGS["MLB"][variation] = (canonical, abbr)
        TEAM_MAPPINGS["MLB"][variation.lower()] = (canonical, abbr)
    TEAM_MAPPINGS["MLB"][abbr] = (canonical, abbr)
    TEAM_MAPPINGS["MLB"][abbr.lower()] = (canonical, abbr)

# Populate NHL mappings
for canonical, abbr, variations in NHL_TEAMS.values():
    TEAM_MAPPINGS["NHL"][canonical] = (canonical, abbr)
    for variation in variations:
        TEAM_MAPPINGS["NHL"][variation] = (canonical, abbr)
        TEAM_MAPPINGS["NHL"][variation.lower()] = (canonical, abbr)
    TEAM_MAPPINGS["NHL"][abbr] = (canonical, abbr)
    TEAM_MAPPINGS["NHL"][abbr.lower()] = (canonical, abbr)

# Populate NCAAB mappings from ncaab_teams.py SSOT
from .ncaab_teams import NCAAB_VARIATIONS as _NCAAB_VARIATIONS  # noqa: E402

TEAM_MAPPINGS["NCAAB"] = dict(_NCAAB_VARIATIONS)


def _normalize_string(s: str) -> str:
    """Normalize string for fuzzy matching."""
    # Remove extra whitespace, convert to lowercase
    s = re.sub(r"\s+", " ", s.strip().lower())
    # Remove common punctuation
    s = re.sub(r"[.,]", "", s)
    return s


def _fuzzy_match(league_code: SportCode, raw_name: str) -> tuple[str, str] | None:
    """Attempt fuzzy matching for team names that don't have exact matches."""
    normalized_input = _normalize_string(raw_name)
    mappings = TEAM_MAPPINGS.get(league_code, {})

    # Try exact match first (case-insensitive)
    for key, (canonical, abbr) in mappings.items():
        if _normalize_string(key) == normalized_input:
            return (canonical, abbr)

    # Try partial matches (contains) — require minimum 4 chars on both sides
    # to prevent false positives from short abbreviations (e.g., "ME" matching
    # any input containing "me").
    if len(normalized_input) >= 4:
        for key, (canonical, abbr) in mappings.items():
            normalized_key = _normalize_string(key)
            if len(normalized_key) < 4:
                continue
            shorter, longer = sorted([normalized_input, normalized_key], key=len)
            if shorter in longer and len(shorter) / len(longer) >= 0.8:
                return (canonical, abbr)

    # Try word-based matching (check if key words match)
    input_words = set(normalized_input.split())
    for key, (canonical, abbr) in mappings.items():
        key_words = set(_normalize_string(key).split())
        # If most words match, consider it a match
        if len(input_words) > 0 and len(key_words) > 0:
            overlap = input_words & key_words
            if len(overlap) >= min(2, len(input_words), len(key_words)):
                return (canonical, abbr)

    return None


def normalize_team_name(league_code: SportCode, raw_name: str) -> tuple[str, str | None]:
    """Normalize team name to canonical form and return (canonical_name, abbreviation).

    Args:
        league_code: The sport league code (NBA, NFL, etc.)
        raw_name: Raw team name from any source

    Returns:
        Tuple of (canonical_name, abbreviation). If no mapping exists, returns
        the input name and a generated abbreviation (first 3-6 chars).
    """
    if not raw_name:
        abbr = raw_name[:6].upper() if raw_name else ""
        return (raw_name, abbr)

    mappings = TEAM_MAPPINGS.get(league_code, {})

    # Try exact match (case-insensitive)
    if raw_name in mappings:
        return mappings[raw_name]

    # Try lowercase match
    if raw_name.lower() in mappings:
        return mappings[raw_name.lower()]

    # Try fuzzy matching
    fuzzy_result = _fuzzy_match(league_code, raw_name)
    if fuzzy_result:
        return fuzzy_result

    # Fallback: generate abbreviation from name
    # Remove common words and take first letters
    words = raw_name.split()
    if len(words) >= 2:
        abbr = (words[0][0] + words[1][0]).upper()
        if len(words) > 2:
            abbr += words[2][0].upper()
        abbr = abbr[:3]
    else:
        abbr = raw_name[:3].upper()

    return (raw_name, abbr)

