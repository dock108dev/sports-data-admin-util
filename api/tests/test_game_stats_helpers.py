"""Tests for game_stats_helpers module."""

from app.services.pipeline.stages.game_stats_helpers import (
    compute_running_player_stats,
    compute_lead_context,
    format_player_stat_hint,
    _is_three_pointer,
)


class TestComputeRunningPlayerStats:
    """Tests for running player stats computation."""

    def test_empty_events(self):
        """Empty PBP returns empty stats."""
        result = compute_running_player_stats([], 100)
        assert result == {}

    def test_single_made_shot(self):
        """Single made two-pointer tracked correctly."""
        events = [
            {"play_index": 1, "player_name": "LeBron James", "play_type": "made_shot", "description": "layup"}
        ]
        result = compute_running_player_stats(events, 1)
        assert result["LeBron James"]["pts"] == 2
        assert result["LeBron James"]["fgm"] == 1
        assert result["LeBron James"]["3pm"] == 0

    def test_three_pointer_detection(self):
        """Three-pointers tracked correctly."""
        events = [
            {"play_index": 1, "player_name": "Curry", "play_type": "3pt_made", "description": "3-pt shot"}
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Curry"]["pts"] == 3
        assert result["Curry"]["fgm"] == 1
        assert result["Curry"]["3pm"] == 1

    def test_free_throw(self):
        """Free throws tracked correctly."""
        events = [
            {"play_index": 1, "player_name": "Harden", "play_type": "free_throw_made", "description": ""}
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Harden"]["pts"] == 1
        assert result["Harden"]["ftm"] == 1
        assert result["Harden"]["fgm"] == 0

    def test_multiple_players(self):
        """Stats tracked separately per player."""
        events = [
            {"play_index": 1, "player_name": "Player A", "play_type": "made_shot", "description": ""},
            {"play_index": 2, "player_name": "Player B", "play_type": "3pt_made", "description": ""},
            {"play_index": 3, "player_name": "Player A", "play_type": "free_throw_made", "description": ""},
        ]
        result = compute_running_player_stats(events, 3)
        assert result["Player A"]["pts"] == 3  # 2 + 1
        assert result["Player B"]["pts"] == 3
        assert result["Player A"]["fgm"] == 1
        assert result["Player B"]["fgm"] == 1

    def test_up_to_play_index(self):
        """Only includes events up to specified index."""
        events = [
            {"play_index": 1, "player_name": "Player", "play_type": "made_shot", "description": ""},
            {"play_index": 2, "player_name": "Player", "play_type": "made_shot", "description": ""},
            {"play_index": 3, "player_name": "Player", "play_type": "made_shot", "description": ""},
        ]
        # Only first two
        result = compute_running_player_stats(events, 2)
        assert result["Player"]["pts"] == 4
        assert result["Player"]["fgm"] == 2

    def test_description_fallback(self):
        """Falls back to parsing description when play_type unclear."""
        events = [
            {"play_index": 1, "player_name": "Player", "play_type": "other", "description": "Player makes 3-pt shot"}
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Player"]["pts"] == 3
        assert result["Player"]["3pm"] == 1


class TestIsThreePointer:
    """Tests for three-pointer detection."""

    def test_explicit_3pt_type(self):
        """Detects 3pt from play type."""
        assert _is_three_pointer("3pt_made", "") is True
        assert _is_three_pointer("3-pt", "") is True

    def test_description_contains_three(self):
        """Detects from description keywords."""
        assert _is_three_pointer("", "makes 3-pt shot") is True
        assert _is_three_pointer("", "three pointer") is True

    def test_distance_indicator(self):
        """Detects from distance in description."""
        assert _is_three_pointer("", "26 ft jumper") is True
        assert _is_three_pointer("", "from 24'") is True

    def test_not_three_pointer(self):
        """Normal shots not detected as threes."""
        assert _is_three_pointer("made_shot", "layup") is False
        assert _is_three_pointer("", "15 ft jumper") is False


class TestComputeLeadContext:
    """Tests for lead context computation."""

    def test_tie_game(self):
        """Tie game detected correctly."""
        result = compute_lead_context([10, 10], [10, 10], "Lakers", "Celtics")
        assert result["is_tie_before"] is True
        assert result["is_tie_after"] is True
        assert result["leading_team_before"] is None
        assert result["margin_description"] is None

    def test_home_takes_lead(self):
        """Home team taking lead generates correct context."""
        result = compute_lead_context([10, 10], [10, 15], "Lakers", "Celtics")
        assert result["lead_before"] == 0
        assert result["lead_after"] == 5
        assert result["leading_team_after"] == "Lakers"
        assert result["is_lead_change"] is False  # No previous lead
        assert "take a 5 point lead" in result["margin_description"]

    def test_away_takes_lead(self):
        """Away team taking lead generates correct context."""
        result = compute_lead_context([10, 10], [15, 10], "Lakers", "Celtics")
        assert result["lead_after"] == -5  # Negative = away leads
        assert result["leading_team_after"] == "Celtics"
        assert "take a 5 point lead" in result["margin_description"]

    def test_extend_lead(self):
        """Extending existing lead generates correct context."""
        # Lead from 5 to 8 (not double digits)
        result = compute_lead_context([10, 15], [10, 18], "Lakers", "Celtics")
        assert result["lead_before"] == 5
        assert result["lead_after"] == 8
        assert "extend the lead to 8" in result["margin_description"]

    def test_cut_deficit(self):
        """Cutting deficit generates correct context."""
        result = compute_lead_context([20, 10], [20, 15], "Lakers", "Celtics")
        assert result["lead_before"] == -10  # Away leads by 10
        assert result["lead_after"] == -5  # Away leads by 5
        assert "cut the deficit to 5" in result["margin_description"]

    def test_lead_change(self):
        """Lead change detected correctly."""
        result = compute_lead_context([10, 12], [15, 12], "Lakers", "Celtics")
        assert result["is_lead_change"] is True
        assert result["leading_team_before"] == "Lakers"
        assert result["leading_team_after"] == "Celtics"

    def test_double_digits(self):
        """Double-digit lead generates special description."""
        result = compute_lead_context([10, 18], [10, 22], "Lakers", "Celtics")
        assert result["lead_after"] == 12
        assert "double digits" in result["margin_description"]

    def test_tie_the_game(self):
        """Tying the game generates correct description."""
        result = compute_lead_context([10, 15], [15, 15], "Lakers", "Celtics")
        assert result["is_tie_after"] is True
        assert result["margin_description"] == "tie the game"


class TestFormatPlayerStatHint:
    """Tests for player stat hint formatting."""

    def test_basic_stats(self):
        """Formats basic point stats."""
        result = format_player_stat_hint("Donovan Mitchell", {"pts": 12, "3pm": 2, "fgm": 5, "ftm": 2, "reb": 3, "ast": 2})
        assert "Mitchell" in result
        assert "12 pts" in result
        assert "2 3PM" in result

    def test_no_notable_stats(self):
        """Returns None when no notable stats."""
        result = format_player_stat_hint("Player", {"pts": 0, "3pm": 0, "fgm": 0, "ftm": 0, "reb": 2, "ast": 1})
        assert result is None

    def test_rebounds_threshold(self):
        """Only includes rebounds when >= 5."""
        result_low = format_player_stat_hint("Player", {"pts": 0, "3pm": 0, "fgm": 0, "ftm": 0, "reb": 4, "ast": 0})
        assert result_low is None

        result_high = format_player_stat_hint("Player", {"pts": 0, "3pm": 0, "fgm": 0, "ftm": 0, "reb": 5, "ast": 0})
        assert "5 reb" in result_high

    def test_single_name(self):
        """Handles single-word names."""
        result = format_player_stat_hint("Neymar", {"pts": 10, "3pm": 0, "fgm": 5, "ftm": 0, "reb": 0, "ast": 0})
        assert "Neymar" in result
