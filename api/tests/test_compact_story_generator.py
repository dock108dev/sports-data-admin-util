"""
Unit tests for Compact Story Generator (Phase 1 Issue 12).

These tests validate input discipline, output shape, and safety.
"""

import pytest
import json

from app.services.chapters import (
    generate_compact_story,
    CompactStoryGenerationError,
    validate_compact_story_input,
)
from app.services.chapters.prompts import (
    estimate_reading_time,
    validate_compact_story_length,
    check_for_new_proper_nouns,
)


class MockAIClient:
    """Mock AI client for testing."""
    
    def __init__(self, response: dict | None = None):
        self.response = response or {
            "compact_story": "This is a mock compact story.\n\nIt has multiple paragraphs.\n\nAnd a conclusion."
        }
        self.calls = []
    
    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return json.dumps(self.response)


# Test 1: Summary-Only Input Test

def test_summary_only_input_no_raw_plays():
    """AI payload must contain only summaries, no raw plays."""
    summaries = [
        "LeBron scored early to give the Lakers a lead.",
        "The Warriors responded with a run of their own.",
    ]
    
    mock_client = MockAIClient()
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
    )
    
    # Check prompt doesn't contain raw play indicators
    prompt = mock_client.calls[0]
    assert "raw_data" not in prompt
    assert "play_by_play" not in prompt.lower()
    assert "pbp" not in prompt.lower()


def test_summary_only_input_no_story_state():
    """AI payload must not contain StoryState."""
    summaries = [
        "LeBron scored early.",
        "Warriors responded.",
    ]
    
    mock_client = MockAIClient()
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
    )
    
    # Check prompt doesn't contain StoryState indicators
    prompt = mock_client.calls[0]
    assert "story_state" not in prompt.lower()
    assert "points_so_far" not in prompt


def test_summary_only_input_contains_summaries():
    """AI payload must contain the chapter summaries."""
    summaries = [
        "LeBron scored early to give the Lakers a lead.",
        "The Warriors responded with a run of their own.",
    ]
    
    mock_client = MockAIClient()
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
    )
    
    # Check prompt contains the summaries
    prompt = mock_client.calls[0]
    assert summaries[0] in prompt
    assert summaries[1] in prompt


# Test 2: Output Non-Empty Test

def test_output_non_empty():
    """Compact story must be non-empty."""
    summaries = ["Summary 1", "Summary 2"]
    
    mock_client = MockAIClient()
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
    )
    
    assert result.compact_story
    assert len(result.compact_story) > 0


def test_output_empty_error():
    """Empty compact story should raise error."""
    summaries = ["Summary 1"]
    
    mock_client = MockAIClient({"compact_story": ""})
    
    with pytest.raises(CompactStoryGenerationError, match="empty"):
        generate_compact_story(
            chapter_summaries=summaries,
            ai_client=mock_client,
        )


def test_output_minimum_length():
    """Compact story should meet minimum length."""
    summaries = ["Summary 1", "Summary 2"]
    
    # Generate long enough story
    long_story = " ".join(["word"] * 800)  # ~4 min at 200 wpm
    mock_client = MockAIClient({"compact_story": long_story})
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
    )
    
    # Should have reading time estimate
    assert result.reading_time_minutes > 0


# Test 3: No Contradiction Test

def test_no_new_proper_nouns():
    """Compact story should not introduce new proper nouns."""
    summaries = [
        "LeBron James scored early.",
        "Stephen Curry responded.",
    ]
    
    compact_story = "LeBron James and Stephen Curry battled throughout."
    
    # Should find no new nouns
    new_nouns = check_for_new_proper_nouns(compact_story, summaries)
    assert len(new_nouns) == 0


def test_detects_new_proper_nouns():
    """Should detect new proper nouns not in summaries."""
    summaries = [
        "LeBron scored early.",
        "Curry responded.",
    ]
    
    compact_story = "LeBron and Curry battled, while Durant watched."
    
    # Should detect Durant as new
    new_nouns = check_for_new_proper_nouns(compact_story, summaries)
    assert "Durant" in new_nouns


def test_integration_new_nouns_warning():
    """Generation should warn about new proper nouns."""
    summaries = ["LeBron scored.", "Curry responded."]
    
    # Story with new name
    story_with_new = "LeBron and Curry battled, while Durant watched from the bench."
    mock_client = MockAIClient({"compact_story": story_with_new})
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
        validate_output=True,
    )
    
    # Should detect new nouns
    assert result.new_nouns_detected is not None
    assert "Durant" in result.new_nouns_detected


# Test 4: Structure Test

def test_structure_multiple_paragraphs():
    """Compact story should have multiple paragraphs."""
    summaries = ["Summary 1", "Summary 2", "Summary 3"]
    
    # Story with paragraphs
    story = "Opening paragraph.\n\nMiddle paragraph.\n\nClosing paragraph."
    mock_client = MockAIClient({"compact_story": story})
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
    )
    
    # Should have paragraph breaks
    assert "\n\n" in result.compact_story


def test_structure_has_content():
    """Compact story should have substantial content."""
    summaries = ["Summary 1", "Summary 2"]
    
    mock_client = MockAIClient()
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
    )
    
    # Should have reasonable word count
    assert result.word_count > 10


# Test 5: Determinism (Prompt-Level) Test

def test_determinism_identical_summaries():
    """Identical summaries should produce identical prompts."""
    summaries = ["Summary 1", "Summary 2"]
    
    mock_client1 = MockAIClient()
    mock_client2 = MockAIClient()
    
    result1 = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client1,
    )
    
    result2 = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client2,
    )
    
    # Prompts should be identical
    assert mock_client1.calls[0] == mock_client2.calls[0]


# Test 6: Input Validation

def test_input_validation_empty_summaries():
    """Empty summaries should raise error."""
    with pytest.raises(CompactStoryGenerationError, match="No chapter summaries"):
        generate_compact_story(
            chapter_summaries=[],
            ai_client=MockAIClient(),
        )


def test_input_validation_empty_summary_item():
    """Empty summary item should raise error."""
    summaries = ["Summary 1", "", "Summary 3"]
    
    with pytest.raises(CompactStoryGenerationError, match="empty summary"):
        generate_compact_story(
            chapter_summaries=summaries,
            ai_client=MockAIClient(),
        )


def test_input_validation_titles_mismatch():
    """Mismatched titles and summaries should raise error."""
    summaries = ["Summary 1", "Summary 2"]
    titles = ["Title 1"]  # Mismatch!
    
    with pytest.raises(CompactStoryGenerationError, match="mismatch"):
        generate_compact_story(
            chapter_summaries=summaries,
            chapter_titles=titles,
            ai_client=MockAIClient(),
        )


def test_validate_input_function():
    """validate_compact_story_input should work."""
    summaries = ["Summary 1", "Summary 2"]
    
    result = validate_compact_story_input(summaries)
    
    assert result["valid"]
    assert result["chapter_count"] == 2


# Test 7: Reading Time Estimation

def test_reading_time_estimation():
    """Reading time should be estimated correctly."""
    # 200 words at 200 wpm = 1 minute
    text = " ".join(["word"] * 200)
    
    reading_time = estimate_reading_time(text)
    
    assert 0.9 <= reading_time <= 1.1  # ~1 minute


def test_reading_time_validation():
    """Reading time validation should work."""
    # Too short (< 4 min)
    short_text = " ".join(["word"] * 400)  # ~2 min
    result = validate_compact_story_length(short_text)
    assert not result["valid"]
    assert "short" in result["issues"][0].lower()
    
    # Just right (4-12 min)
    good_text = " ".join(["word"] * 1000)  # ~5 min
    result = validate_compact_story_length(good_text)
    assert result["valid"]
    
    # Too long (> 12 min)
    long_text = " ".join(["word"] * 3000)  # ~15 min
    result = validate_compact_story_length(long_text)
    assert not result["valid"]
    assert "long" in result["issues"][0].lower()


# Test 8: Mock Mode

def test_mock_mode_no_ai_client():
    """Should work without AI client (mock mode)."""
    summaries = ["Summary 1", "Summary 2"]
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=None,  # No client
    )
    
    # Should return mock story
    assert "chapters" in result.compact_story.lower()
    assert result.reading_time_minutes > 0


# Test 9: Validation Integration

def test_validation_integration():
    """Validation should run during generation."""
    summaries = ["Summary 1", "Summary 2"]
    
    # Generate with validation
    mock_client = MockAIClient()
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
        validate_output=True,
    )
    
    # Should have validation result
    assert result.validation_result is not None
    assert "valid" in result.validation_result


def test_validation_can_be_disabled():
    """Validation can be disabled."""
    summaries = ["Summary 1", "Summary 2"]
    
    mock_client = MockAIClient()
    
    result = generate_compact_story(
        chapter_summaries=summaries,
        ai_client=mock_client,
        validate_output=False,
    )
    
    # Should not have validation result
    assert result.validation_result is None


# Test 10: Error Handling

def test_error_handling_invalid_json():
    """Invalid JSON response should raise error."""
    summaries = ["Summary 1"]
    
    class BadAIClient:
        def generate(self, prompt: str) -> str:
            return "Not JSON"
    
    with pytest.raises(CompactStoryGenerationError, match="Failed to parse"):
        generate_compact_story(
            chapter_summaries=summaries,
            ai_client=BadAIClient(),
        )


def test_error_handling_ai_exception():
    """AI client exceptions should be caught and wrapped."""
    summaries = ["Summary 1"]
    
    class FailingAIClient:
        def generate(self, prompt: str) -> str:
            raise Exception("AI service down")
    
    with pytest.raises(CompactStoryGenerationError, match="AI generation failed"):
        generate_compact_story(
            chapter_summaries=summaries,
            ai_client=FailingAIClient(),
        )
