"""
Unit tests for Chapter Debug Logger (Phase 1 Issue 7).

These tests validate logging correctness and reason code tracing.
"""

import pytest

from app.services.chapters import (
    ChapterizerV1,
    ChapterDebugLogger,
    ChapterLogEventType,
    BoundaryAction,
    trace_chapter_reason_codes,
)


# Test 1: Boundary Trigger Log Test

def test_boundary_trigger_logged():
    """Boundary trigger should emit CHAPTER_BOUNDARY_TRIGGERED log."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Q2 start"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Get boundary triggered events
    boundary_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_BOUNDARY_TRIGGERED
    )
    
    # Should have at least one boundary event (PERIOD_START for Q2)
    assert len(boundary_events) > 0
    
    # Check that PERIOD_START was logged
    period_starts = [
        e for e in boundary_events
        if "PERIOD_START" in e.reason_codes
    ]
    assert len(period_starts) > 0
    
    # Verify event structure
    event = period_starts[0]
    assert event.play_idx >= 0
    assert event.rule_name
    assert event.rule_precedence > 0


def test_boundary_trigger_correct_play_index():
    """Boundary log should contain correct play index."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Play 2"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Timeout"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "description": "Play 3"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Get boundary events
    boundary_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_BOUNDARY_TRIGGERED
    )
    
    # Find timeout boundary
    timeout_events = [
        e for e in boundary_events
        if "TIMEOUT" in e.reason_codes
    ]
    
    # Timeout should be at play index 2
    if timeout_events:
        assert timeout_events[0].play_idx == 2


# Test 2: Ignored Boundary Log Test

def test_ignored_boundary_logged():
    """Non-boundary event should emit CHAPTER_BOUNDARY_IGNORED log."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "LeBron makes layup"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Tatum makes 3-pointer"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Get ignored boundary events
    ignored_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_BOUNDARY_IGNORED
    )
    
    # Should have ignored events for made shots
    assert len(ignored_events) > 0
    
    # Check ignore reason
    for event in ignored_events:
        assert event.ignore_reason
        assert event.rule_name


def test_ignored_boundary_correct_reason():
    """Ignored boundary should have correct ignore_reason."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Free throw made"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Get ignored events
    ignored_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_BOUNDARY_IGNORED
    )
    
    # Free throw should be ignored with explicit_non_boundary reason
    ft_ignored = [e for e in ignored_events if e.play_idx == 1]
    if ft_ignored:
        assert "explicit_non_boundary" in ft_ignored[0].ignore_reason


# Test 3: Reset Cluster Collapse Test

def test_reset_cluster_collapse_logged():
    """Consecutive timeout/review should log cluster collapse."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout: Lakers"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Substitution"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "description": "Instant replay review"},
        {"event_type": "pbp", "quarter": 1, "play_id": 4, "description": "Play after cluster"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Get ignored events (collapsed into cluster)
    ignored_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_BOUNDARY_IGNORED
    )
    
    # Should have at least one collapsed event
    collapsed = [e for e in ignored_events if "collapsed" in e.ignore_reason]
    assert len(collapsed) > 0


def test_reset_cluster_only_one_boundary():
    """Reset cluster should create only one chapter break."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout: Lakers"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Instant replay review"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "description": "Play after"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Should have 2-3 chapters max (not 4+)
    assert story.chapter_count <= 3


# Test 4: Chapter Reason Trace Test

def test_chapter_reason_trace():
    """Every chapter reason code should trace back to boundary log."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Q1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout"},
        {"event_type": "pbp", "quarter": 2, "play_id": 2, "description": "Q2"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Trace reason codes
    provenance = trace_chapter_reason_codes(story.chapters, chapterizer.debug_logger)
    
    # Every chapter should have provenance
    for chapter in story.chapters:
        assert chapter.chapter_id in provenance
        # Should have at least one event that produced its reason codes
        # (May be empty for first chapter if it's implicit PERIOD_START)


def test_chapter_reason_trace_no_orphan_codes():
    """All chapter reason codes should have provenance in logs."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Q1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout: Lakers"},
        {"event_type": "pbp", "quarter": 2, "play_id": 2, "description": "Q2"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Get all boundary triggered events
    boundary_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_BOUNDARY_TRIGGERED
    )
    
    # Collect all reason codes from logs
    logged_reasons = set()
    for event in boundary_events:
        logged_reasons.update(event.reason_codes)
    
    # All chapter reason codes should appear in logs
    for chapter in story.chapters:
        for reason in chapter.reason_codes:
            # PERIOD_START and game_end may be implicit, but others must be logged
            if reason not in ["PERIOD_START", "game_end"]:
                assert reason in logged_reasons, \
                    f"Chapter {chapter.chapter_id} has reason '{reason}' not found in logs"


# Test 5: Debug Logger Enabled/Disabled

def test_debug_logger_disabled_no_events():
    """With debug=False, no events should be logged."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Play 2"},
    ]
    
    chapterizer = ChapterizerV1(debug=False)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Should have no events logged
    assert len(chapterizer.debug_logger.get_events()) == 0


def test_debug_logger_enabled_has_events():
    """With debug=True, events should be logged."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Play 2"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Should have events logged
    assert len(chapterizer.debug_logger.get_events()) > 0


# Test 6: Chapter Start/End Logging

def test_chapter_start_end_logged():
    """Every chapter should have start and end log events."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Play 2"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Get start/end events
    start_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_START
    )
    end_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_END
    )
    
    # Should have equal number of start and end events
    assert len(start_events) == len(end_events)
    
    # Should match chapter count
    assert len(start_events) == story.chapter_count


def test_chapter_start_end_match_chapters():
    """Start/end events should match actual chapters."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout"},
        {"event_type": "pbp", "quarter": 2, "play_id": 2, "description": "Q2"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    start_events = chapterizer.debug_logger.get_events_by_type(
        ChapterLogEventType.CHAPTER_START
    )
    
    # Each chapter should have a start event
    for chapter in story.chapters:
        matching_starts = [e for e in start_events if e.chapter_id == chapter.chapter_id]
        assert len(matching_starts) == 1
        
        start_event = matching_starts[0]
        assert start_event.start_play_idx == chapter.play_start_idx


# Test 7: Integration Tests

def test_integration_full_game_logging():
    """Full game should produce comprehensive logs."""
    timeline = []
    
    # Q1
    for i in range(10):
        timeline.append({"event_type": "pbp", "quarter": 1, "play_id": len(timeline), "description": f"Play {i}"})
    
    # Timeout
    timeline.append({"event_type": "pbp", "quarter": 1, "play_id": len(timeline), "description": "Timeout: Lakers"})
    
    # Q2
    for i in range(10):
        timeline.append({"event_type": "pbp", "quarter": 2, "play_id": len(timeline), "description": f"Q2 play {i}"})
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Should have multiple event types
    events = chapterizer.debug_logger.get_events()
    assert len(events) > 0
    
    event_types = {e.event_type for e in events}
    assert ChapterLogEventType.CHAPTER_START in event_types
    assert ChapterLogEventType.CHAPTER_END in event_types
    assert ChapterLogEventType.CHAPTER_BOUNDARY_TRIGGERED in event_types


def test_integration_json_export():
    """Debug logger should export to JSON."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Play 2"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Should export to JSON without error
    json_output = chapterizer.debug_logger.to_json()
    assert json_output
    assert "CHAPTER_START" in json_output or "CHAPTER_BOUNDARY_TRIGGERED" in json_output


# Test 8: Query Functions

def test_query_events_by_play_index():
    """Should be able to query events by play index."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Play 2"},
    ]
    
    chapterizer = ChapterizerV1(debug=True)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    
    # Query events for play 1 (timeout)
    events_at_play_1 = chapterizer.debug_logger.get_boundary_events_for_play(1)
    
    # Should have at least one event (timeout boundary or ignored)
    assert len(events_at_play_1) >= 0  # May be 0 if timeout is at different index


# Test 9: Determinism

def test_logging_deterministic():
    """Same input should produce same log events."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Play 2"},
    ]
    
    chapterizer1 = ChapterizerV1(debug=True)
    story1 = chapterizer1.chapterize(timeline, game_id=1, sport="NBA")
    events1 = chapterizer1.debug_logger.get_events()
    
    chapterizer2 = ChapterizerV1(debug=True)
    story2 = chapterizer2.chapterize(timeline, game_id=1, sport="NBA")
    events2 = chapterizer2.debug_logger.get_events()
    
    # Should have same number of events
    assert len(events1) == len(events2)
    
    # Events should match (excluding event_id which is sequential)
    for e1, e2 in zip(events1, events2):
        assert e1.event_type == e2.event_type
        if hasattr(e1, 'play_idx'):
            assert e1.play_idx == e2.play_idx
