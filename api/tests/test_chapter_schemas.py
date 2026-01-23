"""
Unit tests for Chapter and GameStory schema validation.

These tests enforce the data contracts, not behavior.
They validate that the schemas are strict and that validation catches errors.

CONTRACT ENFORCEMENT:
- Chapter schema validation
- GameStory schema validation
- Chapter-Play consistency
- Reason code enforcement
"""

import pytest
from typing import Any

from app.services.chapters import Play, Chapter, GameStory, TimeRange


# Test 1: Chapter Schema Validation

def test_chapter_schema_missing_chapter_id():
    """Chapter with empty chapter_id must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    with pytest.raises(ValueError, match="chapter_id cannot be empty"):
        Chapter(
            chapter_id="",
            play_start_idx=0,
            play_end_idx=0,
            plays=plays,
            reason_codes=["test"],
        )


def test_chapter_schema_negative_start_idx():
    """Chapter with negative play_start_idx must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    with pytest.raises(ValueError, match="play_start_idx must be non-negative"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=-1,
            play_end_idx=0,
            plays=plays,
            reason_codes=["test"],
        )


def test_chapter_schema_invalid_index_range():
    """Chapter with start_idx > end_idx must fail."""
    plays = [Play(index=5, event_type="pbp", raw_data={})]
    
    with pytest.raises(ValueError, match="start_idx.*>.*end_idx"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=5,
            play_end_idx=3,
            plays=plays,
            reason_codes=["test"],
        )


def test_chapter_schema_empty_plays():
    """Chapter with no plays must fail."""
    with pytest.raises(ValueError, match="has no plays"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=2,
            plays=[],
            reason_codes=["test"],
        )


def test_chapter_schema_empty_reason_codes():
    """Chapter with empty reason_codes must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    with pytest.raises(ValueError, match="empty reason_codes"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=0,
            plays=plays,
            reason_codes=[],
        )


def test_chapter_schema_invalid_period():
    """Chapter with period < 1 must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    with pytest.raises(ValueError, match="period must be >= 1"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=0,
            plays=plays,
            reason_codes=["test"],
            period=0,
        )


def test_chapter_schema_valid_minimal():
    """Valid minimal chapter must pass."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["test"],
    )
    
    assert chapter.chapter_id == "ch_001"
    assert chapter.play_start_idx == 0
    assert chapter.play_end_idx == 0
    assert len(chapter.plays) == 1
    assert chapter.reason_codes == ["test"]
    assert chapter.period is None
    assert chapter.time_range is None


def test_chapter_schema_valid_full():
    """Valid chapter with all fields must pass."""
    plays = [
        Play(index=0, event_type="pbp", raw_data={"quarter": 1, "game_clock": "12:00"}),
        Play(index=1, event_type="pbp", raw_data={"quarter": 1, "game_clock": "11:45"}),
    ]
    
    time_range = TimeRange(start="12:00", end="11:45")
    
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=1,
        plays=plays,
        reason_codes=["quarter_change"],
        period=1,
        time_range=time_range,
    )
    
    assert chapter.chapter_id == "ch_001"
    assert chapter.play_count == 2
    assert chapter.period == 1
    assert chapter.time_range.start == "12:00"
    assert chapter.time_range.end == "11:45"


# Test 2: GameStory Schema Validation

def test_gamestory_schema_invalid_game_id():
    """GameStory with game_id <= 0 must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["test"],
    )
    
    with pytest.raises(ValueError, match="game_id must be positive"):
        GameStory(
            game_id=0,
            sport="NBA",
            chapters=[chapter],
        )


def test_gamestory_schema_empty_sport():
    """GameStory with empty sport must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["test"],
    )
    
    with pytest.raises(ValueError, match="sport cannot be empty"):
        GameStory(
            game_id=1,
            sport="",
            chapters=[chapter],
        )


def test_gamestory_schema_empty_chapters():
    """GameStory with no chapters must fail."""
    with pytest.raises(ValueError, match="has no chapters"):
        GameStory(
            game_id=1,
            sport="NBA",
            chapters=[],
        )


def test_gamestory_schema_non_contiguous_chapters():
    """GameStory with non-contiguous chapters must fail."""
    plays1 = [Play(index=0, event_type="pbp", raw_data={})]
    plays2 = [Play(index=5, event_type="pbp", raw_data={})]  # Gap: should be index 1
    
    chapter1 = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays1,
        reason_codes=["test"],
    )
    chapter2 = Chapter(
        chapter_id="ch_002",
        play_start_idx=5,
        play_end_idx=5,
        plays=plays2,
        reason_codes=["test"],
    )
    
    with pytest.raises(ValueError, match="not contiguous"):
        GameStory(
            game_id=1,
            sport="NBA",
            chapters=[chapter1, chapter2],
        )


def test_gamestory_schema_duplicate_chapter_ids():
    """GameStory with duplicate chapter_ids must fail."""
    plays1 = [Play(index=0, event_type="pbp", raw_data={})]
    plays2 = [Play(index=1, event_type="pbp", raw_data={})]
    
    chapter1 = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays1,
        reason_codes=["test"],
    )
    chapter2 = Chapter(
        chapter_id="ch_001",  # Duplicate
        play_start_idx=1,
        play_end_idx=1,
        plays=plays2,
        reason_codes=["test"],
    )
    
    with pytest.raises(ValueError, match="duplicate chapter_ids"):
        GameStory(
            game_id=1,
            sport="NBA",
            chapters=[chapter1, chapter2],
        )


def test_gamestory_schema_negative_reading_time():
    """GameStory with negative reading_time_estimate_minutes must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["test"],
    )
    
    with pytest.raises(ValueError, match="reading_time_estimate_minutes must be non-negative"):
        GameStory(
            game_id=1,
            sport="NBA",
            chapters=[chapter],
            reading_time_estimate_minutes=-1.0,
        )


def test_gamestory_schema_valid_minimal():
    """Valid minimal GameStory must pass."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["test"],
    )
    
    story = GameStory(
        game_id=1,
        sport="NBA",
        chapters=[chapter],
    )
    
    assert story.game_id == 1
    assert story.sport == "NBA"
    assert story.chapter_count == 1
    assert story.total_plays == 1
    assert story.compact_story is None
    assert story.reading_time_estimate_minutes is None
    assert story.metadata == {}


def test_gamestory_schema_valid_full():
    """Valid GameStory with all fields must pass."""
    plays = [
        Play(index=0, event_type="pbp", raw_data={}),
        Play(index=1, event_type="pbp", raw_data={}),
    ]
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=1,
        plays=plays,
        reason_codes=["test"],
    )
    
    story = GameStory(
        game_id=123,
        sport="NBA",
        chapters=[chapter],
        compact_story="Lakers win in overtime",
        reading_time_estimate_minutes=5.5,
        metadata={"home_team": "Lakers", "away_team": "Celtics"},
    )
    
    assert story.game_id == 123
    assert story.sport == "NBA"
    assert story.chapter_count == 1
    assert story.total_plays == 2
    assert story.compact_story == "Lakers win in overtime"
    assert story.reading_time_estimate_minutes == 5.5
    assert story.metadata["home_team"] == "Lakers"


# Test 3: Chapter-Play Consistency

def test_chapter_play_consistency_count_mismatch():
    """plays.length must equal play_end_idx - play_start_idx + 1."""
    plays = [
        Play(index=0, event_type="pbp", raw_data={}),
        Play(index=1, event_type="pbp", raw_data={}),
    ]
    
    # Indices say 3 plays (0, 1, 2), but only 2 provided
    with pytest.raises(ValueError, match="play count mismatch"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=2,
            plays=plays,
            reason_codes=["test"],
        )


def test_chapter_play_consistency_wrong_indices():
    """Play indices must match chapter range."""
    plays = [
        Play(index=5, event_type="pbp", raw_data={}),
        Play(index=6, event_type="pbp", raw_data={}),
    ]
    
    # Chapter says 0-1, but plays are 5-6
    with pytest.raises(ValueError, match="non-contiguous plays"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=1,
            plays=plays,
            reason_codes=["test"],
        )


def test_chapter_play_consistency_gap_in_plays():
    """Plays must be contiguous (no gaps)."""
    plays = [
        Play(index=0, event_type="pbp", raw_data={}),
        Play(index=2, event_type="pbp", raw_data={}),  # Missing index 1
    ]
    
    # Gap causes count mismatch (expected 3, got 2)
    with pytest.raises(ValueError, match="play count mismatch"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=2,
            plays=plays,
            reason_codes=["test"],
        )


def test_chapter_play_consistency_ordering_preserved():
    """Play ordering must be preserved."""
    plays = [
        Play(index=0, event_type="pbp", raw_data={}),
        Play(index=1, event_type="pbp", raw_data={}),
        Play(index=2, event_type="pbp", raw_data={}),
    ]
    
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=2,
        plays=plays,
        reason_codes=["test"],
    )
    
    # Verify ordering
    for i, play in enumerate(chapter.plays):
        assert play.index == i


def test_chapter_play_consistency_valid():
    """Valid chapter-play consistency must pass."""
    plays = [
        Play(index=10, event_type="pbp", raw_data={}),
        Play(index=11, event_type="pbp", raw_data={}),
        Play(index=12, event_type="pbp", raw_data={}),
        Play(index=13, event_type="pbp", raw_data={}),
        Play(index=14, event_type="pbp", raw_data={}),
    ]
    
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=10,
        play_end_idx=14,
        plays=plays,
        reason_codes=["test"],
    )
    
    # Verify consistency
    assert chapter.play_count == 5
    assert chapter.play_count == chapter.play_end_idx - chapter.play_start_idx + 1
    assert [p.index for p in chapter.plays] == [10, 11, 12, 13, 14]


# Test 4: Reason Code Enforcement

def test_reason_code_enforcement_empty_list():
    """Chapters with empty reason_codes[] must fail."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    with pytest.raises(ValueError, match="empty reason_codes"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=0,
            plays=plays,
            reason_codes=[],
        )


def test_reason_code_enforcement_single_reason():
    """Chapter with single reason code must pass."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["quarter_change"],
    )
    
    assert chapter.reason_codes == ["quarter_change"]


def test_reason_code_enforcement_multiple_reasons():
    """Chapter with multiple reason codes must pass."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["quarter_change", "momentum_shift"],
    )
    
    assert len(chapter.reason_codes) == 2
    assert "quarter_change" in chapter.reason_codes
    assert "momentum_shift" in chapter.reason_codes


# Test 5: JSON Serialization (Contract Validation)

def test_json_serialization_chapter():
    """Chapter.to_dict() must produce contract-compliant JSON."""
    plays = [
        Play(index=0, event_type="pbp", raw_data={"quarter": 1, "game_clock": "12:00"}),
        Play(index=1, event_type="pbp", raw_data={"quarter": 1, "game_clock": "11:45"}),
    ]
    
    time_range = TimeRange(start="12:00", end="11:45")
    
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=1,
        plays=plays,
        reason_codes=["quarter_change"],
        period=1,
        time_range=time_range,
    )
    
    data = chapter.to_dict()
    
    # Required fields
    assert "chapter_id" in data
    assert "play_start_idx" in data
    assert "play_end_idx" in data
    assert "play_count" in data
    assert "plays" in data
    assert "reason_codes" in data
    assert "period" in data
    assert "time_range" in data
    
    # Values
    assert data["chapter_id"] == "ch_001"
    assert data["play_start_idx"] == 0
    assert data["play_end_idx"] == 1
    assert data["play_count"] == 2
    assert len(data["plays"]) == 2
    assert data["reason_codes"] == ["quarter_change"]
    assert data["period"] == 1
    assert data["time_range"]["start"] == "12:00"
    assert data["time_range"]["end"] == "11:45"


def test_json_serialization_gamestory():
    """GameStory.to_dict() must produce contract-compliant JSON."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["test"],
    )
    
    story = GameStory(
        game_id=123,
        sport="NBA",
        chapters=[chapter],
        compact_story="Test story",
        reading_time_estimate_minutes=3.5,
        metadata={"test": True},
    )
    
    data = story.to_dict()
    
    # Required fields
    assert "game_id" in data
    assert "sport" in data
    assert "chapter_count" in data
    assert "total_plays" in data
    assert "chapters" in data
    assert "compact_story" in data
    
    # Optional fields
    assert "reading_time_estimate_minutes" in data
    assert "metadata" in data
    
    # Values
    assert data["game_id"] == 123
    assert data["sport"] == "NBA"
    assert data["chapter_count"] == 1
    assert data["total_plays"] == 1
    assert len(data["chapters"]) == 1
    assert data["compact_story"] == "Test story"
    assert data["reading_time_estimate_minutes"] == 3.5
    assert data["metadata"]["test"] is True


def test_json_serialization_nullable_fields():
    """Nullable fields must be present in JSON (even if null)."""
    plays = [Play(index=0, event_type="pbp", raw_data={})]
    chapter = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=0,
        plays=plays,
        reason_codes=["test"],
        period=None,
        time_range=None,
    )
    
    story = GameStory(
        game_id=1,
        sport="NBA",
        chapters=[chapter],
        compact_story=None,
        reading_time_estimate_minutes=None,
    )
    
    chapter_data = chapter.to_dict()
    story_data = story.to_dict()
    
    # Chapter nullable fields must be present
    assert "period" in chapter_data
    assert chapter_data["period"] is None
    assert "time_range" in chapter_data
    assert chapter_data["time_range"] is None
    
    # GameStory nullable fields must be present
    assert "compact_story" in story_data
    assert story_data["compact_story"] is None
    assert "reading_time_estimate_minutes" in story_data
    assert story_data["reading_time_estimate_minutes"] is None


# Test 6: Play Validation

def test_play_validation_negative_index():
    """Play with negative index must fail."""
    with pytest.raises(ValueError, match="index must be non-negative"):
        Play(index=-1, event_type="pbp", raw_data={})


def test_play_validation_empty_event_type():
    """Play with empty event_type must fail."""
    with pytest.raises(ValueError, match="event_type cannot be empty"):
        Play(index=0, event_type="", raw_data={})


def test_play_validation_invalid_raw_data():
    """Play with non-dict raw_data must fail."""
    with pytest.raises(ValueError, match="raw_data must be a dict"):
        Play(index=0, event_type="pbp", raw_data="not a dict")  # type: ignore


def test_play_validation_valid():
    """Valid play must pass."""
    play = Play(index=0, event_type="pbp", raw_data={"test": True})
    
    assert play.index == 0
    assert play.event_type == "pbp"
    assert play.raw_data == {"test": True}
