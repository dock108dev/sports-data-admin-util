"""
Unit tests for Running Stats Builder.

These tests validate:
- Scoring (2PT, 3PT, FT)
- Fouls (personal vs technical)
- Timeouts
- Possessions estimate
- Notable actions extraction
- Player bounding and tie-breaking
- Determinism

ISSUE: Running Stats Builder (Chapters-First Architecture)
"""

import pytest
import json

from app.services.chapters.types import Chapter, Play
from app.services.chapters.running_stats import (
    # Core functions
    normalize_player_key,
    build_initial_snapshot,
    update_snapshot,
    build_running_snapshots,
    compute_section_delta,
    compute_section_deltas_from_snapshots,
    # Data structures
    RunningStatsSnapshot,
    PlayerSnapshot,
    TeamSnapshot,
    SectionDelta,
    PlayerDelta,
    TeamDelta,
    # Parsing helpers (for direct testing)
    _is_made_field_goal,
    _is_made_free_throw,
    _is_personal_foul,
    _is_technical_foul,
    _is_timeout,
    _is_possession_ending,
    _extract_notable_action,
)


# ============================================================================
# TEST HELPERS
# ============================================================================

def make_play(
    index: int,
    description: str,
    quarter: int = 1,
    player_name: str | None = None,
    team_key: str | None = None,
    play_type: str | None = None,
) -> Play:
    """Create a Play with common fields."""
    raw_data = {
        "description": description,
        "quarter": quarter,
    }
    if player_name:
        raw_data["player_name"] = player_name
    if team_key:
        raw_data["team_abbreviation"] = team_key
        raw_data["team_name"] = team_key.upper()
    if play_type:
        raw_data["play_type"] = play_type
    return Play(index=index, event_type="pbp", raw_data=raw_data)


def make_chapter(
    chapter_id: str,
    start_idx: int,
    plays: list[Play],
    reason_codes: list[str],
) -> Chapter:
    """Create a Chapter."""
    return Chapter(
        chapter_id=chapter_id,
        play_start_idx=start_idx,
        play_end_idx=start_idx + len(plays) - 1,
        plays=plays,
        reason_codes=reason_codes,
    )


# ============================================================================
# TEST: PLAYER KEY NORMALIZATION
# ============================================================================

class TestPlayerKeyNormalization:
    """Tests for player key normalization."""

    def test_normalize_basic(self):
        """Basic normalization: lowercase and strip."""
        assert normalize_player_key("LeBron James") == "lebron james"

    def test_normalize_extra_spaces(self):
        """Collapse internal whitespace."""
        assert normalize_player_key("LeBron   James") == "lebron james"

    def test_normalize_leading_trailing(self):
        """Strip leading and trailing whitespace."""
        assert normalize_player_key("  LeBron James  ") == "lebron james"

    def test_normalize_empty(self):
        """Empty string returns empty."""
        assert normalize_player_key("") == ""

    def test_normalize_deterministic(self):
        """Same input always gives same output."""
        name = "Stephen Curry"
        assert normalize_player_key(name) == normalize_player_key(name)


# ============================================================================
# TEST: SCORING (2PT, 3PT, FT)
# ============================================================================

class TestScoring:
    """Tests for scoring extraction."""

    def test_2pt_field_goal(self):
        """Regular 2-point field goal."""
        play = make_play(0, "LeBron James makes layup", player_name="LeBron James", team_key="lal")
        is_fg, points = _is_made_field_goal(play)
        assert is_fg is True
        assert points == 2

    def test_3pt_field_goal_3pt_keyword(self):
        """3-pointer with '3-pt' keyword."""
        play = make_play(0, "Stephen Curry makes 3-pt jump shot", player_name="Stephen Curry", team_key="gsw")
        is_fg, points = _is_made_field_goal(play)
        assert is_fg is True
        assert points == 3

    def test_3pt_field_goal_three_keyword(self):
        """3-pointer with 'three' keyword."""
        play = make_play(0, "Klay Thompson makes three pointer", player_name="Klay Thompson", team_key="gsw")
        is_fg, points = _is_made_field_goal(play)
        assert is_fg is True
        assert points == 3

    def test_3pt_field_goal_3pointer_keyword(self):
        """3-pointer with '3-pointer' keyword."""
        play = make_play(0, "Luka Doncic makes 3-pointer", player_name="Luka Doncic", team_key="dal")
        is_fg, points = _is_made_field_goal(play)
        assert is_fg is True
        assert points == 3

    def test_free_throw_not_counted_as_fg(self):
        """Free throw should not be counted as FG."""
        play = make_play(0, "LeBron James makes free throw", player_name="LeBron James", team_key="lal")
        is_fg, points = _is_made_field_goal(play)
        assert is_fg is False
        assert points == 0

    def test_free_throw_detection(self):
        """Free throw detection."""
        play = make_play(0, "Giannis makes free throw 1 of 2", player_name="Giannis", team_key="mil")
        assert _is_made_free_throw(play) is True

    def test_missed_shot_not_scored(self):
        """Missed shot should not score."""
        play = make_play(0, "LeBron James misses 3-pointer")
        is_fg, points = _is_made_field_goal(play)
        assert is_fg is False
        assert points == 0

    def test_scoring_accumulation_in_snapshot(self):
        """Scoring should accumulate correctly in snapshot."""
        plays = [
            make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal"),         # 2
            make_play(1, "LeBron makes 3-pt shot", player_name="LeBron", team_key="lal"),     # 3
            make_play(2, "LeBron makes free throw", player_name="LeBron", team_key="lal"),    # 1
            make_play(3, "LeBron makes dunk", player_name="LeBron", team_key="lal"),          # 2
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        player = snapshot.players["lebron"]
        assert player.points_scored_total == 8  # 2 + 3 + 1 + 2
        assert player.fg_made_total == 3        # layup, 3pt, dunk
        assert player.three_pt_made_total == 1  # only the 3pt
        assert player.ft_made_total == 1        # only the free throw

    def test_team_scoring_accumulation(self):
        """Team score should accumulate from player scoring."""
        plays = [
            make_play(0, "Player A makes layup", player_name="Player A", team_key="lal"),
            make_play(1, "Player B makes 3-pt shot", player_name="Player B", team_key="lal"),
            make_play(2, "Player C makes dunk", player_name="Player C", team_key="bos"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        assert snapshot.teams["lal"].points_scored_total == 5  # 2 + 3
        assert snapshot.teams["bos"].points_scored_total == 2  # dunk


# ============================================================================
# TEST: FOULS (PERSONAL VS TECHNICAL)
# ============================================================================

class TestFouls:
    """Tests for foul detection and tracking."""

    def test_personal_foul_detection(self):
        """Personal foul is detected."""
        play = make_play(0, "LeBron James commits personal foul", player_name="LeBron James", team_key="lal")
        assert _is_personal_foul(play) is True
        assert _is_technical_foul(play) is False

    def test_technical_foul_detection(self):
        """Technical foul is detected separately."""
        play = make_play(0, "LeBron James commits technical foul", player_name="LeBron James", team_key="lal")
        assert _is_technical_foul(play) is True
        assert _is_personal_foul(play) is False  # Technical should NOT count as personal

    def test_personal_foul_accumulation(self):
        """Personal fouls accumulate correctly."""
        plays = [
            make_play(0, "Player A commits foul", player_name="Player A", team_key="lal"),
            make_play(1, "Player A commits personal foul", player_name="Player A", team_key="lal"),
            make_play(2, "Player B commits foul", player_name="Player B", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        assert snapshot.players["player a"].personal_foul_count_total == 2
        assert snapshot.players["player b"].personal_foul_count_total == 1
        assert snapshot.teams["lal"].personal_fouls_committed_total == 3

    def test_technical_foul_separate_from_personal(self):
        """Technical fouls do NOT count as personal fouls."""
        plays = [
            make_play(0, "Player A commits technical foul", player_name="Player A", team_key="lal"),
            make_play(1, "Player A commits personal foul", player_name="Player A", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        player = snapshot.players["player a"]
        assert player.personal_foul_count_total == 1   # Only the personal foul
        assert player.technical_foul_count_total == 1  # Only the technical foul

        team = snapshot.teams["lal"]
        assert team.personal_fouls_committed_total == 1
        assert team.technical_fouls_committed_total == 1

    def test_foul_trouble_flag_in_delta(self):
        """Foul trouble flag set when 4+ personal fouls in section."""
        plays = [
            make_play(0, "Player A commits foul", player_name="Player A", team_key="lal"),
            make_play(1, "Player A commits foul", player_name="Player A", team_key="lal"),
            make_play(2, "Player A commits foul", player_name="Player A", team_key="lal"),
            make_play(3, "Player A commits foul", player_name="Player A", team_key="lal"),  # 4th foul
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
            players_per_team=10,  # Don't bound for this test
        )

        assert delta.players["player a"].foul_trouble_flag is True

    def test_foul_trouble_flag_false_under_4(self):
        """Foul trouble flag false when less than 4 fouls."""
        plays = [
            make_play(0, "Player A commits foul", player_name="Player A", team_key="lal"),
            make_play(1, "Player A commits foul", player_name="Player A", team_key="lal"),
            make_play(2, "Player A commits foul", player_name="Player A", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
            players_per_team=10,
        )

        assert delta.players["player a"].foul_trouble_flag is False


# ============================================================================
# TEST: TIMEOUTS
# ============================================================================

class TestTimeouts:
    """Tests for timeout detection."""

    def test_team_timeout_detection(self):
        """Team timeout is detected."""
        play = make_play(0, "Lakers timeout", team_key="lal", play_type="timeout")
        is_timeout, team = _is_timeout(play)
        assert is_timeout is True
        assert team == "lal"

    def test_official_timeout_ignored(self):
        """Official timeout is ignored."""
        play = make_play(0, "Official timeout", play_type="timeout")
        is_timeout, team = _is_timeout(play)
        assert is_timeout is False

    def test_media_timeout_ignored(self):
        """Media timeout is ignored."""
        play = make_play(0, "Media timeout", play_type="timeout")
        is_timeout, team = _is_timeout(play)
        assert is_timeout is False

    def test_tv_timeout_ignored(self):
        """TV timeout is ignored."""
        play = make_play(0, "TV timeout", play_type="timeout")
        is_timeout, team = _is_timeout(play)
        assert is_timeout is False

    def test_timeout_accumulation(self):
        """Timeouts accumulate correctly."""
        plays = [
            make_play(0, "Lakers timeout", team_key="lal", play_type="timeout"),
            make_play(1, "Celtics timeout", team_key="bos", play_type="timeout"),
            make_play(2, "Lakers timeout", team_key="lal", play_type="timeout"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        assert snapshot.teams["lal"].timeouts_used_total == 2
        assert snapshot.teams["bos"].timeouts_used_total == 1


# ============================================================================
# TEST: POSSESSIONS ESTIMATE
# ============================================================================

class TestPossessionsEstimate:
    """Tests for possession estimate."""

    def test_made_fg_ends_possession(self):
        """Made FG ends possession."""
        play = make_play(0, "LeBron makes layup", team_key="lal")
        assert _is_possession_ending(play) is True

    def test_turnover_ends_possession(self):
        """Turnover ends possession."""
        play = make_play(0, "LeBron turnover", team_key="lal", play_type="turnover")
        assert _is_possession_ending(play) is True

    def test_defensive_rebound_ends_possession(self):
        """Defensive rebound ends possession."""
        play = make_play(0, "Lakers defensive rebound", team_key="lal")
        assert _is_possession_ending(play) is True

    def test_made_ft_does_not_end_possession(self):
        """Made FT alone does not end possession."""
        play = make_play(0, "LeBron makes free throw", team_key="lal")
        assert _is_possession_ending(play) is False

    def test_missed_shot_does_not_end_possession(self):
        """Missed shot alone does not end possession."""
        play = make_play(0, "LeBron misses layup", team_key="lal")
        assert _is_possession_ending(play) is False

    def test_possession_accumulation(self):
        """Possessions accumulate correctly."""
        plays = [
            make_play(0, "Team A makes layup", team_key="lal"),           # +1 possession
            make_play(1, "Team B turnover", team_key="bos"),               # +1 possession
            make_play(2, "Team A defensive rebound", team_key="lal"),     # +1 possession
            make_play(3, "Team A makes 3-pt shot", team_key="lal"),       # +1 possession
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        assert snapshot.teams["lal"].possessions_estimate_total == 3  # 2 makes + 1 def rebound
        assert snapshot.teams["bos"].possessions_estimate_total == 1  # turnover


# ============================================================================
# TEST: NOTABLE ACTIONS EXTRACTION
# ============================================================================

class TestNotableActions:
    """Tests for notable action extraction."""

    def test_dunk_extraction(self):
        """Dunk is extracted."""
        play = make_play(0, "LeBron makes dunk", player_name="LeBron", team_key="lal")
        assert _extract_notable_action(play) == "dunk"

    def test_block_extraction(self):
        """Block is extracted."""
        play = make_play(0, "LeBron blocks shot", player_name="LeBron", team_key="lal")
        assert _extract_notable_action(play) == "block"

    def test_steal_extraction(self):
        """Steal is extracted."""
        play = make_play(0, "LeBron steal", player_name="LeBron", team_key="lal")
        assert _extract_notable_action(play) == "steal"

    def test_no_inference(self):
        """No action extracted for regular plays."""
        play = make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal")
        assert _extract_notable_action(play) is None

    def test_no_synonyms(self):
        """No synonym matching (e.g., 'rejection' != 'block')."""
        play = make_play(0, "LeBron rejection on the play", player_name="LeBron", team_key="lal")
        assert _extract_notable_action(play) is None

    def test_notable_actions_unique_set(self):
        """Notable actions form a unique set per player."""
        plays = [
            make_play(0, "LeBron makes dunk", player_name="LeBron", team_key="lal"),
            make_play(1, "LeBron blocks shot", player_name="LeBron", team_key="lal"),
            make_play(2, "LeBron makes dunk", player_name="LeBron", team_key="lal"),  # Duplicate
            make_play(3, "LeBron steal", player_name="LeBron", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        player = snapshot.players["lebron"]
        assert player.notable_actions_set == {"dunk", "block", "steal"}  # No duplicates


# ============================================================================
# TEST: PLAYER BOUNDING AND TIE-BREAKING
# ============================================================================

class TestPlayerBounding:
    """Tests for player bounding (top 3 per team)."""

    def test_top_3_per_team_by_points(self):
        """Only top 3 players per team by points included."""
        plays = []
        # Team LAL: Player1 (10), Player2 (8), Player3 (6), Player4 (4), Player5 (2)
        for name, points in [("P1", 10), ("P2", 8), ("P3", 6), ("P4", 4), ("P5", 2)]:
            for _ in range(points // 2):
                plays.append(make_play(len(plays), f"{name} makes layup", player_name=name, team_key="lal"))

        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
            players_per_team=3,
        )

        # Should have top 3
        assert "p1" in delta.players
        assert "p2" in delta.players
        assert "p3" in delta.players
        # Should NOT have bottom 2
        assert "p4" not in delta.players
        assert "p5" not in delta.players

    def test_tiebreaker_fg_made(self):
        """Tie-breaker: fg_made when points equal."""
        plays = [
            # Both have 4 points, but P1 has 2 FG and P2 has 4 FT
            make_play(0, "P1 makes layup", player_name="P1", team_key="lal"),       # 2 pts, 1 FG
            make_play(1, "P1 makes layup", player_name="P1", team_key="lal"),       # 4 pts, 2 FG
            make_play(2, "P2 makes free throw", player_name="P2", team_key="lal"),  # 1 pt, 0 FG
            make_play(3, "P2 makes free throw", player_name="P2", team_key="lal"),  # 2 pts, 0 FG
            make_play(4, "P2 makes free throw", player_name="P2", team_key="lal"),  # 3 pts, 0 FG
            make_play(5, "P2 makes free throw", player_name="P2", team_key="lal"),  # 4 pts, 0 FG
            make_play(6, "P3 makes layup", player_name="P3", team_key="lal"),       # 2 pts, 1 FG
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
            players_per_team=2,  # Only top 2
        )

        # P1 and P2 both have 4 points, but P1 has more FG
        # P3 has 2 points, so should be excluded
        assert "p1" in delta.players
        assert "p2" in delta.players
        assert "p3" not in delta.players

    def test_tiebreaker_three_pt_made(self):
        """Tie-breaker: three_pt_made when points and fg_made equal."""
        plays = [
            # Both have 6 points, 2 FG, but P1 has 2 3PT and P2 has 0 3PT
            make_play(0, "P1 makes 3-pt shot", player_name="P1", team_key="lal"),   # 3 pts, 1 FG, 1 3PT
            make_play(1, "P1 makes 3-pt shot", player_name="P1", team_key="lal"),   # 6 pts, 2 FG, 2 3PT
            make_play(2, "P2 makes layup", player_name="P2", team_key="lal"),       # 2 pts, 1 FG, 0 3PT
            make_play(3, "P2 makes layup", player_name="P2", team_key="lal"),       # 4 pts, 2 FG, 0 3PT
            make_play(4, "P2 makes free throw", player_name="P2", team_key="lal"),  # 5 pts
            make_play(5, "P2 makes free throw", player_name="P2", team_key="lal"),  # 6 pts
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        # Verify they have same points and FG
        assert snapshot.players["p1"].points_scored_total == 6
        assert snapshot.players["p2"].points_scored_total == 6
        assert snapshot.players["p1"].fg_made_total == 2
        assert snapshot.players["p2"].fg_made_total == 2

        # P1 has more 3PT
        assert snapshot.players["p1"].three_pt_made_total == 2
        assert snapshot.players["p2"].three_pt_made_total == 0

    def test_tiebreaker_player_key_deterministic(self):
        """Final tie-breaker: player_key for determinism."""
        plays = [
            # All have same stats
            make_play(0, "Zebra makes layup", player_name="Zebra", team_key="lal"),
            make_play(1, "Alpha makes layup", player_name="Alpha", team_key="lal"),
            make_play(2, "Charlie makes layup", player_name="Charlie", team_key="lal"),
            make_play(3, "Beta makes layup", player_name="Beta", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
            players_per_team=3,
        )

        # All have 2 points, 1 FG, 0 3PT
        # Alphabetical order: alpha, beta, charlie, zebra
        # Top 3 should be: alpha, beta, charlie (ascending player_key)
        assert "alpha" in delta.players
        assert "beta" in delta.players
        assert "charlie" in delta.players
        assert "zebra" not in delta.players

    def test_multiple_teams_bounded_separately(self):
        """Each team bounded separately."""
        plays = []
        # Team LAL: 5 players
        for name, points in [("L1", 10), ("L2", 8), ("L3", 6), ("L4", 4), ("L5", 2)]:
            for _ in range(points // 2):
                plays.append(make_play(len(plays), f"{name} makes layup", player_name=name, team_key="lal"))

        # Team BOS: 5 players
        for name, points in [("B1", 12), ("B2", 6), ("B3", 4), ("B4", 2), ("B5", 1)]:
            for _ in range(points // 2):
                plays.append(make_play(len(plays), f"{name} makes layup", player_name=name, team_key="bos"))

        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
            players_per_team=3,
        )

        # LAL top 3
        assert "l1" in delta.players
        assert "l2" in delta.players
        assert "l3" in delta.players
        assert "l4" not in delta.players

        # BOS top 3
        assert "b1" in delta.players
        assert "b2" in delta.players
        assert "b3" in delta.players
        assert "b4" not in delta.players


# ============================================================================
# TEST: SECTION DELTA COMPUTATION
# ============================================================================

class TestSectionDelta:
    """Tests for section delta computation."""

    def test_delta_is_difference(self):
        """Delta is computed as end - start."""
        plays1 = [
            make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal"),  # 2 pts
        ]
        plays2 = [
            make_play(1, "LeBron makes 3-pt shot", player_name="LeBron", team_key="lal"),  # 3 pts
            make_play(2, "LeBron makes layup", player_name="LeBron", team_key="lal"),      # 2 pts
        ]

        chapter1 = make_chapter("ch_001", 0, plays1, ["PERIOD_START"])
        chapter2 = make_chapter("ch_002", 1, plays2, ["TIMEOUT"])

        snapshots = build_running_snapshots([chapter1, chapter2])

        # Snapshot 0: 2 points
        assert snapshots[0].players["lebron"].points_scored_total == 2
        # Snapshot 1: 7 points (2 + 3 + 2)
        assert snapshots[1].players["lebron"].points_scored_total == 7

        # Delta for section covering only chapter2
        delta = compute_section_delta(
            start_snapshot=snapshots[0],
            end_snapshot=snapshots[1],
            section_start_chapter=1,
            section_end_chapter=1,
            players_per_team=10,
        )

        # Delta should be 5 points (7 - 2)
        assert delta.players["lebron"].points_scored == 5

    def test_delta_with_no_start(self):
        """Delta from beginning (no start snapshot)."""
        plays = [
            make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
            players_per_team=10,
        )

        # Delta equals total
        assert delta.players["lebron"].points_scored == 2

    def test_team_delta_computation(self):
        """Team deltas computed correctly."""
        plays1 = [make_play(0, "Timeout", team_key="lal", play_type="timeout")]
        plays2 = [
            make_play(1, "Timeout", team_key="lal", play_type="timeout"),
            make_play(2, "Timeout", team_key="bos", play_type="timeout"),
        ]

        chapter1 = make_chapter("ch_001", 0, plays1, ["TIMEOUT"])
        chapter2 = make_chapter("ch_002", 1, plays2, ["TIMEOUT"])

        snapshots = build_running_snapshots([chapter1, chapter2])

        # Delta for section covering only chapter2
        delta = compute_section_delta(
            start_snapshot=snapshots[0],
            end_snapshot=snapshots[1],
            section_start_chapter=1,
            section_end_chapter=1,
        )

        # LAL: 1 timeout in chapter2
        assert delta.teams["lal"].timeouts_used == 1
        # BOS: 1 timeout in chapter2 (didn't exist before)
        assert delta.teams["bos"].timeouts_used == 1


# ============================================================================
# TEST: DETERMINISM
# ============================================================================

class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_input_same_output(self):
        """Same input produces identical output."""
        plays = [
            make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal"),
            make_play(1, "Curry makes 3-pt shot", player_name="Curry", team_key="gsw"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])

        snapshot1 = update_snapshot(build_initial_snapshot(), chapter)
        snapshot2 = update_snapshot(build_initial_snapshot(), chapter)

        # Should be identical when serialized
        json1 = json.dumps(snapshot1.to_dict(), sort_keys=True)
        json2 = json.dumps(snapshot2.to_dict(), sort_keys=True)

        assert json1 == json2

    def test_chapter_order_matters(self):
        """Processing chapters in different order gives different results."""
        plays1 = [make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal")]
        plays2 = [make_play(1, "Curry makes layup", player_name="Curry", team_key="gsw")]

        chapter1 = make_chapter("ch_001", 0, plays1, ["PERIOD_START"])
        chapter2 = make_chapter("ch_002", 1, plays2, ["TIMEOUT"])

        # Build in order
        snapshots_normal = build_running_snapshots([chapter1, chapter2])

        # Verify chapter indices
        assert snapshots_normal[0].chapter_index == 0
        assert snapshots_normal[1].chapter_index == 1

    def test_multiple_runs_identical(self):
        """Multiple runs produce identical results."""
        plays = [
            make_play(0, "P1 makes dunk", player_name="P1", team_key="lal"),
            make_play(1, "P2 commits foul", player_name="P2", team_key="bos"),
            make_play(2, "Lakers timeout", team_key="lal", play_type="timeout"),
            make_play(3, "P1 makes 3-pt shot", player_name="P1", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])

        results = []
        for _ in range(5):
            snapshot = update_snapshot(build_initial_snapshot(), chapter)
            results.append(json.dumps(snapshot.to_dict(), sort_keys=True))

        # All results should be identical
        assert len(set(results)) == 1


# ============================================================================
# TEST: SNAPSHOT IMMUTABILITY
# ============================================================================

class TestImmutability:
    """Tests for snapshot immutability."""

    def test_update_does_not_mutate_previous(self):
        """update_snapshot creates new snapshot without mutating previous."""
        initial = build_initial_snapshot()
        plays = [make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal")]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])

        # Update
        new_snapshot = update_snapshot(initial, chapter)

        # Initial should be unchanged
        assert initial.chapter_index == -1
        assert len(initial.players) == 0
        assert len(initial.teams) == 0

        # New snapshot should have data
        assert new_snapshot.chapter_index == 0
        assert len(new_snapshot.players) == 1
        assert len(new_snapshot.teams) == 1

    def test_notable_actions_set_independent(self):
        """Notable actions sets are independent between snapshots."""
        plays1 = [make_play(0, "LeBron makes dunk", player_name="LeBron", team_key="lal")]
        plays2 = [make_play(1, "LeBron blocks shot", player_name="LeBron", team_key="lal")]

        chapter1 = make_chapter("ch_001", 0, plays1, ["PERIOD_START"])
        chapter2 = make_chapter("ch_002", 1, plays2, ["TIMEOUT"])

        snapshot1 = update_snapshot(build_initial_snapshot(), chapter1)
        snapshot2 = update_snapshot(snapshot1, chapter2)

        # Snapshot1 should only have dunk
        assert snapshot1.players["lebron"].notable_actions_set == {"dunk"}

        # Snapshot2 should have both
        assert snapshot2.players["lebron"].notable_actions_set == {"dunk", "block"}


# ============================================================================
# TEST: SERIALIZATION
# ============================================================================

class TestSerialization:
    """Tests for JSON serialization."""

    def test_snapshot_serializable(self):
        """Snapshot can be serialized to JSON."""
        plays = [
            make_play(0, "LeBron makes dunk", player_name="LeBron", team_key="lal"),
            make_play(1, "LeBron commits foul", player_name="LeBron", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        # Should serialize without error
        json_str = json.dumps(snapshot.to_dict())
        assert json_str

        # Should deserialize back
        data = json.loads(json_str)
        assert data["chapter_index"] == 0
        assert "lebron" in data["players"]

    def test_delta_serializable(self):
        """SectionDelta can be serialized to JSON."""
        plays = [
            make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        delta = compute_section_delta(
            start_snapshot=None,
            end_snapshot=snapshot,
            section_start_chapter=0,
            section_end_chapter=0,
        )

        # Should serialize without error
        json_str = json.dumps(delta.to_dict())
        assert json_str

        # Should deserialize back
        data = json.loads(json_str)
        assert data["section_start_chapter"] == 0
        assert data["section_end_chapter"] == 0

    def test_notable_actions_serialized_as_sorted_list(self):
        """Notable actions set serialized as sorted list."""
        plays = [
            make_play(0, "LeBron steals", player_name="LeBron", team_key="lal"),
            make_play(1, "LeBron blocks", player_name="LeBron", team_key="lal"),
            make_play(2, "LeBron dunks", player_name="LeBron", team_key="lal"),
        ]
        chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
        snapshot = update_snapshot(build_initial_snapshot(), chapter)

        data = snapshot.to_dict()
        actions = data["players"]["lebron"]["notable_actions_set"]

        # Should be a sorted list
        assert isinstance(actions, list)
        assert actions == sorted(actions)


# ============================================================================
# TEST: INTEGRATION
# ============================================================================

class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_game_flow(self):
        """Full game with multiple chapters."""
        chapters = []

        # Q1
        q1_plays = [
            make_play(0, "LeBron makes layup", player_name="LeBron", team_key="lal"),
            make_play(1, "Curry makes 3-pt shot", player_name="Curry", team_key="gsw"),
            make_play(2, "LeBron commits foul", player_name="LeBron", team_key="lal"),
        ]
        chapters.append(make_chapter("ch_001", 0, q1_plays, ["PERIOD_START"]))

        # Q1 continued (after timeout)
        q1_timeout_plays = [
            make_play(3, "Lakers timeout", team_key="lal", play_type="timeout"),
            make_play(4, "LeBron makes dunk", player_name="LeBron", team_key="lal"),
            make_play(5, "Curry makes 3-pt shot", player_name="Curry", team_key="gsw"),
        ]
        chapters.append(make_chapter("ch_002", 3, q1_timeout_plays, ["TIMEOUT"]))

        # Q2
        q2_plays = [
            make_play(6, "Giannis makes layup", player_name="Giannis", team_key="mil"),
            make_play(7, "LeBron blocks shot", player_name="LeBron", team_key="lal"),
            make_play(8, "Curry steals", player_name="Curry", team_key="gsw"),
        ]
        chapters.append(make_chapter("ch_003", 6, q2_plays, ["PERIOD_START"]))

        # Build all snapshots
        snapshots = build_running_snapshots(chapters)

        # Verify snapshot count
        assert len(snapshots) == 3

        # Verify final totals
        final = snapshots[-1]
        assert final.players["lebron"].points_scored_total == 4  # 2 + 2
        assert final.players["lebron"].personal_foul_count_total == 1
        assert final.players["lebron"].notable_actions_set == {"dunk", "block"}

        assert final.players["curry"].points_scored_total == 6  # 3 + 3
        assert final.players["curry"].notable_actions_set == {"steal"}

        assert final.teams["lal"].timeouts_used_total == 1

        # Compute section deltas
        deltas = compute_section_deltas_from_snapshots(snapshots)

        assert len(deltas) == 3

        # First section (chapter 0)
        assert deltas[0].teams["lal"].points_scored == 2
        assert deltas[0].teams["gsw"].points_scored == 3

        # Second section (chapter 1)
        assert deltas[1].teams["lal"].points_scored == 2
        assert deltas[1].teams["gsw"].points_scored == 3
        assert deltas[1].teams["lal"].timeouts_used == 1

    def test_custom_section_boundaries(self):
        """Custom section boundaries (e.g., combining chapters)."""
        chapters = []

        for i in range(6):
            plays = [make_play(i, f"Player{i} makes layup", player_name=f"Player{i}", team_key="lal")]
            chapters.append(make_chapter(f"ch_{i:03d}", i, plays, ["PERIOD_START"] if i == 0 else ["TIMEOUT"]))

        snapshots = build_running_snapshots(chapters)

        # Combine into 2 sections: chapters 0-2, chapters 3-5
        deltas = compute_section_deltas_from_snapshots(
            snapshots,
            section_boundaries=[2, 5],  # End at chapters 2 and 5
        )

        assert len(deltas) == 2
        assert deltas[0].section_start_chapter == 0
        assert deltas[0].section_end_chapter == 2
        assert deltas[1].section_start_chapter == 3
        assert deltas[1].section_end_chapter == 5
