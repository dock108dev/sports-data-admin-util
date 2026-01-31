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
