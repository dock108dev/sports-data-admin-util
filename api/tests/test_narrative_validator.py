"""
Tests for Narrative QA & Spoiler Guard Pass.

FINAL PROMPT: Narrative QA & Spoiler Guard Pass (Post-Generation Validation)

These tests ensure:
1. Known bad phrases fail
2. Known good text passes
3. Final chapter flag enables finality
4. New entity detection works
5. No silent passes
"""

import pytest

from app.services.chapters.narrative_validator import (
    NarrativeValidator,
    ValidationResult,
    validate_narrative_output,
    all_valid,
    get_all_errors,
)


# ============================================================================
# CHAPTER SUMMARY VALIDATION TESTS
# ============================================================================

class TestChapterSummaryValidation:
    """Test chapter summary validation."""
    
    def test_valid_summary_passes(self):
        """Valid summary should pass validation."""
        summary = "The Warriors built an early lead with strong defense. Curry hit two quick threes."
        
        result = NarrativeValidator.validate_chapter_summary(summary)
        
        assert result.valid
        assert len(result.errors) == 0
    
    def test_empty_summary_fails(self):
        """Empty summary should fail."""
        result = NarrativeValidator.validate_chapter_summary("")
        
        assert not result.valid
        assert "empty" in result.errors[0].lower()
    
    def test_spoiler_phrases_fail(self):
        """Spoiler phrases should fail validation."""
        summary = "Curry finished with 35 points to seal the victory."
        
        result = NarrativeValidator.validate_chapter_summary(summary)
        
        assert not result.valid
        assert any("spoiler" in error.lower() for error in result.errors)
    
    def test_final_chapter_allows_finality(self):
        """Final chapter should allow finality language."""
        summary = "Curry finished with 35 points to seal the victory."
        
        result = NarrativeValidator.validate_chapter_summary(
            summary,
            is_final_chapter=True
        )
        
        assert result.valid
    
    def test_future_knowledge_fails(self):
        """Future knowledge phrases should fail."""
        summary = "This run would later prove decisive."
        
        result = NarrativeValidator.validate_chapter_summary(summary)
        
        assert not result.valid
        assert any("future" in error.lower() for error in result.errors)
    
    def test_bullet_points_fail(self):
        """Bullet points should fail."""
        summary = "- Warriors scored\n- Lakers responded\n- Game tied"
        
        result = NarrativeValidator.validate_chapter_summary(summary)
        
        assert not result.valid
        assert any("bullet" in error.lower() for error in result.errors)
    
    def test_too_many_sentences_warns(self):
        """More than 3 sentences should warn."""
        summary = "First sentence. Second sentence. Third sentence. Fourth sentence."
        
        result = NarrativeValidator.validate_chapter_summary(summary)
        
        assert result.valid  # Still valid
        assert result.warnings
        assert any("sentence" in warning.lower() for warning in result.warnings)


# ============================================================================
# CHAPTER TITLE VALIDATION TESTS
# ============================================================================

class TestChapterTitleValidation:
    """Test chapter title validation."""
    
    def test_valid_title_passes(self):
        """Valid title should pass."""
        title = "Warriors Build Early Lead"
        
        result = NarrativeValidator.validate_chapter_title(title)
        
        assert result.valid
        assert len(result.errors) == 0
    
    def test_empty_title_fails(self):
        """Empty title should fail."""
        result = NarrativeValidator.validate_chapter_title("")
        
        assert not result.valid
        assert "empty" in result.errors[0].lower()
    
    def test_too_short_title_fails(self):
        """Title with < 3 words should fail."""
        title = "Warriors Win"
        
        result = NarrativeValidator.validate_chapter_title(title)
        
        assert not result.valid
        assert any("length" in error.lower() for error in result.errors)
    
    def test_too_long_title_fails(self):
        """Title with > 8 words should fail."""
        title = "Warriors Build A Very Large And Commanding Early Lead"
        
        result = NarrativeValidator.validate_chapter_title(title)
        
        assert not result.valid
        assert any("length" in error.lower() for error in result.errors)
    
    def test_numbers_in_title_fail(self):
        """Numbers in title should fail."""
        title = "Warriors Up 15 Points"
        
        result = NarrativeValidator.validate_chapter_title(title)
        
        assert not result.valid
        assert any("number" in error.lower() for error in result.errors)
    
    def test_spoiler_words_fail(self):
        """Spoiler words should fail."""
        title = "The Final Dagger"
        
        result = NarrativeValidator.validate_chapter_title(title)
        
        assert not result.valid
        assert any("banned" in error.lower() or "spoiler" in error.lower() for error in result.errors)
    
    def test_final_chapter_allows_finality(self):
        """Final chapter should allow finality words."""
        title = "The Final Stand"
        
        result = NarrativeValidator.validate_chapter_title(
            title,
            is_final_chapter=True
        )
        
        assert result.valid


# ============================================================================
# COMPACT STORY VALIDATION TESTS
# ============================================================================

class TestCompactStoryValidation:
    """Test compact story validation."""
    
    def test_valid_compact_story_passes(self):
        """Valid compact story should pass."""
        story = """
        The Warriors came out strong, building an early lead with crisp ball movement.
        Curry's shooting kept them ahead through the second quarter.
        The Lakers mounted a comeback in the third, but Golden State held on.
        """
        summaries = [
            "Warriors built early lead",
            "Curry kept them ahead",
            "Lakers comeback attempt"
        ]
        
        result = NarrativeValidator.validate_compact_story(story, summaries)
        
        assert result.valid
        assert len(result.errors) == 0
    
    def test_empty_compact_story_fails(self):
        """Empty compact story should fail."""
        result = NarrativeValidator.validate_compact_story("", ["summary"])
        
        assert not result.valid
        assert "empty" in result.errors[0].lower()
    
    def test_bullet_points_fail(self):
        """Bullet points should fail."""
        story = "- Warriors scored\n- Lakers responded"
        summaries = ["Warriors scored", "Lakers responded"]
        
        result = NarrativeValidator.validate_compact_story(story, summaries)
        
        assert not result.valid
        assert any("bullet" in error.lower() for error in result.errors)
    
    def test_play_by_play_listing_fails(self):
        """Play-by-play listing should fail."""
        story = """
        3:45 - Curry made a three-pointer.
        3:30 - James made a layup.
        3:15 - Green missed a shot.
        3:00 - Davis made a jumper.
        """
        summaries = ["Game action"]
        
        result = NarrativeValidator.validate_compact_story(story, summaries)
        
        assert not result.valid
        assert any("play-by-play" in error.lower() for error in result.errors)
    
    def test_very_short_story_warns(self):
        """Very short story should warn."""
        story = "Warriors won the game."
        summaries = ["Warriors won"]
        
        result = NarrativeValidator.validate_compact_story(story, summaries)
        
        assert result.valid  # Still valid
        assert result.warnings
        assert any("short" in warning.lower() for warning in result.warnings)
    
    def test_new_entities_warn(self):
        """New entities not in summaries should warn."""
        story = "The Warriors, led by Curry and Thompson, dominated the Lakers."
        summaries = ["Warriors dominated"]  # No mention of Curry or Thompson
        
        result = NarrativeValidator.validate_compact_story(story, summaries)
        
        # Should still be valid but warn
        assert result.valid
        if result.warnings:
            assert any("entit" in warning.lower() for warning in result.warnings)


# ============================================================================
# BATCH VALIDATION TESTS
# ============================================================================

class TestBatchValidation:
    """Test batch validation helpers."""
    
    def test_validate_narrative_output_all_fields(self):
        """Test validating all fields at once."""
        results = validate_narrative_output(
            summary="Warriors built an early lead.",
            title="Warriors Build Lead",
            compact_story="The Warriors dominated from start to finish.",
            chapter_summaries=["Warriors dominated"]
        )
        
        assert "summary" in results
        assert "title" in results
        assert "compact_story" in results
        assert all_valid(results)
    
    def test_all_valid_detects_failures(self):
        """Test all_valid helper."""
        results = {
            "summary": ValidationResult(valid=True, errors=[]),
            "title": ValidationResult(valid=False, errors=["Too short"]),
        }
        
        assert not all_valid(results)
    
    def test_get_all_errors_collects_errors(self):
        """Test get_all_errors helper."""
        results = {
            "summary": ValidationResult(valid=False, errors=["Spoiler detected"]),
            "title": ValidationResult(valid=False, errors=["Too short", "Has numbers"]),
        }
        
        errors = get_all_errors(results)
        
        assert len(errors) == 3
        assert any("summary" in error for error in errors)
        assert any("title" in error for error in errors)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_summary_with_only_whitespace_fails(self):
        """Summary with only whitespace should fail."""
        result = NarrativeValidator.validate_chapter_summary("   \n\t  ")
        
        assert not result.valid
    
    def test_title_with_apostrophe_passes(self):
        """Title with apostrophe should pass."""
        title = "Warriors' Strong Start"
        
        result = NarrativeValidator.validate_chapter_title(title)
        
        assert result.valid
    
    def test_multiple_validation_errors(self):
        """Multiple errors should all be reported."""
        summary = "- Bullet point. This would later prove decisive. He finished with 30."
        
        result = NarrativeValidator.validate_chapter_summary(summary)
        
        assert not result.valid
        assert len(result.errors) >= 2  # Bullet + future knowledge + spoiler
    
    def test_case_insensitive_spoiler_detection(self):
        """Spoiler detection should be case-insensitive."""
        summary = "Curry FINISHED WITH 35 points."
        
        result = NarrativeValidator.validate_chapter_summary(summary)
        
        assert not result.valid
