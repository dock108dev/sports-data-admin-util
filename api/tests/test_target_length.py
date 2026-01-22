"""
Unit tests for Target Word Count Selection.

These tests validate:
- LOW quality → correct range (300-500, target 400)
- MEDIUM quality → correct range (600-800, target 700)
- HIGH quality → correct range (900-1200, target 1050)
- Determinism (same input → same output)
- Range constants are locked

ISSUE: Target Word Count (Chapters-First Architecture)
"""

import pytest

from app.services.chapters.game_quality import GameQuality
from app.services.chapters.target_length import (
    # Types
    TargetLengthResult,
    # Functions
    select_target_word_count,
    get_target_words,
    format_target_debug,
    # Constants
    LOW_MIN,
    LOW_MAX,
    LOW_TARGET,
    MEDIUM_MIN,
    MEDIUM_MAX,
    MEDIUM_TARGET,
    HIGH_MIN,
    HIGH_MAX,
    HIGH_TARGET,
)


# ============================================================================
# TEST: LOCKED CONSTANTS
# ============================================================================

class TestLockedConstants:
    """Verify constants match specification."""

    def test_low_range(self):
        """LOW range is 300-500."""
        assert LOW_MIN == 300
        assert LOW_MAX == 500

    def test_low_target_is_midpoint(self):
        """LOW target is midpoint of range."""
        assert LOW_TARGET == 400
        assert LOW_TARGET == (LOW_MIN + LOW_MAX) // 2

    def test_medium_range(self):
        """MEDIUM range is 600-800."""
        assert MEDIUM_MIN == 600
        assert MEDIUM_MAX == 800

    def test_medium_target_is_midpoint(self):
        """MEDIUM target is midpoint of range."""
        assert MEDIUM_TARGET == 700
        assert MEDIUM_TARGET == (MEDIUM_MIN + MEDIUM_MAX) // 2

    def test_high_range(self):
        """HIGH range is 900-1200."""
        assert HIGH_MIN == 900
        assert HIGH_MAX == 1200

    def test_high_target_is_midpoint(self):
        """HIGH target is midpoint of range."""
        assert HIGH_TARGET == 1050
        assert HIGH_TARGET == (HIGH_MIN + HIGH_MAX) // 2


# ============================================================================
# TEST: LOW QUALITY SELECTION
# ============================================================================

class TestLowQuality:
    """Tests for LOW quality word count selection."""

    def test_low_returns_correct_target(self):
        """LOW quality returns 400 words."""
        result = select_target_word_count(GameQuality.LOW)
        assert result.target_words == 400

    def test_low_returns_correct_range(self):
        """LOW quality returns 300-500 range."""
        result = select_target_word_count(GameQuality.LOW)
        assert result.range_min == 300
        assert result.range_max == 500

    def test_low_returns_correct_quality(self):
        """LOW quality echoes back LOW."""
        result = select_target_word_count(GameQuality.LOW)
        assert result.quality == GameQuality.LOW

    def test_low_target_within_range(self):
        """LOW target is within its range."""
        result = select_target_word_count(GameQuality.LOW)
        assert result.range_min <= result.target_words <= result.range_max


# ============================================================================
# TEST: MEDIUM QUALITY SELECTION
# ============================================================================

class TestMediumQuality:
    """Tests for MEDIUM quality word count selection."""

    def test_medium_returns_correct_target(self):
        """MEDIUM quality returns 700 words."""
        result = select_target_word_count(GameQuality.MEDIUM)
        assert result.target_words == 700

    def test_medium_returns_correct_range(self):
        """MEDIUM quality returns 600-800 range."""
        result = select_target_word_count(GameQuality.MEDIUM)
        assert result.range_min == 600
        assert result.range_max == 800

    def test_medium_returns_correct_quality(self):
        """MEDIUM quality echoes back MEDIUM."""
        result = select_target_word_count(GameQuality.MEDIUM)
        assert result.quality == GameQuality.MEDIUM

    def test_medium_target_within_range(self):
        """MEDIUM target is within its range."""
        result = select_target_word_count(GameQuality.MEDIUM)
        assert result.range_min <= result.target_words <= result.range_max


# ============================================================================
# TEST: HIGH QUALITY SELECTION
# ============================================================================

class TestHighQuality:
    """Tests for HIGH quality word count selection."""

    def test_high_returns_correct_target(self):
        """HIGH quality returns 1050 words."""
        result = select_target_word_count(GameQuality.HIGH)
        assert result.target_words == 1050

    def test_high_returns_correct_range(self):
        """HIGH quality returns 900-1200 range."""
        result = select_target_word_count(GameQuality.HIGH)
        assert result.range_min == 900
        assert result.range_max == 1200

    def test_high_returns_correct_quality(self):
        """HIGH quality echoes back HIGH."""
        result = select_target_word_count(GameQuality.HIGH)
        assert result.quality == GameQuality.HIGH

    def test_high_target_within_range(self):
        """HIGH target is within its range."""
        result = select_target_word_count(GameQuality.HIGH)
        assert result.range_min <= result.target_words <= result.range_max


# ============================================================================
# TEST: DETERMINISM
# ============================================================================

class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_low_deterministic(self):
        """LOW quality produces same result every time."""
        results = [select_target_word_count(GameQuality.LOW) for _ in range(10)]
        targets = [r.target_words for r in results]
        assert len(set(targets)) == 1

    def test_medium_deterministic(self):
        """MEDIUM quality produces same result every time."""
        results = [select_target_word_count(GameQuality.MEDIUM) for _ in range(10)]
        targets = [r.target_words for r in results]
        assert len(set(targets)) == 1

    def test_high_deterministic(self):
        """HIGH quality produces same result every time."""
        results = [select_target_word_count(GameQuality.HIGH) for _ in range(10)]
        targets = [r.target_words for r in results]
        assert len(set(targets)) == 1

    def test_all_qualities_deterministic(self):
        """All qualities produce deterministic results."""
        for quality in GameQuality:
            results = [select_target_word_count(quality) for _ in range(5)]
            assert len(set(r.target_words for r in results)) == 1


# ============================================================================
# TEST: CONVENIENCE FUNCTION
# ============================================================================

class TestConvenienceFunction:
    """Tests for get_target_words convenience function."""

    def test_get_target_words_low(self):
        """get_target_words returns correct value for LOW."""
        assert get_target_words(GameQuality.LOW) == 400

    def test_get_target_words_medium(self):
        """get_target_words returns correct value for MEDIUM."""
        assert get_target_words(GameQuality.MEDIUM) == 700

    def test_get_target_words_high(self):
        """get_target_words returns correct value for HIGH."""
        assert get_target_words(GameQuality.HIGH) == 1050

    def test_get_target_words_matches_full_function(self):
        """get_target_words matches select_target_word_count."""
        for quality in GameQuality:
            simple = get_target_words(quality)
            full = select_target_word_count(quality).target_words
            assert simple == full


# ============================================================================
# TEST: RANGES DO NOT OVERLAP
# ============================================================================

class TestRangesSeparation:
    """Tests verifying ranges don't overlap."""

    def test_low_max_less_than_medium_min(self):
        """LOW max < MEDIUM min (ranges don't overlap)."""
        assert LOW_MAX < MEDIUM_MIN

    def test_medium_max_less_than_high_min(self):
        """MEDIUM max < HIGH min (ranges don't overlap)."""
        assert MEDIUM_MAX < HIGH_MIN

    def test_targets_are_distinct(self):
        """All targets are distinct values."""
        targets = {LOW_TARGET, MEDIUM_TARGET, HIGH_TARGET}
        assert len(targets) == 3

    def test_targets_increase_with_quality(self):
        """Targets increase from LOW to HIGH."""
        assert LOW_TARGET < MEDIUM_TARGET < HIGH_TARGET


# ============================================================================
# TEST: SERIALIZATION
# ============================================================================

class TestSerialization:
    """Tests for serialization."""

    def test_result_to_dict(self):
        """TargetLengthResult serializes correctly."""
        result = select_target_word_count(GameQuality.MEDIUM)
        data = result.to_dict()

        assert data["target_words"] == 700
        assert data["quality"] == "MEDIUM"
        assert data["range_min"] == 600
        assert data["range_max"] == 800

    def test_all_qualities_serialize(self):
        """All qualities serialize correctly."""
        for quality in GameQuality:
            result = select_target_word_count(quality)
            data = result.to_dict()
            assert "target_words" in data
            assert "quality" in data
            assert "range_min" in data
            assert "range_max" in data


# ============================================================================
# TEST: DEBUG OUTPUT
# ============================================================================

class TestDebugOutput:
    """Tests for debug formatting."""

    def test_format_includes_quality(self):
        """Debug output includes quality."""
        result = select_target_word_count(GameQuality.HIGH)
        output = format_target_debug(result)
        assert "HIGH" in output

    def test_format_includes_target(self):
        """Debug output includes target."""
        result = select_target_word_count(GameQuality.MEDIUM)
        output = format_target_debug(result)
        assert "700" in output

    def test_format_includes_range(self):
        """Debug output includes range."""
        result = select_target_word_count(GameQuality.LOW)
        output = format_target_debug(result)
        assert "300" in output
        assert "500" in output
