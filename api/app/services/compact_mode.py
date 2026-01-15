"""
Compact Mode: Semantic grouping and compression for timelines.

Compact mode operates on SEMANTIC GROUPS, not individual events.
- Social events are NEVER dropped
- PBP groups collapse to summaries
- Higher excitement → more groups shown (implicitly)

Excitement scores are internal only - never exposed in API responses.

See docs/COMPACT_MODE.md for the canonical specification.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Sequence

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Play types that are NEVER compressed
NEVER_COMPRESS_PLAY_TYPES = frozenset({
    "made_shot", "made_three", "made_ft", "dunk", "and_one",  # Scoring
    "technical", "ejection", "flagrant",  # Drama
    "timeout", "end_period", "start_period",  # Structural
    "injury",  # Context-critical
})

# Play types that are ALWAYS compressed
ALWAYS_COMPRESS_PLAY_TYPES = frozenset({
    "substitution", "sub_in", "sub_out",
    "jump_ball",  # Non-opening
    "violation", "lane_violation",
})

# Exciting play types that boost excitement score
EXCITING_PLAY_TYPES = frozenset({
    "dunk", "block", "steal", "made_three", "and_one", "alley_oop",
})

# Compression levels
class CompressionLevel(Enum):
    HIGHLIGHTS = 1  # ~15-20% retention
    STANDARD = 2    # ~40-50% retention (default)
    DETAILED = 3    # ~70-80% retention


# =============================================================================
# SEMANTIC GROUP TYPES
# =============================================================================

class GroupType(Enum):
    SCORING_RUN = "scoring_run"    # 3+ consecutive scores by one team
    SWING = "swing"                # Lead change or tie-breaking
    DROUGHT = "drought"            # 2+ min without scoring
    FINISH = "finish"              # Final 2 min of period
    OPENER = "opener"              # First 2 min of period
    ROUTINE = "routine"            # No scoring, no drama


@dataclass
class SemanticGroup:
    """A sequence of plays that form a coherent narrative unit."""
    group_type: GroupType
    events: list[dict[str, Any]] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0
    team_id: int | None = None  # For scoring runs
    excitement: float = 0.0     # Internal only, never exposed
    
    @property
    def play_count(self) -> int:
        return len([e for e in self.events if e.get("event_type") == "pbp"])
    
    @property
    def social_count(self) -> int:
        return len([e for e in self.events if e.get("event_type") == "tweet"])
    
    @property
    def has_social(self) -> bool:
        return self.social_count > 0


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _parse_game_clock(clock: str | None) -> float:
    """Parse game clock string to seconds remaining. Returns 720 (12:00) if unparsable."""
    if not clock:
        return 720.0
    try:
        parts = clock.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(clock)
    except (ValueError, TypeError):
        return 720.0


def _is_scoring_play(event: dict[str, Any]) -> bool:
    """Check if event is a scoring play."""
    if event.get("event_type") != "pbp":
        return False
    play_type = event.get("play_type", "")
    return play_type in {"made_shot", "made_three", "made_ft", "dunk", "and_one", "alley_oop"}


def _is_final_minutes(event: dict[str, Any], threshold_seconds: float = 120) -> bool:
    """Check if event is in final minutes of a period."""
    clock = _parse_game_clock(event.get("game_clock"))
    return clock <= threshold_seconds


def _is_opening_minutes(event: dict[str, Any], threshold_seconds: float = 600) -> bool:
    """Check if event is in opening minutes of a period (clock > 10:00)."""
    clock = _parse_game_clock(event.get("game_clock"))
    return clock >= threshold_seconds


def _get_scoring_team(event: dict[str, Any]) -> int | None:
    """Get the team that scored (for scoring plays)."""
    return event.get("team_id")


def _should_never_compress(event: dict[str, Any]) -> bool:
    """Check if event should never be compressed."""
    if event.get("event_type") == "tweet":
        return True  # Social posts NEVER compressed
    
    play_type = event.get("play_type", "")
    if play_type in NEVER_COMPRESS_PLAY_TYPES:
        return True
    
    # Period boundaries
    if event.get("is_period_start") or event.get("is_period_end"):
        return True
    
    return False


def _should_always_compress(event: dict[str, Any]) -> bool:
    """Check if event should always be compressed."""
    if event.get("event_type") == "tweet":
        return False  # Social posts NEVER compressed
    
    play_type = event.get("play_type", "")
    return play_type in ALWAYS_COMPRESS_PLAY_TYPES


# =============================================================================
# EXCITEMENT SCORING (INTERNAL ONLY)
# =============================================================================

def _compute_excitement(group: SemanticGroup, all_events: Sequence[dict[str, Any]]) -> float:
    """
    Compute excitement score for a semantic group.
    
    Returns 0.0 - 1.0 score.
    INTERNAL ONLY - never exposed in API responses.
    
    Uses score-blind signals:
    - Pace (short gaps between plays)
    - Social density (tweets in window)
    - Play type variety (blocks, steals, dunks)
    - Late game context
    """
    if not group.events:
        return 0.0
    
    score = 0.0
    pbp_events = [e for e in group.events if e.get("event_type") == "pbp"]
    
    # Base excitement by group type
    if group.group_type == GroupType.FINISH:
        score += 0.3  # Final minutes always exciting
    elif group.group_type == GroupType.SCORING_RUN:
        score += 0.2
    elif group.group_type == GroupType.SWING:
        score += 0.25
    
    # Social density signal
    tweet_count = group.social_count
    if tweet_count >= 2:
        score += 0.25
    elif tweet_count == 1:
        score += 0.1
    
    # Play type variety signal
    exciting_count = sum(
        1 for e in pbp_events 
        if e.get("play_type") in EXCITING_PLAY_TYPES
    )
    score += min(exciting_count * 0.1, 0.3)
    
    # Pace signal (if timestamps available)
    if len(pbp_events) >= 2:
        clocks = [_parse_game_clock(e.get("game_clock")) for e in pbp_events]
        gaps = [abs(clocks[i] - clocks[i+1]) for i in range(len(clocks)-1)]
        avg_gap = sum(gaps) / len(gaps) if gaps else 60
        if avg_gap < 20:  # Fast pace
            score += 0.2
        elif avg_gap < 40:
            score += 0.1
    
    return min(score, 1.0)


# =============================================================================
# SEMANTIC GROUP DETECTION
# =============================================================================

def detect_semantic_groups(events: Sequence[dict[str, Any]]) -> list[SemanticGroup]:
    """
    Analyze timeline events and detect semantic groups.
    
    Groups are narrative units like:
    - Scoring runs (same team scores 3+ times)
    - Swings (lead changes)
    - Droughts (no scoring for 2+ min)
    - Finish (final 2 min)
    - Opener (first 2 min)
    - Routine (everything else)
    """
    if not events:
        return []
    
    groups: list[SemanticGroup] = []
    current_group: SemanticGroup | None = None
    
    # Track scoring for run detection
    last_scoring_team: int | None = None
    consecutive_scores = 0
    
    for i, event in enumerate(events):
        # Determine what kind of group this event belongs to
        new_group_type: GroupType | None = None
        
        if _is_final_minutes(event):
            # Final minutes - always Finish group
            if current_group is None or current_group.group_type != GroupType.FINISH:
                new_group_type = GroupType.FINISH
        elif _is_opening_minutes(event):
            # Opening minutes - Opener group
            if current_group is None or current_group.group_type != GroupType.OPENER:
                new_group_type = GroupType.OPENER
        elif _is_scoring_play(event):
            team = _get_scoring_team(event)
            if team == last_scoring_team:
                consecutive_scores += 1
                if consecutive_scores >= 3:
                    # Scoring run by same team
                    if current_group is None or current_group.group_type != GroupType.SCORING_RUN:
                        new_group_type = GroupType.SCORING_RUN
            else:
                # Different team scored - could be swing
                if consecutive_scores >= 2:
                    new_group_type = GroupType.SWING
                else:
                    new_group_type = GroupType.ROUTINE
                last_scoring_team = team
                consecutive_scores = 1
        else:
            # Non-scoring play
            if current_group is None:
                new_group_type = GroupType.ROUTINE
        
        # Create new group if needed
        if new_group_type is not None:
            if current_group is not None:
                current_group.end_index = i - 1
                groups.append(current_group)
            
            current_group = SemanticGroup(
                group_type=new_group_type,
                events=[],
                start_index=i,
                team_id=last_scoring_team if new_group_type == GroupType.SCORING_RUN else None,
            )
        
        # Add event to current group
        if current_group is not None:
            current_group.events.append(event)
    
    # Finalize last group
    if current_group is not None:
        current_group.end_index = len(events) - 1
        groups.append(current_group)
    
    # Compute excitement for each group
    for group in groups:
        group.excitement = _compute_excitement(group, events)
    
    return groups


# =============================================================================
# COMPRESSION LOGIC
# =============================================================================

def _create_summary_marker(
    events: list[dict[str, Any]],
    summary_type: str,
    phase: str,
) -> dict[str, Any]:
    """Create a summary marker for compressed events."""
    pbp_events = [e for e in events if e.get("event_type") == "pbp"]
    
    # Calculate duration from game clocks
    duration_seconds = 0
    if len(pbp_events) >= 2:
        first_clock = _parse_game_clock(pbp_events[0].get("game_clock"))
        last_clock = _parse_game_clock(pbp_events[-1].get("game_clock"))
        duration_seconds = int(abs(first_clock - last_clock))
    
    # Generate description based on summary type
    descriptions = {
        "routine": "Back-and-forth play",
        "drought": "Both teams cold from the field",
        "free_throws": "Free throw shooting",
        "subs": "Both teams make substitutions",
        "review": "Play under review",
        "defense": "Defensive struggle",
    }
    description = descriptions.get(summary_type, "Game action")
    
    # Use timestamp from first event
    timestamp = None
    if pbp_events:
        timestamp = pbp_events[0].get("synthetic_timestamp")
    
    return {
        "event_type": "summary",
        "phase": phase,
        "summary_type": summary_type,
        "plays_compressed": len(pbp_events),
        "duration_seconds": duration_seconds,
        "description": description,
        "synthetic_timestamp": timestamp,
    }


def _compress_group(
    group: SemanticGroup,
    level: CompressionLevel,
) -> list[dict[str, Any]]:
    """
    Compress a semantic group based on compression level.
    
    Returns list of events (may include summary markers).
    Social posts are NEVER dropped.
    """
    result: list[dict[str, Any]] = []
    pending_compression: list[dict[str, Any]] = []
    
    # Determine compression behavior based on group type and level
    if group.group_type == GroupType.FINISH:
        # Final minutes: never compress
        return list(group.events)
    
    # Excitement-based compression threshold
    # Higher excitement = less compression
    if group.excitement >= 0.8:
        # Very exciting: no compression
        return list(group.events)
    elif group.excitement >= 0.6:
        # Exciting: light compression (keep most)
        compress_routine = True
        keep_every_nth = 2
    elif group.excitement >= 0.3:
        # Standard: moderate compression
        compress_routine = True
        keep_every_nth = 3
    else:
        # Low excitement: heavy compression
        compress_routine = True
        keep_every_nth = 5
    
    # Adjust by compression level
    if level == CompressionLevel.HIGHLIGHTS:
        keep_every_nth = max(keep_every_nth, 5)
    elif level == CompressionLevel.DETAILED:
        keep_every_nth = min(keep_every_nth, 2)
    
    # Process events
    routine_count = 0
    phase = group.events[0].get("phase", "unknown") if group.events else "unknown"
    
    for event in group.events:
        # Social posts: ALWAYS keep, flush pending compression
        if event.get("event_type") == "tweet":
            if pending_compression:
                summary = _create_summary_marker(pending_compression, "routine", phase)
                result.append(summary)
                pending_compression = []
            result.append(event)
            continue
        
        # Never-compress events: always keep
        if _should_never_compress(event):
            if pending_compression:
                summary = _create_summary_marker(pending_compression, "routine", phase)
                result.append(summary)
                pending_compression = []
            result.append(event)
            continue
        
        # Always-compress events: add to pending
        if _should_always_compress(event):
            pending_compression.append(event)
            continue
        
        # Conditional compression based on excitement
        if compress_routine:
            routine_count += 1
            if routine_count % keep_every_nth == 1:
                # Keep this one
                if pending_compression:
                    summary = _create_summary_marker(pending_compression, "routine", phase)
                    result.append(summary)
                    pending_compression = []
                result.append(event)
            else:
                pending_compression.append(event)
        else:
            result.append(event)
    
    # Flush remaining pending compression
    if pending_compression:
        summary = _create_summary_marker(pending_compression, "routine", phase)
        result.append(summary)
    
    return result


# =============================================================================
# MAIN API
# =============================================================================

def apply_compact_mode(
    timeline: Sequence[dict[str, Any]],
    level: CompressionLevel = CompressionLevel.STANDARD,
) -> list[dict[str, Any]]:
    """
    Apply compact mode compression to a timeline.
    
    Operates on semantic groups, not individual events.
    - Social posts are NEVER dropped
    - PBP groups collapse to summary markers
    - Higher excitement → more events shown
    
    Excitement scores are computed internally but never exposed.
    
    Args:
        timeline: Full timeline events
        level: Compression level (HIGHLIGHTS, STANDARD, DETAILED)
    
    Returns:
        Compressed timeline with summary markers
    """
    if not timeline:
        return []
    
    # Detect semantic groups
    groups = detect_semantic_groups(list(timeline))
    
    logger.info(
        "compact_mode_groups_detected",
        extra={
            "total_events": len(timeline),
            "group_count": len(groups),
            "group_types": [g.group_type.value for g in groups],
        },
    )
    
    # Compress each group
    compressed: list[dict[str, Any]] = []
    for group in groups:
        compressed_group = _compress_group(group, level)
        compressed.extend(compressed_group)
    
    # Log compression stats
    original_pbp = sum(1 for e in timeline if e.get("event_type") == "pbp")
    compressed_pbp = sum(1 for e in compressed if e.get("event_type") == "pbp")
    summary_count = sum(1 for e in compressed if e.get("event_type") == "summary")
    
    logger.info(
        "compact_mode_applied",
        extra={
            "level": level.value,
            "original_events": len(timeline),
            "compressed_events": len(compressed),
            "original_pbp": original_pbp,
            "retained_pbp": compressed_pbp,
            "summary_markers": summary_count,
            "retention_rate": round(compressed_pbp / original_pbp, 2) if original_pbp > 0 else 1.0,
        },
    )
    
    return compressed


def get_compact_timeline(
    timeline: Sequence[dict[str, Any]],
    level: int = 2,
) -> list[dict[str, Any]]:
    """
    Get compact timeline with specified compression level.
    
    Args:
        timeline: Full timeline events
        level: 1 (highlights), 2 (standard), 3 (detailed)
    
    Returns:
        Compressed timeline
    """
    compression_level = {
        1: CompressionLevel.HIGHLIGHTS,
        2: CompressionLevel.STANDARD,
        3: CompressionLevel.DETAILED,
    }.get(level, CompressionLevel.STANDARD)
    
    return apply_compact_mode(timeline, compression_level)
