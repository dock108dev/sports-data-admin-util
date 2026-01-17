"""
Compact Mode: Pure timeline compression for display.

=============================================================================
DESIGN PHILOSOPHY (2026-01 Refactor)
=============================================================================

Compact Mode is a PURE TRANSFORMATION. It does NOT:
- Detect patterns
- Analyze game flow
- Make structural decisions
- Create or modify moment boundaries

Compact Mode ONLY:
- Takes pre-computed Moments (from moments.py)
- Applies compression rules based on MomentType
- Outputs a display-ready timeline with summary markers

This is a deliberate separation of concerns:
- DETECTION: moments.py (Lead Ladder-based partitioning)
- PRESENTATION: compact_mode.py (compression for display)

Compact Mode "never thinks" - it just compresses what it's told to compress.

=============================================================================
COMPRESSION RULES
=============================================================================

NEVER COLLAPSE (always show all events):
- FLIP: Lead changes are the most important narrative events
- TIE: Game going to even is always dramatic
- CLOSING_CONTROL: Late-game daggers must be shown in full
- HIGH_IMPACT: Ejections, injuries, etc. need full context

LIGHT COMPRESSION (show most events):
- LEAD_BUILD: Important but can trim routine plays
- CUT: Comebacks are exciting, keep most

MODERATE COMPRESSION:
- OPENER: Period starts matter but can be condensed

HEAVY COMPRESSION (collapse to summaries):
- NEUTRAL: Routine play, condense heavily

=============================================================================
SOCIAL POSTS
=============================================================================

Social posts are NEVER dropped or compressed. They provide the reaction
layer and are always preserved in the compressed timeline.

See docs/COMPACT_MODE.md for the canonical specification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

# Import Moment type only - NO detection functions
# Compact Mode receives pre-computed Moments, it does not create them
from .moments import Moment, MomentType

logger = logging.getLogger(__name__)


# =============================================================================
# COMPRESSION LEVELS
# =============================================================================

class CompressionLevel(Enum):
    """
    Display density levels for compact mode.
    
    These control how aggressively events are compressed:
    - HIGHLIGHTS: Maximum compression (~15-20% retention)
    - STANDARD: Balanced compression (~40-50% retention)  
    - DETAILED: Minimal compression (~70-80% retention)
    """
    HIGHLIGHTS = 1
    STANDARD = 2
    DETAILED = 3


# =============================================================================
# COMPRESSION BEHAVIOR BY MOMENT TYPE
# =============================================================================

@dataclass(frozen=True)
class CompressionBehavior:
    """
    Defines how a MomentType should be compressed.
    
    This is a pure data structure - no logic, just rules.
    """
    collapse_allowed: bool  # Can events be collapsed into summaries?
    base_retention: float   # Base fraction of events to keep (0.0-1.0)
    min_events: int         # Minimum events to always show
    description: str        # Human-readable explanation


# COMPRESSION BEHAVIOR MAP
# This is the single source of truth for how each MomentType is compressed.
# Compact Mode consults this map and applies rules - it does not "decide".
COMPRESSION_BEHAVIOR: dict[MomentType, CompressionBehavior] = {
    # === NEVER COLLAPSE ===
    # These moment types are too important to compress at all.
    # Every event is shown regardless of compression level.
    
    MomentType.FLIP: CompressionBehavior(
        collapse_allowed=False,
        base_retention=1.0,
        min_events=999,  # Show all
        description="Lead changes - always show in full",
    ),
    
    MomentType.TIE: CompressionBehavior(
        collapse_allowed=False,
        base_retention=1.0,
        min_events=999,
        description="Game tied - always show in full",
    ),
    
    MomentType.CLOSING_CONTROL: CompressionBehavior(
        collapse_allowed=False,
        base_retention=1.0,
        min_events=999,
        description="Late-game daggers - always show in full",
    ),
    
    MomentType.HIGH_IMPACT: CompressionBehavior(
        collapse_allowed=False,
        base_retention=1.0,
        min_events=999,
        description="High-impact events (ejections, etc.) - always show in full",
    ),
    
    # === LIGHT COMPRESSION ===
    # These types are important but can have routine plays trimmed.
    
    MomentType.LEAD_BUILD: CompressionBehavior(
        collapse_allowed=True,
        base_retention=0.7,
        min_events=3,
        description="Lead extended - show most, trim routine",
    ),
    
    MomentType.CUT: CompressionBehavior(
        collapse_allowed=True,
        base_retention=0.7,
        min_events=3,
        description="Comeback attempt - show most, trim routine",
    ),
    
    # === MODERATE COMPRESSION ===
    
    MomentType.OPENER: CompressionBehavior(
        collapse_allowed=True,
        base_retention=0.5,
        min_events=2,
        description="Period start - condense after opening plays",
    ),
    
    # === HEAVY COMPRESSION ===
    
    MomentType.NEUTRAL: CompressionBehavior(
        collapse_allowed=True,
        base_retention=0.3,
        min_events=1,
        description="Routine play - collapse heavily into summaries",
    ),
}


# =============================================================================
# PLAY TYPE CLASSIFICATION
# =============================================================================

# Play types that are NEVER compressed, regardless of moment type
NEVER_COMPRESS_PLAY_TYPES = frozenset({
    # Scoring plays - always show the points
    "made_shot", "made_three", "made_ft", "dunk", "and_one",
    # Drama - always show the action
    "technical", "ejection", "flagrant",
    # Structural - timeline markers
    "timeout", "end_period", "start_period",
    # Context-critical
    "injury",
})

# Play types that are ALWAYS compressed, regardless of moment type
ALWAYS_COMPRESS_PLAY_TYPES = frozenset({
    "substitution", "sub_in", "sub_out",
    "jump_ball",  # Non-opening jump balls
    "violation", "lane_violation",
})

# Exciting play types that boost retention
EXCITING_PLAY_TYPES = frozenset({
    "dunk", "block", "steal", "made_three", "and_one", "alley_oop",
})


# =============================================================================
# HELPER FUNCTIONS (Pure, no side effects)
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


def _should_never_compress(event: dict[str, Any]) -> bool:
    """
    Check if event should never be compressed.
    
    These events are always preserved regardless of moment type or compression level.
    """
    # Social posts are NEVER compressed
    if event.get("event_type") == "tweet":
        return True

    play_type = event.get("play_type", "")
    if play_type in NEVER_COMPRESS_PLAY_TYPES:
        return True

    # Period boundaries
    if event.get("is_period_start") or event.get("is_period_end"):
        return True

    return False


def _should_always_compress(event: dict[str, Any]) -> bool:
    """
    Check if event should always be compressed.
    
    These events are never shown individually - they become part of summaries.
    """
    # Social posts are NEVER compressed
    if event.get("event_type") == "tweet":
        return False

    play_type = event.get("play_type", "")
    return play_type in ALWAYS_COMPRESS_PLAY_TYPES


def _has_exciting_plays(events: list[dict[str, Any]]) -> bool:
    """Check if event list contains exciting plays (affects retention)."""
    return any(
        e.get("play_type") in EXCITING_PLAY_TYPES
        for e in events
        if e.get("event_type") == "pbp"
    )


def _has_social_density(events: list[dict[str, Any]], threshold: int = 2) -> bool:
    """Check if event list has high social post density."""
    tweet_count = sum(1 for e in events if e.get("event_type") == "tweet")
    return tweet_count >= threshold


# =============================================================================
# EVENT EXTRACTION
# =============================================================================

def _extract_moment_events(
    timeline: Sequence[dict[str, Any]],
    moment: Moment,
) -> list[dict[str, Any]]:
    """
    Extract events from timeline that belong to a moment.
    
    Uses Moment.start_play and Moment.end_play indices.
    This is a pure extraction - no detection or analysis.
    """
    events: list[dict[str, Any]] = []
    in_range = False
    
    for i, event in enumerate(timeline):
        event_type = event.get("event_type")
        
        if event_type == "pbp":
            play_index = event.get("play_index", i)
            
            # Check if we're entering the moment range
            if play_index >= moment.start_play and not in_range:
                in_range = True
            
            # Check if we've exited the moment range
            if play_index > moment.end_play:
                break
            
            if in_range:
                events.append(event)
                
        elif event_type == "tweet" and in_range:
            # Social posts within moment range are always included
            events.append(event)
    
    return events


# =============================================================================
# SUMMARY MARKERS
# =============================================================================

def _create_summary_marker(
    events: list[dict[str, Any]],
    summary_type: str,
    phase: str,
) -> dict[str, Any]:
    """
    Create a summary marker for compressed events.
    
    Summary markers replace groups of compressed events in the output.
    They preserve essential metadata for display.
    """
    pbp_events = [e for e in events if e.get("event_type") == "pbp"]

    # Calculate duration from game clocks
    duration_seconds = 0
    if len(pbp_events) >= 2:
        first_clock = _parse_game_clock(pbp_events[0].get("game_clock"))
        last_clock = _parse_game_clock(pbp_events[-1].get("game_clock"))
        duration_seconds = int(abs(first_clock - last_clock))

    # Description based on summary type
    descriptions = {
        "routine": "Back-and-forth play",
        "neutral": "Routine game action",
        "drought": "Both teams cold from the field",
        "free_throws": "Free throw shooting",
        "subs": "Both teams make substitutions",
        "review": "Play under review",
        "defense": "Defensive struggle",
    }
    description = descriptions.get(summary_type, "Game action")

    # Use timestamp from first event
    timestamp = pbp_events[0].get("synthetic_timestamp") if pbp_events else None

    return {
        "event_type": "summary",
        "phase": phase,
        "summary_type": summary_type,
        "plays_compressed": len(pbp_events),
        "duration_seconds": duration_seconds,
        "description": description,
        "synthetic_timestamp": timestamp,
    }


# =============================================================================
# MOMENT COMPRESSION (Pure transformation)
# =============================================================================

def _compress_moment(
    moment: Moment,
    events: list[dict[str, Any]],
    level: CompressionLevel,
) -> list[dict[str, Any]]:
    """
    Compress events within a Moment based on compression behavior rules.
    
    This is a PURE TRANSFORMATION:
    - Looks up compression behavior by MomentType
    - Applies retention rules
    - Returns compressed event list
    
    It does NOT analyze, detect, or make structural decisions.
    Social posts are NEVER dropped.
    """
    if not events:
        return []
    
    # === LOOK UP COMPRESSION BEHAVIOR ===
    # This is pure lookup - no analysis
    behavior = COMPRESSION_BEHAVIOR.get(
        moment.type,
        # Default: moderate compression if type is unknown
        CompressionBehavior(
            collapse_allowed=True,
            base_retention=0.5,
            min_events=2,
            description="Unknown moment type",
        )
    )
    
    # === NEVER-COLLAPSE MOMENTS ===
    # If collapse is not allowed, return all events unchanged
    if not behavior.collapse_allowed:
        return list(events)
    
    # === CALCULATE EFFECTIVE RETENTION ===
    # Base retention from behavior, adjusted by compression level
    retention = behavior.base_retention
    
    # Adjust by compression level
    if level == CompressionLevel.HIGHLIGHTS:
        retention *= 0.5  # More aggressive
    elif level == CompressionLevel.DETAILED:
        retention = min(retention * 1.5, 1.0)  # Less aggressive
    
    # Boost retention if social density is high
    if _has_social_density(events):
        retention = min(retention + 0.2, 1.0)
    
    # Boost retention if exciting plays present
    if _has_exciting_plays(events):
        retention = min(retention + 0.15, 1.0)
    
    # === APPLY COMPRESSION ===
    result: list[dict[str, Any]] = []
    pending_compression: list[dict[str, Any]] = []
    phase = events[0].get("phase", "unknown") if events else "unknown"
    
    # Calculate keep-every-nth based on retention
    # retention=1.0 → keep_every=1, retention=0.5 → keep_every=2, etc.
    keep_every_nth = max(1, int(1.0 / retention)) if retention > 0 else 10
    routine_count = 0
    
    for event in events:
        # === SOCIAL POSTS: ALWAYS KEEP ===
        if event.get("event_type") == "tweet":
            # Flush pending compression before the tweet
            if pending_compression:
                summary = _create_summary_marker(pending_compression, "neutral", phase)
                result.append(summary)
                pending_compression = []
            result.append(event)
            continue
        
        # === NEVER-COMPRESS EVENTS ===
        if _should_never_compress(event):
            if pending_compression:
                summary = _create_summary_marker(pending_compression, "neutral", phase)
                result.append(summary)
                pending_compression = []
            result.append(event)
            continue
        
        # === ALWAYS-COMPRESS EVENTS ===
        if _should_always_compress(event):
            pending_compression.append(event)
            continue
        
        # === CONDITIONAL COMPRESSION ===
        routine_count += 1
        if routine_count % keep_every_nth == 1:
            # Keep this event
            if pending_compression:
                summary = _create_summary_marker(pending_compression, "neutral", phase)
                result.append(summary)
                pending_compression = []
            result.append(event)
        else:
            # Compress this event
            pending_compression.append(event)
    
    # === FLUSH REMAINING ===
    if pending_compression:
        summary = _create_summary_marker(pending_compression, "neutral", phase)
        result.append(summary)
    
    # === ENSURE MINIMUM EVENTS ===
    # If we compressed too much, we still have the never-compress events
    # This is informational - the min_events is handled by base_retention
    
    return result


# =============================================================================
# PUBLIC API
# =============================================================================

def apply_compact_mode(
    timeline: Sequence[dict[str, Any]],
    moments: Sequence[Moment],
    level: CompressionLevel = CompressionLevel.STANDARD,
) -> list[dict[str, Any]]:
    """
    Apply compact mode compression to a timeline.
    
    PURE TRANSFORMATION: This function receives pre-computed Moments
    and applies compression rules. It does NOT detect or analyze.
    
    Moment boundaries are NEVER altered. Compression happens WITHIN
    moments, not across them.
    
    Args:
        timeline: Full timeline events (PBP + social)
        moments: Pre-computed Moments from partition_game()
        level: Compression level (HIGHLIGHTS, STANDARD, DETAILED)
    
    Returns:
        Compressed timeline with summary markers
        
    Guarantees:
        - Social posts are NEVER dropped
        - Moment boundaries are preserved
        - FLIP/TIE/CLOSING_CONTROL moments are never collapsed
    """
    if not timeline:
        return []
    
    if not moments:
        # No moments provided - caller should always provide moments
        # Return timeline as-is as a fallback
        logger.warning("compact_mode_no_moments: returning uncompressed timeline")
        return list(timeline)
    
    logger.info(
        "compact_mode_start",
        extra={
            "total_events": len(timeline),
            "moment_count": len(moments),
            "compression_level": level.value,
        },
    )
    
    # === COMPRESS EACH MOMENT ===
    # This is a pure map operation over moments
    compressed: list[dict[str, Any]] = []
    
    for moment in moments:
        # Extract events for this moment
        moment_events = _extract_moment_events(timeline, moment)
        
        if not moment_events:
            continue
        
        # Apply compression (pure transformation)
        compressed_events = _compress_moment(moment, moment_events, level)
        compressed.extend(compressed_events)
    
    # === LOG COMPRESSION STATS ===
    original_pbp = sum(1 for e in timeline if e.get("event_type") == "pbp")
    compressed_pbp = sum(1 for e in compressed if e.get("event_type") == "pbp")
    summary_count = sum(1 for e in compressed if e.get("event_type") == "summary")
    
    logger.info(
        "compact_mode_complete",
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


def get_compression_behavior(moment_type: MomentType) -> CompressionBehavior:
    """
    Get the compression behavior for a moment type.
    
    This is exposed for testing and documentation purposes.
    """
    return COMPRESSION_BEHAVIOR.get(
        moment_type,
        CompressionBehavior(
            collapse_allowed=True,
            base_retention=0.5,
            min_events=2,
            description="Unknown moment type",
        )
    )
