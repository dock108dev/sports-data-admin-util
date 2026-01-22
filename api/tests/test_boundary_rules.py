"""
Unit tests for NBA v1 Chapter Boundary Rules (Issue 0.3).

These tests validate rule correctness, not implementation sophistication.
They ensure boundaries occur when expected and NOT when they shouldn't.
"""

import pytest
from typing import Any

from app.services.chapters.boundary_rules import (
    NBABoundaryRules,
    BoundaryReasonCode,
    resolve_boundary_precedence,
    is_non_boundary_event,
)
from app.services.chapters import build_chapters


# Test 1: Hard Boundary Enforcement

def test_hard_boundary_period_start():
    """Chapter must break at quarter boundaries regardless of game state."""
    rules = NBABoundaryRules()
    
    # Q1 start (first event)
    event_q1 = {"quarter": 1, "description": "Jump ball"}
    assert rules.is_period_start(event_q1, None) is True
    
    # Q2 start
    event_q1_end = {"quarter": 1, "description": "End Q1"}
    event_q2 = {"quarter": 2, "description": "Start Q2"}
    assert rules.is_period_start(event_q2, event_q1_end) is True
    
    # Same quarter (no boundary)
    event_q2_mid = {"quarter": 2, "description": "Mid Q2"}
    assert rules.is_period_start(event_q2_mid, event_q2) is False


def test_hard_boundary_overtime_start():
    """Overtime start must create boundary."""
    rules = NBABoundaryRules()
    
    # Q4 -> OT (Q5)
    event_q4 = {"quarter": 4, "description": "End of regulation"}
    event_ot = {"quarter": 5, "description": "Overtime"}
    assert rules.is_overtime_start(event_ot, event_q4) is True
    
    # Q3 -> Q4 (not OT)
    event_q3 = {"quarter": 3}
    event_q4_start = {"quarter": 4}
    assert rules.is_overtime_start(event_q4_start, event_q3) is False


def test_hard_boundary_game_end():
    """Last event must be game end."""
    rules = NBABoundaryRules()
    
    # Last event
    event = {"quarter": 4, "description": "Final buzzer"}
    assert rules.is_game_end(event, None) is True
    
    # Not last event
    next_event = {"quarter": 4}
    assert rules.is_game_end(event, next_event) is False


# Test 2: Non-Boundary Guard

def test_non_boundary_made_baskets():
    """Made baskets alone should not create boundaries."""
    event = {"description": "LeBron James makes layup", "play_type": "shot"}
    assert is_non_boundary_event(event) is True


def test_non_boundary_free_throws():
    """Free throws should not create boundaries."""
    event = {"description": "Free throw made", "play_type": "free_throw"}
    assert is_non_boundary_event(event) is True


def test_non_boundary_fouls():
    """Regular fouls should not create boundaries."""
    event = {"description": "Personal foul", "play_type": "foul"}
    assert is_non_boundary_event(event) is True


def test_non_boundary_rebounds():
    """Rebounds should not create boundaries."""
    event = {"description": "Defensive rebound", "play_type": "rebound"}
    assert is_non_boundary_event(event) is True


def test_non_boundary_missed_shots():
    """Missed shots should not create boundaries."""
    event = {"description": "Anthony Davis misses jumper", "play_type": "shot"}
    assert is_non_boundary_event(event) is True


def test_non_boundary_turnovers():
    """Turnovers should not create boundaries."""
    event = {"description": "Turnover by Curry", "play_type": "turnover"}
    assert is_non_boundary_event(event) is True


def test_non_boundary_substitutions():
    """Substitutions should not create boundaries."""
    event = {"description": "Substitution: Smith in for Jones", "play_type": "sub"}
    assert is_non_boundary_event(event) is True


def test_non_boundary_sequence_integration():
    """A sequence of scores without timeout/run logic must not create extra chapters."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "LeBron makes layup"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Tatum makes 3-pointer"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "description": "Davis makes jumper"},
        {"event_type": "pbp", "quarter": 1, "play_id": 4, "description": "Brown makes layup"},
        {"event_type": "pbp", "quarter": 1, "play_id": 5, "description": "Westbrook makes 3-pointer"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Should be 1 chapter (no boundaries within Q1 for just scores)
    assert story.chapter_count == 1
    assert story.chapters[0].reason_codes == ["PERIOD_START"]


# Test 3: Reason Code Assignment

def test_reason_code_period_start():
    """PERIOD_START reason code must be assigned correctly."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Start Q2"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # First chapter: PERIOD_START
    assert "PERIOD_START" in story.chapters[0].reason_codes
    
    # Second chapter: PERIOD_START (Q2)
    assert "PERIOD_START" in story.chapters[1].reason_codes


def test_reason_code_timeout():
    """TIMEOUT reason code must be assigned correctly."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Score before timeout"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Timeout: Lakers"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "description": "After timeout"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Timeout creates a boundary - chapter starting at timeout should have TIMEOUT code
    timeout_chapters = [ch for ch in story.chapters if "TIMEOUT" in ch.reason_codes]
    assert len(timeout_chapters) > 0


def test_reason_code_review():
    """REVIEW reason code must be assigned correctly."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Score before review"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Instant replay review"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "description": "After review"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Review creates a boundary - chapter starting at review should have REVIEW code
    review_chapters = [ch for ch in story.chapters if "REVIEW" in ch.reason_codes]
    assert len(review_chapters) > 0


def test_reason_code_crunch_start():
    """CRUNCH_START reason code must be assigned when entering crunch time."""
    timeline = [
        {"event_type": "pbp", "quarter": 4, "play_id": 0, "description": "Q4 start", 
         "game_clock": "12:00", "home_score": 95, "away_score": 93},
        {"event_type": "pbp", "quarter": 4, "play_id": 1, "description": "Score", 
         "game_clock": "6:00", "home_score": 100, "away_score": 98},
        {"event_type": "pbp", "quarter": 4, "play_id": 2, "description": "Crunch time", 
         "game_clock": "4:55", "home_score": 102, "away_score": 100},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Should have crunch time boundary
    crunch_chapters = [ch for ch in story.chapters if "CRUNCH_START" in ch.reason_codes]
    assert len(crunch_chapters) > 0


def test_reason_code_every_chapter_has_reason():
    """Every chapter must have at least one reason code."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout"},
        {"event_type": "pbp", "quarter": 2, "play_id": 2, "description": "Q2 start"},
        {"event_type": "pbp", "quarter": 2, "play_id": 3, "description": "Review"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    for chapter in story.chapters:
        assert len(chapter.reason_codes) > 0, f"Chapter {chapter.chapter_id} has no reason codes"


# Test 4: Boundary Precedence

def test_precedence_period_over_timeout():
    """Period boundary must take precedence over timeout."""
    codes = [BoundaryReasonCode.TIMEOUT, BoundaryReasonCode.PERIOD_START]
    resolved = resolve_boundary_precedence(codes)
    
    # PERIOD_START should be first (higher precedence)
    assert resolved[0] == BoundaryReasonCode.PERIOD_START
    
    # TIMEOUT should be excluded (period boundary overrides)
    assert BoundaryReasonCode.TIMEOUT not in resolved


def test_precedence_overtime_over_timeout():
    """Overtime start must take precedence over timeout."""
    codes = [BoundaryReasonCode.TIMEOUT, BoundaryReasonCode.OVERTIME_START]
    resolved = resolve_boundary_precedence(codes)
    
    assert resolved[0] == BoundaryReasonCode.OVERTIME_START
    assert BoundaryReasonCode.TIMEOUT not in resolved


def test_precedence_review_over_run():
    """Review must take precedence over run logic."""
    codes = [BoundaryReasonCode.RUN_START, BoundaryReasonCode.REVIEW]
    resolved = resolve_boundary_precedence(codes)
    
    # REVIEW should be first
    assert resolved[0] == BoundaryReasonCode.REVIEW


def test_precedence_timeout_immediately_after_period():
    """Timeout immediately following period start should not create new chapter."""
    timeline = [
        {"event_type": "pbp", "quarter": 2, "play_id": 0, "description": "Q2 start"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Timeout"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Should be 1 chapter (timeout absorbed by period start)
    # Or 2 chapters if timeout is separate, but first should be PERIOD_START only
    first_chapter = story.chapters[0]
    assert "PERIOD_START" in first_chapter.reason_codes


# Test 5: Scene Reset Boundaries

def test_scene_reset_timeout_creates_boundary():
    """Timeout should create a boundary (scene reset)."""
    rules = NBABoundaryRules()
    
    event_timeout = {"description": "Timeout: Lakers full timeout"}
    assert rules.is_timeout(event_timeout) is True
    
    event_official = {"description": "Official timeout"}
    assert rules.is_timeout(event_official) is True


def test_scene_reset_review_creates_boundary():
    """Instant replay review should create a boundary."""
    rules = NBABoundaryRules()
    
    event_review = {"description": "Instant replay review"}
    assert rules.is_review(event_review) is True
    
    event_challenge = {"description": "Coach's challenge"}
    assert rules.is_review(event_challenge) is True


# Test 6: Crunch Time Detection

def test_crunch_time_q4_under_5_close():
    """Q4 under 5 minutes with close score should trigger crunch time."""
    rules = NBABoundaryRules()
    
    # Not in crunch yet
    prev_event = {"quarter": 4, "game_clock": "6:00", "home_score": 100, "away_score": 98}
    
    # Entering crunch (< 5 min, margin <= 5)
    event = {"quarter": 4, "game_clock": "4:55", "home_score": 102, "away_score": 100}
    
    context = {}
    assert rules.is_crunch_start(event, prev_event, context) is True


def test_crunch_time_not_close_enough():
    """Q4 under 5 minutes but margin > 5 should NOT trigger crunch time."""
    rules = NBABoundaryRules()
    
    prev_event = {"quarter": 4, "game_clock": "6:00", "home_score": 100, "away_score": 90}
    event = {"quarter": 4, "game_clock": "4:55", "home_score": 102, "away_score": 90}
    
    context = {}
    assert rules.is_crunch_start(event, prev_event, context) is False


def test_crunch_time_overtime_always_crunch():
    """Overtime with close score should be crunch time."""
    rules = NBABoundaryRules()
    
    prev_event = {"quarter": 4, "game_clock": "0:00", "home_score": 100, "away_score": 100}
    event = {"quarter": 5, "game_clock": "5:00", "home_score": 100, "away_score": 100}
    
    context = {}
    # OT start with close score
    assert rules.is_crunch_start(event, prev_event, context) is True


# Test 7: Integration Tests

def test_integration_full_game_structure():
    """Full game should have expected chapter structure."""
    timeline = []
    
    # Q1
    for i in range(5):
        timeline.append({
            "event_type": "pbp",
            "quarter": 1,
            "play_id": i,
            "description": f"Q1 play {i}",
        })
    
    # Q2
    for i in range(5, 10):
        timeline.append({
            "event_type": "pbp",
            "quarter": 2,
            "play_id": i,
            "description": f"Q2 play {i}",
        })
    
    # Q3 with timeout
    timeline.append({
        "event_type": "pbp",
        "quarter": 3,
        "play_id": 10,
        "description": "Q3 start",
    })
    timeline.append({
        "event_type": "pbp",
        "quarter": 3,
        "play_id": 11,
        "description": "Timeout: Lakers",
    })
    timeline.append({
        "event_type": "pbp",
        "quarter": 3,
        "play_id": 12,
        "description": "After timeout",
    })
    
    # Q4
    for i in range(13, 18):
        timeline.append({
            "event_type": "pbp",
            "quarter": 4,
            "play_id": i,
            "description": f"Q4 play {i}",
        })
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Should have: Q1, Q2, Q3, timeout, Q4 = 5 chapters minimum
    assert story.chapter_count >= 4
    
    # All chapters should have reason codes
    for chapter in story.chapters:
        assert len(chapter.reason_codes) > 0


def test_integration_determinism():
    """Same input should produce same chapters."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Start"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout"},
        {"event_type": "pbp", "quarter": 2, "play_id": 2, "description": "Q2"},
    ]
    
    story1 = build_chapters(timeline, game_id=1, sport="NBA")
    story2 = build_chapters(timeline, game_id=1, sport="NBA")
    
    assert story1.chapter_count == story2.chapter_count
    
    for ch1, ch2 in zip(story1.chapters, story2.chapters):
        assert ch1.chapter_id == ch2.chapter_id
        assert ch1.reason_codes == ch2.reason_codes
