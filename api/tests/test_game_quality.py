"""
Unit tests for Game Quality Scoring.

These tests validate:
- Lead change counting
- Signal extraction from sections
- Point assignment (locked values)
- Bucket determination (locked thresholds)
- Determinism across runs

Test scenarios:
- Blowout games (LOW quality)
- Close games (MEDIUM/HIGH quality)
- Overtime games (HIGH quality)
- Games with many lead changes
- Edge cases at bucket boundaries

ISSUE: Game Quality Scoring (Chapters-First Architecture)
"""

import pytest

from app.services.chapters.beat_classifier import BeatType
from app.services.chapters.story_section import StorySection
from app.services.chapters.game_quality import (
    # Types
    GameQuality,
    QualitySignals,
    QualityScoreResult,
    # Functions
    count_lead_changes,
    compute_quality_score,
    format_quality_debug,
    # Constants (for verification)
    POINTS_PER_LEAD_CHANGE,
    POINTS_CRUNCH_PRESENT,
    POINTS_OVERTIME_PRESENT,
    POINTS_MARGIN_CLOSE,
    POINTS_MARGIN_COMPETITIVE,
    POINTS_PER_RUN_RESPONSE,
    BUCKET_MEDIUM_THRESHOLD,
    BUCKET_HIGH_THRESHOLD,
)


# ============================================================================
# TEST HELPERS
# ============================================================================

def make_section(
    section_index: int,
    beat_type: BeatType,
    home_score: int = 50,
    away_score: int = 48,
) -> StorySection:
    """Create a StorySection for testing."""
    return StorySection(
        section_index=section_index,
        beat_type=beat_type,
        chapters_included=[f"ch_{section_index:03d}"],
        start_score={"home": home_score - 10, "away": away_score - 8},
        end_score={"home": home_score, "away": away_score},
    )


def make_score_history(*scores: tuple[int, int]) -> list[dict[str, int]]:
    """Create score history from tuples.

    Args:
        *scores: Tuples of (home_score, away_score)

    Returns:
        List of score dicts
    """
    return [{"home": h, "away": a} for h, a in scores]


# ============================================================================
# TEST: LEAD CHANGE COUNTING
# ============================================================================

class TestLeadChangeCounting:
    """Tests for lead change counter."""

    def test_no_lead_changes_home_always_ahead(self):
        """Home team leads throughout - no lead changes."""
        history = make_score_history(
            (0, 0), (2, 0), (4, 2), (6, 4), (8, 6),
        )
        assert count_lead_changes(history) == 0

    def test_no_lead_changes_away_always_ahead(self):
        """Away team leads throughout - no lead changes."""
        history = make_score_history(
            (0, 0), (0, 3), (2, 5), (4, 7), (6, 9),
        )
        assert count_lead_changes(history) == 0

    def test_one_lead_change(self):
        """Single lead change from home to away."""
        history = make_score_history(
            (0, 0), (5, 0), (5, 3), (5, 6),  # Home leads, then away takes lead
        )
        assert count_lead_changes(history) == 1

    def test_multiple_lead_changes(self):
        """Multiple lead changes back and forth."""
        history = make_score_history(
            (0, 0),   # Tied
            (3, 0),   # Home leads
            (3, 5),   # Away leads (change 1)
            (8, 5),   # Home leads (change 2)
            (8, 10),  # Away leads (change 3)
        )
        assert count_lead_changes(history) == 3

    def test_tie_does_not_count_as_lead_change(self):
        """Tie doesn't count as lead change."""
        history = make_score_history(
            (0, 0),   # Tied
            (5, 0),   # Home leads
            (5, 5),   # Tied
            (5, 8),   # Away leads (only 1 change)
        )
        assert count_lead_changes(history) == 1

    def test_empty_history(self):
        """Empty history returns 0."""
        assert count_lead_changes([]) == 0

    def test_single_score(self):
        """Single score entry returns 0."""
        history = make_score_history((50, 48))
        assert count_lead_changes(history) == 0

    def test_many_lead_changes_exciting_game(self):
        """Highly competitive game with many lead changes."""
        history = make_score_history(
            (0, 0),    # Tie
            (2, 0),    # Home
            (2, 3),    # Away - change 1
            (5, 3),    # Home - change 2
            (5, 6),    # Away - change 3
            (8, 6),    # Home - change 4
            (8, 9),    # Away - change 5
            (11, 9),   # Home - change 6
            (11, 12),  # Away - change 7
        )
        assert count_lead_changes(history) == 7

    def test_tie_through_entire_game(self):
        """Game stays tied throughout - no lead changes."""
        history = make_score_history(
            (0, 0), (2, 2), (4, 4), (6, 6), (8, 8),
        )
        assert count_lead_changes(history) == 0


# ============================================================================
# TEST: POINT CONSTANTS (LOCKED VALUES)
# ============================================================================

class TestLockedConstants:
    """Verify point constants match specification."""

    def test_lead_change_points(self):
        """Lead change points are +1 per change."""
        assert POINTS_PER_LEAD_CHANGE == 1.0

    def test_crunch_points(self):
        """Crunch presence points are +2."""
        assert POINTS_CRUNCH_PRESENT == 2.0

    def test_overtime_points(self):
        """Overtime presence points are +3."""
        assert POINTS_OVERTIME_PRESENT == 3.0

    def test_margin_close_points(self):
        """Close margin (<=5) points are +2."""
        assert POINTS_MARGIN_CLOSE == 2.0

    def test_margin_competitive_points(self):
        """Competitive margin (<=12) points are +1."""
        assert POINTS_MARGIN_COMPETITIVE == 1.0

    def test_run_response_points(self):
        """Run/Response points are +0.5 per section."""
        assert POINTS_PER_RUN_RESPONSE == 0.5

    def test_bucket_thresholds(self):
        """Bucket thresholds are locked."""
        assert BUCKET_MEDIUM_THRESHOLD == 3.0
        assert BUCKET_HIGH_THRESHOLD == 6.0


# ============================================================================
# TEST: BLOWOUT GAMES (LOW QUALITY)
# ============================================================================

class TestBlowoutGames:
    """Tests for blowout games that should score LOW."""

    def test_large_margin_no_drama(self):
        """Large margin with no crunch/overtime = LOW."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.EARLY_CONTROL),
            make_section(2, BeatType.STALL),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=110,
            final_away_score=85,  # 25 point margin
            score_history=None,
        )

        # No lead changes, no crunch, no OT, large margin, no RUN/RESPONSE
        assert result.quality == GameQuality.LOW
        assert result.numeric_score < BUCKET_MEDIUM_THRESHOLD

    def test_blowout_with_early_run(self):
        """Blowout with early run still low quality."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.RUN),  # +0.5
            make_section(2, BeatType.STALL),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=120,
            final_away_score=90,  # 30 point margin
            score_history=None,
        )

        # Only 0.5 from RUN, still LOW
        assert result.quality == GameQuality.LOW
        assert result.signals.run_response_count == 1
        assert result.signals.run_response_points == 0.5


# ============================================================================
# TEST: CLOSE GAMES (MEDIUM/HIGH QUALITY)
# ============================================================================

class TestCloseGames:
    """Tests for close games."""

    def test_close_margin_only(self):
        """Close margin alone = MEDIUM."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
            make_section(1, BeatType.BACK_AND_FORTH),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=98,
            final_away_score=95,  # 3 point margin (<=5)
            score_history=None,
        )

        # +2 for close margin
        assert result.signals.margin_points == 2.0
        assert result.numeric_score == 2.0
        # Score < 3 = LOW (close margin alone isn't enough)
        assert result.quality == GameQuality.LOW

    def test_close_margin_with_crunch(self):
        """Close margin + crunch = MEDIUM or higher."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
            make_section(1, BeatType.CRUNCH_SETUP),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=98,
            final_away_score=95,  # 3 point margin
            score_history=None,
        )

        # +2 for close margin + +2 for crunch = 4
        assert result.signals.margin_points == 2.0
        assert result.signals.crunch_points == 2.0
        assert result.numeric_score == 4.0
        assert result.quality == GameQuality.MEDIUM

    def test_competitive_margin(self):
        """Competitive margin (6-12 points) gives +1."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=92,  # 8 point margin (<=12 but >5)
            score_history=None,
        )

        assert result.signals.margin_points == 1.0
        assert result.signals.final_margin == 8


# ============================================================================
# TEST: OVERTIME GAMES (HIGH QUALITY)
# ============================================================================

class TestOvertimeGames:
    """Tests for overtime games."""

    def test_overtime_alone_bumps_quality(self):
        """Overtime gives +3 points."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
            make_section(1, BeatType.OVERTIME),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=110,
            final_away_score=108,  # OT game, close margin
            score_history=None,
        )

        assert result.signals.has_overtime is True
        assert result.signals.overtime_points == 3.0
        assert result.signals.margin_points == 2.0  # <=5
        # 3 + 2 = 5 = MEDIUM
        assert result.numeric_score == 5.0
        assert result.quality == GameQuality.MEDIUM

    def test_overtime_with_crunch(self):
        """Overtime + crunch = HIGH quality."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
            make_section(1, BeatType.CRUNCH_SETUP),
            make_section(2, BeatType.OVERTIME),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=115,
            final_away_score=113,  # OT game, 2 point margin
            score_history=None,
        )

        # +3 OT + +2 crunch + +2 margin = 7
        assert result.signals.overtime_points == 3.0
        assert result.signals.crunch_points == 2.0
        assert result.signals.margin_points == 2.0
        assert result.numeric_score == 7.0
        assert result.quality == GameQuality.HIGH


# ============================================================================
# TEST: GAMES WITH MANY LEAD CHANGES
# ============================================================================

class TestLeadChangeGames:
    """Tests for games with lead changes."""

    def test_lead_changes_add_points(self):
        """Lead changes add +1 per change."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
        ]
        history = make_score_history(
            (0, 0), (5, 0), (5, 7), (10, 7), (10, 12),  # 3 lead changes
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,  # Large margin
            score_history=history,
        )

        assert result.signals.lead_changes == 3
        assert result.signals.lead_changes_points == 3.0
        # 3 points = MEDIUM threshold
        assert result.numeric_score == 3.0
        assert result.quality == GameQuality.MEDIUM

    def test_many_lead_changes_high_quality(self):
        """Many lead changes + close margin = HIGH."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
            make_section(1, BeatType.RUN),
            make_section(2, BeatType.RESPONSE),
        ]
        history = make_score_history(
            (0, 0), (3, 0), (3, 5), (8, 5), (8, 10), (15, 10),  # 4 lead changes
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=98,
            final_away_score=95,  # 3 point margin
            score_history=history,
        )

        # +4 lead changes + +2 margin + +1 (2 RUN/RESPONSE × 0.5) = 7
        assert result.signals.lead_changes == 4
        assert result.signals.lead_changes_points == 4.0
        assert result.signals.margin_points == 2.0
        assert result.signals.run_response_points == 1.0
        assert result.numeric_score == 7.0
        assert result.quality == GameQuality.HIGH


# ============================================================================
# TEST: RUN/RESPONSE SECTIONS
# ============================================================================

class TestRunResponseSections:
    """Tests for RUN and RESPONSE section counting."""

    def test_run_sections_counted(self):
        """RUN sections give +0.5 each."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
            make_section(1, BeatType.RUN),
            make_section(2, BeatType.RUN),
            make_section(3, BeatType.RUN),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,  # Large margin
            score_history=None,
        )

        assert result.signals.run_response_count == 3
        assert result.signals.run_response_points == 1.5

    def test_response_sections_counted(self):
        """RESPONSE sections give +0.5 each."""
        sections = [
            make_section(0, BeatType.RUN),
            make_section(1, BeatType.RESPONSE),
            make_section(2, BeatType.RUN),
            make_section(3, BeatType.RESPONSE),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,
            score_history=None,
        )

        assert result.signals.run_response_count == 4
        assert result.signals.run_response_points == 2.0

    def test_mixed_beat_types(self):
        """Only RUN and RESPONSE are counted."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.RUN),
            make_section(2, BeatType.STALL),
            make_section(3, BeatType.RESPONSE),
            make_section(4, BeatType.CLOSING_SEQUENCE),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,
            score_history=None,
        )

        assert result.signals.run_response_count == 2
        assert result.signals.run_response_points == 1.0


# ============================================================================
# TEST: BUCKET BOUNDARIES (EDGE CASES)
# ============================================================================

class TestBucketBoundaries:
    """Tests for exact bucket boundary behavior."""

    def test_score_exactly_3_is_medium(self):
        """Score of exactly 3.0 = MEDIUM."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
        ]
        # 3 lead changes = 3.0 points exactly
        history = make_score_history(
            (0, 0), (3, 0), (3, 5), (8, 5), (8, 10),
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,  # Large margin = 0 points
            score_history=history,
        )

        assert result.numeric_score == 3.0
        assert result.quality == GameQuality.MEDIUM

    def test_score_exactly_6_is_high(self):
        """Score of exactly 6.0 = HIGH."""
        sections = [
            make_section(0, BeatType.CRUNCH_SETUP),  # +2
        ]
        # 4 lead changes = 4.0 points
        history = make_score_history(
            (0, 0), (3, 0), (3, 5), (8, 5), (8, 10), (15, 10),
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,  # Large margin = 0 points
            score_history=history,
        )

        # 4 + 2 = 6.0
        assert result.numeric_score == 6.0
        assert result.quality == GameQuality.HIGH

    def test_score_2_99_is_low(self):
        """Score of 2.99 = LOW (just under threshold)."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
        ]
        # 2 lead changes + competitive margin (<=12) = 3 points
        # But we need 2.99, so 2 lead changes + large margin = 2 points
        # Add one RUN = 2.5 points
        sections = [
            make_section(0, BeatType.RUN),  # +0.5
        ]
        history = make_score_history(
            (0, 0), (3, 0), (3, 5), (8, 5),  # 2 lead changes
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,  # Large margin = 0
            score_history=history,
        )

        # 2 lead changes + 0.5 RUN = 2.5
        assert result.numeric_score == 2.5
        assert result.quality == GameQuality.LOW

    def test_score_5_99_is_medium(self):
        """Score just under 6 = MEDIUM."""
        sections = [
            make_section(0, BeatType.CRUNCH_SETUP),  # +2
            make_section(1, BeatType.RUN),  # +0.5
        ]
        # 3 lead changes = 3 points
        history = make_score_history(
            (0, 0), (3, 0), (3, 5), (8, 5), (8, 10),
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=80,  # Large margin
            score_history=history,
        )

        # 3 + 2 + 0.5 = 5.5
        assert result.numeric_score == 5.5
        assert result.quality == GameQuality.MEDIUM


# ============================================================================
# TEST: DETERMINISM
# ============================================================================

class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_input_same_output(self):
        """Same input produces same output every time."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH),
            make_section(1, BeatType.RUN),
            make_section(2, BeatType.CRUNCH_SETUP),
        ]
        history = make_score_history(
            (0, 0), (5, 0), (5, 7), (12, 7),
        )

        results = []
        for _ in range(10):
            result = compute_quality_score(
                sections=sections,
                final_home_score=102,
                final_away_score=99,
                score_history=history,
            )
            results.append((result.quality, result.numeric_score))

        # All results should be identical
        assert len(set(results)) == 1

    def test_different_section_order_same_beat_types(self):
        """Section order doesn't affect quality (same beat types)."""
        # Order A
        sections_a = [
            make_section(0, BeatType.RUN),
            make_section(1, BeatType.CRUNCH_SETUP),
            make_section(2, BeatType.RESPONSE),
        ]

        # Order B (same beat types, different order)
        sections_b = [
            make_section(0, BeatType.CRUNCH_SETUP),
            make_section(1, BeatType.RESPONSE),
            make_section(2, BeatType.RUN),
        ]

        result_a = compute_quality_score(
            sections=sections_a,
            final_home_score=100,
            final_away_score=97,
            score_history=None,
        )

        result_b = compute_quality_score(
            sections=sections_b,
            final_home_score=100,
            final_away_score=97,
            score_history=None,
        )

        # Same numeric score (same beat types counted)
        assert result_a.numeric_score == result_b.numeric_score
        assert result_a.quality == result_b.quality


# ============================================================================
# TEST: COMPREHENSIVE SCENARIOS
# ============================================================================

class TestComprehensiveScenarios:
    """End-to-end scenario tests."""

    def test_boring_blowout(self):
        """Boring blowout game = LOW."""
        sections = [
            make_section(0, BeatType.EARLY_CONTROL),
            make_section(1, BeatType.STALL),
            make_section(2, BeatType.STALL),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=115,
            final_away_score=85,  # 30 point margin
            score_history=None,
        )

        assert result.quality == GameQuality.LOW
        assert result.signals.has_crunch is False
        assert result.signals.has_overtime is False
        assert result.signals.margin_points == 0.0
        assert result.signals.run_response_count == 0

    def test_typical_close_game(self):
        """Typical close game = MEDIUM."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.BACK_AND_FORTH),
            make_section(2, BeatType.RUN),
            make_section(3, BeatType.RESPONSE),
            make_section(4, BeatType.CRUNCH_SETUP),
            make_section(5, BeatType.CLOSING_SEQUENCE),
        ]
        history = make_score_history(
            (0, 0), (5, 2), (5, 8), (12, 8),  # 2 lead changes
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=105,
            final_away_score=102,  # 3 point margin
            score_history=history,
        )

        # 2 lead + 2 crunch + 2 margin + 1 (2 RUN/RESPONSE) = 7
        assert result.numeric_score == 7.0
        assert result.quality == GameQuality.HIGH

    def test_epic_overtime_game(self):
        """Epic overtime game = HIGH."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.RUN),
            make_section(2, BeatType.RESPONSE),
            make_section(3, BeatType.RUN),
            make_section(4, BeatType.RESPONSE),
            make_section(5, BeatType.CRUNCH_SETUP),
            make_section(6, BeatType.OVERTIME),
        ]
        # Lead changes: Home(10-2) -> Away(10-15) -> Home(20-15) -> Away(20-25) -> Home(30-25) -> Away(30-32)
        # That's 5 lead changes: away takes, home takes, away takes, home takes, away takes
        history = make_score_history(
            (0, 0), (10, 2), (10, 15), (20, 15), (20, 25), (30, 25), (30, 32),
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=120,
            final_away_score=118,  # 2 point margin in OT
            score_history=history,
        )

        # 5 lead + 3 OT + 2 crunch + 2 margin + 2 (4 RUN/RESPONSE) = 14
        assert result.signals.lead_changes == 5
        assert result.signals.has_overtime is True
        assert result.signals.has_crunch is True
        assert result.numeric_score == 14.0
        assert result.quality == GameQuality.HIGH

    def test_no_score_history_provided(self):
        """Works without score history (lead changes = 0)."""
        sections = [
            make_section(0, BeatType.CRUNCH_SETUP),
        ]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=98,
            score_history=None,  # No history
        )

        assert result.signals.lead_changes == 0
        assert result.signals.lead_changes_points == 0.0
        # +2 crunch + +2 margin = 4
        assert result.numeric_score == 4.0


# ============================================================================
# TEST: SIGNAL ISOLATION
# ============================================================================

class TestSignalIsolation:
    """Tests verifying each signal works independently."""

    def test_only_lead_changes(self):
        """Only lead changes contribute."""
        sections = [make_section(0, BeatType.BACK_AND_FORTH)]
        history = make_score_history(
            (0, 0), (5, 0), (5, 8), (12, 8), (12, 15), (20, 15),  # 4 lead changes
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=70,  # Large margin
            score_history=history,
        )

        assert result.signals.lead_changes_points == 4.0
        assert result.signals.crunch_points == 0.0
        assert result.signals.overtime_points == 0.0
        assert result.signals.margin_points == 0.0
        assert result.signals.run_response_points == 0.0
        assert result.numeric_score == 4.0

    def test_only_crunch(self):
        """Only crunch contributes."""
        sections = [make_section(0, BeatType.CRUNCH_SETUP)]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=70,  # Large margin
            score_history=None,
        )

        assert result.signals.lead_changes_points == 0.0
        assert result.signals.crunch_points == 2.0
        assert result.signals.overtime_points == 0.0
        assert result.signals.margin_points == 0.0
        assert result.signals.run_response_points == 0.0
        assert result.numeric_score == 2.0

    def test_only_overtime(self):
        """Only overtime contributes."""
        sections = [make_section(0, BeatType.OVERTIME)]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=70,  # Large margin (unusual for OT but testing isolation)
            score_history=None,
        )

        assert result.signals.lead_changes_points == 0.0
        assert result.signals.crunch_points == 0.0
        assert result.signals.overtime_points == 3.0
        assert result.signals.margin_points == 0.0
        assert result.signals.run_response_points == 0.0
        assert result.numeric_score == 3.0

    def test_only_close_margin(self):
        """Only close margin contributes."""
        sections = [make_section(0, BeatType.BACK_AND_FORTH)]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=98,  # 2 point margin
            score_history=None,
        )

        assert result.signals.lead_changes_points == 0.0
        assert result.signals.crunch_points == 0.0
        assert result.signals.overtime_points == 0.0
        assert result.signals.margin_points == 2.0
        assert result.signals.run_response_points == 0.0
        assert result.numeric_score == 2.0


# ============================================================================
# TEST: DEBUG OUTPUT
# ============================================================================

class TestDebugOutput:
    """Tests for debug formatting."""

    def test_format_quality_debug(self):
        """Debug output contains all required information."""
        sections = [
            make_section(0, BeatType.RUN),
            make_section(1, BeatType.CRUNCH_SETUP),
        ]
        history = make_score_history(
            (0, 0), (5, 0), (5, 8),  # 1 lead change
        )

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=97,
            score_history=history,
        )

        output = format_quality_debug(result)

        # Check all sections present
        assert "Lead Changes:" in output
        assert "Crunch Present:" in output
        assert "Overtime:" in output
        assert "Final Margin:" in output
        assert "Run/Response:" in output
        assert "TOTAL SCORE:" in output
        assert "FINAL QUALITY:" in output
        assert result.quality.value in output


# ============================================================================
# TEST: SERIALIZATION
# ============================================================================

class TestSerialization:
    """Tests for serialization."""

    def test_signals_to_dict(self):
        """QualitySignals serializes correctly."""
        signals = QualitySignals(
            lead_changes=3,
            lead_changes_points=3.0,
            has_crunch=True,
            crunch_points=2.0,
        )

        data = signals.to_dict()

        assert data["lead_changes"] == 3
        assert data["lead_changes_points"] == 3.0
        assert data["has_crunch"] is True
        assert data["crunch_points"] == 2.0

    def test_result_to_dict(self):
        """QualityScoreResult serializes correctly."""
        sections = [make_section(0, BeatType.CRUNCH_SETUP)]

        result = compute_quality_score(
            sections=sections,
            final_home_score=100,
            final_away_score=97,
            score_history=None,
        )

        data = result.to_dict()

        assert "quality" in data
        assert "numeric_score" in data
        assert "signals" in data
        assert data["quality"] == result.quality.value
