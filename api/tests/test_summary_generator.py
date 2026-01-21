"""
Unit tests for Chapter Summary Generator (Phase 1 Issue 10).

These tests validate context discipline and output shape.
"""

import pytest
import json

from app.services.chapters import (
    Chapter,
    Play,
    generate_chapter_summary,
    generate_summaries_sequentially,
    SummaryGenerationError,
    check_for_spoilers,
    BANNED_PHRASES,
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
        self.response = response or {
            "chapter_summary": "Mock summary text.",
            "chapter_title": "Mock Title"
        }
        self.calls = []
    
    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return json.dumps(self.response)


# Test 1: Context Boundary Test

def test_context_boundary_no_future_plays():
    """AI payload must not contain plays from future chapters."""
    chapters = [
        make_chapter("ch_001", 0, [
            make_play(0, "LeBron makes layup"),
            make_play(1, "Curry makes 3-pointer"),
        ], ["PERIOD_START"]),
        make_chapter("ch_002", 2, [
            make_play(2, "Durant makes dunk"),  # Future play
        ], ["TIMEOUT"]),
    ]
    
    mock_client = MockAIClient()
    
    # Generate summary for Chapter 0
    result = generate_chapter_summary(
        current_chapter=chapters[0],
        prior_chapters=[],
        ai_client=mock_client,
    )
    
    # Check that prompt doesn't contain future plays
    prompt = mock_client.calls[0]
    assert "Durant" not in prompt  # Future player
    assert "makes dunk" not in prompt  # Future play


def test_context_boundary_no_future_summaries():
    """AI payload must not contain summaries from future chapters."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"]),
        make_chapter("ch_002", 1, [make_play(1, "Play 2")], ["TIMEOUT"]),
    ]
    
    mock_client = MockAIClient()
    
    # Generate summary for Chapter 0 (no prior summaries)
    result = generate_chapter_summary(
        current_chapter=chapters[0],
        prior_chapters=[],
        prior_summaries=[],
        ai_client=mock_client,
    )
    
    # Prompt should indicate no prior context
    prompt = mock_client.calls[0]
    assert "first chapter" in prompt.lower() or "no prior" in prompt.lower()


def test_context_boundary_validation():
    """Context boundary violations should raise error."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"]),
    ]
    
    # Try to include current chapter in prior chapters (invalid)
    with pytest.raises(SummaryGenerationError, match="found in prior chapters"):
        generate_chapter_summary(
            current_chapter=chapters[0],
            prior_chapters=chapters,  # Invalid: includes current
            ai_client=MockAIClient(),
        )


# Test 2: Determinism Test (Prompt Level)

def test_determinism_identical_inputs():
    """Identical inputs must produce identical prompts."""
    chapter = make_chapter("ch_001", 0, [
        make_play(0, "LeBron makes layup"),
    ], ["PERIOD_START"])
    
    mock_client1 = MockAIClient()
    mock_client2 = MockAIClient()
    
    # Generate twice with same inputs
    result1 = generate_chapter_summary(
        current_chapter=chapter,
        prior_chapters=[],
        ai_client=mock_client1,
    )
    
    result2 = generate_chapter_summary(
        current_chapter=chapter,
        prior_chapters=[],
        ai_client=mock_client2,
    )
    
    # Prompts should be identical
    assert mock_client1.calls[0] == mock_client2.calls[0]


# Test 3: Output Shape Test

def test_output_shape_summary_non_empty():
    """Summary must be non-empty."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    
    mock_client = MockAIClient({"chapter_summary": "", "chapter_title": "Title"})
    
    # Should raise error for empty summary
    with pytest.raises(SummaryGenerationError, match="empty summary"):
        generate_chapter_summary(
            current_chapter=chapter,
            prior_chapters=[],
            ai_client=mock_client,
        )


def test_output_shape_summary_returned():
    """Summary should be returned in result."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    
    mock_client = MockAIClient({
        "chapter_summary": "This is a test summary.",
        "chapter_title": "Test Title"
    })
    
    result = generate_chapter_summary(
        current_chapter=chapter,
        prior_chapters=[],
        ai_client=mock_client,
    )
    
    assert result.chapter_summary == "This is a test summary."
    assert result.chapter_title == "Test Title"
    assert result.chapter_index == 0


def test_output_shape_title_optional():
    """Title is optional."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    
    mock_client = MockAIClient({
        "chapter_summary": "This is a test summary.",
        # No title
    })
    
    result = generate_chapter_summary(
        current_chapter=chapter,
        prior_chapters=[],
        ai_client=mock_client,
    )
    
    assert result.chapter_summary == "This is a test summary."
    assert result.chapter_title is None


# Test 4: Spoiler Guard Test

def test_spoiler_guard_banned_phrases():
    """Banned phrases should be detected."""
    # Test each banned phrase
    for phrase in ["finished with", "sealed it", "the dagger"]:
        spoilers = check_for_spoilers(f"He {phrase} 30 points", is_final_chapter=False)
        assert len(spoilers) > 0, f"Failed to detect: {phrase}"


def test_spoiler_guard_clean_text():
    """Clean text should have no spoilers."""
    clean_text = "LeBron had 20 points so far and kept attacking the rim."
    spoilers = check_for_spoilers(clean_text, is_final_chapter=False)
    assert len(spoilers) == 0


def test_spoiler_guard_final_chapter_exception():
    """Final chapter can use conclusive language."""
    # This would normally be a spoiler, but allowed in final chapter
    text = "LeBron finished with 35 points to seal the victory."
    
    # Not allowed in non-final chapter
    spoilers_non_final = check_for_spoilers(text, is_final_chapter=False)
    assert len(spoilers_non_final) > 0
    
    # Allowed in final chapter (some phrases still banned)
    spoilers_final = check_for_spoilers(text, is_final_chapter=True)
    # "finished with" is still banned even in final
    assert len(spoilers_final) > 0


def test_spoiler_guard_integration():
    """Spoiler detection should work in generation."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    
    # Mock response with spoiler
    mock_client = MockAIClient({
        "chapter_summary": "LeBron finished with 30 points.",  # Spoiler!
        "chapter_title": "Title"
    })
    
    result = generate_chapter_summary(
        current_chapter=chapter,
        prior_chapters=[],
        ai_client=mock_client,
        check_spoilers=True,
    )
    
    # Should have spoiler warnings
    assert result.spoiler_warnings is not None
    assert len(result.spoiler_warnings) > 0


# Test 5: Sequential Generation

def test_sequential_generation():
    """Sequential generation should build context correctly."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "LeBron makes layup")], ["PERIOD_START"]),
        make_chapter("ch_002", 1, [make_play(1, "Curry makes 3-pointer")], ["TIMEOUT"]),
        make_chapter("ch_003", 2, [make_play(2, "Durant makes dunk")], ["PERIOD_START"]),
    ]
    
    mock_client = MockAIClient()
    
    results = generate_summaries_sequentially(chapters, ai_client=mock_client)
    
    # Should have 3 results
    assert len(results) == 3
    
    # Each should have correct index
    assert results[0].chapter_index == 0
    assert results[1].chapter_index == 1
    assert results[2].chapter_index == 2
    
    # Should have made 3 AI calls
    assert len(mock_client.calls) == 3


def test_sequential_generation_prior_context():
    """Later chapters should have prior summaries in context."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"]),
        make_chapter("ch_002", 1, [make_play(1, "Play 2")], ["TIMEOUT"]),
    ]
    
    mock_client = MockAIClient()
    
    results = generate_summaries_sequentially(chapters, ai_client=mock_client)
    
    # Chapter 1 prompt should include Chapter 0 summary
    prompt_ch1 = mock_client.calls[1]
    assert "Chapter 0:" in prompt_ch1  # Prior summary header


# Test 6: Error Handling

def test_error_handling_invalid_json():
    """Invalid JSON response should raise error."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    
    class BadAIClient:
        def generate(self, prompt: str) -> str:
            return "Not JSON"
    
    with pytest.raises(SummaryGenerationError, match="Failed to parse"):
        generate_chapter_summary(
            current_chapter=chapter,
            prior_chapters=[],
            ai_client=BadAIClient(),
        )


def test_error_handling_ai_exception():
    """AI client exceptions should be caught and wrapped."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    
    class FailingAIClient:
        def generate(self, prompt: str) -> str:
            raise Exception("AI service down")
    
    with pytest.raises(SummaryGenerationError, match="AI generation failed"):
        generate_chapter_summary(
            current_chapter=chapter,
            prior_chapters=[],
            ai_client=FailingAIClient(),
        )


# Test 7: Mock Mode

def test_mock_mode_no_ai_client():
    """Should work without AI client (mock mode)."""
    chapter = make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"])
    
    result = generate_chapter_summary(
        current_chapter=chapter,
        prior_chapters=[],
        ai_client=None,  # No client
    )
    
    # Should return mock summary
    assert "Mock summary" in result.chapter_summary
    assert result.chapter_index == 0


# Test 8: Banned Phrases List

def test_banned_phrases_list_exists():
    """Banned phrases list should be defined."""
    assert len(BANNED_PHRASES) > 0
    assert "finished with" in BANNED_PHRASES
    assert "sealed it" in BANNED_PHRASES
    assert "the dagger" in BANNED_PHRASES
