"""
Chapter Debug Logger: Structured logging for chapter breakpoint tracing.

This module provides first-class, structured debug logging so that every
chapter breakpoint is explainable and traceable.

PHASE 1 ISSUE 7: Add Chapter Debug Logging and Breakpoint Reason Tracing

GUARANTEES:
- Every chapter boundary is explainable via logs
- Reason codes are fully traceable end-to-end
- Logs are deterministic and queryable
- No silent chapter breaks
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any
from enum import Enum

logger = logging.getLogger(__name__)


class ChapterLogEventType(str, Enum):
    """Types of chapter debug log events."""

    CHAPTER_START = "CHAPTER_START"
    CHAPTER_END = "CHAPTER_END"
    CHAPTER_BOUNDARY_TRIGGERED = "CHAPTER_BOUNDARY_TRIGGERED"
    CHAPTER_BOUNDARY_IGNORED = "CHAPTER_BOUNDARY_IGNORED"
    CHAPTER_RESET_CLUSTER = "CHAPTER_RESET_CLUSTER"


class BoundaryAction(str, Enum):
    """Action taken for a boundary trigger."""

    START_NEW = "start_new"  # Start new chapter
    IGNORED = "ignored"  # Boundary ignored
    COLLAPSED = "collapsed"  # Collapsed into cluster


@dataclass
class ChapterLogEvent:
    """Base class for chapter debug log events.

    All events are structured and serializable for queryability.
    """

    event_type: ChapterLogEventType
    event_id: int  # Sequential ID for tracing

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


@dataclass
class ChapterStartEvent(ChapterLogEvent):
    """Log event for chapter start.

    Fields:
        chapter_id: Chapter identifier
        start_play_idx: Starting play index
        trigger_event_type: Type of event that triggered start (if applicable)
        reason_codes: Reason codes for this chapter
        period: Period/quarter number
        clock_time: Game clock time
    """

    chapter_id: str
    start_play_idx: int
    trigger_event_type: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    period: int | None = None
    clock_time: str | None = None

    def __post_init__(self):
        if not isinstance(self.event_type, ChapterLogEventType):
            self.event_type = ChapterLogEventType.CHAPTER_START


@dataclass
class ChapterEndEvent(ChapterLogEvent):
    """Log event for chapter end.

    Fields:
        chapter_id: Chapter identifier
        end_play_idx: Ending play index
        trigger_event_type: Type of event that triggered end
        reason_codes: Reason codes for next chapter (if applicable)
        period: Period/quarter number
        clock_time: Game clock time
        chapter_play_count: Number of plays in chapter
    """

    chapter_id: str
    end_play_idx: int
    trigger_event_type: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    period: int | None = None
    clock_time: str | None = None
    chapter_play_count: int = 0

    def __post_init__(self):
        if not isinstance(self.event_type, ChapterLogEventType):
            self.event_type = ChapterLogEventType.CHAPTER_END


@dataclass
class ChapterBoundaryTriggeredEvent(ChapterLogEvent):
    """Log event for triggered chapter boundary.

    Fields:
        play_idx: Play index where boundary triggered
        event_type_name: Type of play event
        reason_codes: Reason codes for this boundary
        rule_name: Name of rule that triggered boundary
        rule_precedence: Precedence value of rule
        boundary_action: Action taken (start_new/ignored/collapsed)
    """

    play_idx: int
    event_type_name: str
    reason_codes: list[str] = field(default_factory=list)
    rule_name: str = ""
    rule_precedence: int = 0
    boundary_action: BoundaryAction = BoundaryAction.START_NEW

    def __post_init__(self):
        if not isinstance(self.event_type, ChapterLogEventType):
            self.event_type = ChapterLogEventType.CHAPTER_BOUNDARY_TRIGGERED


@dataclass
class ChapterBoundaryIgnoredEvent(ChapterLogEvent):
    """Log event for ignored boundary.

    Fields:
        play_idx: Play index where boundary was considered
        event_type_name: Type of play event
        rule_name: Name of rule that was considered
        ignore_reason: Why boundary was ignored
    """

    play_idx: int
    event_type_name: str
    rule_name: str
    ignore_reason: str

    def __post_init__(self):
        if not isinstance(self.event_type, ChapterLogEventType):
            self.event_type = ChapterLogEventType.CHAPTER_BOUNDARY_IGNORED


@dataclass
class ChapterResetClusterEvent(ChapterLogEvent):
    """Log event for reset cluster collapse.

    Fields:
        cluster_start_play_idx: First play in cluster
        cluster_end_play_idx: Last play in cluster
        collapsed_events: List of events collapsed into cluster
        final_reason_codes: Final reason codes after collapse
    """

    cluster_start_play_idx: int
    cluster_end_play_idx: int
    collapsed_events: list[dict[str, Any]] = field(default_factory=list)
    final_reason_codes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.event_type, ChapterLogEventType):
            self.event_type = ChapterLogEventType.CHAPTER_RESET_CLUSTER


class ChapterDebugLogger:
    """Structured debug logger for chapter breakpoint tracing.

    Provides queryable, deterministic logging for chapter boundaries.

    Usage:
        debug_logger = ChapterDebugLogger(enabled=True)
        debug_logger.log_chapter_start(...)
        events = debug_logger.get_events()
    """

    def __init__(self, enabled: bool = False):
        """Initialize debug logger.

        Args:
            enabled: Whether debug logging is enabled
        """
        self.enabled = enabled
        self.events: list[ChapterLogEvent] = []
        self._event_counter = 0

    def _next_event_id(self) -> int:
        """Get next event ID."""
        self._event_counter += 1
        return self._event_counter

    def log_chapter_start(
        self,
        chapter_id: str,
        start_play_idx: int,
        trigger_event_type: str | None = None,
        reason_codes: list[str] | None = None,
        period: int | None = None,
        clock_time: str | None = None,
    ) -> None:
        """Log chapter start event.

        Args:
            chapter_id: Chapter identifier
            start_play_idx: Starting play index
            trigger_event_type: Type of event that triggered start
            reason_codes: Reason codes for this chapter
            period: Period/quarter number
            clock_time: Game clock time
        """
        if not self.enabled:
            return

        event = ChapterStartEvent(
            event_type=ChapterLogEventType.CHAPTER_START,
            event_id=self._next_event_id(),
            chapter_id=chapter_id,
            start_play_idx=start_play_idx,
            trigger_event_type=trigger_event_type,
            reason_codes=reason_codes or [],
            period=period,
            clock_time=clock_time,
        )

        self.events.append(event)
        logger.debug(f"CHAPTER_START: {event.to_json()}")

    def log_chapter_end(
        self,
        chapter_id: str,
        end_play_idx: int,
        trigger_event_type: str | None = None,
        reason_codes: list[str] | None = None,
        period: int | None = None,
        clock_time: str | None = None,
        chapter_play_count: int = 0,
    ) -> None:
        """Log chapter end event.

        Args:
            chapter_id: Chapter identifier
            end_play_idx: Ending play index
            trigger_event_type: Type of event that triggered end
            reason_codes: Reason codes for next chapter
            period: Period/quarter number
            clock_time: Game clock time
            chapter_play_count: Number of plays in chapter
        """
        if not self.enabled:
            return

        event = ChapterEndEvent(
            event_type=ChapterLogEventType.CHAPTER_END,
            event_id=self._next_event_id(),
            chapter_id=chapter_id,
            end_play_idx=end_play_idx,
            trigger_event_type=trigger_event_type,
            reason_codes=reason_codes or [],
            period=period,
            clock_time=clock_time,
            chapter_play_count=chapter_play_count,
        )

        self.events.append(event)
        logger.debug(f"CHAPTER_END: {event.to_json()}")

    def log_boundary_triggered(
        self,
        play_idx: int,
        event_type_name: str,
        reason_codes: list[str],
        rule_name: str,
        rule_precedence: int,
        boundary_action: BoundaryAction = BoundaryAction.START_NEW,
    ) -> None:
        """Log boundary trigger event.

        Args:
            play_idx: Play index where boundary triggered
            event_type_name: Type of play event
            reason_codes: Reason codes for this boundary
            rule_name: Name of rule that triggered boundary
            rule_precedence: Precedence value of rule
            boundary_action: Action taken
        """
        if not self.enabled:
            return

        event = ChapterBoundaryTriggeredEvent(
            event_type=ChapterLogEventType.CHAPTER_BOUNDARY_TRIGGERED,
            event_id=self._next_event_id(),
            play_idx=play_idx,
            event_type_name=event_type_name,
            reason_codes=reason_codes,
            rule_name=rule_name,
            rule_precedence=rule_precedence,
            boundary_action=boundary_action,
        )

        self.events.append(event)
        logger.debug(f"BOUNDARY_TRIGGERED: {event.to_json()}")

    def log_boundary_ignored(
        self, play_idx: int, event_type_name: str, rule_name: str, ignore_reason: str
    ) -> None:
        """Log ignored boundary event.

        Args:
            play_idx: Play index where boundary was considered
            event_type_name: Type of play event
            rule_name: Name of rule that was considered
            ignore_reason: Why boundary was ignored
        """
        if not self.enabled:
            return

        event = ChapterBoundaryIgnoredEvent(
            event_type=ChapterLogEventType.CHAPTER_BOUNDARY_IGNORED,
            event_id=self._next_event_id(),
            play_idx=play_idx,
            event_type_name=event_type_name,
            rule_name=rule_name,
            ignore_reason=ignore_reason,
        )

        self.events.append(event)
        logger.debug(f"BOUNDARY_IGNORED: {event.to_json()}")

    def log_reset_cluster(
        self,
        cluster_start_play_idx: int,
        cluster_end_play_idx: int,
        collapsed_events: list[dict[str, Any]],
        final_reason_codes: list[str],
    ) -> None:
        """Log reset cluster collapse event.

        Args:
            cluster_start_play_idx: First play in cluster
            cluster_end_play_idx: Last play in cluster
            collapsed_events: List of events collapsed into cluster
            final_reason_codes: Final reason codes after collapse
        """
        if not self.enabled:
            return

        event = ChapterResetClusterEvent(
            event_type=ChapterLogEventType.CHAPTER_RESET_CLUSTER,
            event_id=self._next_event_id(),
            cluster_start_play_idx=cluster_start_play_idx,
            cluster_end_play_idx=cluster_end_play_idx,
            collapsed_events=collapsed_events,
            final_reason_codes=final_reason_codes,
        )

        self.events.append(event)
        logger.debug(f"RESET_CLUSTER: {event.to_json()}")

    def get_events(self) -> list[ChapterLogEvent]:
        """Get all logged events.

        Returns:
            List of all logged events
        """
        return self.events

    def get_events_by_type(
        self, event_type: ChapterLogEventType
    ) -> list[ChapterLogEvent]:
        """Get events of a specific type.

        Args:
            event_type: Type of events to retrieve

        Returns:
            List of events of specified type
        """
        return [e for e in self.events if e.event_type == event_type]

    def get_boundary_events_for_play(self, play_idx: int) -> list[ChapterLogEvent]:
        """Get all boundary events for a specific play.

        Args:
            play_idx: Play index

        Returns:
            List of boundary events for this play
        """
        return [
            e for e in self.events if hasattr(e, "play_idx") and e.play_idx == play_idx
        ]

    def clear(self) -> None:
        """Clear all logged events."""
        self.events = []
        self._event_counter = 0

    def to_json(self) -> str:
        """Export all events as JSON.

        Returns:
            JSON string of all events
        """
        return json.dumps([e.to_dict() for e in self.events], indent=2)


def trace_chapter_reason_codes(
    chapters: list[Any], debug_logger: ChapterDebugLogger
) -> dict[str, list[int]]:
    """Trace chapter reason codes back to boundary events.

    For each chapter, find the boundary events that produced its reason codes.

    Args:
        chapters: List of chapters
        debug_logger: Debug logger with events

    Returns:
        Dict mapping chapter_id to list of event_ids that produced its reason codes
    """
    provenance = {}

    boundary_events = debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_BOUNDARY_TRIGGERED
    )

    for chapter in chapters:
        chapter_id = chapter.chapter_id
        chapter_reasons = set(chapter.reason_codes)

        # Find boundary events that match this chapter's reason codes
        matching_event_ids = []

        for event in boundary_events:
            event_reasons = set(event.reason_codes)
            if event_reasons & chapter_reasons:  # Intersection
                matching_event_ids.append(event.event_id)

        provenance[chapter_id] = matching_event_ids

    return provenance
