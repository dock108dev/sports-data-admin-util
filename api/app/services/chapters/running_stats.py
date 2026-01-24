"""
Running Stats Builder: Authoritative statistical signals for game story generation.

This module computes CUMULATIVE statistical snapshots at chapter boundaries and
SECTION-LEVEL DELTAS for use in StorySection construction.

DESIGN PRINCIPLES:
- This layer is INTERNAL, post-game only, and deterministic
- Contains NO AI logic and NO narrative decisions
- Produces signals that will later be used by a single AI call

ARCHITECTURE:
- RunningStatsSnapshot: Cumulative totals from game start → end of chapter
- SectionDelta: Difference between two snapshots (section_end - section_start)

RELATIONSHIP TO story_state.py:
- story_state.py is for AI PROMPT BUILDING (momentum hints, theme tags, top 6 global)
- running_stats.py is for AUTHORITATIVE STATISTICAL SIGNALS (fouls, timeouts, deltas)
- Both are deterministic, but serve different purposes
- This module does NOT replace story_state.py; they complement each other

PLAYER ID DECISION:
- Primary key: player_name (deterministically normalized to lowercase, stripped)
- Reason: player_id is an external reference that may be null or inconsistent
- player_id is PRESERVED in snapshots when available for future reference
- This decision is documented per the specification requirement

ISSUE: Running Stats Builder (Chapters-First Architecture)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import copy

from .types import Chapter, Play


# ============================================================================
# PLAYER ID NORMALIZATION
# ============================================================================


def normalize_player_key(player_name: str) -> str:
    """Normalize player name for use as dictionary key.

    PLAYER ID DECISION (DOCUMENTED):
    - We use player_name as the primary key because player_id is an external
      reference that may be null or inconsistent across data sources.
    - Normalization: lowercase, stripped whitespace, collapsed internal spaces.
    - This ensures deterministic matching regardless of case variations.

    Args:
        player_name: Raw player name from play data

    Returns:
        Normalized key for dictionary lookups
    """
    if not player_name:
        return ""
    # Lowercase, strip whitespace, collapse internal spaces
    return " ".join(player_name.lower().split())


# ============================================================================
# SNAPSHOT DATA STRUCTURES (CUMULATIVE TOTALS)
# ============================================================================


@dataclass
class PlayerSnapshot:
    """Cumulative player statistics from game start → end of chapter.

    Snapshots are IMMUTABLE once computed.

    PLAYER ID NOTE:
    - player_key is the normalized name used for lookups
    - player_name is the display name (original case preserved)
    - player_id is the external reference (preserved when available, may be null)
    """

    # Identity
    player_key: str  # Normalized name (primary key)
    player_name: str  # Display name (original case)
    player_id: str | None = None  # External ref (may be null)
    team_key: str | None = None  # Which team this player is on

    # Scoring (Cumulative Totals)
    points_scored_total: int = 0
    fg_made_total: int = 0  # Field goals made
    three_pt_made_total: int = 0  # 3-pointers made
    ft_made_total: int = 0  # Free throws made

    # Expanded Stats (Cumulative Totals) - Player Prominence
    assists_total: int = 0
    blocks_total: int = 0
    steals_total: int = 0

    # Fouls (Cumulative Totals)
    personal_foul_count_total: int = 0
    technical_foul_count_total: int = 0  # Separate from personal fouls

    # Notable Actions (Unique Set)
    notable_actions_set: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "player_key": self.player_key,
            "player_name": self.player_name,
            "player_id": self.player_id,
            "team_key": self.team_key,
            "points_scored_total": self.points_scored_total,
            "fg_made_total": self.fg_made_total,
            "three_pt_made_total": self.three_pt_made_total,
            "ft_made_total": self.ft_made_total,
            "assists_total": self.assists_total,
            "blocks_total": self.blocks_total,
            "steals_total": self.steals_total,
            "personal_foul_count_total": self.personal_foul_count_total,
            "technical_foul_count_total": self.technical_foul_count_total,
            "notable_actions_set": sorted(self.notable_actions_set),
        }


@dataclass
class TeamSnapshot:
    """Cumulative team statistics from game start → end of chapter.

    Snapshots are IMMUTABLE once computed.
    """

    # Identity
    team_key: str  # Normalized team identifier
    team_name: str  # Display name

    # Scoring
    points_scored_total: int = 0

    # Fouls (Cumulative Totals)
    personal_fouls_committed_total: int = 0
    technical_fouls_committed_total: int = 0

    # Timeouts
    timeouts_used_total: int = 0

    # Pace (Very Rough Estimate)
    possessions_estimate_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "team_key": self.team_key,
            "team_name": self.team_name,
            "points_scored_total": self.points_scored_total,
            "personal_fouls_committed_total": self.personal_fouls_committed_total,
            "technical_fouls_committed_total": self.technical_fouls_committed_total,
            "timeouts_used_total": self.timeouts_used_total,
            "possessions_estimate_total": self.possessions_estimate_total,
        }


@dataclass
class RunningStatsSnapshot:
    """Complete statistical snapshot at a chapter boundary.

    Represents totals from game start → end of the specified chapter.
    Snapshots are IMMUTABLE once computed.

    SEMANTICS:
    - chapter_index: The chapter this snapshot is taken AFTER (0-indexed)
    - A snapshot at chapter_index=2 contains totals through chapters 0, 1, 2
    - Initial snapshot (before any chapters) has chapter_index=-1
    """

    chapter_index: int  # -1 for initial, 0+ for after chapter N

    # Team snapshots (keyed by team_key)
    teams: dict[str, TeamSnapshot] = field(default_factory=dict)

    # Player snapshots (keyed by player_key)
    players: dict[str, PlayerSnapshot] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "chapter_index": self.chapter_index,
            "teams": {k: v.to_dict() for k, v in self.teams.items()},
            "players": {k: v.to_dict() for k, v in self.players.items()},
        }


# ============================================================================
# SECTION DELTA DATA STRUCTURES
# ============================================================================


@dataclass
class PlayerDelta:
    """Player statistics for a SECTION (delta between two snapshots).

    Computed as: snapshot_at_section_end - snapshot_at_section_start
    """

    player_key: str
    player_name: str
    player_id: str | None = None
    team_key: str | None = None

    # Scoring (Section Delta)
    points_scored: int = 0
    fg_made: int = 0
    three_pt_made: int = 0
    ft_made: int = 0

    # Expanded Stats (Section Delta) - Player Prominence
    assists: int = 0
    blocks: int = 0
    steals: int = 0

    # Fouls (Section Delta)
    personal_foul_count: int = 0
    technical_foul_count: int = 0

    # Notable Actions (Unique set for this section)
    notable_actions: set[str] = field(default_factory=set)

    # Flags
    foul_trouble_flag: bool = False  # personal_foul_count >= 4 in section

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "player_key": self.player_key,
            "player_name": self.player_name,
            "player_id": self.player_id,
            "team_key": self.team_key,
            "points_scored": self.points_scored,
            "fg_made": self.fg_made,
            "three_pt_made": self.three_pt_made,
            "ft_made": self.ft_made,
            "assists": self.assists,
            "blocks": self.blocks,
            "steals": self.steals,
            "personal_foul_count": self.personal_foul_count,
            "technical_foul_count": self.technical_foul_count,
            "notable_actions": sorted(self.notable_actions),
            "foul_trouble_flag": self.foul_trouble_flag,
        }


@dataclass
class TeamDelta:
    """Team statistics for a SECTION (delta between two snapshots)."""

    team_key: str
    team_name: str

    # Scoring (Section Delta)
    points_scored: int = 0

    # Fouls (Section Delta)
    personal_fouls_committed: int = 0
    technical_fouls_committed: int = 0

    # Timeouts (Section Delta)
    timeouts_used: int = 0

    # Pace (Section Delta)
    possessions_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "team_key": self.team_key,
            "team_name": self.team_name,
            "points_scored": self.points_scored,
            "personal_fouls_committed": self.personal_fouls_committed,
            "technical_fouls_committed": self.technical_fouls_committed,
            "timeouts_used": self.timeouts_used,
            "possessions_estimate": self.possessions_estimate,
        }


@dataclass
class SectionDelta:
    """Complete statistics for a SECTION (chapter range).

    Computed by differencing snapshots at section boundaries.

    PLAYER BOUNDING:
    - Only top 3 players per team by points_scored (section delta) are included
    - Tie-breakers: fg_made, three_pt_made, then player_key (deterministic)
    """

    section_start_chapter: int  # First chapter in section (inclusive)
    section_end_chapter: int  # Last chapter in section (inclusive)

    # Team deltas
    teams: dict[str, TeamDelta] = field(default_factory=dict)

    # Player deltas (bounded: top 3 per team)
    players: dict[str, PlayerDelta] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "section_start_chapter": self.section_start_chapter,
            "section_end_chapter": self.section_end_chapter,
            "teams": {k: v.to_dict() for k, v in self.teams.items()},
            "players": {k: v.to_dict() for k, v in self.players.items()},
        }


# ============================================================================
# EVENT PARSING RULES (AUTHORITATIVE)
# ============================================================================


def _extract_team_key(play: Play) -> str | None:
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


def _extract_player_info(
    play: Play,
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
        team_key = _extract_team_key(play)
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


def _is_made_field_goal(play: Play) -> tuple[bool, int]:
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


def _is_made_free_throw(play: Play) -> bool:
    """Check if play is a made free throw.

    SCORING RULES:
    - +1 on made FT
    """
    description = (play.raw_data.get("description") or "").lower()
    return "makes" in description and "free throw" in description


def _is_personal_foul(play: Play) -> bool:
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


def _is_technical_foul(play: Play) -> bool:
    """Check if play is a technical foul.

    FOUL RULES:
    - Technical fouls: increment technical_foul_count
    - DO NOT count as personal fouls
    - DO NOT affect foul limits
    - MUST remain available for narrative use later
    """
    description = (play.raw_data.get("description") or "").lower()
    return "technical" in description and "foul" in description


def _is_timeout(play: Play) -> tuple[bool, str | None]:
    """Check if play is a timeout and extract team.

    TIMEOUT RULES:
    - Increment timeouts_used for the team on explicit timeout events
    - Ignore official/media timeouts unless clearly attributed

    Returns:
        Tuple of (is_timeout, team_key)
    """
    description = (play.raw_data.get("description") or "").lower()
    play_type = (play.raw_data.get("play_type") or "").lower()

    is_timeout = "timeout" in description or "timeout" in play_type
    if not is_timeout:
        return False, None

    # Ignore official/media timeouts
    if "official" in description or "media" in description or "tv" in description:
        return False, None

    # Extract team
    team_key = _extract_team_key(play)
    return True, team_key


def _is_possession_ending(play: Play) -> bool:
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


def _extract_notable_action(play: Play) -> str | None:
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
# EXPANDED STATS PARSING (ASSISTS, BLOCKS, STEALS)
# ============================================================================


def _is_assist(play: Play) -> tuple[bool, str | None, str | None, str | None]:
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


def _is_block(play: Play) -> tuple[bool, str | None, str | None, str | None]:
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


def _is_steal(play: Play) -> tuple[bool, str | None, str | None, str | None]:
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


# ============================================================================
# SNAPSHOT BUILDING
# ============================================================================


def build_initial_snapshot() -> RunningStatsSnapshot:
    """Build initial empty snapshot (before any chapters).

    Returns:
        Empty snapshot with chapter_index=-1
    """
    return RunningStatsSnapshot(chapter_index=-1)


def _ensure_team(
    snapshot: RunningStatsSnapshot, team_key: str, team_name: str | None = None
) -> TeamSnapshot:
    """Ensure team exists in snapshot, create if needed."""
    if team_key not in snapshot.teams:
        snapshot.teams[team_key] = TeamSnapshot(
            team_key=team_key,
            team_name=team_name or team_key,
        )
    return snapshot.teams[team_key]


def _ensure_player(
    snapshot: RunningStatsSnapshot,
    player_key: str,
    player_name: str,
    player_id: str | None = None,
    team_key: str | None = None,
) -> PlayerSnapshot:
    """Ensure player exists in snapshot, create if needed."""
    if player_key not in snapshot.players:
        snapshot.players[player_key] = PlayerSnapshot(
            player_key=player_key,
            player_name=player_name,
            player_id=player_id,
            team_key=team_key,
        )
    else:
        # Update player_id if we now have it
        if player_id and not snapshot.players[player_key].player_id:
            snapshot.players[player_key].player_id = player_id
        # Update team_key if we now have it
        if team_key and not snapshot.players[player_key].team_key:
            snapshot.players[player_key].team_key = team_key
    return snapshot.players[player_key]


def _process_play(
    play: Play,
    snapshot: RunningStatsSnapshot,
    resolver: "PlayerIdentityResolver | None" = None,
) -> None:
    """Process a single play and update snapshot in place.

    This function implements all event parsing rules.
    When a resolver is provided, player names are resolved to canonical forms.

    Args:
        play: Play to process
        snapshot: Snapshot to update
        resolver: Optional PlayerIdentityResolver for name canonicalization
    """
    # Extract player info (using resolver if available)
    player_key, player_name, player_id = _extract_player_info(play, resolver)
    team_key = _extract_team_key(play)

    # Get team name for display
    team_name = play.raw_data.get("team_name") or play.raw_data.get("team")

    # Process scoring
    is_made_fg, fg_points = _is_made_field_goal(play)
    if is_made_fg and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.points_scored_total += fg_points
        player.fg_made_total += 1
        if fg_points == 3:
            player.three_pt_made_total += 1

        # Update team score
        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.points_scored_total += fg_points

    if _is_made_free_throw(play) and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.points_scored_total += 1
        player.ft_made_total += 1

        # Update team score
        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.points_scored_total += 1

    # Process fouls
    if _is_personal_foul(play) and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.personal_foul_count_total += 1

        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.personal_fouls_committed_total += 1

    if _is_technical_foul(play) and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.technical_foul_count_total += 1

        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.technical_fouls_committed_total += 1

    # Process timeouts
    is_timeout, timeout_team = _is_timeout(play)
    if is_timeout and timeout_team:
        team = _ensure_team(snapshot, timeout_team, team_name)
        team.timeouts_used_total += 1

    # Process possessions estimate
    if _is_possession_ending(play) and team_key:
        team = _ensure_team(snapshot, team_key, team_name)
        team.possessions_estimate_total += 1

    # Process notable actions
    notable_action = _extract_notable_action(play)
    if notable_action and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.notable_actions_set.add(notable_action)

    # Process assists (Player Prominence)
    is_assist, assister_key, assister_name, assister_id = _is_assist(play)
    if is_assist and assister_key and assister_name:
        # Resolve assister name if resolver available
        if resolver is not None:
            resolved = resolver.resolve(assister_name, assister_id, team_key)
            if resolved:
                assister_key = resolved.canonical_key
                assister_name = resolved.canonical_name
                assister_id = resolved.player_id
        assister = _ensure_player(
            snapshot, assister_key, assister_name, assister_id, team_key
        )
        assister.assists_total += 1

    # Process blocks (Player Prominence)
    is_block, blocker_key, blocker_name, blocker_id = _is_block(play)
    if is_block and blocker_key and blocker_name:
        # Resolve blocker name if resolver available
        if resolver is not None:
            resolved = resolver.resolve(blocker_name, blocker_id, team_key)
            if resolved:
                blocker_key = resolved.canonical_key
                blocker_name = resolved.canonical_name
                blocker_id = resolved.player_id
        blocker = _ensure_player(
            snapshot, blocker_key, blocker_name, blocker_id, team_key
        )
        blocker.blocks_total += 1

    # Process steals (Player Prominence)
    is_steal, stealer_key, stealer_name, stealer_id = _is_steal(play)
    if is_steal and stealer_key and stealer_name:
        # Resolve stealer name if resolver available
        if resolver is not None:
            resolved = resolver.resolve(stealer_name, stealer_id, team_key)
            if resolved:
                stealer_key = resolved.canonical_key
                stealer_name = resolved.canonical_name
                stealer_id = resolved.player_id
        stealer = _ensure_player(
            snapshot, stealer_key, stealer_name, stealer_id, team_key
        )
        stealer.steals_total += 1


def update_snapshot(
    previous: RunningStatsSnapshot,
    chapter: Chapter,
    resolver: "PlayerIdentityResolver | None" = None,
) -> RunningStatsSnapshot:
    """Update snapshot with a new chapter's plays.

    This creates a NEW snapshot (immutable) by copying previous state
    and adding the chapter's data.

    Args:
        previous: Snapshot from previous chapter boundary
        chapter: New chapter to process
        resolver: Optional PlayerIdentityResolver for name canonicalization

    Returns:
        New snapshot including data from this chapter
    """
    # Deep copy previous snapshot
    new_snapshot = RunningStatsSnapshot(
        chapter_index=previous.chapter_index + 1,
        teams={k: copy.deepcopy(v) for k, v in previous.teams.items()},
        players={k: copy.deepcopy(v) for k, v in previous.players.items()},
    )

    # Deep copy the sets (they don't copy properly with copy.deepcopy on dataclass)
    for player in new_snapshot.players.values():
        player.notable_actions_set = set(player.notable_actions_set)

    # Process each play in the chapter
    for play in chapter.plays:
        _process_play(play, new_snapshot, resolver)

    return new_snapshot


def build_running_snapshots(
    chapters: list[Chapter],
    resolver: "PlayerIdentityResolver | None" = None,
) -> list[RunningStatsSnapshot]:
    """Build snapshots at every chapter boundary.

    NAME RESOLUTION:
    When a PlayerIdentityResolver is provided, all player names are resolved
    to canonical forms during stat aggregation. This prevents stat loss and
    ghost players caused by truncated or aliased names.

    Args:
        chapters: List of chapters in chronological order
        resolver: Optional PlayerIdentityResolver for name canonicalization

    Returns:
        List of snapshots, one after each chapter.
        snapshots[0] = state after chapter 0
        snapshots[N] = state after chapter N
    """
    snapshots = []
    current = build_initial_snapshot()

    for chapter in chapters:
        current = update_snapshot(current, chapter, resolver)
        snapshots.append(current)

    return snapshots


# ============================================================================
# SECTION DELTA COMPUTATION
# ============================================================================


def _compute_player_delta(
    player_key: str,
    start_player: PlayerSnapshot | None,
    end_player: PlayerSnapshot,
) -> PlayerDelta:
    """Compute player delta between two snapshots."""
    if start_player is None:
        # No prior data, delta equals end values
        delta = PlayerDelta(
            player_key=end_player.player_key,
            player_name=end_player.player_name,
            player_id=end_player.player_id,
            team_key=end_player.team_key,
            points_scored=end_player.points_scored_total,
            fg_made=end_player.fg_made_total,
            three_pt_made=end_player.three_pt_made_total,
            ft_made=end_player.ft_made_total,
            assists=end_player.assists_total,
            blocks=end_player.blocks_total,
            steals=end_player.steals_total,
            personal_foul_count=end_player.personal_foul_count_total,
            technical_foul_count=end_player.technical_foul_count_total,
            notable_actions=set(end_player.notable_actions_set),
        )
    else:
        delta = PlayerDelta(
            player_key=end_player.player_key,
            player_name=end_player.player_name,
            player_id=end_player.player_id,
            team_key=end_player.team_key,
            points_scored=end_player.points_scored_total
            - start_player.points_scored_total,
            fg_made=end_player.fg_made_total - start_player.fg_made_total,
            three_pt_made=end_player.three_pt_made_total
            - start_player.three_pt_made_total,
            ft_made=end_player.ft_made_total - start_player.ft_made_total,
            assists=end_player.assists_total - start_player.assists_total,
            blocks=end_player.blocks_total - start_player.blocks_total,
            steals=end_player.steals_total - start_player.steals_total,
            personal_foul_count=end_player.personal_foul_count_total
            - start_player.personal_foul_count_total,
            technical_foul_count=end_player.technical_foul_count_total
            - start_player.technical_foul_count_total,
            notable_actions=end_player.notable_actions_set
            - start_player.notable_actions_set,
        )

    # Set foul trouble flag
    delta.foul_trouble_flag = delta.personal_foul_count >= 4

    return delta


def _compute_team_delta(
    team_key: str,
    start_team: TeamSnapshot | None,
    end_team: TeamSnapshot,
) -> TeamDelta:
    """Compute team delta between two snapshots."""
    if start_team is None:
        return TeamDelta(
            team_key=end_team.team_key,
            team_name=end_team.team_name,
            points_scored=end_team.points_scored_total,
            personal_fouls_committed=end_team.personal_fouls_committed_total,
            technical_fouls_committed=end_team.technical_fouls_committed_total,
            timeouts_used=end_team.timeouts_used_total,
            possessions_estimate=end_team.possessions_estimate_total,
        )
    else:
        return TeamDelta(
            team_key=end_team.team_key,
            team_name=end_team.team_name,
            points_scored=end_team.points_scored_total - start_team.points_scored_total,
            personal_fouls_committed=end_team.personal_fouls_committed_total
            - start_team.personal_fouls_committed_total,
            technical_fouls_committed=end_team.technical_fouls_committed_total
            - start_team.technical_fouls_committed_total,
            timeouts_used=end_team.timeouts_used_total - start_team.timeouts_used_total,
            possessions_estimate=end_team.possessions_estimate_total
            - start_team.possessions_estimate_total,
        )


def _player_sort_key(delta: PlayerDelta) -> tuple:
    """Sort key for player bounding.

    PLAYER BOUNDING TIE-BREAKERS (in order):
    1. points_scored (descending)
    2. fg_made (descending)
    3. three_pt_made (descending)
    4. player_key (ascending, for determinism)
    """
    return (
        -delta.points_scored,
        -delta.fg_made,
        -delta.three_pt_made,
        delta.player_key,  # Ascending for determinism
    )


def compute_section_delta(
    start_snapshot: RunningStatsSnapshot | None,
    end_snapshot: RunningStatsSnapshot,
    section_start_chapter: int,
    section_end_chapter: int,
    players_per_team: int = 3,
) -> SectionDelta:
    """Compute section delta between two snapshots.

    PLAYER BOUNDING:
    - Include ONLY the top N players per team by points_scored (section delta)
    - Tie-breakers: fg_made, three_pt_made, player_key

    Args:
        start_snapshot: Snapshot at section start (None for initial)
        end_snapshot: Snapshot at section end
        section_start_chapter: First chapter in section (inclusive)
        section_end_chapter: Last chapter in section (inclusive)
        players_per_team: Number of top players per team to include (default: 3)

    Returns:
        SectionDelta with bounded player list
    """
    # Compute team deltas
    team_deltas: dict[str, TeamDelta] = {}
    for team_key, end_team in end_snapshot.teams.items():
        start_team = start_snapshot.teams.get(team_key) if start_snapshot else None
        team_deltas[team_key] = _compute_team_delta(team_key, start_team, end_team)

    # Compute all player deltas
    all_player_deltas: dict[str, PlayerDelta] = {}
    for player_key, end_player in end_snapshot.players.items():
        start_player = (
            start_snapshot.players.get(player_key) if start_snapshot else None
        )
        all_player_deltas[player_key] = _compute_player_delta(
            player_key, start_player, end_player
        )

    # Group players by team
    players_by_team: dict[str, list[PlayerDelta]] = {}
    unaffiliated_players: list[PlayerDelta] = []

    for delta in all_player_deltas.values():
        if delta.team_key:
            if delta.team_key not in players_by_team:
                players_by_team[delta.team_key] = []
            players_by_team[delta.team_key].append(delta)
        else:
            unaffiliated_players.append(delta)

    # Select top N per team
    bounded_players: dict[str, PlayerDelta] = {}

    for team_key, team_players in players_by_team.items():
        # Sort by bounding criteria
        sorted_players = sorted(team_players, key=_player_sort_key)
        # Take top N
        for player in sorted_players[:players_per_team]:
            bounded_players[player.player_key] = player

    # Handle unaffiliated players (take top N overall if any)
    if unaffiliated_players:
        sorted_unaffiliated = sorted(unaffiliated_players, key=_player_sort_key)
        for player in sorted_unaffiliated[:players_per_team]:
            bounded_players[player.player_key] = player

    return SectionDelta(
        section_start_chapter=section_start_chapter,
        section_end_chapter=section_end_chapter,
        teams=team_deltas,
        players=bounded_players,
    )


def compute_section_deltas_from_snapshots(
    snapshots: list[RunningStatsSnapshot],
    section_boundaries: list[int] | None = None,
    players_per_team: int = 3,
) -> list[SectionDelta]:
    """Compute section deltas from a list of snapshots.

    If section_boundaries is not provided, each chapter becomes its own section.

    Args:
        snapshots: List of snapshots (one per chapter)
        section_boundaries: List of chapter indices where sections end.
                           If None, each chapter is its own section.
        players_per_team: Number of top players per team to include

    Returns:
        List of SectionDelta objects
    """
    if not snapshots:
        return []

    # Default: each chapter is its own section
    if section_boundaries is None:
        section_boundaries = list(range(len(snapshots)))

    deltas = []
    prev_boundary = -1
    prev_snapshot: RunningStatsSnapshot | None = None

    for boundary in section_boundaries:
        if boundary >= len(snapshots):
            break

        end_snapshot = snapshots[boundary]
        delta = compute_section_delta(
            start_snapshot=prev_snapshot,
            end_snapshot=end_snapshot,
            section_start_chapter=prev_boundary + 1,
            section_end_chapter=boundary,
            players_per_team=players_per_team,
        )
        deltas.append(delta)

        prev_boundary = boundary
        prev_snapshot = end_snapshot

    return deltas


# ============================================================================
# KNOWN LIMITATIONS (BY DESIGN)
# ============================================================================

"""
KNOWN LIMITATIONS (Documented as Required):

1. PLAYER IDENTIFICATION:
   - Uses player_name as primary key because player_id is not reliably available
   - Name normalization may incorrectly merge players with same name on different teams
   - This is mitigated by also tracking team_key per player

2. SCORING ACCURACY:
   - Relies on "makes" appearing in play descriptions
   - 3PT detection relies on "3-pt", "three", "3-pointer" patterns
   - May miss scoring if play description format changes

3. FOUL TRACKING:
   - Personal vs technical distinction relies on "technical" keyword
   - Flagrant fouls counted as personal (they do affect foul limits)
   - Ejection tracking not implemented

4. TIMEOUT ATTRIBUTION:
   - Ignores official/media timeouts (cannot attribute to team)
   - Team attribution relies on play data having team info

5. POSSESSIONS ESTIMATE:
   - Very rough approximation (made FG + turnover + defensive rebound)
   - NOT a true possession count
   - Intended only for pace description, not advanced metrics

6. NOTABLE ACTIONS:
   - Only extracts: block, steal, dunk
   - No inference, no synonyms
   - May miss actions if keyword not in description

7. TEAM SCORE TRACKING:
   - Computed from individual plays, not from scoreboard
   - May diverge from actual score if plays are missing

These limitations are intentional design choices to maintain determinism
and avoid inference/guessing. The AI layer can address ambiguities later.
"""
