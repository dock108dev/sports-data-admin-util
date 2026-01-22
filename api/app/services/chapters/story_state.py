"""
Story State: Running context derived from prior chapters only.

This module defines the StoryState schema and derivation logic for AI context.

ISSUE 0.4: AI Context Rules (Prior Chapters Only)
ISSUE 8: Implement Running Story State Builder

CONTRACT:
- Story state is derived deterministically from prior chapters
- No future knowledge allowed
- Bounded lists to prevent prompt bloat
- Serializable as JSON
- Supports incremental updates (chapter by chapter)
- Immutable state (returns new copy on update)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
from enum import Enum

from .types import Chapter, Play


class MomentumHint(str, Enum):
    """Simple momentum indicator derived from chapter patterns."""
    
    SURGING = "surging"      # Team on a run
    STEADY = "steady"        # Normal back-and-forth
    SLIPPING = "slipping"    # Team losing momentum
    VOLATILE = "volatile"    # Momentum swinging rapidly
    UNKNOWN = "unknown"      # Cannot determine


@dataclass
class PlayerStoryState:
    """Player state derived from prior chapters only.
    
    Tracks cumulative stats from chapters processed so far.
    Enables "so far" language in AI prompts.
    
    CONTRACT:
    - All stats are cumulative from chapters 0..N-1
    - notable_actions_so_far is bounded (max 5)
    - Deterministic derivation from play text
    """
    
    player_name: str                    # Display name
    points_so_far: int = 0              # Cumulative points
    made_fg_so_far: int = 0             # Made field goals
    made_3pt_so_far: int = 0            # Made 3-pointers
    made_ft_so_far: int = 0             # Made free throws
    notable_actions_so_far: list[str] = field(default_factory=list)  # Max 5
    
    def __post_init__(self):
        """Validate player state."""
        if not self.player_name:
            raise ValueError("player_name cannot be empty")
        
        if self.points_so_far < 0:
            raise ValueError("points_so_far cannot be negative")
        
        if len(self.notable_actions_so_far) > 5:
            raise ValueError("notable_actions_so_far max 5 items")
    
    def add_notable_action(self, action: str) -> None:
        """Add a notable action, maintaining max 5 (FIFO)."""
        self.notable_actions_so_far.append(action)
        if len(self.notable_actions_so_far) > 5:
            self.notable_actions_so_far.pop(0)  # Remove oldest
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class TeamStoryState:
    """Team state derived from prior chapters only.
    
    Tracks team-level cumulative data.
    """
    
    team_name: str                      # Team display name
    score_so_far: int | None = None     # Cumulative score (if derivable)
    
    def __post_init__(self):
        """Validate team state."""
        if not self.team_name:
            raise ValueError("team_name cannot be empty")
        
        if self.score_so_far is not None and self.score_so_far < 0:
            raise ValueError("score_so_far cannot be negative")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class StoryState:
    """Running story state derived deterministically from prior chapters.
    
    This state is updated incrementally after processing each chapter.
    It contains ONLY information from chapters 0..N-1 when generating Chapter N.
    
    CONTRACT:
    - Must be computed only from chapters already processed
    - Must be serializable as JSON
    - Must be stable/deterministic (same input → same output)
    - Must be minimal (bounded lists to prevent prompt bloat)
    
    BOUNDED LISTS:
    - players: Top 6 by points_so_far
    - notable_actions_so_far: Max 5 per player
    - theme_tags: Max 8
    
    ISSUE 0.4: AI Context Policy
    """
    
    # Meta
    chapter_index_last_processed: int   # Last chapter included in this state (0-based)
    
    # Players (top 6 by points_so_far)
    players: dict[str, PlayerStoryState] = field(default_factory=dict)
    
    # Teams
    teams: dict[str, TeamStoryState] = field(default_factory=dict)
    
    # Momentum
    momentum_hint: MomentumHint = MomentumHint.UNKNOWN
    
    # Themes (max 8)
    theme_tags: list[str] = field(default_factory=list)
    
    # Constraints (metadata)
    constraints: dict[str, Any] = field(default_factory=lambda: {
        "no_future_knowledge": True,
        "source": "derived_from_prior_chapters_only"
    })
    
    def __post_init__(self):
        """Validate story state."""
        if self.chapter_index_last_processed < -1:
            raise ValueError("chapter_index_last_processed cannot be < -1")
        
        if len(self.players) > 6:
            raise ValueError("players max 6 (top by points_so_far)")
        
        if len(self.theme_tags) > 8:
            raise ValueError("theme_tags max 8")
        
        # Validate constraints
        if not self.constraints.get("no_future_knowledge"):
            raise ValueError("constraints.no_future_knowledge must be true")
        
        if self.constraints.get("source") != "derived_from_prior_chapters_only":
            raise ValueError("constraints.source must be 'derived_from_prior_chapters_only'")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "chapter_index_last_processed": self.chapter_index_last_processed,
            "players": {
                name: player.to_dict()
                for name, player in self.players.items()
            },
            "teams": {
                name: team.to_dict()
                for name, team in self.teams.items()
            },
            "momentum_hint": self.momentum_hint.value,
            "theme_tags": self.theme_tags,
            "constraints": self.constraints,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryState:
        """Create from dictionary (for deserialization)."""
        return cls(
            chapter_index_last_processed=data["chapter_index_last_processed"],
            players={
                name: PlayerStoryState(**player_data)
                for name, player_data in data.get("players", {}).items()
            },
            teams={
                name: TeamStoryState(**team_data)
                for name, team_data in data.get("teams", {}).items()
            },
            momentum_hint=MomentumHint(data.get("momentum_hint", "unknown")),
            theme_tags=data.get("theme_tags", []),
            constraints=data.get("constraints", {}),
        )


# ============================================================================
# DETERMINISTIC DERIVATION (NBA v1)
# ============================================================================

def derive_story_state_from_chapters(
    chapters: list[Chapter],
    sport: str = "NBA"
) -> StoryState:
    """Derive story state deterministically from prior chapters.
    
    NBA v1 RULES:
    - Points from made shots and free throws
    - Notable actions from play text patterns
    - Momentum from chapter reason codes
    - Theme tags from chapter patterns
    - No AI, no guessing, no box score
    
    Args:
        chapters: List of chapters to process (in order)
        sport: Sport identifier (NBA v1 only)
        
    Returns:
        StoryState derived from these chapters
    """
    if sport != "NBA":
        # Fallback for non-NBA (minimal state)
        return StoryState(
            chapter_index_last_processed=len(chapters) - 1 if chapters else -1,
        )
    
    # Initialize state
    players: dict[str, PlayerStoryState] = {}
    teams: dict[str, TeamStoryState] = {}
    theme_tags: list[str] = []
    
    # Process each chapter
    for chapter_idx, chapter in enumerate(chapters):
        # Extract player stats from plays
        for play in chapter.plays:
            _extract_player_stats(play, players)
            _extract_notable_actions(play, players, chapter)
        
        # Extract team scores
        _extract_team_scores(chapter, teams)
        
        # Extract theme tags
        _extract_theme_tags(chapter, theme_tags)
    
    # Determine momentum hint from most recent chapter
    momentum_hint = _determine_momentum_hint(chapters[-1] if chapters else None)
    
    # Truncate to top 6 players by points
    top_players = dict(
        sorted(
            players.items(),
            key=lambda item: item[1].points_so_far,
            reverse=True
        )[:6]
    )
    
    # Truncate theme tags to max 8 (most frequent)
    theme_counts = {tag: theme_tags.count(tag) for tag in set(theme_tags)}
    top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    final_themes = [tag for tag, _ in top_themes]
    
    return StoryState(
        chapter_index_last_processed=len(chapters) - 1 if chapters else -1,
        players=top_players,
        teams=teams,
        momentum_hint=momentum_hint,
        theme_tags=final_themes,
    )


def _extract_player_stats(play: Play, players: dict[str, PlayerStoryState]) -> None:
    """Extract player stats from a single play.
    
    NBA v1 RULES:
    - Points from "makes" in description
    - 3PT: "3-pt" or "three" → 3 points
    - FT: "free throw" → 1 point
    - FG: other "makes" → 2 points
    """
    description = play.raw_data.get("description", "").lower()
    
    if "makes" not in description:
        return
    
    # Extract player name (simple heuristic: first capitalized word(s) before "makes")
    raw_desc = play.raw_data.get("description", "")
    if " makes " not in raw_desc:
        return
    
    player_name = raw_desc.split(" makes ")[0].strip()
    if not player_name:
        return
    
    # Initialize player if not seen
    if player_name not in players:
        players[player_name] = PlayerStoryState(player_name=player_name)
    
    player = players[player_name]
    
    # Determine points
    if "3-pt" in description or "three" in description or "3-pointer" in description:
        player.points_so_far += 3
        player.made_3pt_so_far += 1
        player.made_fg_so_far += 1
    elif "free throw" in description:
        player.points_so_far += 1
        player.made_ft_so_far += 1
    else:
        player.points_so_far += 2
        player.made_fg_so_far += 1


def _extract_notable_actions(
    play: Play,
    players: dict[str, PlayerStoryState],
    chapter: Chapter
) -> None:
    """Extract notable actions from play text.
    
    NBA v1 ELIGIBLE ACTIONS:
    - dunk, block, steal, 3PT, and-1, technical, flagrant, challenge, clutch_shot
    """
    description = play.raw_data.get("description", "").lower()
    raw_desc = play.raw_data.get("description", "")
    
    # Extract player name (before action verb)
    player_name = None
    for verb in ["makes", "dunk", "block", "steal"]:
        if verb in raw_desc:
            player_name = raw_desc.split(f" {verb}")[0].strip()
            break
    
    if not player_name or player_name not in players:
        return
    
    player = players[player_name]
    
    # Check for notable actions
    if "dunk" in description:
        player.add_notable_action("dunk")
    
    if "block" in description:
        player.add_notable_action("block")
    
    if "steal" in description:
        player.add_notable_action("steal")
    
    if "3-pt" in description or "three" in description or "3-pointer" in description:
        player.add_notable_action("3PT")
    
    if "and-1" in description or "and 1" in description:
        player.add_notable_action("and-1")
    
    if "technical" in description:
        player.add_notable_action("technical")
    
    if "flagrant" in description:
        player.add_notable_action("flagrant")
    
    if "challenge" in description or "review" in description:
        player.add_notable_action("challenge")
    
    # Clutch shot: made shot in crunch time
    if "CRUNCH_START" in chapter.reason_codes and "makes" in description:
        player.add_notable_action("clutch_shot")


def _extract_team_scores(chapter: Chapter, teams: dict[str, TeamStoryState]) -> None:
    """Extract team scores from chapter plays (if available)."""
    # Look for score in last play of chapter
    if not chapter.plays:
        return
    
    last_play = chapter.plays[-1]
    home_score = last_play.raw_data.get("home_score")
    away_score = last_play.raw_data.get("away_score")
    
    if home_score is not None:
        # Extract team names from metadata (or use generic)
        home_team = last_play.raw_data.get("home_team", "Home")
        away_team = last_play.raw_data.get("away_team", "Away")
        
        if home_team not in teams:
            teams[home_team] = TeamStoryState(team_name=home_team)
        if away_team not in teams:
            teams[away_team] = TeamStoryState(team_name=away_team)
        
        teams[home_team].score_so_far = home_score
        teams[away_team].score_so_far = away_score


def _extract_theme_tags(chapter: Chapter, theme_tags: list[str]) -> None:
    """Extract deterministic theme tags from chapter.
    
    NBA v1 THEME TAGS:
    - defensive_intensity: Multiple blocks/steals
    - hot_shooting: Many made shots
    - free_throw_battle: Many FTs
    - timeout_heavy: TIMEOUT reason codes
    - crunch_time: CRUNCH_START reason code
    - overtime: OVERTIME_START reason code
    - review_heavy: REVIEW reason codes
    - run_based: RUN_START or RUN_END_RESPONSE codes
    """
    # Check reason codes
    if "TIMEOUT" in chapter.reason_codes:
        theme_tags.append("timeout_heavy")
    
    if "CRUNCH_START" in chapter.reason_codes:
        theme_tags.append("crunch_time")
    
    if "OVERTIME_START" in chapter.reason_codes:
        theme_tags.append("overtime")
    
    if "REVIEW" in chapter.reason_codes:
        theme_tags.append("review_heavy")
    
    if "RUN_START" in chapter.reason_codes or "RUN_END_RESPONSE" in chapter.reason_codes:
        theme_tags.append("run_based")
    
    # Check play patterns
    blocks = sum(1 for p in chapter.plays if "block" in p.raw_data.get("description", "").lower())
    steals = sum(1 for p in chapter.plays if "steal" in p.raw_data.get("description", "").lower())
    
    if blocks + steals >= 3:
        theme_tags.append("defensive_intensity")
    
    made_shots = sum(1 for p in chapter.plays if "makes" in p.raw_data.get("description", "").lower())
    if made_shots >= 5:
        theme_tags.append("hot_shooting")
    
    free_throws = sum(1 for p in chapter.plays if "free throw" in p.raw_data.get("description", "").lower())
    if free_throws >= 4:
        theme_tags.append("free_throw_battle")


def _determine_momentum_hint(chapter: Chapter | None) -> MomentumHint:
    """Determine momentum hint from most recent chapter.
    
    NBA v1 RULES:
    - RUN_START → surging
    - RUN_END_RESPONSE → volatile
    - CRUNCH_START → volatile
    - Otherwise → steady
    """
    if not chapter:
        return MomentumHint.UNKNOWN
    
    if "RUN_START" in chapter.reason_codes:
        return MomentumHint.SURGING
    
    if "RUN_END_RESPONSE" in chapter.reason_codes:
        return MomentumHint.VOLATILE
    
    if "CRUNCH_START" in chapter.reason_codes:
        return MomentumHint.VOLATILE
    
    return MomentumHint.STEADY


# ============================================================================
# INCREMENTAL BUILDER (ISSUE 8)
# ============================================================================

def build_initial_state() -> StoryState:
    """Build initial empty story state (before any chapters).
    
    Returns:
        Empty StoryState with chapter_index_last_processed = -1
    """
    return StoryState(
        chapter_index_last_processed=-1,
    )


def update_state(
    previous_state: StoryState,
    chapter: Chapter,
    sport: str = "NBA"
) -> StoryState:
    """Update story state incrementally with a new chapter.
    
    This is the incremental builder that processes one chapter at a time.
    It creates a NEW state (immutable) by copying previous state and adding
    the new chapter's data.
    
    GUARANTEES:
    - No mutation of previous_state
    - Returns new StoryState instance
    - Deterministic (same inputs → same output)
    - Bounded (enforces max players, themes)
    
    Args:
        previous_state: Previous story state (from chapters 0..N-1)
        chapter: New chapter N to process
        sport: Sport identifier (NBA v1 only)
        
    Returns:
        New StoryState including data from chapter N
    """
    if sport != "NBA":
        # Fallback for non-NBA
        return StoryState(
            chapter_index_last_processed=previous_state.chapter_index_last_processed + 1,
        )
    
    # Copy previous state data (deep copy for mutable structures)
    import copy
    players = copy.deepcopy(previous_state.players)
    teams = copy.deepcopy(previous_state.teams)
    theme_tags = previous_state.theme_tags.copy()
    
    # Process new chapter
    for play in chapter.plays:
        _extract_player_stats(play, players)
        _extract_notable_actions(play, players, chapter)
    
    _extract_team_scores(chapter, teams)
    _extract_theme_tags(chapter, theme_tags)
    
    # Determine momentum hint from this chapter
    momentum_hint = _determine_momentum_hint(chapter)
    
    # Truncate to top 6 players by points (deterministic)
    top_players = dict(
        sorted(
            players.items(),
            key=lambda item: (item[1].points_so_far, item[0]),  # Secondary sort by name for determinism
            reverse=True
        )[:6]
    )
    
    # Truncate theme tags to max 8 (most frequent, deterministic)
    theme_counts = {tag: theme_tags.count(tag) for tag in set(theme_tags)}
    top_themes = sorted(
        theme_counts.items(),
        key=lambda x: (x[1], x[0]),  # Secondary sort by tag name for determinism
        reverse=True
    )[:8]
    final_themes = [tag for tag, _ in top_themes]
    
    return StoryState(
        chapter_index_last_processed=previous_state.chapter_index_last_processed + 1,
        players=top_players,
        teams=teams,
        momentum_hint=momentum_hint,
        theme_tags=final_themes,
    )


def build_state_incrementally(
    chapters: list[Chapter],
    sport: str = "NBA"
) -> list[StoryState]:
    """Build story state incrementally for each chapter.
    
    This demonstrates the incremental builder by processing chapters one at a time.
    
    Args:
        chapters: List of chapters to process (in order)
        sport: Sport identifier (NBA v1 only)
        
    Returns:
        List of StoryState objects, one after each chapter
    """
    states = []
    current_state = build_initial_state()
    
    for chapter in chapters:
        current_state = update_state(current_state, chapter, sport)
        states.append(current_state)
    
    return states
