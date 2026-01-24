"""
Play Extractors: Event parsing rules for running stats.

This module provides functions to extract statistical information from
play-by-play data. All extraction is DETERMINISTIC and based on explicit
patterns in play descriptions.

EVENT PARSING RULES (AUTHORITATIVE):
- Scoring: +3 on made 3PT, +2 on other made FG, +1 on made FT
- Fouls: Personal fouls tracked separately from technical fouls
- Timeouts: Team timeouts only (ignore official/media)
- Possessions: Rough estimate from made FG, turnovers, defensive rebounds
- Notable actions: Block, steal, dunk only
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .stat_types import normalize_player_key

if TYPE_CHECKING:
    from .types import Play


# ============================================================================
# TEAM AND PLAYER EXTRACTION
# ============================================================================


def extract_team_key(play: "Play") -> str | None:
    """Extract team key from play data.

    Tries multiple sources:
    1. team_abbreviation (preferred)
    2. team_name
    3. home_team/away_team based on scoring
    """
    raw = play.raw_data

    # Try explicit team fields
    team_abbr = raw.get("team_abbreviation") or raw.get("team_abbrev")
    if team_abbr:
        return team_abbr.lower().strip()

    team_name = raw.get("team_name") or raw.get("team")
    if team_name:
        return team_name.lower().strip()

    return None


def extract_player_info(
    play: "Play",
    resolver: "PlayerIdentityResolver | None" = None,
) -> tuple[str | None, str | None, str | None]:
    """Extract player information from play data.

    When a PlayerIdentityResolver is provided, truncated/aliased names
    are resolved to canonical identities.

    Returns:
        Tuple of (player_key, player_name, player_id)
        - player_key: Normalized name for dictionary lookups (canonical if resolved)
        - player_name: Display name (canonical if resolved)
        - player_id: External reference (may be null)
    """
    raw = play.raw_data

    # Try explicit player fields first
    raw_name = raw.get("player_name") or raw.get("player")
    player_id = raw.get("player_id")

    # Fallback: extract from description
    if not raw_name:
        description = raw.get("description", "")
        # Common pattern: "Player Name makes/misses..."
        for verb in [" makes ", " misses ", " commits ", " called for "]:
            if verb in description:
                raw_name = description.split(verb)[0].strip()
                break

    if not raw_name:
        return None, None, None

    # Use resolver if available to get canonical identity
    if resolver is not None:
        team_key = extract_team_key(play)
        resolved = resolver.resolve(raw_name, player_id, team_key)
        if resolved:
            return resolved.canonical_key, resolved.canonical_name, resolved.player_id

    # Fallback to simple normalization
    player_key = normalize_player_key(raw_name)
    return player_key, raw_name, player_id


# Import PlayerIdentityResolver at runtime to avoid circular import
def _get_resolver_type():
    """Get PlayerIdentityResolver type for type hints."""
    from .player_identity import PlayerIdentityResolver

    return PlayerIdentityResolver


# Type hint placeholder
PlayerIdentityResolver = None  # Will be imported at runtime


# ============================================================================
# SCORING EXTRACTION
# ============================================================================


def is_made_field_goal(play: "Play") -> tuple[bool, int]:
    """Check if play is a made field goal and return points.

    SCORING RULES:
    - +3 on made 3PT (patterns: "3-pt", "three", "3-pointer")
    - +2 on other made FG

    Returns:
        Tuple of (is_made_fg, points)
    """
    description = (play.raw_data.get("description") or "").lower()

    if "makes" not in description:
        return False, 0

    # Check for 3-pointer
    if "3-pt" in description or "three" in description or "3-pointer" in description:
        return True, 3

    # Check for free throw (handled separately)
    if "free throw" in description:
        return False, 0

    # Regular field goal
    return True, 2


def is_made_free_throw(play: "Play") -> bool:
    """Check if play is a made free throw.

    SCORING RULES:
    - +1 on made FT
    """
    description = (play.raw_data.get("description") or "").lower()
    return "makes" in description and "free throw" in description


# ============================================================================
# FOUL EXTRACTION
# ============================================================================


def is_personal_foul(play: "Play") -> bool:
    """Check if play is a personal foul.

    FOUL RULES:
    - Personal fouls: increment player personal_foul_count + team personal_fouls
    - EXCLUDE technical fouls (counted separately)
    - EXCLUDE flagrant fouls (counted as personal + notable action)
    """
    description = (play.raw_data.get("description") or "").lower()
    play_type = (play.raw_data.get("play_type") or "").lower()

    # Check for foul
    is_foul = "foul" in description or "foul" in play_type
    if not is_foul:
        return False

    # Exclude technical fouls
    if "technical" in description:
        return False

    return True


def is_technical_foul(play: "Play") -> bool:
    """Check if play is a technical foul.

    FOUL RULES:
    - Technical fouls: increment technical_foul_count
    - DO NOT count as personal fouls
    - DO NOT affect foul limits
    - MUST remain available for narrative use later
    """
    description = (play.raw_data.get("description") or "").lower()
    return "technical" in description and "foul" in description


# ============================================================================
# TIMEOUT EXTRACTION
# ============================================================================


def is_timeout(play: "Play") -> tuple[bool, str | None]:
    """Check if play is a timeout and extract team.

    TIMEOUT RULES:
    - Increment timeouts_used for the team on explicit timeout events
    - Ignore official/media timeouts unless clearly attributed

    Returns:
        Tuple of (is_timeout, team_key)
    """
    description = (play.raw_data.get("description") or "").lower()
    play_type = (play.raw_data.get("play_type") or "").lower()

    is_to = "timeout" in description or "timeout" in play_type
    if not is_to:
        return False, None

    # Ignore official/media timeouts
    if "official" in description or "media" in description or "tv" in description:
        return False, None

    # Extract team
    team_key = extract_team_key(play)
    return True, team_key


# ============================================================================
# POSSESSION EXTRACTION
# ============================================================================


def is_possession_ending(play: "Play") -> bool:
    """Check if play ends a possession (for rough pace estimate).

    POSSESSIONS ESTIMATE RULES (Very Rough, Intentional):
    Increment possessions_estimate on:
    - made FG
    - turnover
    - defensive rebound

    Do NOT attempt full possession accounting.
    This signal is for pace description only.
    """
    description = (play.raw_data.get("description") or "").lower()
    play_type = (play.raw_data.get("play_type") or "").lower()

    # Made FG
    if "makes" in description and "free throw" not in description:
        return True

    # Turnover
    if "turnover" in description or "turnover" in play_type:
        return True

    # Defensive rebound
    if "defensive rebound" in description or "def rebound" in description:
        return True

    return False


# ============================================================================
# NOTABLE ACTION EXTRACTION
# ============================================================================


def extract_notable_action(play: "Play") -> str | None:
    """Extract notable action from play if present.

    NOTABLE ACTIONS RULES (Strict, Deterministic):
    Extract ONLY if explicitly present in play text:
    - block
    - steal
    - dunk

    Rules:
    - No inference
    - No synonyms
    - Return exactly one action (or None)
    """
    description = (play.raw_data.get("description") or "").lower()

    # Check for dunk (most specific first)
    if "dunk" in description:
        return "dunk"

    # Check for block
    if "block" in description:
        return "block"

    # Check for steal
    if "steal" in description:
        return "steal"

    return None


# ============================================================================
# EXPANDED STATS EXTRACTION (ASSISTS, BLOCKS, STEALS)
# ============================================================================


def is_assist(play: "Play") -> tuple[bool, str | None, str | None, str | None]:
    """Check if play contains an assist and extract assister info.

    ASSIST RULES:
    - Look for "assist" keyword in description
    - Common patterns: "(Player Name assists)", "assisted by Player Name"

    Returns:
        Tuple of (is_assist, assister_key, assister_name, assister_id)
    """
    description = (play.raw_data.get("description") or "").lower()
    raw = play.raw_data

    if "assist" not in description:
        return False, None, None, None

    # Try to extract assister name
    # Pattern 1: "(Player Name assists)" or "assisted by Player Name"
    original_desc = play.raw_data.get("description") or ""

    # Try explicit assist_player field first
    assist_player = raw.get("assist_player") or raw.get("assist_player_name")
    if assist_player:
        assister_key = normalize_player_key(assist_player)
        return True, assister_key, assist_player, raw.get("assist_player_id")

    # Pattern: "assisted by Player Name" or "(Player Name assists)"
    # Extract from description
    if "assisted by " in original_desc.lower():
        parts = original_desc.lower().split("assisted by ")
        if len(parts) > 1:
            # Take text after "assisted by" up to next punctuation
            name_part = parts[1].split(")")[0].split(",")[0].strip()
            if name_part:
                # Find original case name
                idx = original_desc.lower().find(name_part)
                if idx >= 0:
                    assister_name = original_desc[idx : idx + len(name_part)]
                    assister_key = normalize_player_key(assister_name)
                    return True, assister_key, assister_name, None

    # Pattern: "(Player assists)"
    if " assists)" in original_desc.lower():
        # Find the opening paren
        idx = original_desc.lower().find(" assists)")
        if idx > 0:
            # Find matching open paren
            open_idx = original_desc.rfind("(", 0, idx)
            if open_idx >= 0:
                name_part = original_desc[open_idx + 1 : idx].strip()
                if name_part:
                    assister_key = normalize_player_key(name_part)
                    return True, assister_key, name_part, None

    # Assist detected but couldn't extract player
    return True, None, None, None


def is_block(play: "Play") -> tuple[bool, str | None, str | None, str | None]:
    """Check if play contains a block and extract blocker info.

    BLOCK RULES:
    - Look for "block" keyword in description
    - Common patterns: "blocked by Player Name"

    Returns:
        Tuple of (is_block, blocker_key, blocker_name, blocker_id)
    """
    description = (play.raw_data.get("description") or "").lower()
    raw = play.raw_data

    if "block" not in description:
        return False, None, None, None

    original_desc = play.raw_data.get("description") or ""

    # Try explicit block_player field first
    block_player = raw.get("block_player") or raw.get("block_player_name")
    if block_player:
        blocker_key = normalize_player_key(block_player)
        return True, blocker_key, block_player, raw.get("block_player_id")

    # Pattern: "blocked by Player Name"
    if "blocked by " in original_desc.lower():
        parts = original_desc.lower().split("blocked by ")
        if len(parts) > 1:
            name_part = parts[1].split(")")[0].split(",")[0].strip()
            if name_part:
                idx = original_desc.lower().find(name_part)
                if idx >= 0:
                    blocker_name = original_desc[idx : idx + len(name_part)]
                    blocker_key = normalize_player_key(blocker_name)
                    return True, blocker_key, blocker_name, None

    # Block detected but couldn't extract player
    return True, None, None, None


def is_steal(play: "Play") -> tuple[bool, str | None, str | None, str | None]:
    """Check if play contains a steal and extract stealer info.

    STEAL RULES:
    - Look for "steal" keyword in description
    - Common patterns: "Player Name steals", "stolen by Player Name"

    Returns:
        Tuple of (is_steal, stealer_key, stealer_name, stealer_id)
    """
    description = (play.raw_data.get("description") or "").lower()
    raw = play.raw_data

    if "steal" not in description:
        return False, None, None, None

    original_desc = play.raw_data.get("description") or ""

    # Try explicit steal_player field first
    steal_player = raw.get("steal_player") or raw.get("steal_player_name")
    if steal_player:
        stealer_key = normalize_player_key(steal_player)
        return True, stealer_key, steal_player, raw.get("steal_player_id")

    # Pattern: "stolen by Player Name"
    if "stolen by " in original_desc.lower():
        parts = original_desc.lower().split("stolen by ")
        if len(parts) > 1:
            name_part = parts[1].split(")")[0].split(",")[0].strip()
            if name_part:
                idx = original_desc.lower().find(name_part)
                if idx >= 0:
                    stealer_name = original_desc[idx : idx + len(name_part)]
                    stealer_key = normalize_player_key(stealer_name)
                    return True, stealer_key, stealer_name, None

    # Pattern: "Player Name steals"
    if " steals" in original_desc.lower():
        idx = original_desc.lower().find(" steals")
        if idx > 0:
            # Take text before " steals"
            name_part = original_desc[:idx].split(",")[-1].strip()
            if name_part:
                stealer_key = normalize_player_key(name_part)
                return True, stealer_key, name_part, None

    # Steal detected but couldn't extract player
    return True, None, None, None
