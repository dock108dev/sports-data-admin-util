"""
ChapterizerV1: Deterministic PBP → Chapters converter for NBA v1.

This module implements the core chapterization logic that converts normalized
play-by-play data into Chapter objects following NBA v1 boundary rules.

PHASE 1 ISSUE 5: Implement ChapterizerV1

CONTRACT:
- Deterministic (same input → same output)
- Explainable (reason codes + logs)
- No AI, no ladder logic, no moments
- Schema-valid GameStory output
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from .types import Play, Chapter, GameStory, ChapterBoundary, TimeRange
from .boundary_rules import (
    NBABoundaryRules,
    BoundaryReasonCode,
    resolve_boundary_precedence,
    is_non_boundary_event,
)

logger = logging.getLogger(__name__)


@dataclass
class ChapterizerConfig:
    """Configuration for NBA v1 chapterization.
    
    These values control boundary detection and chapter creation.
    All values are deterministic and testable.
    """
    
    # Crunch time detection
    crunch_time_seconds: int = 300  # Last 5 minutes (300 seconds)
    close_game_margin: int = 5      # Within 5 points
    
    # Run detection (minimal v1)
    run_min_points: int = 6         # 6+ unanswered points
    run_min_plays: int = 3          # Across 3+ scoring plays
    
    # Chapter size constraints
    min_plays_per_chapter: int = 1  # Minimum plays (allow single-play chapters for now)
    max_chapters_soft_cap: int = 20 # Diagnostic warning only
    
    # Reset cluster handling
    collapse_reset_clusters: bool = True  # Merge consecutive timeouts/reviews
    reset_cluster_window_plays: int = 3   # Max plays between resets to collapse


class ChapterizerV1:
    """Deterministic chapterizer for NBA v1.
    
    Converts normalized play-by-play into chapters following NBA v1 rules.
    
    PHILOSOPHY:
    - Chapters are scenes, not possessions
    - Boundaries are rare (4-8 per game typical)
    - Deterministic and explainable
    """
    
    def __init__(self, config: ChapterizerConfig | None = None):
        """Initialize chapterizer.
        
        Args:
            config: Configuration (uses defaults if None)
        """
        self.config = config or ChapterizerConfig()
        self.rules = NBABoundaryRules()
    
    def chapterize(
        self,
        timeline: Sequence[dict[str, Any]],
        game_id: int,
        sport: str = "NBA",
        metadata: dict[str, Any] | None = None
    ) -> GameStory:
        """Convert play-by-play timeline into chapters.
        
        This is the main entry point for chapterization.
        
        Args:
            timeline: Sequence of PBP events
            game_id: Game identifier
            sport: Sport (must be "NBA" for v1)
            metadata: Game metadata
            
        Returns:
            GameStory with chapters
            
        Raises:
            ValueError: If sport is not NBA or timeline is invalid
        """
        if sport != "NBA":
            raise ValueError(f"ChapterizerV1 only supports NBA, got {sport}")
        
        if not timeline:
            raise ValueError("Timeline cannot be empty")
        
        logger.info(
            "chapterizer_start",
            extra={
                "game_id": game_id,
                "sport": sport,
                "timeline_length": len(timeline),
            }
        )
        
        # Step 1: Extract plays
        plays = self._extract_plays(timeline)
        logger.info(f"Extracted {len(plays)} plays from timeline")
        
        # Step 2: Detect boundaries
        boundaries = self._detect_boundaries(plays)
        logger.info(f"Detected {len(boundaries)} boundaries")
        
        # Step 3: Create chapters
        chapters = self._create_chapters(plays, boundaries)
        logger.info(f"Created {len(chapters)} chapters")
        
        # Step 4: Validate and build GameStory
        self._validate_chapters(chapters, plays)
        
        story = GameStory(
            game_id=game_id,
            sport=sport,
            chapters=chapters,
            compact_story=None,
            reading_time_estimate_minutes=None,
            metadata=metadata or {},
        )
        
        # Diagnostic: check soft cap
        if len(chapters) > self.config.max_chapters_soft_cap:
            logger.warning(
                f"Chapter count ({len(chapters)}) exceeds soft cap "
                f"({self.config.max_chapters_soft_cap}). May indicate over-segmentation."
            )
        
        logger.info(
            "chapterizer_complete",
            extra={
                "game_id": game_id,
                "chapter_count": len(chapters),
                "play_count": len(plays),
                "avg_plays_per_chapter": len(plays) / len(chapters) if chapters else 0,
            }
        )
        
        return story
    
    def _extract_plays(self, timeline: Sequence[dict[str, Any]]) -> list[Play]:
        """Extract Play objects from timeline.
        
        Args:
            timeline: Raw timeline events
            
        Returns:
            List of Play objects
        """
        plays = []
        
        for idx, event in enumerate(timeline):
            # Only process PBP events
            if event.get("event_type") != "pbp":
                continue
            
            play = Play(
                index=idx,
                event_type="pbp",
                raw_data=event,
            )
            plays.append(play)
        
        return plays
    
    def _detect_boundaries(self, plays: list[Play]) -> list[ChapterBoundary]:
        """Detect chapter boundaries using NBA v1 rules.
        
        Args:
            plays: All plays in chronological order
            
        Returns:
            List of ChapterBoundary objects
        """
        if not plays:
            return []
        
        boundaries = []
        reset_cluster_start: int | None = None  # Track reset clusters
        
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
            if self.rules.is_period_start(event, prev_event):
                triggered_codes.append(BoundaryReasonCode.PERIOD_START)
                logger.debug(
                    f"Boundary at play {i}: PERIOD_START (quarter {event.get('quarter')})"
                )
            
            if self.rules.is_overtime_start(event, prev_event):
                triggered_codes.append(BoundaryReasonCode.OVERTIME_START)
                logger.debug(f"Boundary at play {i}: OVERTIME_START")
            
            # 2. Scene reset boundaries (medium precedence)
            is_timeout = self.rules.is_timeout(event)
            is_review = self.rules.is_review(event)
            
            if is_timeout or is_review:
                # Check for reset cluster
                if self.config.collapse_reset_clusters:
                    if reset_cluster_start is None:
                        # Start new cluster
                        reset_cluster_start = i
                        if is_timeout:
                            triggered_codes.append(BoundaryReasonCode.TIMEOUT)
                        if is_review:
                            triggered_codes.append(BoundaryReasonCode.REVIEW)
                    else:
                        # Check if within cluster window
                        if i - reset_cluster_start <= self.config.reset_cluster_window_plays:
                            # Add to existing cluster (don't create new boundary)
                            logger.debug(
                                f"Play {i}: Reset event collapsed into cluster at {reset_cluster_start}"
                            )
                            continue
                        else:
                            # Outside window, start new cluster
                            reset_cluster_start = i
                            if is_timeout:
                                triggered_codes.append(BoundaryReasonCode.TIMEOUT)
                            if is_review:
                                triggered_codes.append(BoundaryReasonCode.REVIEW)
                else:
                    # No clustering, create boundary
                    if is_timeout:
                        triggered_codes.append(BoundaryReasonCode.TIMEOUT)
                    if is_review:
                        triggered_codes.append(BoundaryReasonCode.REVIEW)
                
                if triggered_codes:
                    logger.debug(
                        f"Boundary at play {i}: {', '.join(c.value for c in triggered_codes)}"
                    )
            else:
                # Not a reset event, clear cluster
                reset_cluster_start = None
            
            # 3. Momentum boundaries (low precedence, minimal v1)
            context = {}  # Placeholder for future run tracking
            
            if self.rules.is_crunch_start(event, prev_event, context):
                triggered_codes.append(BoundaryReasonCode.CRUNCH_START)
                logger.debug(
                    f"Boundary at play {i}: CRUNCH_START "
                    f"(Q{event.get('quarter')}, clock {event.get('game_clock')})"
                )
            
            # Note: RUN_START and RUN_END_RESPONSE are stubbed in v1
            # They return False, so no boundaries created
            
            # Resolve precedence and create boundary
            if triggered_codes:
                resolved_codes = resolve_boundary_precedence(triggered_codes)
                if resolved_codes:
                    boundaries.append(ChapterBoundary(
                        play_index=play.index,
                        reason_codes=[code.value for code in resolved_codes],
                    ))
        
        logger.info(
            "boundaries_detected",
            extra={
                "boundary_count": len(boundaries),
                "total_plays": len(plays),
                "reason_code_distribution": self._count_reason_codes(boundaries),
            }
        )
        
        return boundaries
    
    def _create_chapters(
        self,
        plays: list[Play],
        boundaries: list[ChapterBoundary],
    ) -> list[Chapter]:
        """Create chapters from plays and boundaries.
        
        Args:
            plays: All plays in chronological order
            boundaries: Detected boundaries
            
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
            period, time_range = self._extract_period_and_time(plays)
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
            logger.info(f"Created single chapter (no boundaries): {chapter.chapter_id}")
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
                period, time_range = self._extract_period_and_time(chapter_plays)
                
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
                
                logger.debug(
                    f"Created chapter {chapter.chapter_id}: "
                    f"plays {chapter.play_start_idx}-{chapter.play_end_idx} "
                    f"({len(chapter_plays)} plays), "
                    f"reasons: {', '.join(reason_codes)}"
                )
                
                chapter_id += 1
            
            current_start_idx = boundary.play_index
        
        # Create final chapter (from last boundary to end)
        final_plays = [p for p in plays if p.index >= current_start_idx]
        if final_plays:
            # Extract period and time range
            period, time_range = self._extract_period_and_time(final_plays)
            
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
            
            logger.debug(
                f"Created final chapter {chapter.chapter_id}: "
                f"plays {chapter.play_start_idx}-{chapter.play_end_idx} "
                f"({len(final_plays)} plays), "
                f"reasons: {', '.join(reason_codes)}"
            )
        
        logger.info(
            "chapters_created",
            extra={
                "chapter_count": len(chapters),
                "total_plays": len(plays),
                "play_coverage": f"{plays[0].index}-{plays[-1].index}",
            }
        )
        
        return chapters
    
    def _extract_period_and_time(self, plays: list[Play]) -> tuple[int | None, TimeRange | None]:
        """Extract period and time range from plays.
        
        Args:
            plays: List of plays
            
        Returns:
            Tuple of (period, time_range)
        """
        if not plays:
            return None, None
        
        period = plays[0].raw_data.get("quarter")
        start_clock = plays[0].raw_data.get("game_clock")
        end_clock = plays[-1].raw_data.get("game_clock")
        
        time_range = TimeRange(start=start_clock, end=end_clock) if start_clock or end_clock else None
        
        return period, time_range
    
    def _validate_chapters(self, chapters: list[Chapter], plays: list[Play]) -> None:
        """Validate chapters for coverage and contiguity.
        
        Args:
            chapters: Created chapters
            plays: All plays
            
        Raises:
            ValueError: If validation fails
        """
        if not chapters:
            raise ValueError("No chapters created")
        
        # Check coverage: all plays must be in exactly one chapter
        covered_indices = set()
        for chapter in chapters:
            for play in chapter.plays:
                if play.index in covered_indices:
                    raise ValueError(f"Play {play.index} appears in multiple chapters")
                covered_indices.add(play.index)
        
        play_indices = {p.index for p in plays}
        if covered_indices != play_indices:
            missing = play_indices - covered_indices
            extra = covered_indices - play_indices
            raise ValueError(
                f"Coverage mismatch: missing {missing}, extra {extra}"
            )
        
        # Check contiguity: chapters must be ordered and non-overlapping
        for i in range(len(chapters) - 1):
            curr = chapters[i]
            next_ch = chapters[i + 1]
            
            if curr.play_end_idx >= next_ch.play_start_idx:
                raise ValueError(
                    f"Chapters {curr.chapter_id} and {next_ch.chapter_id} overlap"
                )
        
        logger.debug("Chapter validation passed: full coverage and contiguity")
    
    def _count_reason_codes(self, boundaries: list[ChapterBoundary]) -> dict[str, int]:
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
