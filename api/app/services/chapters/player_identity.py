"""
Player Identity Resolution: Canonical player key resolution for NBA games.

This module resolves player identity BEFORE chaptering, beats, or stat deltas.
Truncated names are treated as aliases, never as primary keys.

DESIGN PRINCIPLES:
- Player identity is resolved at ingestion, not during stat aggregation
- Canonical player identity is based on player_id > roster lookup > alias match
- Story generation only sees canonical names
- No truncated or aliased names may appear in AI input

CANONICAL PLAYER KEY PRIORITY:
1. player_id (when available)
2. (team_id, full_name) from roster
3. Alias match (last-name + initial resolution)

ALIAS RESOLUTION:
- Detect truncated names (e.g., "N. Vu", "I. Joe")
- Map to canonical player via active roster
- Store raw name as alias, not as key

ISSUE: Name Resolution (Chapters-First Architecture)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class RosterPlayer:
    """Player from active game roster.

    Represents a canonical player identity from the roster.
    """

    player_id: str
    full_name: str
    team_id: str
    first_name: str = ""
    last_name: str = ""

    def __post_init__(self) -> None:
        """Extract first/last name if not provided."""
        if not self.first_name or not self.last_name:
            parts = self.full_name.strip().split()
            if len(parts) >= 2:
                self.first_name = parts[0]
                self.last_name = " ".join(parts[1:])
            elif len(parts) == 1:
                self.first_name = ""
                self.last_name = parts[0]


@dataclass
class ResolvedPlayer:
    """Result of player identity resolution.

    Contains canonical identity information for a resolved player.
    """

    canonical_key: str  # Normalized canonical key (e.g., "nikola vucevic")
    canonical_name: str  # Display name (e.g., "Nikola Vucevic")
    player_id: str | None  # External ID (when available)
    team_id: str | None  # Team identifier
    raw_name: str  # Original name from play data (may be truncated)
    is_alias: bool = False  # True if raw_name was resolved via alias


@dataclass
class ResolutionStats:
    """Statistics about player resolution outcomes."""

    total_resolutions: int = 0
    direct_matches: int = 0
    alias_matches: int = 0
    player_id_matches: int = 0
    unresolved: int = 0
    unresolved_names: list[str] = field(default_factory=list)


# ============================================================================
# NAME NORMALIZATION
# ============================================================================


def normalize_for_matching(name: str) -> str:
    """Normalize a name for matching purposes.

    Handles:
    - Case normalization (lowercase)
    - Whitespace normalization
    - Diacritics removal (e.g., Vučević -> Vucevic)
    - Punctuation removal

    Args:
        name: Raw player name

    Returns:
        Normalized name for matching
    """
    if not name:
        return ""

    # Normalize Unicode (decompose diacritics)
    normalized = unicodedata.normalize("NFKD", name)

    # Remove diacritics (non-ASCII characters from decomposition)
    ascii_name = normalized.encode("ASCII", "ignore").decode("ASCII")

    # Lowercase
    ascii_name = ascii_name.lower()

    # Remove punctuation except spaces
    ascii_name = re.sub(r"[^\w\s]", "", ascii_name)

    # Collapse whitespace
    ascii_name = " ".join(ascii_name.split())

    return ascii_name


def extract_initial_and_lastname(name: str) -> tuple[str, str] | None:
    """Extract initial and last name from a potentially truncated name.

    Patterns recognized:
    - "N. Vucevic" -> ("n", "vucevic")
    - "N Vucevic" -> ("n", "vucevic")
    - "Vucevic, N." -> ("n", "vucevic")

    Args:
        name: Potentially truncated player name

    Returns:
        Tuple of (initial, last_name) or None if not a truncated name
    """
    if not name:
        return None

    normalized = normalize_for_matching(name)
    parts = normalized.split()

    if len(parts) < 2:
        return None

    # Pattern: "N Lastname" or "N. Lastname"
    if len(parts[0]) == 1:
        return parts[0], " ".join(parts[1:])

    # Pattern: "Lastname N" (less common)
    if len(parts[-1]) == 1:
        return parts[-1], " ".join(parts[:-1])

    return None


def is_truncated_name(name: str) -> bool:
    """Check if a name appears to be truncated.

    A name is considered truncated if:
    - First part is a single character (initial)
    - Contains abbreviated patterns like "N." or "J."

    Args:
        name: Player name to check

    Returns:
        True if name appears truncated
    """
    if not name:
        return False

    # Check for initial pattern
    result = extract_initial_and_lastname(name)
    if result is not None:
        return True

    # Check for abbreviated first name pattern (e.g., "N. Vucevic")
    if re.match(r"^[A-Za-z]\.\s+\w", name):
        return True

    return False


# ============================================================================
# PLAYER IDENTITY RESOLVER
# ============================================================================


class PlayerIdentityResolver:
    """Resolves player identities to canonical keys.

    Uses game roster to map truncated/abbreviated names to full canonical names.
    Maintains alias mappings for consistent resolution across plays.

    Usage:
        roster = [RosterPlayer(player_id="vuc1", full_name="Nikola Vucevic", team_id="CHI")]
        resolver = PlayerIdentityResolver(roster)
        resolved = resolver.resolve("N. Vucevic", team_id="CHI")
        # Returns ResolvedPlayer with canonical_name="Nikola Vucevic"
    """

    def __init__(self, roster: list[RosterPlayer] | None = None) -> None:
        """Initialize resolver with game roster.

        Args:
            roster: List of players on active game roster
        """
        self._roster: list[RosterPlayer] = roster or []
        self._alias_cache: dict[str, ResolvedPlayer] = {}
        self._stats = ResolutionStats()

        # Build lookup indices
        self._by_player_id: dict[str, RosterPlayer] = {}
        self._by_normalized_name: dict[str, RosterPlayer] = {}
        self._by_team_lastname: dict[tuple[str, str], list[RosterPlayer]] = {}
        self._by_lastname: dict[str, list[RosterPlayer]] = {}

        self._build_indices()

    def _build_indices(self) -> None:
        """Build lookup indices from roster."""
        for player in self._roster:
            # Index by player_id
            if player.player_id:
                self._by_player_id[player.player_id] = player

            # Index by normalized full name
            normalized = normalize_for_matching(player.full_name)
            self._by_normalized_name[normalized] = player

            # Index by (team_id, last_name)
            if player.last_name and player.team_id:
                last_norm = normalize_for_matching(player.last_name)
                key = (player.team_id.lower(), last_norm)
                if key not in self._by_team_lastname:
                    self._by_team_lastname[key] = []
                self._by_team_lastname[key].append(player)

            # Index by last_name only (for cross-team matching)
            if player.last_name:
                last_norm = normalize_for_matching(player.last_name)
                if last_norm not in self._by_lastname:
                    self._by_lastname[last_norm] = []
                self._by_lastname[last_norm].append(player)

    def resolve(
        self,
        raw_name: str,
        player_id: str | None = None,
        team_id: str | None = None,
    ) -> ResolvedPlayer | None:
        """Resolve a player name to canonical identity.

        Resolution priority:
        1. player_id (if provided and in roster)
        2. Exact name match (normalized)
        3. Alias match (initial + last name)
        4. Cache hit (previously resolved alias)

        Args:
            raw_name: Player name from play data (may be truncated)
            player_id: External player ID (if available)
            team_id: Team identifier (helps disambiguate)

        Returns:
            ResolvedPlayer with canonical identity, or None if unresolved
        """
        if not raw_name:
            return None

        self._stats.total_resolutions += 1

        # Check alias cache first
        cache_key = self._make_cache_key(raw_name, team_id)
        if cache_key in self._alias_cache:
            return self._alias_cache[cache_key]

        # Priority 1: player_id lookup
        if player_id and player_id in self._by_player_id:
            roster_player = self._by_player_id[player_id]
            resolved = self._create_resolved(roster_player, raw_name, is_alias=False)
            self._alias_cache[cache_key] = resolved
            self._stats.player_id_matches += 1
            return resolved

        # Priority 2: Exact name match (normalized)
        normalized = normalize_for_matching(raw_name)
        if normalized in self._by_normalized_name:
            roster_player = self._by_normalized_name[normalized]
            resolved = self._create_resolved(roster_player, raw_name, is_alias=False)
            self._alias_cache[cache_key] = resolved
            self._stats.direct_matches += 1
            return resolved

        # Priority 3: Alias match (truncated name resolution)
        if is_truncated_name(raw_name):
            result = extract_initial_and_lastname(raw_name)
            if result:
                initial, last_name = result
                roster_player = self._find_by_initial_lastname(
                    initial, last_name, team_id
                )
                if roster_player:
                    resolved = self._create_resolved(
                        roster_player, raw_name, is_alias=True
                    )
                    self._alias_cache[cache_key] = resolved
                    self._stats.alias_matches += 1
                    return resolved

        # Unresolved - log warning
        self._stats.unresolved += 1
        if raw_name not in self._stats.unresolved_names:
            self._stats.unresolved_names.append(raw_name)
            logger.warning(
                f"Unresolved player name: '{raw_name}' (team_id={team_id}, player_id={player_id})"
            )

        # Return unresolved with raw name as canonical (fallback)
        return ResolvedPlayer(
            canonical_key=normalize_for_matching(raw_name),
            canonical_name=raw_name,
            player_id=player_id,
            team_id=team_id,
            raw_name=raw_name,
            is_alias=False,
        )

    def _find_by_initial_lastname(
        self,
        initial: str,
        last_name: str,
        team_id: str | None,
    ) -> RosterPlayer | None:
        """Find roster player by initial and last name.

        Args:
            initial: First initial (single character, lowercase)
            last_name: Last name (normalized)
            team_id: Team identifier for disambiguation

        Returns:
            Matching RosterPlayer or None
        """
        candidates: list[RosterPlayer] = []

        # Try team-specific lookup first
        if team_id:
            key = (team_id.lower(), last_name)
            candidates = self._by_team_lastname.get(key, [])
        else:
            # Fall back to all players with this last name
            candidates = self._by_lastname.get(last_name, [])

        # Filter by initial match
        for player in candidates:
            if player.first_name:
                player_initial = normalize_for_matching(player.first_name[0])
                if player_initial == initial:
                    return player

        # If only one candidate with matching last name, accept it
        if len(candidates) == 1:
            return candidates[0]

        return None

    def _create_resolved(
        self,
        roster_player: RosterPlayer,
        raw_name: str,
        is_alias: bool,
    ) -> ResolvedPlayer:
        """Create ResolvedPlayer from roster match."""
        return ResolvedPlayer(
            canonical_key=normalize_for_matching(roster_player.full_name),
            canonical_name=roster_player.full_name,
            player_id=roster_player.player_id,
            team_id=roster_player.team_id,
            raw_name=raw_name,
            is_alias=is_alias,
        )

    def _make_cache_key(self, raw_name: str, team_id: str | None) -> str:
        """Create cache key for alias lookup."""
        team = team_id.lower() if team_id else ""
        return f"{team}:{normalize_for_matching(raw_name)}"

    def get_stats(self) -> ResolutionStats:
        """Get resolution statistics."""
        return self._stats

    def get_canonical_key(
        self,
        raw_name: str,
        player_id: str | None = None,
        team_id: str | None = None,
    ) -> str:
        """Get canonical key for a player name (convenience method).

        Returns normalized raw_name if resolution fails.
        """
        resolved = self.resolve(raw_name, player_id, team_id)
        if resolved:
            return resolved.canonical_key
        return normalize_for_matching(raw_name)

    def get_canonical_name(
        self,
        raw_name: str,
        player_id: str | None = None,
        team_id: str | None = None,
    ) -> str:
        """Get canonical display name for a player (convenience method).

        Returns raw_name if resolution fails.
        """
        resolved = self.resolve(raw_name, player_id, team_id)
        if resolved:
            return resolved.canonical_name
        return raw_name


# ============================================================================
# ROSTER BUILDING HELPERS
# ============================================================================


def build_roster_from_boxscore(boxscore: dict[str, Any]) -> list[RosterPlayer]:
    """Build roster from boxscore data.

    Args:
        boxscore: Boxscore data containing player information

    Returns:
        List of RosterPlayer objects
    """
    roster: list[RosterPlayer] = []

    # Common boxscore structures
    for key in ["home_players", "away_players", "players", "home", "away"]:
        players_data = boxscore.get(key)
        if isinstance(players_data, list):
            for p in players_data:
                if isinstance(p, dict):
                    player = _extract_roster_player(p, boxscore, key)
                    if player:
                        roster.append(player)
        elif isinstance(players_data, dict):
            # Nested structure like {"players": [...]}
            nested = players_data.get("players", [])
            for p in nested:
                if isinstance(p, dict):
                    player = _extract_roster_player(p, boxscore, key)
                    if player:
                        roster.append(player)

    return roster


def _extract_roster_player(
    player_data: dict[str, Any],
    boxscore: dict[str, Any],
    source_key: str,
) -> RosterPlayer | None:
    """Extract RosterPlayer from player data dict."""
    # Get player ID
    player_id = player_data.get("player_id") or player_data.get("id") or ""
    if not player_id:
        return None

    # Get full name
    full_name = (
        player_data.get("player_name")
        or player_data.get("full_name")
        or player_data.get("name")
        or ""
    )
    if not full_name:
        return None

    # Get team ID
    team_id = player_data.get("team_id") or player_data.get("team_abbreviation") or ""

    # Infer team from source key if not present
    if not team_id:
        if "home" in source_key.lower():
            team_id = boxscore.get("home_team_id") or boxscore.get("home_team", {}).get(
                "id", ""
            )
        elif "away" in source_key.lower():
            team_id = boxscore.get("away_team_id") or boxscore.get("away_team", {}).get(
                "id", ""
            )

    # Get first/last name if available
    first_name = player_data.get("first_name", "")
    last_name = player_data.get("last_name", "")

    return RosterPlayer(
        player_id=str(player_id),
        full_name=full_name,
        team_id=str(team_id) if team_id else "",
        first_name=first_name,
        last_name=last_name,
    )


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Data structures
    "RosterPlayer",
    "ResolvedPlayer",
    "ResolutionStats",
    # Functions
    "normalize_for_matching",
    "extract_initial_and_lastname",
    "is_truncated_name",
    "build_roster_from_boxscore",
    # Resolver class
    "PlayerIdentityResolver",
]
