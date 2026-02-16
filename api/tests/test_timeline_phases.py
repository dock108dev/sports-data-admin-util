"""Tests for time-based tweet classification functions.

Tests the league-aware, time-based phase classification and segment mapping
implemented in timeline_phases.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.timeline_phases import (
    get_league_timing,
    estimate_game_end,
    compute_league_phase_boundaries,
)
from app.services.tweet_phase_classifier import (
    classify_tweet_phase,
    map_tweet_to_segment,
    assign_tweet_phase_and_segment,
)
from app.services.timeline_types import (
    NCAAB_REGULATION_REAL_MINUTES,
    NBA_REGULATION_REAL_MINUTES,
    NHL_REGULATION_REAL_MINUTES,
)


@pytest.fixture
def game_start() -> datetime:
    """Sample game start time."""
    return datetime(2026, 1, 15, 19, 0, 0, tzinfo=timezone.utc)


class TestGetLeagueTiming:
    """Tests for get_league_timing function."""

    def test_nba_timing(self):
        """NBA returns correct timing constants."""
        reg, ot = get_league_timing("NBA")
        assert reg == NBA_REGULATION_REAL_MINUTES
        assert ot == 20  # NBA_OT_BUFFER_MINUTES

    def test_ncaab_timing(self):
        """NCAAB returns correct timing constants."""
        reg, ot = get_league_timing("NCAAB")
        assert reg == NCAAB_REGULATION_REAL_MINUTES
        assert ot == 15  # NCAAB_OT_BUFFER_MINUTES

    def test_nhl_timing(self):
        """NHL returns correct timing constants."""
        reg, ot = get_league_timing("NHL")
        assert reg == NHL_REGULATION_REAL_MINUTES
        assert ot == 20  # NHL_OT_BUFFER_MINUTES

    def test_unknown_league_defaults_to_nba(self):
        """Unknown league defaults to NBA timing."""
        reg, ot = get_league_timing("UNKNOWN")
        assert reg == NBA_REGULATION_REAL_MINUTES
        assert ot == 20

    def test_case_insensitive(self):
        """League code is case-insensitive."""
        reg1, ot1 = get_league_timing("nba")
        reg2, ot2 = get_league_timing("NBA")
        assert reg1 == reg2
        assert ot1 == ot2


class TestEstimateGameEnd:
    """Tests for estimate_game_end function."""

    def test_nba_regulation(self, game_start):
        """NBA regulation game ends ~2h45m after start."""
        end = estimate_game_end(game_start, "NBA", has_overtime=False)
        expected = game_start + timedelta(minutes=NBA_REGULATION_REAL_MINUTES)
        assert end == expected

    def test_nba_with_overtime(self, game_start):
        """NBA overtime adds ~20 minutes."""
        end = estimate_game_end(game_start, "NBA", has_overtime=True)
        expected = game_start + timedelta(minutes=NBA_REGULATION_REAL_MINUTES + 20)
        assert end == expected

    def test_ncaab_regulation(self, game_start):
        """NCAAB regulation game ends ~2h15m after start."""
        end = estimate_game_end(game_start, "NCAAB", has_overtime=False)
        expected = game_start + timedelta(minutes=NCAAB_REGULATION_REAL_MINUTES)
        assert end == expected


class TestClassifyTweetPhase:
    """Tests for classify_tweet_phase function."""

    def test_pregame_tweet(self, game_start):
        """Tweet before game start is pregame."""
        tweet_time = game_start - timedelta(hours=1)
        phase = classify_tweet_phase(tweet_time, game_start, "NBA")
        assert phase == "pregame"

    def test_in_game_tweet_early(self, game_start):
        """Tweet at game start is in-game."""
        tweet_time = game_start + timedelta(minutes=5)
        phase = classify_tweet_phase(tweet_time, game_start, "NBA")
        assert phase == "in_game"

    def test_in_game_tweet_middle(self, game_start):
        """Tweet in middle of game is in-game."""
        tweet_time = game_start + timedelta(minutes=90)
        phase = classify_tweet_phase(tweet_time, game_start, "NBA")
        assert phase == "in_game"

    def test_postgame_tweet(self, game_start):
        """Tweet after game end is postgame."""
        tweet_time = game_start + timedelta(minutes=200)
        phase = classify_tweet_phase(tweet_time, game_start, "NBA")
        assert phase == "postgame"

    def test_postgame_tweet_late(self, game_start):
        """Tweet hours after game is still postgame."""
        tweet_time = game_start + timedelta(hours=6)
        phase = classify_tweet_phase(tweet_time, game_start, "NBA")
        assert phase == "postgame"

    def test_overtime_extends_in_game(self, game_start):
        """Overtime extends the in-game window."""
        # Without overtime, this would be postgame
        tweet_time = game_start + timedelta(minutes=170)

        phase_no_ot = classify_tweet_phase(
            tweet_time, game_start, "NBA", has_overtime=False
        )
        phase_with_ot = classify_tweet_phase(
            tweet_time, game_start, "NBA", has_overtime=True
        )

        assert phase_no_ot == "postgame"
        assert phase_with_ot == "in_game"


class TestMapTweetToSegment:
    """Tests for map_tweet_to_segment function."""

    def test_nba_q1(self, game_start):
        """Early tweet maps to Q1."""
        tweet_time = game_start + timedelta(minutes=10)
        segment = map_tweet_to_segment(tweet_time, game_start, "NBA")
        assert segment == "q1"

    def test_nba_q2(self, game_start):
        """Mid-first-half tweet maps to Q2."""
        tweet_time = game_start + timedelta(minutes=50)
        segment = map_tweet_to_segment(tweet_time, game_start, "NBA")
        assert segment == "q2"

    def test_nba_halftime(self, game_start):
        """Half-way tweet maps to halftime."""
        tweet_time = game_start + timedelta(minutes=75)
        segment = map_tweet_to_segment(tweet_time, game_start, "NBA")
        assert segment == "halftime"

    def test_nba_q3(self, game_start):
        """Third-quarter tweet maps to Q3."""
        tweet_time = game_start + timedelta(minutes=100)
        segment = map_tweet_to_segment(tweet_time, game_start, "NBA")
        assert segment == "q3"

    def test_nba_q4(self, game_start):
        """Late game tweet maps to Q4."""
        tweet_time = game_start + timedelta(minutes=140)
        segment = map_tweet_to_segment(tweet_time, game_start, "NBA")
        assert segment == "q4"

    def test_ncaab_first_half(self, game_start):
        """Early NCAAB tweet maps to first_half."""
        tweet_time = game_start + timedelta(minutes=30)
        segment = map_tweet_to_segment(tweet_time, game_start, "NCAAB")
        assert segment == "first_half"

    def test_ncaab_halftime(self, game_start):
        """Mid-game NCAAB tweet maps to halftime."""
        tweet_time = game_start + timedelta(minutes=65)
        segment = map_tweet_to_segment(tweet_time, game_start, "NCAAB")
        assert segment == "halftime"

    def test_ncaab_second_half(self, game_start):
        """Late NCAAB tweet maps to second_half."""
        tweet_time = game_start + timedelta(minutes=100)
        segment = map_tweet_to_segment(tweet_time, game_start, "NCAAB")
        assert segment == "second_half"

    def test_nhl_p1(self, game_start):
        """Early NHL tweet maps to p1."""
        tweet_time = game_start + timedelta(minutes=30)
        segment = map_tweet_to_segment(tweet_time, game_start, "NHL")
        assert segment == "p1"

    def test_nhl_p2(self, game_start):
        """Mid-game NHL tweet maps to p2."""
        tweet_time = game_start + timedelta(minutes=80)
        segment = map_tweet_to_segment(tweet_time, game_start, "NHL")
        assert segment == "p2"

    def test_nhl_p3(self, game_start):
        """Late NHL tweet maps to p3."""
        tweet_time = game_start + timedelta(minutes=130)
        segment = map_tweet_to_segment(tweet_time, game_start, "NHL")
        assert segment == "p3"

    def test_nhl_overtime(self, game_start):
        """Very late NHL tweet with OT maps to ot."""
        # Near end of estimated duration with OT
        tweet_time = game_start + timedelta(minutes=180)
        segment = map_tweet_to_segment(tweet_time, game_start, "NHL", has_overtime=True)
        assert segment == "ot"


class TestAssignTweetPhaseAndSegment:
    """Tests for assign_tweet_phase_and_segment combined function."""

    def test_pregame_no_segment(self, game_start):
        """Pregame tweets have no segment."""
        tweet_time = game_start - timedelta(minutes=30)
        phase, segment = assign_tweet_phase_and_segment(tweet_time, game_start, "NBA")
        assert phase == "pregame"
        assert segment is None

    def test_in_game_with_segment(self, game_start):
        """In-game tweets have a segment."""
        tweet_time = game_start + timedelta(minutes=50)
        phase, segment = assign_tweet_phase_and_segment(tweet_time, game_start, "NBA")
        assert phase == "in_game"
        assert segment == "q2"

    def test_postgame_no_segment(self, game_start):
        """Postgame tweets have no segment."""
        tweet_time = game_start + timedelta(hours=4)
        phase, segment = assign_tweet_phase_and_segment(tweet_time, game_start, "NBA")
        assert phase == "postgame"
        assert segment is None


class TestComputeLeaguePhaseBoundaries:
    """Tests for compute_league_phase_boundaries function."""

    def test_nba_has_all_phases(self, game_start):
        """NBA boundaries include all expected phases."""
        boundaries = compute_league_phase_boundaries(game_start, "NBA")

        expected_phases = ["pregame", "q1", "q2", "halftime", "q3", "q4", "postgame"]
        for phase in expected_phases:
            assert phase in boundaries
            start, end = boundaries[phase]
            assert start < end

    def test_ncaab_has_all_phases(self, game_start):
        """NCAAB boundaries include halves instead of quarters."""
        boundaries = compute_league_phase_boundaries(game_start, "NCAAB")

        expected_phases = [
            "pregame",
            "first_half",
            "halftime",
            "second_half",
            "postgame",
        ]
        for phase in expected_phases:
            assert phase in boundaries
            start, end = boundaries[phase]
            assert start < end

    def test_nhl_has_all_phases(self, game_start):
        """NHL boundaries include three periods."""
        boundaries = compute_league_phase_boundaries(game_start, "NHL")

        expected_phases = ["pregame", "p1", "p2", "p3", "postgame"]
        for phase in expected_phases:
            assert phase in boundaries
            start, end = boundaries[phase]
            assert start < end

    def test_overtime_adds_ot_phase_nba(self, game_start):
        """NBA with OT includes ot1 phase."""
        boundaries = compute_league_phase_boundaries(
            game_start, "NBA", has_overtime=True
        )
        assert "ot1" in boundaries

    def test_overtime_adds_ot_phase_ncaab(self, game_start):
        """NCAAB with OT includes ot phase."""
        boundaries = compute_league_phase_boundaries(
            game_start, "NCAAB", has_overtime=True
        )
        assert "ot" in boundaries

    def test_overtime_adds_ot_phase_nhl(self, game_start):
        """NHL with OT includes ot phase."""
        boundaries = compute_league_phase_boundaries(
            game_start, "NHL", has_overtime=True
        )
        assert "ot" in boundaries

    def test_pregame_starts_2_hours_before(self, game_start):
        """Pregame window starts 2 hours before game."""
        boundaries = compute_league_phase_boundaries(game_start, "NBA")
        pregame_start, pregame_end = boundaries["pregame"]

        expected_start = game_start - timedelta(hours=2)
        assert pregame_start == expected_start
        assert pregame_end == game_start
