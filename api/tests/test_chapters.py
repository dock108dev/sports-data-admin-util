"""
Unit tests for the Book + Chapters model.

These tests enforce the core contracts of the new architecture:
1. Chapter coverage (every play in exactly one chapter)
2. Determinism (same input → same output)
3. Structural integrity (contiguous, valid boundaries)
4. Moment regression guard (no moment objects produced)
"""

import pytest
from typing import Any

from app.services.chapters import Play, Chapter, GameStory, build_chapters


# Test fixtures

def create_test_timeline(num_plays: int = 10, quarters: list[int] | None = None) -> list[dict[str, Any]]:
    """Create a test timeline with PBP events.
    
    Args:
        num_plays: Number of plays to create
        quarters: Quarter assignments for each play (defaults to all Q1)
        
    Returns:
        List of timeline events
    """
    if quarters is None:
        quarters = [1] * num_plays
    
    if len(quarters) != num_plays:
        raise ValueError("quarters length must match num_plays")
    
    timeline = []
    for i in range(num_plays):
        timeline.append({
            "event_type": "pbp",
            "quarter": quarters[i],
            "play_id": i,
            "description": f"Play {i}",
            "home_score": i,
            "away_score": i,
        })
    
    return timeline


def create_multi_quarter_timeline() -> list[dict[str, Any]]:
    """Create a timeline spanning multiple quarters."""
    return create_test_timeline(
        num_plays=20,
        quarters=[1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4],
    )


# Test 1: Chapter Coverage

def test_chapter_coverage_all_plays_assigned():
    """Every play must belong to exactly one chapter."""
    timeline = create_test_timeline(num_plays=10)
    story = build_chapters(timeline, game_id=1)
    
    # Collect all play indices from chapters
    assigned_indices = set()
    for chapter in story.chapters:
        for play in chapter.plays:
            if play.index in assigned_indices:
                pytest.fail(f"Play {play.index} assigned to multiple chapters")
            assigned_indices.add(play.index)
    
    # Verify all plays are assigned
    expected_indices = set(range(len(timeline)))
    assert assigned_indices == expected_indices, (
        f"Not all plays assigned. Expected {expected_indices}, "
        f"got {assigned_indices}"
    )


def test_chapter_coverage_no_gaps():
    """Chapters must be contiguous with no gaps."""
    timeline = create_multi_quarter_timeline()
    story = build_chapters(timeline, game_id=1)
    
    # Verify no gaps between chapters
    for i in range(1, len(story.chapters)):
        prev_end = story.chapters[i - 1].play_end_idx
        curr_start = story.chapters[i].play_start_idx
        
        assert curr_start == prev_end + 1, (
            f"Gap between chapters: chapter {i-1} ends at {prev_end}, "
            f"chapter {i} starts at {curr_start}"
        )


def test_chapter_coverage_no_overlaps():
    """Chapters must not overlap."""
    timeline = create_multi_quarter_timeline()
    story = build_chapters(timeline, game_id=1)
    
    # Verify no overlaps
    for i in range(1, len(story.chapters)):
        prev_end = story.chapters[i - 1].play_end_idx
        curr_start = story.chapters[i].play_start_idx
        
        assert curr_start > prev_end, (
            f"Overlap between chapters: chapter {i-1} ends at {prev_end}, "
            f"chapter {i} starts at {curr_start}"
        )


def test_chapter_coverage_empty_timeline():
    """Empty timeline should raise ValueError."""
    with pytest.raises(ValueError, match="empty timeline"):
        build_chapters([], game_id=1)


def test_chapter_coverage_no_pbp_events():
    """Timeline with no PBP events should raise ValueError."""
    timeline = [
        {"event_type": "social", "content": "Tweet 1"},
        {"event_type": "social", "content": "Tweet 2"},
    ]
    
    with pytest.raises(ValueError, match="No canonical plays"):
        build_chapters(timeline, game_id=1)


# Test 2: Determinism

def test_determinism_same_input_same_output():
    """Same PBP input must produce same chapters output."""
    timeline = create_multi_quarter_timeline()
    
    # Build chapters twice
    story1 = build_chapters(timeline, game_id=1)
    story2 = build_chapters(timeline, game_id=1)
    
    # Verify identical output
    assert story1.chapter_count == story2.chapter_count
    
    for i, (ch1, ch2) in enumerate(zip(story1.chapters, story2.chapters)):
        assert ch1.chapter_id == ch2.chapter_id, f"Chapter {i} ID mismatch"
        assert ch1.play_start_idx == ch2.play_start_idx, f"Chapter {i} start mismatch"
        assert ch1.play_end_idx == ch2.play_end_idx, f"Chapter {i} end mismatch"
        assert ch1.play_count == ch2.play_count, f"Chapter {i} count mismatch"
        assert ch1.reason_codes == ch2.reason_codes, f"Chapter {i} reasons mismatch"


def test_determinism_order_preserved():
    """Chapters must be in chronological order."""
    timeline = create_multi_quarter_timeline()
    story = build_chapters(timeline, game_id=1)
    
    for i in range(1, len(story.chapters)):
        prev_start = story.chapters[i - 1].play_start_idx
        curr_start = story.chapters[i].play_start_idx
        
        assert curr_start > prev_start, (
            f"Chapters not in chronological order: chapter {i-1} starts at "
            f"{prev_start}, chapter {i} starts at {curr_start}"
        )


def test_determinism_reproducible_boundaries():
    """Chapter boundaries must be reproducible."""
    timeline = create_multi_quarter_timeline()
    
    # Build chapters multiple times
    stories = [build_chapters(timeline, game_id=1) for _ in range(5)]
    
    # Verify all have same boundary points
    boundary_sets = [
        {ch.play_start_idx for ch in story.chapters}
        for story in stories
    ]
    
    assert all(bs == boundary_sets[0] for bs in boundary_sets), (
        "Chapter boundaries not reproducible across runs"
    )


# Test 3: Structural Integrity

def test_structural_integrity_contiguous_plays():
    """Plays within a chapter must be contiguous."""
    timeline = create_test_timeline(num_plays=10)
    story = build_chapters(timeline, game_id=1)
    
    for chapter in story.chapters:
        expected_indices = list(range(chapter.play_start_idx, chapter.play_end_idx + 1))
        actual_indices = [p.index for p in chapter.plays]
        
        assert actual_indices == expected_indices, (
            f"Chapter {chapter.chapter_id} has non-contiguous plays. "
            f"Expected {expected_indices}, got {actual_indices}"
        )


def test_structural_integrity_valid_boundaries():
    """Chapter boundaries must align to play indices."""
    timeline = create_multi_quarter_timeline()
    story = build_chapters(timeline, game_id=1)
    
    all_play_indices = set(range(len(timeline)))
    
    for chapter in story.chapters:
        # Start and end must be valid play indices
        assert chapter.play_start_idx in all_play_indices, (
            f"Chapter {chapter.chapter_id} start index {chapter.play_start_idx} "
            f"not in timeline"
        )
        assert chapter.play_end_idx in all_play_indices, (
            f"Chapter {chapter.chapter_id} end index {chapter.play_end_idx} "
            f"not in timeline"
        )


def test_structural_integrity_no_empty_chapters():
    """Chapters must not be empty."""
    timeline = create_multi_quarter_timeline()
    story = build_chapters(timeline, game_id=1)
    
    for chapter in story.chapters:
        assert chapter.play_count > 0, (
            f"Chapter {chapter.chapter_id} is empty"
        )
        assert len(chapter.plays) > 0, (
            f"Chapter {chapter.chapter_id} has no plays"
        )


def test_structural_integrity_chapter_validation():
    """Chapter validation should catch invalid structures."""
    timeline = create_test_timeline(num_plays=5)
    plays = [Play(index=i, event_type="pbp", raw_data=event) 
             for i, event in enumerate(timeline)]
    
    # Test: start > end
    with pytest.raises(ValueError, match="start_idx.*>.*end_idx"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=3,
            play_end_idx=1,
            plays=plays[1:4],
        )
    
    # Test: empty plays
    with pytest.raises(ValueError, match="no plays"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=2,
            plays=[],
        )
    
    # Test: non-contiguous plays
    with pytest.raises(ValueError, match="non-contiguous"):
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=3,
            plays=[plays[0], plays[2], plays[3]],  # Missing plays[1]
        )


def test_structural_integrity_story_validation():
    """GameStory validation should catch invalid structures."""
    timeline = create_test_timeline(num_plays=10)
    plays = [Play(index=i, event_type="pbp", raw_data=event) 
             for i, event in enumerate(timeline)]
    
    # Test: empty chapters
    with pytest.raises(ValueError, match="no chapters"):
        GameStory(game_id=1, chapters=[])
    
    # Test: non-contiguous chapters
    ch1 = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=2,
        plays=plays[0:3],
    )
    ch2 = Chapter(
        chapter_id="ch_002",
        play_start_idx=5,  # Gap: should be 3
        play_end_idx=7,
        plays=plays[5:8],
    )
    
    with pytest.raises(ValueError, match="not contiguous"):
        GameStory(game_id=1, chapters=[ch1, ch2])


# Test 4: Moment Regression Guard

def test_moment_regression_no_moment_objects():
    """Pipeline must not produce any Moment objects."""
    timeline = create_multi_quarter_timeline()
    story = build_chapters(timeline, game_id=1)
    
    # Verify story contains only Chapter objects
    for chapter in story.chapters:
        assert isinstance(chapter, Chapter), (
            f"Expected Chapter, got {type(chapter).__name__}"
        )
        assert not hasattr(chapter, 'type'), (
            "Chapter has 'type' attribute (looks like a Moment)"
        )
        assert not hasattr(chapter, 'moment_type'), (
            "Chapter has 'moment_type' attribute (looks like a Moment)"
        )


def test_moment_regression_no_moment_imports():
    """Chapter module must not import Moment types."""
    import app.services.chapters.types as chapter_types
    import app.services.chapters.builder as chapter_builder
    
    # Check for moment-related names in module namespace
    moment_names = [
        'Moment', 'MomentType', 'MomentReason', 'LEAD_BUILD', 'CUT', 'FLIP', 'TIE',
    ]
    
    for name in moment_names:
        assert not hasattr(chapter_types, name), (
            f"Chapter types module has Moment-related name: {name}"
        )
        assert not hasattr(chapter_builder, name), (
            f"Chapter builder module has Moment-related name: {name}"
        )


def test_moment_regression_chapter_schema():
    """Chapter schema must not contain moment-specific fields."""
    timeline = create_test_timeline(num_plays=5)
    story = build_chapters(timeline, game_id=1)
    
    chapter_dict = story.chapters[0].to_dict()
    
    # Verify no moment-specific fields
    moment_fields = [
        'type', 'moment_type', 'ladder_tier_before', 'ladder_tier_after',
        'team_in_control', 'is_notable', 'importance_score',
    ]
    
    for field in moment_fields:
        assert field not in chapter_dict, (
            f"Chapter schema contains moment field: {field}"
        )


# Test 5: JSON Schema Validation

def test_json_schema_chapter():
    """Chapter.to_dict() must produce valid JSON schema."""
    timeline = create_test_timeline(num_plays=5)
    story = build_chapters(timeline, game_id=1)
    
    chapter_dict = story.chapters[0].to_dict()
    
    # Required fields
    assert "chapter_id" in chapter_dict
    assert "play_start_idx" in chapter_dict
    assert "play_end_idx" in chapter_dict
    assert "play_count" in chapter_dict
    assert "plays" in chapter_dict
    assert "reason_codes" in chapter_dict
    
    # Type validation
    assert isinstance(chapter_dict["chapter_id"], str)
    assert isinstance(chapter_dict["play_start_idx"], int)
    assert isinstance(chapter_dict["play_end_idx"], int)
    assert isinstance(chapter_dict["play_count"], int)
    assert isinstance(chapter_dict["plays"], list)
    assert isinstance(chapter_dict["reason_codes"], list)


def test_json_schema_game_story():
    """GameStory.to_dict() must produce valid JSON schema."""
    timeline = create_multi_quarter_timeline()
    story = build_chapters(timeline, game_id=123)
    
    story_dict = story.to_dict()
    
    # Required fields
    assert "game_id" in story_dict
    assert "chapter_count" in story_dict
    assert "total_plays" in story_dict
    assert "chapters" in story_dict
    assert "compact_story" in story_dict
    assert "metadata" in story_dict
    
    # Type validation
    assert isinstance(story_dict["game_id"], int)
    assert story_dict["game_id"] == 123
    assert isinstance(story_dict["chapter_count"], int)
    assert isinstance(story_dict["total_plays"], int)
    assert isinstance(story_dict["chapters"], list)
    assert story_dict["compact_story"] is None or isinstance(story_dict["compact_story"], str)
    assert isinstance(story_dict["metadata"], dict)


# Test 6: Edge Cases

def test_edge_case_single_play():
    """Single play should create one chapter."""
    timeline = create_test_timeline(num_plays=1)
    story = build_chapters(timeline, game_id=1)
    
    assert story.chapter_count == 1
    assert story.chapters[0].play_count == 1


def test_edge_case_single_quarter():
    """All plays in one quarter should create one chapter."""
    timeline = create_test_timeline(num_plays=10, quarters=[1] * 10)
    story = build_chapters(timeline, game_id=1)
    
    assert story.chapter_count == 1
    assert story.chapters[0].play_count == 10


def test_edge_case_many_quarters():
    """Each quarter change should create a new chapter."""
    timeline = create_test_timeline(
        num_plays=8,
        quarters=[1, 1, 2, 2, 3, 3, 4, 4],
    )
    story = build_chapters(timeline, game_id=1)
    
    # Should have 4 chapters (one per quarter)
    assert story.chapter_count == 4


def test_edge_case_metadata_preserved():
    """Game metadata should be preserved in story."""
    timeline = create_test_timeline(num_plays=5)
    metadata = {
        "home_team": "Lakers",
        "away_team": "Celtics",
        "final_score": "110-105",
    }
    
    story = build_chapters(timeline, game_id=1, metadata=metadata)
    
    assert story.metadata == metadata


# Test 7: Integration Test

def test_integration_full_pipeline():
    """Full pipeline: timeline → plays → chapters → story."""
    # Create realistic timeline
    timeline = []
    for q in [1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4]:
        timeline.append({
            "event_type": "pbp",
            "quarter": q,
            "play_id": len(timeline),
            "description": f"Play in Q{q}",
            "home_score": len(timeline),
            "away_score": len(timeline),
            "game_clock": "10:00",
        })
    
    # Build story
    story = build_chapters(timeline, game_id=999, metadata={"sport": "NBA"})
    
    # Validate structure
    assert story.game_id == 999
    assert story.chapter_count == 4  # 4 quarters
    assert story.total_plays == 20
    assert story.metadata["sport"] == "NBA"
    
    # Validate each chapter
    for i, chapter in enumerate(story.chapters):
        assert chapter.chapter_id == f"ch_{i+1:03d}"
        assert chapter.play_count == 5  # 5 plays per quarter
        assert len(chapter.plays) == 5
        
        # Verify plays are contiguous
        for j, play in enumerate(chapter.plays):
            expected_idx = i * 5 + j
            assert play.index == expected_idx
    
    # Validate JSON serialization
    story_dict = story.to_dict()
    assert len(story_dict["chapters"]) == 4
    
    # Validate no moment artifacts
    for chapter in story.chapters:
        assert not hasattr(chapter, 'type')
        assert not hasattr(chapter, 'moment_type')
