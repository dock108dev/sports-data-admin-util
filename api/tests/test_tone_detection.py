"""Tests for tone detection module."""

import pytest

from app.services.pipeline.stages.tone_detection import (
    ToneCategory,
    detect_tone,
    get_tone_prompt_directives,
)


def _make_blocks(
    scores: list[tuple[list[int], list[int]]],
    roles: list[str] | None = None,
    period_ends: list[int] | None = None,
    peak_margins: list[int] | None = None,
) -> list[dict]:
    """Helper to build block dicts from score pairs."""
    blocks = []
    for i, (before, after) in enumerate(scores):
        block = {
            "block_index": i,
            "score_before": before,
            "score_after": after,
            "role": roles[i] if roles else "MOMENTUM_SHIFT",
            "period_start": (period_ends[i] if period_ends else i + 1),
            "period_end": (period_ends[i] if period_ends else i + 1),
        }
        if peak_margins and i < len(peak_margins):
            block["peak_margin"] = peak_margins[i]
        blocks.append(block)
    return blocks


class TestDetectToneBlowout:
    """Tests for blowout detection (>20pt margin for NBA)."""

    def test_nba_blowout_large_margin(self):
        blocks = _make_blocks([
            ([0, 0], [30, 10]),
            ([30, 10], [60, 20]),
            ([60, 20], [90, 60]),
            ([90, 60], [110, 85]),
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result == ToneCategory.BLOWOUT

    def test_nba_not_blowout_close_game(self):
        blocks = _make_blocks([
            ([0, 0], [25, 22]),
            ([25, 22], [50, 48]),
            ([50, 48], [75, 72]),
            ([75, 72], [100, 95]),
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result != ToneCategory.BLOWOUT

    def test_nba_blowout_threshold_boundary(self):
        """Exactly 20pt margin is NOT a blowout (must be >20)."""
        blocks = _make_blocks([
            ([0, 0], [30, 10]),
            ([30, 10], [55, 25]),
            ([55, 25], [80, 55]),
            ([80, 55], [100, 80]),
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result != ToneCategory.BLOWOUT

    def test_nba_blowout_21pt_margin(self):
        """21pt margin IS a blowout."""
        blocks = _make_blocks([
            ([0, 0], [30, 10]),
            ([30, 10], [60, 25]),
            ([60, 25], [85, 50]),
            ([85, 50], [111, 90]),
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result == ToneCategory.BLOWOUT

    def test_mlb_blowout(self):
        """MLB blowout threshold is 7 runs (must be >7)."""
        blocks = _make_blocks([
            ([0, 0], [3, 0]),
            ([3, 0], [6, 1]),
            ([6, 1], [10, 1]),
        ], period_ends=[3, 6, 9])
        result = detect_tone(blocks, {}, "MLB")
        assert result == ToneCategory.BLOWOUT


class TestDetectToneComeback:
    """Tests for comeback detection (>10pt swing in final quarter)."""

    def test_nba_comeback_large_swing(self):
        """Team trailing by 15 comes back to win in Q4 — lead changes hands."""
        blocks = _make_blocks([
            ([0, 0], [25, 15]),
            ([25, 15], [50, 35]),   # Home leads by 15
            ([50, 35], [70, 60]),
            ([70, 60], [85, 92]),   # Away takes lead in Q4, swing of 17
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result == ToneCategory.COMEBACK

    def test_nba_no_comeback_steady_game(self):
        blocks = _make_blocks([
            ([0, 0], [25, 23]),
            ([25, 23], [50, 48]),
            ([50, 48], [75, 73]),
            ([75, 73], [100, 98]),
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result != ToneCategory.COMEBACK

    def test_comeback_lead_changes_hands(self):
        """Lead changes from home to away in the final period."""
        blocks = _make_blocks([
            ([0, 0], [20, 15]),
            ([20, 15], [45, 30]),
            ([45, 30], [65, 55]),
            ([65, 55], [80, 92]),  # Away storms back, swing of 22
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result == ToneCategory.COMEBACK


class TestDetectToneUpset:
    """Tests for upset detection (underdog wins by >15pts)."""

    def test_upset_with_expected_winner(self):
        blocks = _make_blocks([
            ([0, 0], [25, 20]),
            ([25, 20], [50, 45]),
            ([50, 45], [80, 70]),
            ([80, 70], [110, 90]),
        ], period_ends=[1, 2, 3, 4])
        context = {
            "expected_winner": "Team A",
            "actual_winner": "Team B",
        }
        result = detect_tone(blocks, context, "NBA")
        assert result == ToneCategory.UPSET_ALERT

    def test_no_upset_when_favorite_wins(self):
        blocks = _make_blocks([
            ([0, 0], [25, 20]),
            ([25, 20], [50, 45]),
            ([50, 45], [80, 70]),
            ([80, 70], [110, 90]),
        ], period_ends=[1, 2, 3, 4])
        context = {
            "expected_winner": "Team A",
            "actual_winner": "Team A",
        }
        result = detect_tone(blocks, context, "NBA")
        assert result != ToneCategory.UPSET_ALERT

    def test_upset_with_low_pregame_probability(self):
        blocks = _make_blocks([
            ([0, 0], [20, 15]),
            ([20, 15], [45, 30]),
            ([45, 30], [70, 50]),
            ([70, 50], [96, 78]),
        ], period_ends=[1, 2, 3, 4])
        context = {"pregame_win_probability": "0.25"}
        result = detect_tone(blocks, context, "NBA")
        assert result == ToneCategory.UPSET_ALERT

    def test_no_upset_close_margin(self):
        """Even if underdog wins, margin must be >15."""
        blocks = _make_blocks([
            ([0, 0], [25, 22]),
            ([25, 22], [50, 48]),
            ([50, 48], [75, 72]),
            ([75, 72], [100, 95]),
        ], period_ends=[1, 2, 3, 4])
        context = {
            "expected_winner": "Team A",
            "actual_winner": "Team B",
        }
        result = detect_tone(blocks, context, "NBA")
        assert result != ToneCategory.UPSET_ALERT


class TestDetectTonePitcherDuel:
    """Tests for pitcher duel detection (MLB-only, low-scoring)."""

    def test_pitchers_duel(self):
        blocks = _make_blocks([
            ([0, 0], [0, 0]),
            ([0, 0], [1, 0]),
            ([1, 0], [1, 1]),
        ], period_ends=[3, 6, 9])
        result = detect_tone(blocks, {}, "MLB")
        assert result == ToneCategory.PITCHER_DUEL

    def test_not_pitchers_duel_high_scoring(self):
        blocks = _make_blocks([
            ([0, 0], [3, 2]),
            ([3, 2], [5, 4]),
            ([5, 4], [7, 6]),
        ], period_ends=[3, 6, 9])
        result = detect_tone(blocks, {}, "MLB")
        assert result != ToneCategory.PITCHER_DUEL

    def test_pitchers_duel_only_mlb(self):
        """Pitcher duel detection should not trigger for NBA."""
        blocks = _make_blocks([
            ([0, 0], [1, 0]),
            ([1, 0], [1, 1]),
            ([1, 1], [2, 1]),
        ], period_ends=[1, 2, 3])
        result = detect_tone(blocks, {}, "NBA")
        assert result != ToneCategory.PITCHER_DUEL


class TestDetectToneHistoric:
    def test_historic_milestone(self):
        blocks = _make_blocks([
            ([0, 0], [25, 20]),
            ([25, 20], [50, 45]),
        ], period_ends=[1, 2])
        context = {"has_milestone": True}
        result = detect_tone(blocks, context, "NBA")
        assert result == ToneCategory.HISTORIC


class TestDetectToneRivalry:
    def test_rivalry_game(self):
        blocks = _make_blocks([
            ([0, 0], [25, 22]),
            ([25, 22], [50, 48]),
            ([50, 48], [75, 72]),
            ([75, 72], [100, 98]),
        ], period_ends=[1, 2, 3, 4])
        context = {"is_division_rival": True}
        result = detect_tone(blocks, context, "NBA")
        assert result == ToneCategory.RIVALRY


class TestDetectToneStandard:
    def test_standard_game(self):
        blocks = _make_blocks([
            ([0, 0], [25, 22]),
            ([25, 22], [50, 48]),
            ([50, 48], [75, 72]),
            ([75, 72], [100, 95]),
        ], period_ends=[1, 2, 3, 4])
        result = detect_tone(blocks, {}, "NBA")
        assert result == ToneCategory.STANDARD

    def test_empty_blocks(self):
        result = detect_tone([], {}, "NBA")
        assert result == ToneCategory.STANDARD


class TestDetectTonePriority:
    """Tone categories are checked in priority order."""

    def test_historic_beats_blowout(self):
        blocks = _make_blocks([
            ([0, 0], [30, 5]),
            ([30, 5], [60, 10]),
            ([60, 10], [90, 20]),
            ([90, 20], [120, 40]),
        ], period_ends=[1, 2, 3, 4])
        context = {"has_milestone": True}
        result = detect_tone(blocks, context, "NBA")
        assert result == ToneCategory.HISTORIC


class TestGetTonePromptDirectives:
    def test_standard_directives(self):
        result = get_tone_prompt_directives(ToneCategory.STANDARD)
        assert "TONE: STANDARD" in result
        assert "Voice:" in result
        assert "Emphasis:" in result
        assert "Pacing:" in result

    def test_blowout_directives(self):
        result = get_tone_prompt_directives(ToneCategory.BLOWOUT)
        assert "TONE: BLOWOUT" in result
        assert "drama" in result.lower()

    def test_comeback_directives(self):
        result = get_tone_prompt_directives(ToneCategory.COMEBACK)
        assert "TONE: COMEBACK" in result
        assert "crescendo" in result.lower() or "turning" in result.lower()

    def test_all_categories_have_directives(self):
        for tone in ToneCategory:
            result = get_tone_prompt_directives(tone)
            assert "Voice:" in result
            assert "Emphasis:" in result
            assert "Pacing:" in result
