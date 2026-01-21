"""
AI Signals: Locked set of signals exposed to AI for NBA v1.

This module defines and validates the exact signals that AI may reference
during story generation.

ISSUE 9: Define Player, Team, and Theme Signals Exposed to AI

GUARANTEES:
- Only whitelisted signals exposed
- No disallowed signals leak through
- Signals are bounded and deterministic
- Schema validation enforced
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from .story_state import StoryState, MomentumHint


# ============================================================================
# SIGNAL DEFINITIONS (NBA V1 - LOCKED)
# ============================================================================

# Allowed player signal fields
ALLOWED_PLAYER_SIGNALS = {
    "player_name",
    "points_so_far",
    "made_fg_so_far",
    "made_3pt_so_far",
    "made_ft_so_far",
    "notable_actions_so_far",
}

# Allowed team signal fields
ALLOWED_TEAM_SIGNALS = {
    "team_name",
    "score_so_far",
}

# Allowed story state fields
ALLOWED_STORY_STATE_SIGNALS = {
    "chapter_index_last_processed",
    "players",
    "teams",
    "momentum_hint",
    "theme_tags",
    "constraints",
}

# Disallowed signals (explicit blacklist)
DISALLOWED_SIGNALS = {
    # Stats & Totals
    "final_points",
    "shooting_percentage",
    "fg_percentage",
    "three_pt_percentage",
    "ft_percentage",
    "plus_minus",
    "efficiency_rating",
    "rebounds",
    "assists",
    "turnovers",
    "steals",
    "blocks",
    
    # Predictive Metrics
    "win_probability",
    "expected_points",
    "clutch_rating",
    "importance_score",
    
    # Legacy Moments Engine
    "ladder_tier",
    "moment_type",
    "lead_change_count",
    "tier_crossing_count",
    
    # External Context
    "season_stats",
    "career_stats",
    "team_record",
    "playoff_context",
    
    # Subjective
    "best_player",
    "clutch_performer",
    "momentum_shifter",
}

# Allowed theme tags (NBA v1)
ALLOWED_THEME_TAGS = {
    "timeout_heavy",
    "crunch_time",
    "overtime",
    "review_heavy",
    "run_based",
    "defensive_intensity",
    "hot_shooting",
    "free_throw_battle",
}

# Allowed notable actions (NBA v1)
ALLOWED_NOTABLE_ACTIONS = {
    "dunk",
    "block",
    "steal",
    "3PT",
    "and-1",
    "technical",
    "flagrant",
    "challenge",
    "clutch_shot",
}


# ============================================================================
# SIGNAL VALIDATION
# ============================================================================

class SignalValidationError(Exception):
    """Raised when AI signals fail validation."""
    pass


def validate_player_signals(player_data: dict[str, Any]) -> None:
    """Validate player signals against whitelist.
    
    Args:
        player_data: Player signal dictionary
        
    Raises:
        SignalValidationError: If invalid signals found
    """
    for field in player_data.keys():
        if field not in ALLOWED_PLAYER_SIGNALS:
            raise SignalValidationError(
                f"Disallowed player signal: '{field}'. "
                f"Allowed: {ALLOWED_PLAYER_SIGNALS}"
            )
        
        if field in DISALLOWED_SIGNALS:
            raise SignalValidationError(
                f"Blacklisted signal in player data: '{field}'"
            )
    
    # Validate notable actions
    if "notable_actions_so_far" in player_data:
        for action in player_data["notable_actions_so_far"]:
            if action not in ALLOWED_NOTABLE_ACTIONS:
                raise SignalValidationError(
                    f"Disallowed notable action: '{action}'. "
                    f"Allowed: {ALLOWED_NOTABLE_ACTIONS}"
                )


def validate_team_signals(team_data: dict[str, Any]) -> None:
    """Validate team signals against whitelist.
    
    Args:
        team_data: Team signal dictionary
        
    Raises:
        SignalValidationError: If invalid signals found
    """
    for field in team_data.keys():
        if field not in ALLOWED_TEAM_SIGNALS:
            raise SignalValidationError(
                f"Disallowed team signal: '{field}'. "
                f"Allowed: {ALLOWED_TEAM_SIGNALS}"
            )
        
        if field in DISALLOWED_SIGNALS:
            raise SignalValidationError(
                f"Blacklisted signal in team data: '{field}'"
            )


def validate_story_state_signals(state_data: dict[str, Any]) -> None:
    """Validate story state signals against whitelist.
    
    Args:
        state_data: Story state signal dictionary
        
    Raises:
        SignalValidationError: If invalid signals found
    """
    for field in state_data.keys():
        if field not in ALLOWED_STORY_STATE_SIGNALS:
            raise SignalValidationError(
                f"Disallowed story state signal: '{field}'. "
                f"Allowed: {ALLOWED_STORY_STATE_SIGNALS}"
            )
        
        if field in DISALLOWED_SIGNALS:
            raise SignalValidationError(
                f"Blacklisted signal in story state: '{field}'"
            )
    
    # Validate theme tags
    if "theme_tags" in state_data:
        for tag in state_data["theme_tags"]:
            if tag not in ALLOWED_THEME_TAGS:
                raise SignalValidationError(
                    f"Disallowed theme tag: '{tag}'. "
                    f"Allowed: {ALLOWED_THEME_TAGS}"
                )
    
    # Validate momentum hint
    if "momentum_hint" in state_data:
        try:
            MomentumHint(state_data["momentum_hint"])
        except ValueError:
            raise SignalValidationError(
                f"Invalid momentum hint: '{state_data['momentum_hint']}'. "
                f"Allowed: {[m.value for m in MomentumHint]}"
            )


def validate_ai_signals(story_state: StoryState) -> None:
    """Validate all AI signals in story state.
    
    This is the main validation function that ensures only allowed signals
    are present in the AI input payload.
    
    Args:
        story_state: Story state to validate
        
    Raises:
        SignalValidationError: If any invalid signals found
    """
    state_dict = story_state.to_dict()
    
    # Validate top-level story state
    validate_story_state_signals(state_dict)
    
    # Validate each player
    for player_name, player_data in state_dict.get("players", {}).items():
        validate_player_signals(player_data)
    
    # Validate each team
    for team_name, team_data in state_dict.get("teams", {}).items():
        validate_team_signals(team_data)
    
    # Validate bounding
    if len(state_dict.get("players", {})) > 6:
        raise SignalValidationError(
            f"Too many players exposed to AI: {len(state_dict['players'])}. Max: 6"
        )
    
    if len(state_dict.get("theme_tags", [])) > 8:
        raise SignalValidationError(
            f"Too many theme tags exposed to AI: {len(state_dict['theme_tags'])}. Max: 8"
        )
    
    # Validate constraints
    constraints = state_dict.get("constraints", {})
    if not constraints.get("no_future_knowledge"):
        raise SignalValidationError(
            "AI signals must have no_future_knowledge constraint"
        )
    
    if constraints.get("source") != "derived_from_prior_chapters_only":
        raise SignalValidationError(
            "AI signals must be derived_from_prior_chapters_only"
        )


def check_for_disallowed_signals(data: dict[str, Any], path: str = "") -> list[str]:
    """Recursively check for disallowed signals in data.
    
    Args:
        data: Dictionary to check
        path: Current path (for error reporting)
        
    Returns:
        List of found disallowed signals with paths
    """
    found = []
    
    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        
        # Check if key is disallowed
        if key in DISALLOWED_SIGNALS:
            found.append(current_path)
        
        # Recurse into nested dicts
        if isinstance(value, dict):
            found.extend(check_for_disallowed_signals(value, current_path))
        
        # Check lists of dicts
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    found.extend(check_for_disallowed_signals(item, f"{current_path}[{i}]"))
    
    return found


# ============================================================================
# SIGNAL FORMATTING (FOR CLI)
# ============================================================================

def format_ai_signals_summary(story_state: StoryState) -> str:
    """Format AI signals as human-readable summary.
    
    Args:
        story_state: Story state to format
        
    Returns:
        Formatted string for CLI output
    """
    lines = []
    lines.append("=== AI SIGNALS ===\n")
    
    # Players
    lines.append(f"Players (Top {len(story_state.players)}):")
    for i, (name, player) in enumerate(story_state.players.items(), 1):
        notable = ", ".join(player.notable_actions_so_far) if player.notable_actions_so_far else "none"
        lines.append(
            f"  {i}. {name}: {player.points_so_far} pts "
            f"({player.made_fg_so_far} FG, {player.made_3pt_so_far} 3PT, {player.made_ft_so_far} FT) | "
            f"Notable: {notable}"
        )
    
    if not story_state.players:
        lines.append("  (none)")
    
    # Teams
    lines.append("\nTeams:")
    for name, team in story_state.teams.items():
        score = f"{team.score_so_far} pts" if team.score_so_far is not None else "score unknown"
        lines.append(f"  {name}: {score}")
    
    if not story_state.teams:
        lines.append("  (none)")
    
    # Momentum
    lines.append(f"\nMomentum: {story_state.momentum_hint.value}")
    
    # Themes
    lines.append(f"\nThemes ({len(story_state.theme_tags)}):")
    if story_state.theme_tags:
        for tag in story_state.theme_tags:
            lines.append(f"  - {tag}")
    else:
        lines.append("  (none)")
    
    # Constraints
    lines.append("\nConstraints:")
    lines.append(f"  ✓ no_future_knowledge: {story_state.constraints['no_future_knowledge']}")
    lines.append(f"  ✓ source: {story_state.constraints['source']}")
    
    return "\n".join(lines)
