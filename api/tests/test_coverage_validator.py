"""
Unit tests for Coverage Validator.

These tests deliberately try to break coverage guarantees.
"""

import pytest

from app.services.chapters import (
    Chapter,
    Play,
    GameStory,
    CoverageValidationError,
    compute_chapters_fingerprint,
    validate_chapter_coverage,
    validate_game_story_coverage,
)


# Test 1: Gap Detection


def test_gap_detection_missing_plays():
    """Chapters with index gap should fail validation."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
        Chapter(
            chapter_id="ch_002",
            play_start_idx=7,  # Gap: missing indices 5, 6
            play_end_idx=9,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(7, 10)],
            reason_codes=["TIMEOUT"],
            period=1,
        ),
    ]

    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage(chapters, fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any("Gap" in err for err in result.errors)
    assert any("5" in err and "6" in err for err in result.errors)


# Test 2: Overlap Detection


def test_overlap_detection_duplicate_indices():
    """Overlapping chapter ranges should fail validation."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=5,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(6)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
        Chapter(
            chapter_id="ch_002",
            play_start_idx=4,  # Overlaps with ch_001 (indices 4, 5)
            play_end_idx=9,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(4, 10)],
            reason_codes=["TIMEOUT"],
            period=1,
        ),
    ]

    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage(chapters, fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any("overlap" in err.lower() for err in result.errors)


# Test 3: Out-of-Order Detection


def test_out_of_order_chapters():
    """Chapters not sorted by start index should fail validation."""
    chapters = [
        Chapter(
            chapter_id="ch_002",
            play_start_idx=5,
            play_end_idx=9,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
            reason_codes=["TIMEOUT"],
            period=1,
        ),
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage(chapters, fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any("not sorted" in err for err in result.errors)


# Test 4: Wrong Plays Length


def test_wrong_plays_length():
    """Chapter with mismatched play count should fail validation."""
    # Note: Chapter __post_init__ already validates this, so this would fail at creation
    # This test validates that the validator also catches it
    # We test this by checking the validator's logic directly

    # Create valid chapters first
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    # Manually modify to create invalid state (bypassing __post_init__)
    chapters[0].__dict__["play_end_idx"] = 9  # Now says 10 plays but has 5

    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage(chapters, fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any("play count mismatch" in err for err in result.errors)


# Test 5: Boundary Coverage


def test_first_chapter_not_starting_at_zero():
    """First chapter not starting at 0 should fail validation."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=5,  # Should start at 0
            play_end_idx=9,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage(chapters, base_index=0, fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any(
        "First chapter" in err and "starts at index 5" in err for err in result.errors
    )


def test_last_chapter_not_ending_at_last_play():
    """Last chapter not ending at last play should fail validation."""
    plays = [Play(index=i, event_type="pbp", raw_data={}) for i in range(10)]

    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=7,  # Ends at 7, but last play is at 9
            plays=plays[:8],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage(chapters, plays=plays, fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any(
        "Last chapter" in err and "ends at index 7" in err for err in result.errors
    )


# Test 6: Determinism Fingerprint Test


def test_determinism_fingerprint_identical_input():
    """Same chapters should produce identical fingerprint."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
        Chapter(
            chapter_id="ch_002",
            play_start_idx=5,
            play_end_idx=9,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
            reason_codes=["TIMEOUT"],
            period=1,
        ),
    ]

    fingerprint1 = compute_chapters_fingerprint(chapters)
    fingerprint2 = compute_chapters_fingerprint(chapters)

    assert fingerprint1 == fingerprint2
    assert len(fingerprint1) == 64  # SHA256 hex digest


def test_determinism_different_chapters_different_fingerprint():
    """Different chapters should produce different fingerprint."""
    chapters1 = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    chapters2 = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=5,  # Different end index
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(6)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    fingerprint1 = compute_chapters_fingerprint(chapters1)
    fingerprint2 = compute_chapters_fingerprint(chapters2)

    assert fingerprint1 != fingerprint2


# Test 7: Reason Code Normalization Test


def test_reason_code_normalization():
    """Same chapter with reason codes in different order should produce identical fingerprint."""
    chapters1 = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["TIMEOUT", "PERIOD_START"],  # Order 1
            period=1,
        ),
    ]

    chapters2 = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START", "TIMEOUT"],  # Order 2 (reversed)
            period=1,
        ),
    ]

    fingerprint1 = compute_chapters_fingerprint(chapters1)
    fingerprint2 = compute_chapters_fingerprint(chapters2)

    # Should be identical (reason codes are sorted in fingerprint)
    assert fingerprint1 == fingerprint2


# Test 8: Valid Coverage


def test_valid_coverage_passes():
    """Valid chapters should pass validation."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
        Chapter(
            chapter_id="ch_002",
            play_start_idx=5,
            play_end_idx=9,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
            reason_codes=["TIMEOUT"],
            period=1,
        ),
    ]

    result = validate_chapter_coverage(chapters, fail_fast=True)

    assert result.passed
    assert len(result.errors) == 0
    assert result.chapter_count == 2
    assert result.chapters_fingerprint


def test_valid_game_story_coverage():
    """Valid GameStory should pass validation."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    story = GameStory(
        game_id=1,
        sport="NBA",
        chapters=chapters,
        compact_story=None,
    )

    result = validate_game_story_coverage(story, fail_fast=True)

    assert result.passed
    assert len(result.errors) == 0


# Test 9: Integration with Chapterizer


def test_integration_chapterizer_produces_valid_coverage():
    """Chapterizer should produce valid coverage."""
    from app.services.chapters import Chapterizer

    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": i, "description": f"Play {i}"}
        for i in range(20)
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should have fingerprint in metadata
    assert "chapters_fingerprint" in story.metadata

    # Validate coverage
    result = validate_game_story_coverage(story, fail_fast=True)
    assert result.passed


def test_integration_chapterizer_deterministic():
    """Chapterizer should produce deterministic fingerprints."""
    from app.services.chapters import Chapterizer

    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": i, "description": f"Play {i}"}
        for i in range(10)
    ]

    chapterizer = Chapterizer()

    story1 = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    story2 = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Fingerprints should match
    assert (
        story1.metadata["chapters_fingerprint"]
        == story2.metadata["chapters_fingerprint"]
    )


# Test 10: Play Ordering Validation


def test_play_ordering_within_chapter():
    """Plays within chapter must be in order."""
    # Note: Chapter __post_init__ already validates this, so this would fail at creation
    # This test validates that the validator also catches it

    # Create valid chapter first
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=4,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]

    # Manually modify plays to be out of order (bypassing __post_init__)
    chapters[0].__dict__["plays"] = [
        Play(index=0, event_type="pbp", raw_data={}),
        Play(index=1, event_type="pbp", raw_data={}),
        Play(index=4, event_type="pbp", raw_data={}),  # Out of order
        Play(index=3, event_type="pbp", raw_data={}),
        Play(index=2, event_type="pbp", raw_data={}),
    ]

    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage(chapters, fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any("not in order" in err for err in result.errors)


# Test 11: Fail Fast vs Collect All Errors


def test_fail_fast_false_collects_all_errors():
    """With fail_fast=False, should collect all errors."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=5,  # Error: doesn't start at 0
            play_end_idx=9,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
        Chapter(
            chapter_id="ch_002",
            play_start_idx=12,  # Error: gap from 10-11
            play_end_idx=14,
            plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(12, 15)],
            reason_codes=["TIMEOUT"],
            period=1,
        ),
    ]

    result = validate_chapter_coverage(chapters, fail_fast=False)

    assert not result.passed
    assert len(result.errors) >= 2  # At least 2 errors


# Test 12: Empty Chapters


def test_empty_chapters_list():
    """Empty chapters list should fail validation."""
    with pytest.raises(CoverageValidationError) as exc_info:
        validate_chapter_coverage([], fail_fast=True)

    result = exc_info.value.result
    assert not result.passed
    assert any("No chapters" in err for err in result.errors)
