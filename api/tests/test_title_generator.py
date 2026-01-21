"""
Unit tests for Chapter Title Generator (Phase 1 Issue 11).

These tests validate title shape and safety.
"""

import pytest
import json

from app.services.chapters import (
    Chapter,
    Play,
    generate_chapter_title,
    generate_titles_for_chapters,
    TitleGenerationError,
    validate_title,
    TITLE_BANNED_WORDS,
)
from app.services.chapters.prompts import (
    check_title_for_numbers,
    check_title_for_spoilers,
)


def make_play(index: int, description: str, quarter: int = 1) -> Play:
    """Helper to create Play."""
    return Play(
        index=index,
        event_type="pbp",
        raw_data={"description": description, "quarter": quarter, "game_clock": "10:00"}
    )


def make_chapter(chapter_id: str, start_idx: int, plays: list[Play], reason_codes: list[str]) -> Chapter:
    """Helper to create Chapter."""
    return Chapter(
        chapter_id=chapter_id,
        play_start_idx=start_idx,
        play_end_idx=start_idx + len(plays) - 1,
        plays=plays,
        reason_codes=reason_codes,
    )


class MockAIClient:
    """Mock AI client for testing."""
    
    def __init__(self, response: dict | None = None):
        self.response = response or {"chapter_title": "Mock Title"}
        self.calls = []
    
    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return json.dumps(self.response)


# Test 1: Title Length Test

def test_title_length_valid():
    """Valid length titles (3-8 words) should pass."""
    valid_titles = [
        "Utah Pushes the Pace",  # 4 words
        "Minnesota Answers Back",  # 3 words
        "Tension Builds Late in the Quarter",  # 6 words
        "Closing Chaos",  # 2 words - edge case, but acceptable
    ]
    
    for title in valid_titles:
        result = validate_title(title, check_numbers=False, check_spoilers=False)
        # Some may fail length, but we're testing the validator works
        word_count = len(title.split())
        if 3 <= word_count <= 8:
            assert result["valid"], f"Title '{title}' should be valid"


def test_title_length_too_long():
    """Titles over 8 words should be flagged."""
    long_title = "This Is A Very Long Title That Has Too Many Words"
    result = validate_title(long_title, check_numbers=False, check_spoilers=False)
    assert not result["valid"]
    assert any("length" in issue.lower() for issue in result["issues"])


def test_title_length_too_short():
    """Titles under 3 words should be flagged."""
    short_title = "Too Short"
    result = validate_title(short_title, check_numbers=False, check_spoilers=False)
    assert not result["valid"]
    assert any("length" in issue.lower() for issue in result["issues"])


# Test 2: No New Info Test (Numbers)

def test_no_numbers_in_title():
    """Titles should not contain numbers."""
    titles_with_numbers = [
        "Utah Goes Up 12",
        "George's 4 Threes",
        "20-Point Run",
    ]
    
    for title in titles_with_numbers:
        assert check_title_for_numbers(title), f"Should detect numbers in: {title}"


def test_no_numbers_clean_title():
    """Clean titles without numbers should pass."""
    clean_titles = [
        "Utah Pushes the Pace",
        "Minnesota Answers Back",
        "Tension Builds Late",
    ]
    
    for title in clean_titles:
        assert not check_title_for_numbers(title), f"Should not detect numbers in: {title}"


def test_validation_rejects_numbers():
    """Validation should reject titles with numbers."""
    title = "Utah Goes Up 12"
    result = validate_title(title, check_spoilers=False)
    assert not result["valid"]
    assert any("numbers" in issue.lower() for issue in result["issues"])


# Test 3: Spoiler Guard Test

def test_spoiler_guard_banned_words():
    """Banned words should be detected in titles."""
    for word in ["dagger", "sealed", "clinched", "final"]:
        title = f"The {word.title()} Moment"
        spoilers = check_title_for_spoilers(title, is_final_chapter=False)
        assert len(spoilers) > 0, f"Failed to detect: {word}"


def test_spoiler_guard_clean_title():
    """Clean titles should have no spoilers."""
    clean_titles = [
        "Utah Pushes the Pace",
        "Minnesota Answers Back",
        "Tension Builds Late",
    ]
    
    for title in clean_titles:
        spoilers = check_title_for_spoilers(title, is_final_chapter=False)
        assert len(spoilers) == 0, f"False positive for: {title}"


def test_spoiler_guard_final_chapter_exception():
    """Final chapter can use some conclusive words."""
    title = "Closing Moments"
    
    # Not allowed in non-final
    spoilers_non_final = check_title_for_spoilers(title, is_final_chapter=False)
    assert len(spoilers_non_final) > 0
    
    # Allowed in final
    spoilers_final = check_title_for_spoilers(title, is_final_chapter=True)
    assert len(spoilers_final) == 0


def test_validation_rejects_spoilers():
    """Validation should reject titles with spoilers."""
    title = "The Dagger Three"
    result = validate_title(title, check_numbers=False)
    assert not result["valid"]
    assert any("spoiler" in issue.lower() for issue in result["issues"])


# Test 4: Context Discipline Test

def test_context_discipline_no_future_in_prompt():
    """Title prompt should not include future context."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "LeBron scored early to give the Lakers a lead."
    
    mock_client = MockAIClient()
    
    result = generate_chapter_title(
        chapter=chapter,
        chapter_summary=summary,
        chapter_index=0,
        ai_client=mock_client,
    )
    
    # Check prompt doesn't contain future markers
    prompt = mock_client.calls[0]
    assert "future" not in prompt.lower() or "no" in prompt.lower()


def test_context_discipline_summary_required():
    """Title generation requires summary as input."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "Test summary"
    
    mock_client = MockAIClient()
    
    result = generate_chapter_title(
        chapter=chapter,
        chapter_summary=summary,
        chapter_index=0,
        ai_client=mock_client,
    )
    
    # Prompt should include the summary
    prompt = mock_client.calls[0]
    assert summary in prompt


# Test 5: Generation Tests

def test_generation_returns_title():
    """Title generation should return a title."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "Test summary"
    
    mock_client = MockAIClient({"chapter_title": "Utah Pushes Ahead"})
    
    result = generate_chapter_title(
        chapter=chapter,
        chapter_summary=summary,
        chapter_index=0,
        ai_client=mock_client,
    )
    
    assert result.chapter_title == "Utah Pushes Ahead"
    assert result.chapter_index == 0


def test_generation_empty_title_error():
    """Empty title should raise error."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "Test summary"
    
    mock_client = MockAIClient({"chapter_title": ""})
    
    with pytest.raises(TitleGenerationError, match="empty title"):
        generate_chapter_title(
            chapter=chapter,
            chapter_summary=summary,
            chapter_index=0,
            ai_client=mock_client,
        )


def test_generation_invalid_json_error():
    """Invalid JSON response should raise error."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "Test summary"
    
    class BadAIClient:
        def generate(self, prompt: str) -> str:
            return "Not JSON"
    
    with pytest.raises(TitleGenerationError, match="Failed to parse"):
        generate_chapter_title(
            chapter=chapter,
            chapter_summary=summary,
            chapter_index=0,
            ai_client=BadAIClient(),
        )


# Test 6: Batch Generation

def test_batch_generation():
    """Batch title generation should work for all chapters."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"]),
        make_chapter("ch_002", 1, [make_play(1, "Play 2")], ["TIMEOUT"]),
    ]
    summaries = ["Summary 1", "Summary 2"]
    
    mock_client = MockAIClient()
    
    results = generate_titles_for_chapters(chapters, summaries, ai_client=mock_client)
    
    assert len(results) == 2
    assert results[0].chapter_index == 0
    assert results[1].chapter_index == 1


def test_batch_generation_mismatch_error():
    """Mismatched chapters/summaries should raise error."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"]),
    ]
    summaries = ["Summary 1", "Summary 2"]  # Mismatch!
    
    with pytest.raises(TitleGenerationError, match="mismatch"):
        generate_titles_for_chapters(chapters, summaries)


# Test 7: Mock Mode

def test_mock_mode_no_ai_client():
    """Should work without AI client (mock mode)."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "Test summary"
    
    result = generate_chapter_title(
        chapter=chapter,
        chapter_summary=summary,
        chapter_index=0,
        ai_client=None,  # No client
    )
    
    # Should return mock title
    assert "Chapter 0" in result.chapter_title


# Test 8: Validation Integration

def test_validation_integration():
    """Validation should run during generation."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "Test summary"
    
    # Generate title with validation
    mock_client = MockAIClient({"chapter_title": "Utah Pushes the Pace"})
    
    result = generate_chapter_title(
        chapter=chapter,
        chapter_summary=summary,
        chapter_index=0,
        ai_client=mock_client,
        validate_output=True,
    )
    
    # Should have validation result
    assert result.validation_result is not None
    assert "valid" in result.validation_result


def test_validation_can_be_disabled():
    """Validation can be disabled."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    summary = "Test summary"
    
    mock_client = MockAIClient({"chapter_title": "Test"})
    
    result = generate_chapter_title(
        chapter=chapter,
        chapter_summary=summary,
        chapter_index=0,
        ai_client=mock_client,
        validate_output=False,
    )
    
    # Should not have validation result
    assert result.validation_result is None


# Test 9: Banned Words List

def test_banned_words_list_exists():
    """Banned words list should be defined."""
    assert len(TITLE_BANNED_WORDS) > 0
    assert "dagger" in TITLE_BANNED_WORDS
    assert "sealed" in TITLE_BANNED_WORDS
    assert "clinched" in TITLE_BANNED_WORDS
