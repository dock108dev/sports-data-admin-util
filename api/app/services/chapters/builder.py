"""
Chapter builder: Create chapters from play-by-play events.

This module contains the core logic for partitioning a game's plays
into chapters.

ISSUE 0.3: NBA v1 Boundary Rules
This implementation uses the authoritative NBA v1 boundary rules defined
in boundary_rules.py. Boundaries are determined by:
- Hard boundaries (period start/end, OT, game end)
- Scene reset boundaries (timeouts, reviews)
- Momentum boundaries (runs, crunch time) - minimal in v1

The core contract remains:
- Deterministic (same input → same output)
- Complete coverage (every play in exactly one chapter)
- No AI involvement in chapter creation
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .types import Play, Chapter, ChapterBoundary, GameStory, TimeRange
from .boundary_rules import (
    NBABoundaryRules,
    BoundaryReasonCode,
    resolve_boundary_precedence,
    is_non_boundary_event,
)

logger = logging.getLogger(__name__)


def _extract_plays(timeline: Sequence[dict[str, Any]]) -> list[Play]:
    """Extract canonical plays from timeline.
    
    For Phase 0, we only extract PBP events. Future phases may include
    other event types.
    
    Args:
        timeline: Full timeline events (PBP + social)
        
    Returns:
        List of Play objects in chronological order
    """
    plays = []
    for i, event in enumerate(timeline):
        if event.get("event_type") == "pbp":
            plays.append(Play(
                index=i,
                event_type="pbp",
                raw_data=event,
            ))
    
    return plays


def _detect_boundaries(plays: list[Play], sport: str = "NBA") -> list[ChapterBoundary]:
    """Detect structural boundaries between chapters.
    
    ISSUE 0.3: NBA v1 Boundary Rules
    Uses authoritative boundary rules from boundary_rules.py:
    - Hard boundaries (period start/end, OT, game end)
    - Scene reset boundaries (timeouts, reviews)
    - Momentum boundaries (runs, crunch time) - minimal in v1
    
    Boundaries are deterministic and structural. No AI, no ladder logic.
    
    Args:
        plays: All plays in chronological order
        sport: Sport identifier (currently only NBA supported)
        
    Returns:
        List of ChapterBoundary objects with reason codes
    """
    if not plays:
        return []
    
    if sport != "NBA":
        # Fallback to simple quarter boundaries for non-NBA
        return _detect_boundaries_simple(plays)
    
    boundaries = []
    rules = NBABoundaryRules()
    context: dict[str, Any] = {}  # Game context for conditional rules
    
    for i, play in enumerate(plays):
        event = play.raw_data
        prev_event = plays[i - 1].raw_data if i > 0 else None
        next_event = plays[i + 1].raw_data if i < len(plays) - 1 else None
        
        # Skip explicit non-boundaries
        if is_non_boundary_event(event):
            continue
        
        # Collect triggered reason codes
        triggered_codes: list[BoundaryReasonCode] = []
        
        # 1. Hard boundaries (highest precedence)
        if rules.is_period_start(event, prev_event):
            triggered_codes.append(BoundaryReasonCode.PERIOD_START)
        
        if rules.is_overtime_start(event, prev_event):
            triggered_codes.append(BoundaryReasonCode.OVERTIME_START)
        
        # Note: PERIOD_END handled by next event's PERIOD_START
        # Note: GAME_END handled separately for final chapter
        
        # 2. Scene reset boundaries (medium precedence)
        if rules.is_timeout(event):
            triggered_codes.append(BoundaryReasonCode.TIMEOUT)
        
        if rules.is_review(event):
            triggered_codes.append(BoundaryReasonCode.REVIEW)
        
        # 3. Momentum boundaries (low precedence, minimal v1)
        if rules.is_crunch_start(event, prev_event, context):
            triggered_codes.append(BoundaryReasonCode.CRUNCH_START)
        
        if rules.is_run_start(event, context):
            triggered_codes.append(BoundaryReasonCode.RUN_START)
        
        if rules.is_run_end_response(event, context):
            triggered_codes.append(BoundaryReasonCode.RUN_END_RESPONSE)
        
        # Resolve precedence and create boundary
        if triggered_codes:
            resolved_codes = resolve_boundary_precedence(triggered_codes)
            if resolved_codes:
                boundaries.append(ChapterBoundary(
                    play_index=play.index,
                    reason_codes=[code.value for code in resolved_codes],
                ))
    
    logger.info(
        "chapter_boundaries_detected",
        extra={
            "sport": sport,
            "boundary_count": len(boundaries),
            "total_plays": len(plays),
            "reason_code_distribution": _count_reason_codes(boundaries),
        },
    )
    
    return boundaries


def _detect_boundaries_simple(plays: list[Play]) -> list[ChapterBoundary]:
    """Fallback boundary detection for non-NBA sports.
    
    Simple quarter/period change detection.
    
    Args:
        plays: All plays in chronological order
        
    Returns:
        List of ChapterBoundary objects
    """
    boundaries = []
    prev_quarter = None
    
    for play in plays:
        quarter = play.raw_data.get("quarter")
        
        if prev_quarter is not None and quarter != prev_quarter:
            boundaries.append(ChapterBoundary(
                play_index=play.index,
                reason_codes=["PERIOD_START"],
            ))
        
        prev_quarter = quarter
    
    return boundaries


def _count_reason_codes(boundaries: list[ChapterBoundary]) -> dict[str, int]:
    """Count reason code distribution for logging.
    
    Args:
        boundaries: List of boundaries
        
    Returns:
        Dict of reason code -> count
    """
    counts: dict[str, int] = {}
    for boundary in boundaries:
        for code in boundary.reason_codes:
            counts[code] = counts.get(code, 0) + 1
    return counts


def _extract_period_and_time(plays: list[Play]) -> tuple[int | None, TimeRange | None]:
    """Extract period and time range from plays.
    
    Issue 0.2: Populate period and time_range fields.
    
    Args:
        plays: List of plays in the chapter
        
    Returns:
        Tuple of (period, time_range)
    """
    if not plays:
        return None, None
    
    # Extract period from first play
    period = plays[0].raw_data.get("quarter")
    
    # Extract time range if available
    start_clock = plays[0].raw_data.get("game_clock")
    end_clock = plays[-1].raw_data.get("game_clock")
    
    time_range = None
    if start_clock is not None or end_clock is not None:
        time_range = TimeRange(start=start_clock, end=end_clock)
    
    return period, time_range


def _create_chapters(
    plays: list[Play],
    boundaries: list[ChapterBoundary],
) -> list[Chapter]:
    """Create chapters from plays and boundaries.
    
    This function ensures:
    - Every play belongs to exactly one chapter
    - Chapters are contiguous (no gaps)
    - Chapters are chronologically ordered
    
    Issue 0.2: Populates all required fields including period and time_range.
    Issue 0.3: Uses NBA v1 boundary rules with reason codes.
    
    Args:
        plays: All plays in chronological order
        boundaries: Structural boundaries
        
    Returns:
        List of Chapter objects
    """
    if not plays:
        return []
    
    chapters = []
    chapter_id = 1
    current_start_idx = 0
    
    # Sort boundaries by play index
    sorted_boundaries = sorted(boundaries, key=lambda b: b.play_index)
    
    # Collect reason codes for each boundary index
    boundary_reasons: dict[int, list[str]] = {}
    for boundary in sorted_boundaries:
        if boundary.play_index not in boundary_reasons:
            boundary_reasons[boundary.play_index] = []
        boundary_reasons[boundary.play_index].extend(boundary.reason_codes)
    
    # If no boundaries, create one chapter with all plays
    if not sorted_boundaries:
        period, time_range = _extract_period_and_time(plays)
        chapter = Chapter(
            chapter_id=f"ch_{chapter_id:03d}",
            play_start_idx=plays[0].index,
            play_end_idx=plays[-1].index,
            plays=plays,
            reason_codes=["PERIOD_START"],  # First chapter always starts period
            period=period,
            time_range=time_range,
        )
        chapters.append(chapter)
        return chapters
    
    # Create chapters between boundaries
    for boundary in sorted_boundaries:
        # Skip if this boundary is at or before current start
        if boundary.play_index <= current_start_idx:
            continue
        
        # Get plays for this chapter (from current_start to boundary)
        chapter_plays = [
            p for p in plays
            if current_start_idx <= p.index < boundary.play_index
        ]
        
        if chapter_plays:
            # Extract period and time range
            period, time_range = _extract_period_and_time(chapter_plays)
            
            # Determine reason codes for this chapter
            # First chapter gets PERIOD_START if no explicit reason
            if chapter_id == 1 and current_start_idx == 0:
                reason_codes = ["PERIOD_START"]
            else:
                # Use reason codes from the boundary that STARTED this chapter
                reason_codes = boundary_reasons.get(current_start_idx, ["PERIOD_START"])
            
            chapter = Chapter(
                chapter_id=f"ch_{chapter_id:03d}",
                play_start_idx=chapter_plays[0].index,
                play_end_idx=chapter_plays[-1].index,
                plays=chapter_plays,
                reason_codes=reason_codes,
                period=period,
                time_range=time_range,
            )
            chapters.append(chapter)
            chapter_id += 1
        
        current_start_idx = boundary.play_index
    
    # Create final chapter (from last boundary to end)
    final_plays = [p for p in plays if p.index >= current_start_idx]
    if final_plays:
        # Extract period and time range
        period, time_range = _extract_period_and_time(final_plays)
        
        # Use reason codes from the boundary that started this chapter
        reason_codes = boundary_reasons.get(current_start_idx, ["game_end"])
        
        chapter = Chapter(
            chapter_id=f"ch_{chapter_id:03d}",
            play_start_idx=final_plays[0].index,
            play_end_idx=final_plays[-1].index,
            plays=final_plays,
            reason_codes=reason_codes,
            period=period,
            time_range=time_range,
        )
        chapters.append(chapter)
    
    logger.info(
        "chapters_created",
        extra={
            "chapter_count": len(chapters),
            "total_plays": len(plays),
        },
    )
    
    return chapters


def build_chapters(
    timeline: Sequence[dict[str, Any]],
    game_id: int,
    sport: str = "NBA",
    metadata: dict[str, Any] | None = None,
) -> GameStory:
    """Build a GameStory from a play-by-play timeline.
    
    This is the main entry point for chapter creation. It:
    1. Extracts plays from timeline
    2. Detects structural boundaries
    3. Creates chapters from boundaries
    4. Validates structural integrity
    5. Returns a GameStory
    
    GUARANTEES:
    - Deterministic (same input → same output)
    - Complete coverage (every play in exactly one chapter)
    - No AI involvement
    - No "moment" objects produced
    
    Issue 0.2: Populates all required GameStory fields including sport.
    
    Args:
        timeline: Full timeline events (PBP + social)
        game_id: Database game ID
        sport: Sport identifier (e.g., "NBA", "NHL")
        metadata: Optional game metadata (teams, score, etc.)
        
    Returns:
        GameStory with chapters
        
    Raises:
        ValueError: If structural validation fails
    """
    if not timeline:
        raise ValueError("Cannot build chapters from empty timeline")
    
    # Step 1: Extract plays
    plays = _extract_plays(timeline)
    
    if not plays:
        raise ValueError("No canonical plays found in timeline")
    
    logger.info(
        "chapter_building_started",
        extra={
            "game_id": game_id,
            "sport": sport,
            "play_count": len(plays),
        },
    )
    
    # Step 2: Detect boundaries (Issue 0.3: NBA v1 rules)
    boundaries = _detect_boundaries(plays, sport)
    
    # Step 3: Create chapters
    chapters = _create_chapters(plays, boundaries)
    
    # Step 4: Create GameStory (Issue 0.2: all required fields)
    story = GameStory(
        game_id=game_id,
        sport=sport,
        chapters=chapters,
        compact_story=None,  # Explicitly null at this phase
        reading_time_estimate_minutes=None,  # Can be computed later
        metadata=metadata or {},
    )
    
    logger.info(
        "chapter_building_complete",
        extra={
            "game_id": game_id,
            "sport": sport,
            "chapter_count": story.chapter_count,
            "total_plays": story.total_plays,
        },
    )
    
    return story
