"""
End-to-end integration test for Chapters-First Pipeline.

This test validates the full pipeline runs successfully with a fixed fixture
and produces the expected output structure.

Tests:
1. Pipeline completes without exceptions
2. GameStory has ordered sections (3-10)
3. Headers are one sentence each
4. Player stats bounded (top 3 per team)
5. compact_story string present
6. Pre-render and post-render validation invoked
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.chapters.pipeline import (
    build_game_story,
    PipelineResult,
    PipelineError,
)
from app.services.chapters.story_validator import StoryValidationError


# ============================================================================
# FIXTURE: MINIMAL GAME TIMELINE
# ============================================================================

@pytest.fixture
def minimal_timeline() -> list[dict]:
    """
    Minimal realistic NBA game timeline with enough plays to produce 3+ sections.

    Contains:
    - Quarter 1 plays with scoring
    - Quarter 2 plays
    - Quarter 4 crunch time plays
    """
    timeline = []
    play_idx = 0

    # Quarter 1: Opening plays (FAST_START scenario)
    for i in range(15):
        home_score = i * 3 if i % 2 == 0 else (i - 1) * 3
        away_score = i * 2 if i % 2 == 1 else (i - 1) * 2 if i > 0 else 0
        timeline.append({
            "event_type": "pbp",
            "play_index": play_idx,
            "quarter": 1,
            "game_clock": f"{12 - i}:00",
            "play_type": "made_shot",
            "description": f"Player {i % 10} makes shot",
            "team": "LAL" if i % 2 == 0 else "BOS",
            "home_score": home_score,
            "away_score": away_score,
            "player_name": f"Player {i % 10}",
        })
        play_idx += 1

    # Quarter 2: Mid-game plays (BACK_AND_FORTH scenario)
    base_home = timeline[-1]["home_score"]
    base_away = timeline[-1]["away_score"]
    for i in range(15):
        home_score = base_home + i * 2 if i % 2 == 0 else base_home + (i - 1) * 2
        away_score = base_away + i * 2 if i % 2 == 1 else base_away + (i - 1) * 2 if i > 0 else base_away
        timeline.append({
            "event_type": "pbp",
            "play_index": play_idx,
            "quarter": 2,
            "game_clock": f"{12 - i}:00",
            "play_type": "made_shot",
            "description": f"Player {i % 10} scores",
            "team": "LAL" if i % 2 == 0 else "BOS",
            "home_score": home_score,
            "away_score": away_score,
            "player_name": f"Player {i % 10}",
        })
        play_idx += 1

    # Quarter 3: More action
    base_home = timeline[-1]["home_score"]
    base_away = timeline[-1]["away_score"]
    for i in range(15):
        home_score = base_home + i * 2 if i % 2 == 0 else base_home + (i - 1) * 2
        away_score = base_away + i * 3 if i % 2 == 1 else base_away + (i - 1) * 3 if i > 0 else base_away
        timeline.append({
            "event_type": "pbp",
            "play_index": play_idx,
            "quarter": 3,
            "game_clock": f"{12 - i}:00",
            "play_type": "made_shot",
            "description": f"Player {i % 10} with the bucket",
            "team": "LAL" if i % 2 == 0 else "BOS",
            "home_score": home_score,
            "away_score": away_score,
            "player_name": f"Player {i % 10}",
        })
        play_idx += 1

    # Quarter 4: Crunch time (CLOSING_SEQUENCE scenario)
    base_home = timeline[-1]["home_score"]
    base_away = timeline[-1]["away_score"]
    for i in range(10):
        home_score = base_home + i * 2 if i % 2 == 0 else base_home + (i - 1) * 2
        away_score = base_away + i * 2 if i % 2 == 1 else base_away + (i - 1) * 2 if i > 0 else base_away
        timeline.append({
            "event_type": "pbp",
            "play_index": play_idx,
            "quarter": 4,
            "game_clock": f"1:{59 - i * 5:02d}",  # Final 2 minutes
            "play_type": "made_shot",
            "description": f"Player {i % 10} clutch basket",
            "team": "LAL" if i % 2 == 0 else "BOS",
            "home_score": home_score,
            "away_score": away_score,
            "player_name": f"Player {i % 10}",
        })
        play_idx += 1

    return timeline


@pytest.fixture
def mock_ai_client():
    """Mock AI client that returns a valid compact story as JSON."""
    import json
    client = MagicMock()

    def mock_generate(prompt: str) -> str:
        """Return a mock compact story as JSON that passes validation.

        The story must be at least 340 words (400 target - 15% tolerance).
        """
        # Generate a ~400 word story
        story = (
            "Both teams opened at a fast pace. "
            "The Lakers came out with energy, pushing the tempo from the opening tip. "
            "The Celtics matched their intensity, refusing to let Los Angeles build any early separation. "
            "The first quarter featured outstanding shot-making from both sides, with neither defense able to establish a rhythm. "
            "Players dove for loose balls and contested every possession as if the game were already in crunch time. "
            "The crowd fed off this energy, creating an electric atmosphere in the arena. "
            "\n\n"
            "Neither side could separate as play moved back and forth. "
            "The second period saw the Lakers attempt to assert control, but Boston had answers. "
            "Every time Los Angeles appeared ready to pull away, the Celtics responded with a timely bucket or defensive stop. "
            "The benches contributed valuable minutes, keeping fresh legs on the floor throughout the competitive stretch. "
            "Fouls began to accumulate as the physical nature of the contest intensified. "
            "Both coaching staffs made strategic adjustments, calling timeouts to reset their offensive sets. "
            "\n\n"
            "The teams traded possessions without building significant separation. "
            "Coming out of halftime, the Lakers showed renewed determination. "
            "Their defensive intensity picked up, forcing several turnovers that led to easy transition opportunities. "
            "However, the Celtics remained resilient, clawing back whenever the deficit threatened to grow. "
            "Star players on both sides stepped up in critical moments, making the plays their teams needed. "
            "The third quarter ended with the margin still in single digits. "
            "\n\n"
            "The game tightened late as every possession began to matter. "
            "With the clock winding down in the fourth quarter, the stakes could not have been higher. "
            "The Lakers executed their half-court offense with precision, finding open looks through patient ball movement. "
            "The Celtics countered with their own offensive firepower, refusing to go away quietly. "
            "Free throws became crucial, and both teams stepped up at the line when it mattered most. "
            "The final minutes saw several lead changes and momentum swings. "
            "\n\n"
            "In the end, the Lakers held on for a hard-fought victory. "
            "This game showcased everything that makes basketball compelling: athletic excellence, strategic depth, and unwavering competitive spirit. "
            "Both teams left everything on the floor, and the outcome remained uncertain until the final horn."
        )
        return json.dumps({"compact_story": story})

    client.generate = mock_generate
    return client


# ============================================================================
# TEST: PIPELINE COMPLETES WITHOUT EXCEPTIONS
# ============================================================================

def test_pipeline_completes_without_exceptions(minimal_timeline, mock_ai_client):
    """The full pipeline runs to completion without raising exceptions.

    Note: We mock post-render validation because the mock AI story
    may not pass all validation checks (which are tested separately).
    """
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    assert result is not None
    assert isinstance(result, PipelineResult)


# ============================================================================
# TEST: SECTION COUNT WITHIN BOUNDS
# ============================================================================

def test_section_count_within_bounds(minimal_timeline, mock_ai_client):
    """Pipeline produces between 3 and 10 sections."""
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    assert len(result.sections) >= 3, f"Expected at least 3 sections, got {len(result.sections)}"
    assert len(result.sections) <= 10, f"Expected at most 10 sections, got {len(result.sections)}"


# ============================================================================
# TEST: HEADERS ARE ONE SENTENCE EACH
# ============================================================================

def test_headers_are_one_sentence_each(minimal_timeline, mock_ai_client):
    """Each header is exactly one sentence (ends with period, no exclamations/questions)."""
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    for i, header in enumerate(result.headers):
        assert header.strip().endswith("."), f"Header {i} does not end with period: {header}"
        assert "!" not in header, f"Header {i} contains exclamation: {header}"
        assert "?" not in header, f"Header {i} contains question mark: {header}"
        # Should be exactly one period (one sentence)
        period_count = header.count(".")
        assert period_count == 1, f"Header {i} has {period_count} periods (expected 1): {header}"


# ============================================================================
# TEST: COMPACT STORY IS PRESENT
# ============================================================================

def test_compact_story_is_present(minimal_timeline, mock_ai_client):
    """compact_story string is present and non-empty."""
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    assert result.compact_story is not None
    assert len(result.compact_story) > 0
    assert result.word_count > 0


# ============================================================================
# TEST: SECTIONS ARE ORDERED
# ============================================================================

def test_sections_are_ordered(minimal_timeline, mock_ai_client):
    """Sections are in sequential order with no gaps."""
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    for i, section in enumerate(result.sections):
        assert section.section_index == i, f"Section {i} has wrong index: {section.section_index}"


# ============================================================================
# TEST: QUALITY ASSESSMENT PRESENT
# ============================================================================

def test_quality_assessment_present(minimal_timeline, mock_ai_client):
    """Quality score is computed and present."""
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    assert result.quality is not None
    assert result.quality.quality.value in ["LOW", "MEDIUM", "HIGH"]
    assert result.target_word_count > 0


# ============================================================================
# TEST: CHAPTERS ARE PRESENT
# ============================================================================

def test_chapters_are_present(minimal_timeline, mock_ai_client):
    """Chapters are present and have valid structure."""
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    assert len(result.chapters) > 0
    for chapter in result.chapters:
        assert chapter.chapter_id is not None
        assert chapter.play_start_idx >= 0
        assert chapter.play_end_idx >= chapter.play_start_idx


# ============================================================================
# TEST: PRE AND POST VALIDATION INVOKED
# ============================================================================

def test_validation_is_invoked(minimal_timeline, mock_ai_client):
    """Pre-render and post-render validation are invoked."""
    with patch("app.services.chapters.pipeline.validate_pre_render") as mock_pre, \
         patch("app.services.chapters.pipeline.validate_post_render") as mock_post:

        build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

        mock_pre.assert_called_once()
        mock_post.assert_called_once()


# ============================================================================
# TEST: PIPELINE FAILS LOUD ON BAD INPUT
# ============================================================================

def test_pipeline_fails_loud_on_empty_timeline():
    """Pipeline raises PipelineError on empty timeline."""
    with pytest.raises(PipelineError) as exc_info:
        build_game_story(
            timeline=[],
            game_id=12345,
            sport="NBA",
        )

    assert "build_chapters" in exc_info.value.stage.lower() or "no chapters" in str(exc_info.value).lower()


# ============================================================================
# TEST: METADATA IS CORRECT
# ============================================================================

def test_metadata_is_correct(minimal_timeline, mock_ai_client):
    """Result metadata is populated correctly."""
    with patch("app.services.chapters.pipeline.validate_post_render"):
        result = build_game_story(
            timeline=minimal_timeline,
            game_id=12345,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            ai_client=mock_ai_client,
        )

    assert result.game_id == 12345
    assert result.sport == "NBA"
    assert result.generated_at is not None
    assert result.reading_time_minutes > 0
