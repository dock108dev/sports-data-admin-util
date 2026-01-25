"""
Unit tests for Target Word Count Selection.

These tests validate:
- LOW quality → correct range (350-500, target 450)
- MEDIUM quality → correct range (450-650, target 550)
- HIGH quality → correct range (550-850, target 700)
- Determinism (same input → same output)
- Targets calibrated to AI's natural output range

ISSUE: Target Word Count (Chapters-First Architecture)
"""

from app.services.chapters.game_quality import GameQuality
from app.services.chapters.target_length import (
    # Types
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
# TEST: CALIBRATED CONSTANTS
# ============================================================================


class TestCalibratedConstants:
    """Verify constants match AI-calibrated specification."""

    def test_low_range(self):
        """LOW range is 350-500."""
        assert LOW_MIN == 350
        assert LOW_MAX == 500

    def test_low_target(self):
        """LOW target is 450."""
        assert LOW_TARGET == 450

    def test_medium_range(self):
        """MEDIUM range is 450-650."""
        assert MEDIUM_MIN == 450
        assert MEDIUM_MAX == 650

    def test_medium_target(self):
        """MEDIUM target is 550."""
        assert MEDIUM_TARGET == 550

    def test_high_range(self):
        """HIGH range is 550-850."""
        assert HIGH_MIN == 550
        assert HIGH_MAX == 850

    def test_high_target(self):
        """HIGH target is 700."""
        assert HIGH_TARGET == 700


# ============================================================================
# TEST: LOW QUALITY SELECTION
# ============================================================================


class TestLowQuality:
    """Tests for LOW quality word count selection."""

    def test_low_returns_correct_target(self):
        """LOW quality returns 450 words."""
        result = select_target_word_count(GameQuality.LOW)
        assert result.target_words == 450

    def test_low_returns_correct_range(self):
        """LOW quality returns 350-500 range."""
        result = select_target_word_count(GameQuality.LOW)
        assert result.range_min == 350
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
        """MEDIUM quality returns 550 words."""
        result = select_target_word_count(GameQuality.MEDIUM)
        assert result.target_words == 550

    def test_medium_returns_correct_range(self):
        """MEDIUM quality returns 450-650 range."""
        result = select_target_word_count(GameQuality.MEDIUM)
        assert result.range_min == 450
        assert result.range_max == 650

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
        """HIGH quality returns 700 words."""
        result = select_target_word_count(GameQuality.HIGH)
        assert result.target_words == 700

    def test_high_returns_correct_range(self):
        """HIGH quality returns 550-850 range."""
        result = select_target_word_count(GameQuality.HIGH)
        assert result.range_min == 550
        assert result.range_max == 850

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
        assert get_target_words(GameQuality.LOW) == 450

    def test_get_target_words_medium(self):
        """get_target_words returns correct value for MEDIUM."""
        assert get_target_words(GameQuality.MEDIUM) == 550

    def test_get_target_words_high(self):
        """get_target_words returns correct value for HIGH."""
        assert get_target_words(GameQuality.HIGH) == 700

    def test_get_target_words_matches_full_function(self):
        """get_target_words matches select_target_word_count."""
        for quality in GameQuality:
            simple = get_target_words(quality)
            full = select_target_word_count(quality).target_words
            assert simple == full


# ============================================================================
# TEST: RANGES OVERLAP INTENTIONALLY
# ============================================================================


class TestRangesOverlap:
    """Tests verifying ranges overlap intentionally for smooth transitions."""

    def test_low_and_medium_overlap(self):
        """LOW and MEDIUM ranges overlap."""
        # LOW max (500) >= MEDIUM min (450)
        assert LOW_MAX >= MEDIUM_MIN

    def test_medium_and_high_overlap(self):
        """MEDIUM and HIGH ranges overlap."""
        # MEDIUM max (650) >= HIGH min (550)
        assert MEDIUM_MAX >= HIGH_MIN

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

        assert data["target_words"] == 550
        assert data["quality"] == "MEDIUM"
        assert data["range_min"] == 450
        assert data["range_max"] == 650

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
        assert "550" in output

    def test_format_includes_range(self):
        """Debug output includes range."""
        result = select_target_word_count(GameQuality.LOW)
        output = format_target_debug(result)
        assert "350" in output
        assert "500" in output
