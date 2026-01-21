"""
Chapter builder: Create chapters from play-by-play events.

This module contains the core logic for partitioning a game's plays
into chapters.

PHASE 0 IMPLEMENTATION:
This is a minimal, deterministic implementation that creates chapters
based on simple structural boundaries (quarter/period changes).

Future phases will add more sophisticated boundary detection based on
narrative state tracking, but the core contract remains:
- Deterministic (same input → same output)
- Complete coverage (every play in exactly one chapter)
- No AI involvement in chapter creation
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .types import Play, Chapter, ChapterBoundary, GameStory

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


def _detect_boundaries(plays: list[Play]) -> list[ChapterBoundary]:
    """Detect structural boundaries between chapters.
    
    PHASE 0 IMPLEMENTATION:
    Creates boundaries at quarter/period changes only.
    
    This is intentionally simple. Future phases will add:
    - Narrative state tracking
    - Intent change detection
    - Momentum shift detection
    
    But the contract remains: boundaries are deterministic and structural.
    
    Args:
        plays: All plays in chronological order
        
    Returns:
        List of ChapterBoundary objects
    """
    if not plays:
        return []
    
    boundaries = []
    prev_quarter = None
    
    for play in plays:
        quarter = play.raw_data.get("quarter")
        
        # Boundary at quarter/period change
        if prev_quarter is not None and quarter != prev_quarter:
            boundaries.append(ChapterBoundary(
                play_index=play.index,
                reason_codes=["quarter_change"],
            ))
        
        prev_quarter = quarter
    
    logger.info(
        "chapter_boundaries_detected",
        extra={
            "boundary_count": len(boundaries),
            "total_plays": len(plays),
        },
    )
    
    return boundaries


def _create_chapters(
    plays: list[Play],
    boundaries: list[ChapterBoundary],
) -> list[Chapter]:
    """Create chapters from plays and boundaries.
    
    This function ensures:
    - Every play belongs to exactly one chapter
    - Chapters are contiguous (no gaps)
    - Chapters are chronologically ordered
    
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
    current_start = 0
    
    # Sort boundaries by play index
    sorted_boundaries = sorted(boundaries, key=lambda b: b.play_index)
    
    # Collect reason codes for each boundary index
    boundary_reasons: dict[int, list[str]] = {}
    for boundary in sorted_boundaries:
        if boundary.play_index not in boundary_reasons:
            boundary_reasons[boundary.play_index] = []
        boundary_reasons[boundary.play_index].extend(boundary.reason_codes)
    
    # Create chapters between boundaries
    for boundary in sorted_boundaries:
        if boundary.play_index <= current_start:
            continue
        
        # Get plays for this chapter
        chapter_plays = [
            p for p in plays
            if current_start <= p.index < boundary.play_index
        ]
        
        if chapter_plays:
            chapter = Chapter(
                chapter_id=f"ch_{chapter_id:03d}",
                play_start_idx=chapter_plays[0].index,
                play_end_idx=chapter_plays[-1].index,
                plays=chapter_plays,
                reason_codes=boundary_reasons.get(boundary.play_index, []),
            )
            chapters.append(chapter)
            chapter_id += 1
        
        current_start = boundary.play_index
    
    # Create final chapter (from last boundary to end)
    final_plays = [p for p in plays if p.index >= current_start]
    if final_plays:
        chapter = Chapter(
            chapter_id=f"ch_{chapter_id:03d}",
            play_start_idx=final_plays[0].index,
            play_end_idx=final_plays[-1].index,
            plays=final_plays,
            reason_codes=["game_end"],
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
    
    Args:
        timeline: Full timeline events (PBP + social)
        game_id: Database game ID
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
            "play_count": len(plays),
        },
    )
    
    # Step 2: Detect boundaries
    boundaries = _detect_boundaries(plays)
    
    # Step 3: Create chapters
    chapters = _create_chapters(plays, boundaries)
    
    # Step 4: Create GameStory
    story = GameStory(
        game_id=game_id,
        chapters=chapters,
        metadata=metadata or {},
    )
    
    logger.info(
        "chapter_building_complete",
        extra={
            "game_id": game_id,
            "chapter_count": story.chapter_count,
            "total_plays": story.total_plays,
        },
    )
    
    return story
