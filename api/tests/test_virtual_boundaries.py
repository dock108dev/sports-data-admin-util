"""
Unit tests for Phase 1.1: Candidate Boundary System.

Tests cover:
1. Virtual boundary detection (runs, lead changes, ties)
2. Boundary type classification (HARD vs SOFT)
3. Backward compatibility (no change to chapter counts)
4. Serialization (to_dict with and without debug)
"""

import pytest
from typing import Any

from app.services.chapters import (
    Play,
    Chapter,
    build_chapters,
    BoundaryType,
    BoundaryMarker,
    VirtualBoundaryReason,
    get_boundary_type_for_reasons,
    detect_virtual_boundaries,
)
from app.services.chapters.types import TimeRange


# =============================================================================
# Test Fixtures
# =============================================================================


def create_play(
    index: int,
    home_score: int = 0,
    away_score: int = 0,
    quarter: int = 1,
    description: str = "",
) -> Play:
    """Create a test Play object."""
    return Play(
        index=index,
        event_type="pbp",
        raw_data={
            "event_type": "pbp",
            "quarter": quarter,
            "home_score": home_score,
            "away_score": away_score,
            "description": description,
            "game_clock": "12:00",
        },
    )


def create_chapter_with_plays(plays: list[Play], reason_codes: list[str] | None = None) -> Chapter:
    """Create a test Chapter object."""
    if not plays:
        raise ValueError("Cannot create chapter with no plays")
    return Chapter(
        chapter_id="ch_001",
        play_start_idx=plays[0].index,
        play_end_idx=plays[-1].index,
        plays=plays,
        reason_codes=reason_codes or ["PERIOD_START"],
        period=1,
        time_range=TimeRange(start="12:00", end="10:00"),
    )


def create_timeline_with_scores(
    scores: list[tuple[int, int]],
    quarter: int = 1,
) -> list[dict[str, Any]]:
    """Create a timeline with specified (home, away) score snapshots.

    Args:
        scores: List of (home_score, away_score) tuples for each play
        quarter: Quarter number for all plays

    Returns:
        List of timeline events
    """
    timeline = []
    for i, (home, away) in enumerate(scores):
        timeline.append({
            "event_type": "pbp",
            "quarter": quarter,
            "play_id": i,
            "description": f"Play {i}",
            "home_score": home,
            "away_score": away,
            "game_clock": f"{12 - i}:00",
        })
    return timeline


# =============================================================================
# Test 1: RUN_START Detection
# =============================================================================


def test_detect_run_start_6_points():
    """Run of 6+ unanswered points should create RUN_START marker."""
    # Home team scores 6 unanswered (0-0 -> 6-0)
    plays = [
        create_play(0, home_score=0, away_score=0),
        create_play(1, home_score=2, away_score=0),  # +2
        create_play(2, home_score=4, away_score=0),  # +2
        create_play(3, home_score=6, away_score=0),  # +2 = 6 total (threshold)
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    assert len(boundaries) == 1
    assert boundaries[0].reason == VirtualBoundaryReason.RUN_START.value
    assert boundaries[0].team_id == "home"
    assert boundaries[0].boundary_type == BoundaryType.VIRTUAL


def test_detect_run_start_8_points():
    """Larger runs should also create RUN_START marker."""
    # Away team scores 8 unanswered (5-0 -> 5-8)
    plays = [
        create_play(0, home_score=5, away_score=0),
        create_play(1, home_score=5, away_score=3),  # +3
        create_play(2, home_score=5, away_score=5),  # +2
        create_play(3, home_score=5, away_score=8),  # +3 = 8 total
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    run_starts = [b for b in boundaries if b.reason == VirtualBoundaryReason.RUN_START.value]
    assert len(run_starts) == 1
    assert run_starts[0].team_id == "away"


def test_no_run_start_under_threshold():
    """5 unanswered points should NOT create RUN_START marker."""
    plays = [
        create_play(0, home_score=0, away_score=0),
        create_play(1, home_score=2, away_score=0),  # +2
        create_play(2, home_score=5, away_score=0),  # +3 = 5 total (under threshold)
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    run_starts = [b for b in boundaries if b.reason == VirtualBoundaryReason.RUN_START.value]
    assert len(run_starts) == 0


# =============================================================================
# Test 2: RUN_END Detection
# =============================================================================


def test_detect_run_end():
    """Opposing team scoring after a run should create RUN_END marker."""
    # Home runs 6, then away scores
    plays = [
        create_play(0, home_score=0, away_score=0),
        create_play(1, home_score=2, away_score=0),
        create_play(2, home_score=4, away_score=0),
        create_play(3, home_score=6, away_score=0),  # RUN_START
        create_play(4, home_score=6, away_score=2),  # RUN_END
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    run_ends = [b for b in boundaries if b.reason == VirtualBoundaryReason.RUN_END.value]
    assert len(run_ends) == 1
    assert run_ends[0].team_id == "home"
    assert run_ends[0].play_index == 4


def test_no_run_end_if_run_not_started():
    """RUN_END should not appear if no run reached threshold."""
    # Home scores 4, then away scores - no run was announced
    plays = [
        create_play(0, home_score=0, away_score=0),
        create_play(1, home_score=2, away_score=0),
        create_play(2, home_score=4, away_score=0),  # Only 4 points
        create_play(3, home_score=4, away_score=2),  # Away scores
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    run_ends = [b for b in boundaries if b.reason == VirtualBoundaryReason.RUN_END.value]
    assert len(run_ends) == 0


# =============================================================================
# Test 3: LEAD_CHANGE Detection
# =============================================================================


def test_detect_lead_change():
    """Lead change should create LEAD_CHANGE marker."""
    # Home leads, then away takes lead
    plays = [
        create_play(0, home_score=5, away_score=3),   # Home leads
        create_play(1, home_score=5, away_score=6),   # Away takes lead
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    lead_changes = [b for b in boundaries if b.reason == VirtualBoundaryReason.LEAD_CHANGE.value]
    assert len(lead_changes) == 1
    assert lead_changes[0].team_id == "away"
    assert lead_changes[0].play_index == 1


def test_detect_multiple_lead_changes():
    """Multiple lead changes should all be detected."""
    plays = [
        create_play(0, home_score=5, away_score=3),   # Home leads
        create_play(1, home_score=5, away_score=6),   # Away leads
        create_play(2, home_score=8, away_score=6),   # Home leads again
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    lead_changes = [b for b in boundaries if b.reason == VirtualBoundaryReason.LEAD_CHANGE.value]
    assert len(lead_changes) == 2
    assert lead_changes[0].team_id == "away"
    assert lead_changes[1].team_id == "home"


def test_no_lead_change_from_tie():
    """Taking lead from tie is NOT a lead change."""
    plays = [
        create_play(0, home_score=5, away_score=5),   # Tied
        create_play(1, home_score=7, away_score=5),   # Home takes lead (from tie)
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    lead_changes = [b for b in boundaries if b.reason == VirtualBoundaryReason.LEAD_CHANGE.value]
    assert len(lead_changes) == 0


# =============================================================================
# Test 4: TIE_CREATION Detection
# =============================================================================


def test_detect_tie_creation():
    """Game becoming tied should create TIE_CREATION marker."""
    plays = [
        create_play(0, home_score=5, away_score=3),   # Home leads
        create_play(1, home_score=5, away_score=5),   # Tied
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    ties = [b for b in boundaries if b.reason == VirtualBoundaryReason.TIE_CREATION.value]
    assert len(ties) == 1
    assert ties[0].team_id is None
    assert ties[0].play_index == 1


def test_no_tie_creation_if_already_tied():
    """Staying tied should not create TIE_CREATION marker."""
    plays = [
        create_play(0, home_score=5, away_score=5),   # Already tied
        create_play(1, home_score=5, away_score=5),   # Still tied (no scoring)
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    ties = [b for b in boundaries if b.reason == VirtualBoundaryReason.TIE_CREATION.value]
    assert len(ties) == 0


# =============================================================================
# Test 5: Empty/Edge Cases
# =============================================================================


def test_no_virtual_boundaries_empty_chapter():
    """Empty plays list should return empty boundaries."""
    # Cannot create a valid Chapter with no plays, so test the function directly
    plays = [create_play(0, home_score=0, away_score=0)]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    # Single play, no score changes - no boundaries
    assert len(boundaries) == 0


def test_no_virtual_boundaries_no_scoring():
    """Plays with no scoring should have no virtual boundaries."""
    plays = [
        create_play(0, home_score=0, away_score=0),
        create_play(1, home_score=0, away_score=0),
        create_play(2, home_score=0, away_score=0),
    ]
    chapter = create_chapter_with_plays(plays)

    boundaries = detect_virtual_boundaries(chapter)

    assert len(boundaries) == 0


# =============================================================================
# Test 6: Boundary Type Classification
# =============================================================================


def test_boundary_type_hard_for_period_start():
    """PERIOD_START should classify as HARD."""
    boundary_type = get_boundary_type_for_reasons(["PERIOD_START"])
    assert boundary_type == BoundaryType.HARD


def test_boundary_type_hard_for_overtime():
    """OVERTIME_START should classify as HARD."""
    boundary_type = get_boundary_type_for_reasons(["OVERTIME_START"])
    assert boundary_type == BoundaryType.HARD


def test_boundary_type_soft_for_timeout():
    """TIMEOUT should classify as SOFT."""
    boundary_type = get_boundary_type_for_reasons(["TIMEOUT"])
    assert boundary_type == BoundaryType.SOFT


def test_boundary_type_soft_for_review():
    """REVIEW should classify as SOFT."""
    boundary_type = get_boundary_type_for_reasons(["REVIEW"])
    assert boundary_type == BoundaryType.SOFT


def test_boundary_type_hard_takes_precedence():
    """HARD reason should take precedence over SOFT."""
    boundary_type = get_boundary_type_for_reasons(["TIMEOUT", "PERIOD_START"])
    assert boundary_type == BoundaryType.HARD


def test_boundary_type_unknown_defaults_to_soft():
    """Unknown reason code should default to SOFT."""
    boundary_type = get_boundary_type_for_reasons(["UNKNOWN_REASON"])
    assert boundary_type == BoundaryType.SOFT


# =============================================================================
# Test 7: Chapter Count Unchanged
# =============================================================================


def test_chapter_count_unchanged_with_virtual_boundaries():
    """Adding virtual boundary detection should NOT change chapter count."""
    # Create a timeline where we know a run will occur
    scores = [
        (0, 0), (2, 0), (4, 0), (6, 0),  # Home run of 6
        (6, 2), (6, 4), (6, 6),           # Away answers
    ]
    timeline = create_timeline_with_scores(scores)

    story = build_chapters(timeline, game_id=1)

    # Should still be exactly 1 chapter (no structural boundaries)
    assert story.chapter_count == 1

    # But the chapter should have virtual boundaries
    chapter = story.chapters[0]
    assert len(chapter.virtual_boundaries) > 0


def test_multi_quarter_chapter_count_unchanged():
    """Multi-quarter games should have same chapter count as before."""
    # 4 quarters, 5 plays each
    timeline = []
    for q in range(1, 5):
        for p in range(5):
            play_idx = (q - 1) * 5 + p
            timeline.append({
                "event_type": "pbp",
                "quarter": q,
                "play_id": play_idx,
                "description": f"Play {play_idx}",
                "home_score": play_idx * 2,
                "away_score": play_idx * 2 + 1,
                "game_clock": f"{12 - p}:00",
            })

    story = build_chapters(timeline, game_id=1)

    # Should have 4 chapters (one per quarter)
    assert story.chapter_count == 4

    # Each chapter should have boundary_type set
    for chapter in story.chapters:
        assert chapter.boundary_type is not None


# =============================================================================
# Test 8: Backward Compatible to_dict
# =============================================================================


def test_to_dict_without_debug_excludes_virtual_boundaries():
    """to_dict() without debug should NOT include virtual_boundaries."""
    plays = [
        create_play(0, home_score=0, away_score=0),
        create_play(1, home_score=6, away_score=0),  # Run of 6
    ]
    chapter = create_chapter_with_plays(plays)
    chapter.boundary_type = BoundaryType.HARD
    chapter.virtual_boundaries = detect_virtual_boundaries(chapter)

    result = chapter.to_dict(include_debug=False)

    assert "virtual_boundaries" not in result
    assert "boundary_type" in result  # boundary_type is always included


def test_to_dict_with_debug_includes_virtual_boundaries():
    """to_dict(include_debug=True) should include virtual_boundaries."""
    plays = [
        create_play(0, home_score=0, away_score=0),
        create_play(1, home_score=2, away_score=0),
        create_play(2, home_score=4, away_score=0),
        create_play(3, home_score=6, away_score=0),  # Run of 6
    ]
    chapter = create_chapter_with_plays(plays)
    chapter.boundary_type = BoundaryType.HARD
    chapter.virtual_boundaries = detect_virtual_boundaries(chapter)

    result = chapter.to_dict(include_debug=True)

    assert "virtual_boundaries" in result
    assert len(result["virtual_boundaries"]) > 0
    assert result["virtual_boundaries"][0]["reason"] == VirtualBoundaryReason.RUN_START.value


def test_boundary_marker_to_dict():
    """BoundaryMarker.to_dict() should serialize correctly."""
    marker = BoundaryMarker(
        boundary_type=BoundaryType.VIRTUAL,
        play_index=5,
        reason=VirtualBoundaryReason.LEAD_CHANGE.value,
        team_id="home",
        score_snapshot=(10, 8),
    )

    result = marker.to_dict()

    assert result["boundary_type"] == "VIRTUAL"
    assert result["play_index"] == 5
    assert result["reason"] == "LEAD_CHANGE"
    assert result["team_id"] == "home"
    assert result["score_snapshot"] == {"home": 10, "away": 8}


# =============================================================================
# Test 9: Integration with build_chapters
# =============================================================================


def test_build_chapters_assigns_boundary_type():
    """build_chapters should assign boundary_type to all chapters."""
    timeline = []
    for q in range(1, 3):
        for p in range(3):
            play_idx = (q - 1) * 3 + p
            timeline.append({
                "event_type": "pbp",
                "quarter": q,
                "play_id": play_idx,
                "description": f"Play {play_idx}",
                "home_score": 0,
                "away_score": 0,
                "game_clock": "10:00",
            })

    story = build_chapters(timeline, game_id=1)

    for chapter in story.chapters:
        assert chapter.boundary_type is not None
        assert chapter.boundary_type in (BoundaryType.HARD, BoundaryType.SOFT)


def test_build_chapters_detects_virtual_boundaries():
    """build_chapters should detect virtual boundaries in chapters."""
    # Create a scoring run within Q1
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "home_score": 0, "away_score": 0, "game_clock": "12:00"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "home_score": 2, "away_score": 0, "game_clock": "11:00"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "home_score": 4, "away_score": 0, "game_clock": "10:00"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "home_score": 6, "away_score": 0, "game_clock": "9:00"},
    ]

    story = build_chapters(timeline, game_id=1)

    assert story.chapter_count == 1
    chapter = story.chapters[0]

    # Should have RUN_START virtual boundary
    run_starts = [vb for vb in chapter.virtual_boundaries
                  if vb.reason == VirtualBoundaryReason.RUN_START.value]
    assert len(run_starts) == 1
