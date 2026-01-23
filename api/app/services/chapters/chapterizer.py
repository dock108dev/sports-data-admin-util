"""
Chapterizer: Deterministic PBP → Chapters converter for NBA.

This module implements the core chapterization logic that converts normalized
play-by-play data into Chapter objects following NBA boundary rules.

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
    """Configuration for NBA chapterization.

    These values control boundary detection and chapter creation.
    All values are deterministic and testable.
    """

    # Crunch time detection
    crunch_time_seconds: int = 300  # Last 5 minutes (300 seconds)
    close_game_margin: int = 5      # Within 5 points

    # Chapter size constraints
    min_plays_per_chapter: int = 1  # Minimum plays (allow single-play chapters for now)
    max_chapters_soft_cap: int = 20 # Diagnostic warning only

    # Reset cluster handling
    collapse_reset_clusters: bool = True  # Merge consecutive timeouts/reviews
    reset_cluster_window_plays: int = 3   # Max plays between resets to collapse


class Chapterizer:
    """Deterministic chapterizer for NBA.

    Converts normalized play-by-play into chapters following NBA rules.

    PHILOSOPHY:
    - Chapters are scenes, not possessions
    - Boundaries are rare (4-8 per game typical)
    - Deterministic and explainable
    """
    
    def __init__(self, config: ChapterizerConfig | None = None, debug: bool = False):
        """Initialize chapterizer.
        
        Args:
            config: Configuration (uses defaults if None)
            debug: Enable debug logging (Issue 7)
        """
        self.config = config or ChapterizerConfig()
        self.rules = NBABoundaryRules()
        
        # Issue 7: Debug logger for breakpoint tracing
        from .debug_logger import ChapterDebugLogger
        self.debug_logger = ChapterDebugLogger(enabled=debug)
    
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
            raise ValueError(f"Chapterizer only supports NBA, got {sport}")
        
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
        
        # Step 4: Build GameStory
        story = GameStory(
            game_id=game_id,
            sport=sport,
            chapters=chapters,
            compact_story=None,
            reading_time_estimate_minutes=None,
            metadata=metadata or {},
        )
        
        # Step 5: Validate coverage (Issue 6)
        from .coverage_validator import validate_game_story_coverage
        
        validation_result = validate_game_story_coverage(story, fail_fast=True)
        
        # Store fingerprint in metadata
        story.metadata["chapters_fingerprint"] = validation_result.chapters_fingerprint
        
        logger.info(
            "coverage_validation",
            extra={
                "passed": validation_result.passed,
                "fingerprint": validation_result.chapters_fingerprint,
                "play_count": validation_result.play_count,
                "chapter_count": validation_result.chapter_count,
            }
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

            # Skip explicit non-boundaries
            if is_non_boundary_event(event):
                self.debug_logger.log_boundary_ignored(
                    play_idx=i,
                    event_type_name=event.get("event_type", "unknown"),
                    rule_name="non_boundary_filter",
                    ignore_reason="explicit_non_boundary"
                )
                continue
            
            # Collect triggered reason codes
            triggered_codes: list[BoundaryReasonCode] = []
            
            # 1. Hard boundaries (highest precedence)
            if self.rules.is_period_start(event, prev_event):
                triggered_codes.append(BoundaryReasonCode.PERIOD_START)
                logger.debug(
                    f"Boundary at play {i}: PERIOD_START (quarter {event.get('quarter')})"
                )
                from .boundary_rules import BOUNDARY_PRECEDENCE
                from .debug_logger import BoundaryAction
                self.debug_logger.log_boundary_triggered(
                    play_idx=i,
                    event_type_name="period_start",
                    reason_codes=[BoundaryReasonCode.PERIOD_START.value],
                    rule_name="is_period_start",
                    rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.PERIOD_START, 0),
                    boundary_action=BoundaryAction.START_NEW
                )
            
            if self.rules.is_overtime_start(event, prev_event):
                triggered_codes.append(BoundaryReasonCode.OVERTIME_START)
                logger.debug(f"Boundary at play {i}: OVERTIME_START")
                from .boundary_rules import BOUNDARY_PRECEDENCE
                from .debug_logger import BoundaryAction
                self.debug_logger.log_boundary_triggered(
                    play_idx=i,
                    event_type_name="overtime_start",
                    reason_codes=[BoundaryReasonCode.OVERTIME_START.value],
                    rule_name="is_overtime_start",
                    rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.OVERTIME_START, 0),
                    boundary_action=BoundaryAction.START_NEW
                )
            
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
                            from .boundary_rules import BOUNDARY_PRECEDENCE
                            from .debug_logger import BoundaryAction
                            self.debug_logger.log_boundary_triggered(
                                play_idx=i,
                                event_type_name="timeout",
                                reason_codes=[BoundaryReasonCode.TIMEOUT.value],
                                rule_name="is_timeout",
                                rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.TIMEOUT, 0),
                                boundary_action=BoundaryAction.START_NEW
                            )
                        if is_review:
                            triggered_codes.append(BoundaryReasonCode.REVIEW)
                            from .boundary_rules import BOUNDARY_PRECEDENCE
                            from .debug_logger import BoundaryAction
                            self.debug_logger.log_boundary_triggered(
                                play_idx=i,
                                event_type_name="review",
                                reason_codes=[BoundaryReasonCode.REVIEW.value],
                                rule_name="is_review",
                                rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.REVIEW, 0),
                                boundary_action=BoundaryAction.START_NEW
                            )
                    else:
                        # Check if within cluster window
                        if i - reset_cluster_start <= self.config.reset_cluster_window_plays:
                            # Add to existing cluster (don't create new boundary)
                            logger.debug(
                                f"Play {i}: Reset event collapsed into cluster at {reset_cluster_start}"
                            )
                            self.debug_logger.log_boundary_ignored(
                                play_idx=i,
                                event_type_name="timeout" if is_timeout else "review",
                                rule_name="reset_cluster_collapse",
                                ignore_reason=f"collapsed_into_cluster_at_{reset_cluster_start}"
                            )
                            continue
                        else:
                            # Outside window, start new cluster
                            reset_cluster_start = i
                            if is_timeout:
                                triggered_codes.append(BoundaryReasonCode.TIMEOUT)
                                from .boundary_rules import BOUNDARY_PRECEDENCE
                                from .debug_logger import BoundaryAction
                                self.debug_logger.log_boundary_triggered(
                                    play_idx=i,
                                    event_type_name="timeout",
                                    reason_codes=[BoundaryReasonCode.TIMEOUT.value],
                                    rule_name="is_timeout",
                                    rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.TIMEOUT, 0),
                                    boundary_action=BoundaryAction.START_NEW
                                )
                            if is_review:
                                triggered_codes.append(BoundaryReasonCode.REVIEW)
                                from .boundary_rules import BOUNDARY_PRECEDENCE
                                from .debug_logger import BoundaryAction
                                self.debug_logger.log_boundary_triggered(
                                    play_idx=i,
                                    event_type_name="review",
                                    reason_codes=[BoundaryReasonCode.REVIEW.value],
                                    rule_name="is_review",
                                    rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.REVIEW, 0),
                                    boundary_action=BoundaryAction.START_NEW
                                )
                else:
                    # No clustering, create boundary
                    if is_timeout:
                        triggered_codes.append(BoundaryReasonCode.TIMEOUT)
                        from .boundary_rules import BOUNDARY_PRECEDENCE
                        from .debug_logger import BoundaryAction
                        self.debug_logger.log_boundary_triggered(
                            play_idx=i,
                            event_type_name="timeout",
                            reason_codes=[BoundaryReasonCode.TIMEOUT.value],
                            rule_name="is_timeout",
                            rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.TIMEOUT, 0),
                            boundary_action=BoundaryAction.START_NEW
                        )
                    if is_review:
                        triggered_codes.append(BoundaryReasonCode.REVIEW)
                        from .boundary_rules import BOUNDARY_PRECEDENCE
                        from .debug_logger import BoundaryAction
                        self.debug_logger.log_boundary_triggered(
                            play_idx=i,
                            event_type_name="review",
                            reason_codes=[BoundaryReasonCode.REVIEW.value],
                            rule_name="is_review",
                            rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.REVIEW, 0),
                            boundary_action=BoundaryAction.START_NEW
                        )
                
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
                from .boundary_rules import BOUNDARY_PRECEDENCE
                from .debug_logger import BoundaryAction
                self.debug_logger.log_boundary_triggered(
                    play_idx=i,
                    event_type_name="crunch_start",
                    reason_codes=[BoundaryReasonCode.CRUNCH_START.value],
                    rule_name="is_crunch_start",
                    rule_precedence=BOUNDARY_PRECEDENCE.get(BoundaryReasonCode.CRUNCH_START, 0),
                    boundary_action=BoundaryAction.START_NEW
                )

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
                
                # Issue 7: Log chapter start/end
                self.debug_logger.log_chapter_start(
                    chapter_id=chapter.chapter_id,
                    start_play_idx=chapter.play_start_idx,
                    trigger_event_type=chapter_plays[0].raw_data.get("event_type"),
                    reason_codes=reason_codes,
                    period=period,
                    clock_time=time_range.start if time_range else None
                )
                
                self.debug_logger.log_chapter_end(
                    chapter_id=chapter.chapter_id,
                    end_play_idx=chapter.play_end_idx,
                    trigger_event_type=chapter_plays[-1].raw_data.get("event_type"),
                    reason_codes=reason_codes,
                    period=period,
                    clock_time=time_range.end if time_range else None,
                    chapter_play_count=len(chapter_plays)
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
            
            # Issue 7: Log chapter start/end
            self.debug_logger.log_chapter_start(
                chapter_id=chapter.chapter_id,
                start_play_idx=chapter.play_start_idx,
                trigger_event_type=final_plays[0].raw_data.get("event_type"),
                reason_codes=reason_codes,
                period=period,
                clock_time=time_range.start if time_range else None
            )
            
            self.debug_logger.log_chapter_end(
                chapter_id=chapter.chapter_id,
                end_play_idx=chapter.play_end_idx,
                trigger_event_type=final_plays[-1].raw_data.get("event_type"),
                reason_codes=reason_codes,
                period=period,
                clock_time=time_range.end if time_range else None,
                chapter_play_count=len(final_plays)
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
