"""Tests for normalize_pbp stage helper functions."""

from datetime import datetime, timedelta


class TestNbaPhaseForQuarter:
    """Tests for _nba_phase_for_quarter function."""

    def test_quarter_1(self):
        """Quarter 1 returns q1."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(1) == "q1"

    def test_quarter_2(self):
        """Quarter 2 returns q2."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(2) == "q2"

    def test_quarter_3(self):
        """Quarter 3 returns q3."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(3) == "q3"

    def test_quarter_4(self):
        """Quarter 4 returns q4."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(4) == "q4"

    def test_overtime_1(self):
        """Quarter 5 (OT1) returns ot1."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(5) == "ot1"

    def test_overtime_2(self):
        """Quarter 6 (OT2) returns ot2."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(6) == "ot2"

    def test_overtime_3(self):
        """Quarter 7 (OT3) returns ot3."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(7) == "ot3"

    def test_overtime_4(self):
        """Quarter 8 (OT4) returns ot4."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(8) == "ot4"

    def test_none_returns_unknown(self):
        """None returns unknown."""
        from app.services.pipeline.stages.normalize_pbp import _nba_phase_for_quarter

        assert _nba_phase_for_quarter(None) == "unknown"


class TestNbaBlockForQuarter:
    """Tests for _nba_block_for_quarter function."""

    def test_first_half(self):
        """Quarters 1-2 are first_half."""
        from app.services.pipeline.stages.normalize_pbp import _nba_block_for_quarter

        assert _nba_block_for_quarter(1) == "first_half"
        assert _nba_block_for_quarter(2) == "first_half"

    def test_second_half(self):
        """Quarters 3-4 are second_half."""
        from app.services.pipeline.stages.normalize_pbp import _nba_block_for_quarter

        assert _nba_block_for_quarter(3) == "second_half"
        assert _nba_block_for_quarter(4) == "second_half"

    def test_overtime(self):
        """Quarters 5+ are overtime."""
        from app.services.pipeline.stages.normalize_pbp import _nba_block_for_quarter

        assert _nba_block_for_quarter(5) == "overtime"
        assert _nba_block_for_quarter(6) == "overtime"

    def test_none_returns_unknown(self):
        """None returns unknown."""
        from app.services.pipeline.stages.normalize_pbp import _nba_block_for_quarter

        assert _nba_block_for_quarter(None) == "unknown"


class TestNbaQuarterStart:
    """Tests for _nba_quarter_start function."""

    def test_quarter_1_starts_at_game_start(self):
        """Quarter 1 starts at game start."""
        from app.services.pipeline.stages.normalize_pbp import _nba_quarter_start

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nba_quarter_start(game_start, 1)
        assert result == game_start

    def test_quarter_2_timing(self):
        """Quarter 2 starts after Q1."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_quarter_start,
            NBA_QUARTER_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nba_quarter_start(game_start, 2)
        expected = game_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
        assert result == expected

    def test_quarter_3_timing(self):
        """Quarter 3 starts after halftime."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_quarter_start,
            NBA_QUARTER_REAL_SECONDS,
            NBA_HALFTIME_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nba_quarter_start(game_start, 3)
        expected = game_start + timedelta(
            seconds=2 * NBA_QUARTER_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS
        )
        assert result == expected

    def test_quarter_4_timing(self):
        """Quarter 4 starts after Q3."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_quarter_start,
            NBA_QUARTER_REAL_SECONDS,
            NBA_HALFTIME_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nba_quarter_start(game_start, 4)
        expected = game_start + timedelta(
            seconds=3 * NBA_QUARTER_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS
        )
        assert result == expected


class TestProgressFromIndex:
    """Tests for _progress_from_index function."""

    def test_first_play(self):
        """First play is 0.0 progress."""
        from app.services.pipeline.stages.normalize_pbp import _progress_from_index

        assert _progress_from_index(0, 100) == 0.0

    def test_last_play(self):
        """Last play is 1.0 progress."""
        from app.services.pipeline.stages.normalize_pbp import _progress_from_index

        assert _progress_from_index(99, 100) == 1.0

    def test_middle_play(self):
        """Middle play is 0.5 progress."""
        from app.services.pipeline.stages.normalize_pbp import _progress_from_index

        assert _progress_from_index(50, 101) == 0.5

    def test_single_play(self):
        """Single play game is 0.0 progress."""
        from app.services.pipeline.stages.normalize_pbp import _progress_from_index

        assert _progress_from_index(0, 1) == 0.0

    def test_two_plays(self):
        """Two play game has correct progress."""
        from app.services.pipeline.stages.normalize_pbp import _progress_from_index

        assert _progress_from_index(0, 2) == 0.0
        assert _progress_from_index(1, 2) == 1.0


class TestComputePhaseBoundaries:
    """Tests for _compute_phase_boundaries function."""

    def test_has_all_phases(self):
        """All standard phases are present."""
        from app.services.pipeline.stages.normalize_pbp import _compute_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_phase_boundaries(game_start, has_overtime=False)

        assert "pregame" in boundaries
        assert "q1" in boundaries
        assert "q2" in boundaries
        assert "halftime" in boundaries
        assert "q3" in boundaries
        assert "q4" in boundaries
        assert "postgame" in boundaries

    def test_overtime_phases(self):
        """Overtime phases present when has_overtime=True."""
        from app.services.pipeline.stages.normalize_pbp import _compute_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_phase_boundaries(game_start, has_overtime=True)

        assert "ot1" in boundaries
        assert "ot2" in boundaries
        assert "ot3" in boundaries
        assert "ot4" in boundaries

    def test_no_overtime_phases_when_false(self):
        """No overtime phases when has_overtime=False."""
        from app.services.pipeline.stages.normalize_pbp import _compute_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_phase_boundaries(game_start, has_overtime=False)

        assert "ot1" not in boundaries

    def test_boundaries_are_tuples(self):
        """Each boundary is a (start, end) tuple."""
        from app.services.pipeline.stages.normalize_pbp import _compute_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_phase_boundaries(game_start)

        for phase, (start, end) in boundaries.items():
            assert isinstance(start, datetime)
            assert isinstance(end, datetime)
            assert end > start

    def test_pregame_ends_at_game_start(self):
        """Pregame ends when game starts."""
        from app.services.pipeline.stages.normalize_pbp import _compute_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_phase_boundaries(game_start)

        _, pregame_end = boundaries["pregame"]
        assert pregame_end == game_start

    def test_q1_starts_at_game_start(self):
        """Q1 starts when game starts."""
        from app.services.pipeline.stages.normalize_pbp import _compute_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_phase_boundaries(game_start)

        q1_start, _ = boundaries["q1"]
        assert q1_start == game_start


class TestComputeResolutionStats:
    """Tests for _compute_resolution_stats function."""

    def test_empty_plays(self):
        """Empty plays returns zero stats."""
        from app.services.pipeline.stages.normalize_pbp import _compute_resolution_stats

        result = _compute_resolution_stats([])

        assert result["total_plays"] == 0
        assert result["teams_resolved"] == 0
        assert result["teams_unresolved"] == 0
        assert result["players_with_name"] == 0
        assert result["players_without_name"] == 0
        assert result["plays_with_score"] == 0
        assert result["plays_without_score"] == 0

    def test_counts_teams_resolved(self):
        """Counts plays with team_id."""
        from app.services.pipeline.stages.normalize_pbp import _compute_resolution_stats

        class MockPlay:
            def __init__(self, team_id=None, player_name=None, home_score=None, game_clock="12:00"):
                self.team_id = team_id
                self.player_name = player_name
                self.home_score = home_score
                self.game_clock = game_clock
                self.raw_data = {}

        plays = [
            MockPlay(team_id=1),
            MockPlay(team_id=2),
            MockPlay(team_id=None),
        ]
        result = _compute_resolution_stats(plays)

        assert result["total_plays"] == 3
        assert result["teams_resolved"] == 2

    def test_counts_players_with_name(self):
        """Counts plays with player_name."""
        from app.services.pipeline.stages.normalize_pbp import _compute_resolution_stats

        class MockPlay:
            def __init__(self, team_id=None, player_name=None, home_score=None, game_clock="12:00"):
                self.team_id = team_id
                self.player_name = player_name
                self.home_score = home_score
                self.game_clock = game_clock
                self.raw_data = {}

        plays = [
            MockPlay(player_name="Smith"),
            MockPlay(player_name="Jones"),
            MockPlay(player_name=None),
        ]
        result = _compute_resolution_stats(plays)

        assert result["players_with_name"] == 2
        assert result["players_without_name"] == 1

    def test_counts_plays_with_score(self):
        """Counts plays with score information."""
        from app.services.pipeline.stages.normalize_pbp import _compute_resolution_stats

        class MockPlay:
            def __init__(self, team_id=None, player_name=None, home_score=None, game_clock="12:00"):
                self.team_id = team_id
                self.player_name = player_name
                self.home_score = home_score
                self.game_clock = game_clock
                self.raw_data = {}

        plays = [
            MockPlay(home_score=10),
            MockPlay(home_score=12),
            MockPlay(home_score=None),
        ]
        result = _compute_resolution_stats(plays)

        assert result["plays_with_score"] == 2
        assert result["plays_without_score"] == 1

    def test_calculates_resolution_rate(self):
        """Calculates team resolution rate correctly."""
        from app.services.pipeline.stages.normalize_pbp import _compute_resolution_stats

        class MockPlay:
            def __init__(self, team_id=None, player_name=None, home_score=None, game_clock="12:00"):
                self.team_id = team_id
                self.player_name = player_name
                self.home_score = home_score
                self.game_clock = game_clock
                self.raw_data = {}

        plays = [
            MockPlay(team_id=1),
            MockPlay(team_id=2),
            MockPlay(team_id=None),
            MockPlay(team_id=None),
        ]
        result = _compute_resolution_stats(plays)

        assert result["team_resolution_rate"] == 50.0  # 2/4 = 50%

    def test_counts_clock_parse_failures(self):
        """Counts plays without game_clock."""
        from app.services.pipeline.stages.normalize_pbp import _compute_resolution_stats

        class MockPlay:
            def __init__(self, game_clock=None):
                self.team_id = None
                self.player_name = None
                self.home_score = None
                self.game_clock = game_clock
                self.raw_data = {}

        plays = [
            MockPlay(game_clock="12:00"),
            MockPlay(game_clock=None),
            MockPlay(game_clock=""),
        ]
        result = _compute_resolution_stats(plays)

        assert result["clock_parse_failures"] == 2

    def test_counts_teams_unresolved(self):
        """Counts teams unresolved when raw_data has team info."""
        from app.services.pipeline.stages.normalize_pbp import _compute_resolution_stats

        class MockPlay:
            def __init__(self, team_id=None, raw_data=None):
                self.team_id = team_id
                self.player_name = None
                self.home_score = None
                self.game_clock = "12:00"
                self.raw_data = raw_data or {}

        plays = [
            MockPlay(team_id=1),  # resolved
            MockPlay(team_id=None, raw_data={"teamTricode": "LAL"}),  # unresolved with data
            MockPlay(team_id=None, raw_data={}),  # no team data at all
        ]
        result = _compute_resolution_stats(plays)

        assert result["teams_resolved"] == 1
        assert result["teams_unresolved"] == 1


class TestNbaGameEnd:
    """Tests for _nba_game_end function."""

    def test_regulation_game(self):
        """Regulation game ends after 4 quarters."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_game_end,
            NBA_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 1
        play2 = MagicMock()
        play2.quarter = 4

        plays = [play1, play2]
        result = _nba_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)
        assert result == expected

    def test_single_overtime(self):
        """Game with 1 OT ends after 5th quarter."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_game_end,
            NBA_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 4
        play2 = MagicMock()
        play2.quarter = 5  # OT1

        plays = [play1, play2]
        result = _nba_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS + 15 * 60)
        assert result == expected

    def test_double_overtime(self):
        """Game with 2 OT ends after 6th quarter."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_game_end,
            NBA_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        plays = [MagicMock(quarter=q) for q in [1, 2, 3, 4, 5, 6]]
        result = _nba_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS + 2 * 15 * 60)
        assert result == expected

    def test_empty_plays(self):
        """Empty plays defaults to regulation end."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_game_end,
            NBA_REGULATION_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nba_game_end(game_start, [])

        expected = game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)
        assert result == expected

    def test_none_quarter_ignored(self):
        """Plays with None quarter don't affect max."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nba_game_end,
            NBA_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 4
        play2 = MagicMock()
        play2.quarter = None

        plays = [play1, play2]
        result = _nba_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)
        assert result == expected


class TestBuildPbpEvents:
    """Tests for _build_pbp_events function."""

    def _make_play(
        self,
        play_index,
        quarter=1,
        game_clock="12:00",
        home_score=0,
        away_score=0,
        description="",
        play_type="other",
        player_name=None,
        team=None,
    ):
        """Create a mock play object."""
        from unittest.mock import MagicMock

        play = MagicMock()
        play.play_index = play_index
        play.quarter = quarter
        play.game_clock = game_clock
        play.home_score = home_score
        play.away_score = away_score
        play.description = description
        play.play_type = play_type
        play.player_name = player_name
        play.team = team
        return play

    def test_empty_plays(self):
        """Empty plays returns empty list."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        events, violations = _build_pbp_events([], game_start)

        assert events == []
        assert violations == []

    def test_basic_event_structure(self):
        """Events have required fields."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [self._make_play(1, quarter=1, game_clock="11:30", home_score=2, away_score=0)]
        events, _ = _build_pbp_events(plays, game_start)

        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "pbp"
        assert event["phase"] == "q1"
        assert event["block"] == "first_half"
        assert event["play_index"] == 1
        assert event["quarter"] == 1
        assert event["game_clock"] == "11:30"
        assert event["home_score"] == 2
        assert event["away_score"] == 0
        assert "synthetic_timestamp" in event
        assert "game_progress" in event

    def test_score_continuity_enforced(self):
        """Scores carry forward and never reset."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=1, home_score=0, away_score=0),
            self._make_play(2, quarter=1, home_score=10, away_score=5),
            self._make_play(3, quarter=2, home_score=0, away_score=0),  # Invalid reset
            self._make_play(4, quarter=2, home_score=15, away_score=10),
        ]
        events, violations = _build_pbp_events(plays, game_start, game_id=123)

        # Score should carry forward past the reset
        assert events[2]["home_score"] == 10  # Carried from previous
        assert events[2]["away_score"] == 5
        assert len(violations) == 1
        assert violations[0]["type"] == "SCORE_RESET"

    def test_score_decrease_violation(self):
        """Score decrease triggers violation."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=1, home_score=10, away_score=5),
            self._make_play(2, quarter=1, home_score=8, away_score=5),  # Decrease!
        ]
        events, violations = _build_pbp_events(plays, game_start, game_id=123)

        assert len(violations) == 1
        assert violations[0]["type"] == "SCORE_DECREASE"
        # Score should carry forward
        assert events[1]["home_score"] == 10

    def test_team_abbreviation_extracted(self):
        """Team abbreviation extracted from relationship."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        team = MagicMock()
        team.abbreviation = "LAL"

        plays = [self._make_play(1, team=team)]
        events, _ = _build_pbp_events(plays, game_start)

        assert events[0]["team_abbreviation"] == "LAL"

    def test_none_clock_uses_play_index(self):
        """None game_clock uses play_index for ordering."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [self._make_play(5, game_clock=None)]
        events, _ = _build_pbp_events(plays, game_start)

        assert events[0]["intra_phase_order"] == 5

    def test_multiple_quarters(self):
        """Events from multiple quarters have correct phases."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=1, home_score=5, away_score=3),
            self._make_play(2, quarter=2, home_score=25, away_score=20),
            self._make_play(3, quarter=3, home_score=50, away_score=45),
            self._make_play(4, quarter=4, home_score=100, away_score=95),
        ]
        events, _ = _build_pbp_events(plays, game_start)

        assert events[0]["phase"] == "q1"
        assert events[1]["phase"] == "q2"
        assert events[2]["phase"] == "q3"
        assert events[3]["phase"] == "q4"

        assert events[0]["block"] == "first_half"
        assert events[1]["block"] == "first_half"
        assert events[2]["block"] == "second_half"
        assert events[3]["block"] == "second_half"

    def test_overtime_phases(self):
        """Overtime quarters get correct phases."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=5, home_score=100, away_score=100),
            self._make_play(2, quarter=6, home_score=110, away_score=110),
        ]
        events, _ = _build_pbp_events(plays, game_start)

        assert events[0]["phase"] == "ot1"
        assert events[1]["phase"] == "ot2"
        assert events[0]["block"] == "overtime"
        assert events[1]["block"] == "overtime"

    def test_partial_score_only_home(self):
        """Only home score provided."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, home_score=10, away_score=None),
        ]
        events, _ = _build_pbp_events(plays, game_start)

        assert events[0]["home_score"] == 10
        assert events[0]["away_score"] == 0  # Default

    def test_partial_score_only_away(self):
        """Only away score provided."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, home_score=None, away_score=10),
        ]
        events, _ = _build_pbp_events(plays, game_start)

        assert events[0]["home_score"] == 0  # Default
        assert events[0]["away_score"] == 10

    def test_ncaab_league_uses_half_phases(self):
        """NCAAB games use h1/h2 phases instead of q1-q4."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=1, home_score=20, away_score=15),
            self._make_play(2, quarter=2, home_score=60, away_score=55),
        ]
        events, _ = _build_pbp_events(plays, game_start, league_code="NCAAB")

        assert events[0]["phase"] == "h1"
        assert events[1]["phase"] == "h2"
        assert events[0]["block"] == "first_half"
        assert events[1]["block"] == "second_half"

    def test_ncaab_overtime_phases(self):
        """NCAAB overtime uses ot1, ot2 starting from period 3."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=3, home_score=70, away_score=70),  # OT1
            self._make_play(2, quarter=4, home_score=80, away_score=80),  # OT2
        ]
        events, _ = _build_pbp_events(plays, game_start, league_code="NCAAB")

        assert events[0]["phase"] == "ot1"
        assert events[1]["phase"] == "ot2"
        assert events[0]["block"] == "overtime"
        assert events[1]["block"] == "overtime"


class TestNcaabPhaseForPeriod:
    """Tests for _ncaab_phase_for_period function."""

    def test_half_1(self):
        """Period 1 returns h1."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_phase_for_period

        assert _ncaab_phase_for_period(1) == "h1"

    def test_half_2(self):
        """Period 2 returns h2."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_phase_for_period

        assert _ncaab_phase_for_period(2) == "h2"

    def test_overtime_1(self):
        """Period 3 (OT1) returns ot1."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_phase_for_period

        assert _ncaab_phase_for_period(3) == "ot1"

    def test_overtime_2(self):
        """Period 4 (OT2) returns ot2."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_phase_for_period

        assert _ncaab_phase_for_period(4) == "ot2"

    def test_none_returns_unknown(self):
        """None returns unknown."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_phase_for_period

        assert _ncaab_phase_for_period(None) == "unknown"


class TestNcaabBlockForPeriod:
    """Tests for _ncaab_block_for_period function."""

    def test_first_half(self):
        """Period 1 is first_half."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_block_for_period

        assert _ncaab_block_for_period(1) == "first_half"

    def test_second_half(self):
        """Period 2 is second_half."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_block_for_period

        assert _ncaab_block_for_period(2) == "second_half"

    def test_overtime(self):
        """Periods 3+ are overtime."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_block_for_period

        assert _ncaab_block_for_period(3) == "overtime"
        assert _ncaab_block_for_period(4) == "overtime"

    def test_none_returns_unknown(self):
        """None returns unknown."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_block_for_period

        assert _ncaab_block_for_period(None) == "unknown"


class TestNcaabPeriodStart:
    """Tests for _ncaab_period_start function."""

    def test_half_1_starts_at_game_start(self):
        """First half starts at game start."""
        from app.services.pipeline.stages.normalize_pbp import _ncaab_period_start

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _ncaab_period_start(game_start, 1)
        assert result == game_start

    def test_half_2_timing(self):
        """Second half starts after H1 + halftime."""
        from app.services.pipeline.stages.normalize_pbp import (
            _ncaab_period_start,
            NCAAB_HALF_REAL_SECONDS,
            NCAAB_HALFTIME_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _ncaab_period_start(game_start, 2)
        expected = game_start + timedelta(
            seconds=NCAAB_HALF_REAL_SECONDS + NCAAB_HALFTIME_REAL_SECONDS
        )
        assert result == expected

    def test_overtime_timing(self):
        """Overtime periods start after regulation."""
        from app.services.pipeline.stages.normalize_pbp import (
            _ncaab_period_start,
            NCAAB_REGULATION_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _ncaab_period_start(game_start, 3)  # OT1
        expected = game_start + timedelta(
            seconds=NCAAB_REGULATION_REAL_SECONDS + 10 * 60
        )
        assert result == expected


class TestNcaabGameEnd:
    """Tests for _ncaab_game_end function."""

    def test_regulation_game(self):
        """Regulation game ends after 2 halves."""
        from app.services.pipeline.stages.normalize_pbp import (
            _ncaab_game_end,
            NCAAB_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 1
        play2 = MagicMock()
        play2.quarter = 2

        plays = [play1, play2]
        result = _ncaab_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NCAAB_REGULATION_REAL_SECONDS)
        assert result == expected

    def test_single_overtime(self):
        """Game with 1 OT ends after period 3."""
        from app.services.pipeline.stages.normalize_pbp import (
            _ncaab_game_end,
            NCAAB_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 2
        play2 = MagicMock()
        play2.quarter = 3  # OT1

        plays = [play1, play2]
        result = _ncaab_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NCAAB_REGULATION_REAL_SECONDS + 10 * 60)
        assert result == expected


class TestComputeNcaabPhaseBoundaries:
    """Tests for _compute_ncaab_phase_boundaries function."""

    def test_has_all_phases(self):
        """All standard NCAAB phases are present."""
        from app.services.pipeline.stages.normalize_pbp import _compute_ncaab_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_ncaab_phase_boundaries(game_start, has_overtime=False)

        assert "pregame" in boundaries
        assert "h1" in boundaries
        assert "halftime" in boundaries
        assert "h2" in boundaries
        assert "postgame" in boundaries

    def test_overtime_phases(self):
        """Overtime phases present when has_overtime=True."""
        from app.services.pipeline.stages.normalize_pbp import _compute_ncaab_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_ncaab_phase_boundaries(game_start, has_overtime=True)

        assert "ot1" in boundaries
        assert "ot2" in boundaries
        assert "ot3" in boundaries
        assert "ot4" in boundaries

    def test_no_overtime_phases_when_false(self):
        """No overtime phases when has_overtime=False."""
        from app.services.pipeline.stages.normalize_pbp import _compute_ncaab_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_ncaab_phase_boundaries(game_start, has_overtime=False)

        assert "ot1" not in boundaries

    def test_h1_starts_at_game_start(self):
        """H1 starts when game starts."""
        from app.services.pipeline.stages.normalize_pbp import _compute_ncaab_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_ncaab_phase_boundaries(game_start)

        h1_start, _ = boundaries["h1"]
        assert h1_start == game_start


class TestNhlPhaseForPeriod:
    """Tests for _nhl_phase_for_period function."""

    def test_period_1(self):
        """Period 1 returns p1."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_phase_for_period

        assert _nhl_phase_for_period(1) == "p1"

    def test_period_2(self):
        """Period 2 returns p2."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_phase_for_period

        assert _nhl_phase_for_period(2) == "p2"

    def test_period_3(self):
        """Period 3 returns p3."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_phase_for_period

        assert _nhl_phase_for_period(3) == "p3"

    def test_overtime(self):
        """Period 4 (OT) returns ot."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_phase_for_period

        assert _nhl_phase_for_period(4) == "ot"

    def test_shootout(self):
        """Period 5 (shootout) returns shootout."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_phase_for_period

        assert _nhl_phase_for_period(5) == "shootout"

    def test_extended_overtime(self):
        """Periods 6+ return ot2, ot3, etc. for playoff OT."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_phase_for_period

        assert _nhl_phase_for_period(6) == "ot3"
        assert _nhl_phase_for_period(7) == "ot4"

    def test_none_returns_unknown(self):
        """None returns unknown."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_phase_for_period

        assert _nhl_phase_for_period(None) == "unknown"


class TestNhlBlockForPeriod:
    """Tests for _nhl_block_for_period function."""

    def test_regulation(self):
        """Periods 1-3 are regulation."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_block_for_period

        assert _nhl_block_for_period(1) == "regulation"
        assert _nhl_block_for_period(2) == "regulation"
        assert _nhl_block_for_period(3) == "regulation"

    def test_overtime(self):
        """Period 4 is overtime."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_block_for_period

        assert _nhl_block_for_period(4) == "overtime"

    def test_shootout(self):
        """Period 5 is shootout."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_block_for_period

        assert _nhl_block_for_period(5) == "shootout"

    def test_extended_overtime(self):
        """Periods 6+ are overtime (playoffs)."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_block_for_period

        assert _nhl_block_for_period(6) == "overtime"
        assert _nhl_block_for_period(7) == "overtime"

    def test_none_returns_unknown(self):
        """None returns unknown."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_block_for_period

        assert _nhl_block_for_period(None) == "unknown"


class TestNhlPeriodStart:
    """Tests for _nhl_period_start function."""

    def test_period_1_starts_at_game_start(self):
        """Period 1 starts at game start."""
        from app.services.pipeline.stages.normalize_pbp import _nhl_period_start

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nhl_period_start(game_start, 1)
        assert result == game_start

    def test_period_2_timing(self):
        """Period 2 starts after P1 + first intermission."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nhl_period_start,
            NHL_PERIOD_REAL_SECONDS,
            NHL_INTERMISSION_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nhl_period_start(game_start, 2)
        expected = game_start + timedelta(
            seconds=NHL_PERIOD_REAL_SECONDS + NHL_INTERMISSION_REAL_SECONDS
        )
        assert result == expected

    def test_period_3_timing(self):
        """Period 3 starts after P2 + second intermission."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nhl_period_start,
            NHL_PERIOD_REAL_SECONDS,
            NHL_INTERMISSION_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nhl_period_start(game_start, 3)
        expected = game_start + timedelta(
            seconds=2 * NHL_PERIOD_REAL_SECONDS + 2 * NHL_INTERMISSION_REAL_SECONDS
        )
        assert result == expected

    def test_overtime_timing(self):
        """Overtime starts after regulation."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nhl_period_start,
            NHL_REGULATION_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nhl_period_start(game_start, 4)  # OT
        expected = game_start + timedelta(
            seconds=NHL_REGULATION_REAL_SECONDS + 10 * 60
        )
        assert result == expected


class TestNhlGameEnd:
    """Tests for _nhl_game_end function."""

    def test_regulation_game(self):
        """Regulation game ends after 3 periods."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nhl_game_end,
            NHL_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 1
        play2 = MagicMock()
        play2.quarter = 3

        plays = [play1, play2]
        result = _nhl_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NHL_REGULATION_REAL_SECONDS)
        assert result == expected

    def test_overtime_game(self):
        """Game with OT ends after period 4."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nhl_game_end,
            NHL_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 3
        play2 = MagicMock()
        play2.quarter = 4  # OT

        plays = [play1, play2]
        result = _nhl_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NHL_REGULATION_REAL_SECONDS + 10 * 60)
        assert result == expected

    def test_shootout_game(self):
        """Game with shootout ends after period 5."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nhl_game_end,
            NHL_REGULATION_REAL_SECONDS,
        )
        from unittest.mock import MagicMock

        game_start = datetime(2025, 1, 15, 19, 0, 0)

        play1 = MagicMock()
        play1.quarter = 4  # OT
        play2 = MagicMock()
        play2.quarter = 5  # Shootout

        plays = [play1, play2]
        result = _nhl_game_end(game_start, plays)

        expected = game_start + timedelta(seconds=NHL_REGULATION_REAL_SECONDS + 2 * 10 * 60)
        assert result == expected

    def test_empty_plays(self):
        """Empty plays defaults to regulation end."""
        from app.services.pipeline.stages.normalize_pbp import (
            _nhl_game_end,
            NHL_REGULATION_REAL_SECONDS,
        )

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        result = _nhl_game_end(game_start, [])

        expected = game_start + timedelta(seconds=NHL_REGULATION_REAL_SECONDS)
        assert result == expected


class TestComputeNhlPhaseBoundaries:
    """Tests for _compute_nhl_phase_boundaries function."""

    def test_has_all_regulation_phases(self):
        """All standard NHL phases are present."""
        from app.services.pipeline.stages.normalize_pbp import _compute_nhl_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_nhl_phase_boundaries(game_start)

        assert "pregame" in boundaries
        assert "p1" in boundaries
        assert "int1" in boundaries
        assert "p2" in boundaries
        assert "int2" in boundaries
        assert "p3" in boundaries
        assert "postgame" in boundaries

    def test_overtime_phase(self):
        """Overtime phase present when has_overtime=True."""
        from app.services.pipeline.stages.normalize_pbp import _compute_nhl_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_nhl_phase_boundaries(game_start, has_overtime=True)

        assert "ot" in boundaries

    def test_shootout_phase(self):
        """Shootout phase present when has_shootout=True."""
        from app.services.pipeline.stages.normalize_pbp import _compute_nhl_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_nhl_phase_boundaries(
            game_start, has_overtime=True, has_shootout=True
        )

        assert "ot" in boundaries
        assert "shootout" in boundaries

    def test_no_overtime_phases_when_false(self):
        """No overtime phases when has_overtime=False."""
        from app.services.pipeline.stages.normalize_pbp import _compute_nhl_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_nhl_phase_boundaries(game_start, has_overtime=False)

        assert "ot" not in boundaries
        assert "shootout" not in boundaries

    def test_p1_starts_at_game_start(self):
        """P1 starts when game starts."""
        from app.services.pipeline.stages.normalize_pbp import _compute_nhl_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_nhl_phase_boundaries(game_start)

        p1_start, _ = boundaries["p1"]
        assert p1_start == game_start

    def test_boundaries_are_tuples(self):
        """Each boundary is a (start, end) tuple."""
        from app.services.pipeline.stages.normalize_pbp import _compute_nhl_phase_boundaries

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        boundaries = _compute_nhl_phase_boundaries(game_start)

        for phase, (start, end) in boundaries.items():
            assert isinstance(start, datetime)
            assert isinstance(end, datetime)
            assert end > start


class TestBuildPbpEventsNhl:
    """Tests for _build_pbp_events with NHL games."""

    def _make_play(
        self,
        play_index,
        quarter=1,
        game_clock="20:00",
        home_score=0,
        away_score=0,
        description="",
        play_type="other",
        player_name=None,
        team=None,
    ):
        """Create a mock play object."""
        from unittest.mock import MagicMock

        play = MagicMock()
        play.play_index = play_index
        play.quarter = quarter
        play.game_clock = game_clock
        play.home_score = home_score
        play.away_score = away_score
        play.description = description
        play.play_type = play_type
        play.player_name = player_name
        play.team = team
        return play

    def test_nhl_uses_period_phases(self):
        """NHL games use p1/p2/p3 phases."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=1, home_score=0, away_score=0),
            self._make_play(2, quarter=2, home_score=1, away_score=0),
            self._make_play(3, quarter=3, home_score=2, away_score=1),
        ]
        events, _ = _build_pbp_events(plays, game_start, league_code="NHL")

        assert events[0]["phase"] == "p1"
        assert events[1]["phase"] == "p2"
        assert events[2]["phase"] == "p3"

    def test_nhl_regulation_blocks(self):
        """NHL regulation periods have regulation block."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=1, home_score=0, away_score=0),
            self._make_play(2, quarter=2, home_score=1, away_score=0),
            self._make_play(3, quarter=3, home_score=2, away_score=1),
        ]
        events, _ = _build_pbp_events(plays, game_start, league_code="NHL")

        assert events[0]["block"] == "regulation"
        assert events[1]["block"] == "regulation"
        assert events[2]["block"] == "regulation"

    def test_nhl_overtime_phase(self):
        """NHL overtime uses ot phase."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=4, home_score=2, away_score=2),
        ]
        events, _ = _build_pbp_events(plays, game_start, league_code="NHL")

        assert events[0]["phase"] == "ot"
        assert events[0]["block"] == "overtime"

    def test_nhl_shootout_phase(self):
        """NHL shootout uses shootout phase."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=5, home_score=2, away_score=2),
        ]
        events, _ = _build_pbp_events(plays, game_start, league_code="NHL")

        assert events[0]["phase"] == "shootout"
        assert events[0]["block"] == "shootout"

    def test_nhl_extended_overtime(self):
        """NHL playoff OT periods use ot2, ot3, etc."""
        from app.services.pipeline.stages.normalize_pbp import _build_pbp_events

        game_start = datetime(2025, 1, 15, 19, 0, 0)
        plays = [
            self._make_play(1, quarter=6, home_score=3, away_score=3),
            self._make_play(2, quarter=7, home_score=3, away_score=3),
        ]
        events, _ = _build_pbp_events(plays, game_start, league_code="NHL")

        assert events[0]["phase"] == "ot3"
        assert events[1]["phase"] == "ot4"
        assert events[0]["block"] == "overtime"
        assert events[1]["block"] == "overtime"
