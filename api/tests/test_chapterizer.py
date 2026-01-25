"""
Unit tests for Chapterizer.

These tests validate the chapterization logic for NBA.
"""

import pytest

from app.services.chapters import Chapterizer, ChapterizerConfig


# Test 1: Full Coverage / Contiguity


def test_full_coverage_all_plays_in_chapters():
    """All plays must be covered by chapters (no gaps, no overlaps)."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": i, "description": f"Play {i}"}
        for i in range(20)
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Collect all play indices from chapters
    covered_indices = set()
    for chapter in story.chapters:
        for play in chapter.plays:
            assert play.index not in covered_indices, (
                f"Play {play.index} in multiple chapters"
            )
            covered_indices.add(play.index)

    # All plays should be covered
    expected_indices = set(range(len(timeline)))
    assert covered_indices == expected_indices


def test_contiguity_chapters_ordered_no_overlap():
    """Chapters must be ordered and non-overlapping."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": i, "description": f"Play {i}"}
        for i in range(10)
    ] + [
        {"event_type": "pbp", "quarter": 2, "play_id": i, "description": f"Play {i}"}
        for i in range(10, 20)
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Check ordering and non-overlap
    for i in range(len(story.chapters) - 1):
        curr = story.chapters[i]
        next_ch = story.chapters[i + 1]

        # Current chapter must end before next starts
        assert curr.play_end_idx < next_ch.play_start_idx, (
            f"Chapters {curr.chapter_id} and {next_ch.chapter_id} overlap"
        )


# Test 2: Hard Boundary Test


def test_hard_boundary_quarter_breaks():
    """Quarter boundaries must always create breaks."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Q1 play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Q1 play 2"},
        {"event_type": "pbp", "quarter": 2, "play_id": 2, "description": "Q2 play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 3, "description": "Q2 play 2"},
        {"event_type": "pbp", "quarter": 3, "play_id": 4, "description": "Q3 play 1"},
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should have at least 3 chapters (Q1, Q2, Q3)
    assert story.chapter_count >= 3

    # Check reason codes include PERIOD_START
    period_starts = [ch for ch in story.chapters if "PERIOD_START" in ch.reason_codes]
    assert len(period_starts) >= 3


def test_hard_boundary_reason_codes():
    """Hard boundaries must have correct reason codes."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Q1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Q2"},
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # First chapter should have PERIOD_START
    assert "PERIOD_START" in story.chapters[0].reason_codes

    # Second chapter should have PERIOD_START (Q2)
    assert "PERIOD_START" in story.chapters[1].reason_codes


# Test 3: Timeout/Review Boundary Test


def test_timeout_creates_boundary():
    """Timeout should create a chapter break."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Play 2"},
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 2,
            "description": "Timeout: Lakers",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 3,
            "description": "Play after timeout",
        },
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should have at least 2 chapters (before and after timeout)
    assert story.chapter_count >= 2

    # Check for TIMEOUT reason code
    timeout_chapters = [ch for ch in story.chapters if "TIMEOUT" in ch.reason_codes]
    assert len(timeout_chapters) > 0


def test_review_creates_boundary():
    """Review should create a chapter break."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 1,
            "description": "Instant replay review",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 2,
            "description": "Play after review",
        },
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Check for REVIEW reason code
    review_chapters = [ch for ch in story.chapters if "REVIEW" in ch.reason_codes]
    assert len(review_chapters) > 0


def test_reset_cluster_collapse():
    """Consecutive timeouts/reviews should collapse into single boundary."""
    config = ChapterizerConfig(
        collapse_reset_clusters=True, reset_cluster_window_plays=3
    )

    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 1,
            "description": "Timeout: Lakers",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 2,
            "description": "Substitution",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 3,
            "description": "Instant replay review",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 4,
            "description": "Play after cluster",
        },
    ]

    chapterizer = Chapterizer(config)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should not create micro-chapters for each reset event
    # Exact count depends on implementation, but should be minimal
    assert story.chapter_count <= 3  # Q1 start + reset cluster + after


# Test 4: Non-Boundary Guard Test


def test_non_boundary_scoring_sequence():
    """Scoring plays without timeout/review should not create extra chapters."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 1,
            "description": "LeBron makes layup",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 2,
            "description": "Tatum makes 3-pointer",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 3,
            "description": "Davis makes jumper",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 4,
            "description": "Brown makes layup",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 5,
            "description": "Westbrook makes 3-pointer",
        },
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should be 1 chapter (no boundaries within Q1 for just scores)
    assert story.chapter_count == 1


def test_non_boundary_free_throws():
    """Free throws should not create boundaries."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Jump ball"},
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 1,
            "description": "Free throw made",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 2,
            "description": "Free throw made",
        },
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": 3,
            "description": "Free throw missed",
        },
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should be 1 chapter
    assert story.chapter_count == 1


# Test 5: Min Chapter Size Test


def test_min_chapter_size_enforcement():
    """Chapters should respect minimum size (if configured)."""
    config = ChapterizerConfig(min_plays_per_chapter=2)

    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": i, "description": f"Play {i}"}
        for i in range(10)
    ]

    chapterizer = Chapterizer(config)
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # All chapters should have at least min_plays_per_chapter
    for chapter in story.chapters:
        assert len(chapter.plays) >= config.min_plays_per_chapter


# Test 6: Determinism Test


def test_determinism_same_input_same_output():
    """Same input should produce identical chapters."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Timeout"},
        {"event_type": "pbp", "quarter": 2, "play_id": 2, "description": "Q2"},
    ]

    chapterizer = Chapterizer()

    story1 = chapterizer.chapterize(timeline, game_id=1, sport="NBA")
    story2 = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should have same number of chapters
    assert story1.chapter_count == story2.chapter_count

    # Each chapter should be identical
    for ch1, ch2 in zip(story1.chapters, story2.chapters):
        assert ch1.chapter_id == ch2.chapter_id
        assert ch1.play_start_idx == ch2.play_start_idx
        assert ch1.play_end_idx == ch2.play_end_idx
        assert ch1.reason_codes == ch2.reason_codes


# Test 7: Integration Tests


def test_integration_full_game():
    """Full game with multiple quarters and events."""
    timeline = []

    # Q1
    for i in range(10):
        timeline.append(
            {
                "event_type": "pbp",
                "quarter": 1,
                "play_id": len(timeline),
                "description": f"Q1 play {i}",
            }
        )

    # Timeout
    timeline.append(
        {
            "event_type": "pbp",
            "quarter": 1,
            "play_id": len(timeline),
            "description": "Timeout: Lakers",
        }
    )

    # More Q1
    for i in range(5):
        timeline.append(
            {
                "event_type": "pbp",
                "quarter": 1,
                "play_id": len(timeline),
                "description": f"Q1 play {i + 10}",
            }
        )

    # Q2
    for i in range(10):
        timeline.append(
            {
                "event_type": "pbp",
                "quarter": 2,
                "play_id": len(timeline),
                "description": f"Q2 play {i}",
            }
        )

    # Q3
    for i in range(10):
        timeline.append(
            {
                "event_type": "pbp",
                "quarter": 3,
                "play_id": len(timeline),
                "description": f"Q3 play {i}",
            }
        )

    # Q4 with crunch time
    for i in range(5):
        timeline.append(
            {
                "event_type": "pbp",
                "quarter": 4,
                "play_id": len(timeline),
                "description": f"Q4 play {i}",
                "game_clock": "6:00",
                "home_score": 100,
                "away_score": 95,
            }
        )

    # Crunch time
    timeline.append(
        {
            "event_type": "pbp",
            "quarter": 4,
            "play_id": len(timeline),
            "description": "Crunch time play",
            "game_clock": "4:55",
            "home_score": 102,
            "away_score": 100,
        }
    )

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should have multiple chapters
    assert story.chapter_count >= 4  # At least Q1, Q2, Q3, Q4

    # All plays covered
    total_plays = sum(len(ch.plays) for ch in story.chapters)
    assert total_plays == len(timeline)

    # Check for expected reason codes
    reason_codes = set()
    for ch in story.chapters:
        reason_codes.update(ch.reason_codes)

    assert "PERIOD_START" in reason_codes
    assert "TIMEOUT" in reason_codes or "CRUNCH_START" in reason_codes


def test_integration_schema_valid_output():
    """Output should be schema-valid GameStory."""
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Play 2"},
    ]

    chapterizer = Chapterizer()
    story = chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should be valid GameStory
    assert story.game_id == 1
    assert story.sport == "NBA"
    assert story.chapter_count > 0
    assert story.compact_story is None  # Not generated yet

    # All chapters should be valid
    for chapter in story.chapters:
        assert chapter.chapter_id
        assert len(chapter.reason_codes) > 0
        assert chapter.play_count > 0


def test_config_customization():
    """Config should be customizable."""
    config = ChapterizerConfig(
        crunch_time_seconds=180,  # 3 minutes
        close_game_margin=3,  # 3 points
    )

    timeline = [
        {
            "event_type": "pbp",
            "quarter": 4,
            "play_id": 0,
            "description": "Play",
            "game_clock": "2:55",
            "home_score": 100,
            "away_score": 98,
        },
    ]

    chapterizer = Chapterizer(config)
    chapterizer.chapterize(timeline, game_id=1, sport="NBA")

    # Should use custom config
    assert chapterizer.config.crunch_time_seconds == 180
    assert chapterizer.config.close_game_margin == 3


def test_error_empty_timeline():
    """Empty timeline should raise error."""
    chapterizer = Chapterizer()

    with pytest.raises(ValueError, match="Timeline cannot be empty"):
        chapterizer.chapterize([], game_id=1, sport="NBA")


def test_error_non_nba_sport():
    """Non-NBA sport should raise error."""
    timeline = [{"event_type": "pbp", "quarter": 1, "play_id": 0}]
    chapterizer = Chapterizer()

    with pytest.raises(ValueError, match="only supports NBA"):
        chapterizer.chapterize(timeline, game_id=1, sport="NHL")
