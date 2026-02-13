"""Tests for game_stats_helpers module."""

from app.services.pipeline.stages.game_stats_helpers import (
    _apply_basketball_scoring,
    _compute_single_team_delta,
    compute_running_player_stats,
    compute_lead_context,
    compute_cumulative_box_score,
    compute_block_mini_box,
    format_player_stat_hint,
)


class TestComputeRunningPlayerStats:
    """Tests for running player stats computation."""

    def test_empty_events(self):
        """Empty PBP returns empty stats."""
        result = compute_running_player_stats([], 100)
        assert result == {}

    def test_single_made_shot(self):
        """Single made two-pointer tracked correctly via score delta."""
        events = [
            {
                "play_index": 1,
                "player_name": "LeBron James",
                "play_type": "made_shot",
                "description": "layup",
                "home_score": 2,
                "away_score": 0,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["LeBron James"]["pts"] == 2
        assert result["LeBron James"]["fgm"] == 1
        assert result["LeBron James"]["3pm"] == 0

    def test_three_pointer_detection(self):
        """Three-pointers tracked correctly via score delta of 3."""
        events = [
            {
                "play_index": 1,
                "player_name": "Curry",
                "play_type": "3pt_made",
                "description": "3-pt shot",
                "home_score": 3,
                "away_score": 0,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Curry"]["pts"] == 3
        assert result["Curry"]["fgm"] == 1
        assert result["Curry"]["3pm"] == 1

    def test_free_throw(self):
        """Free throws tracked correctly via score delta of 1."""
        events = [
            {
                "play_index": 1,
                "player_name": "Harden",
                "play_type": "free_throw_made",
                "description": "",
                "home_score": 1,
                "away_score": 0,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Harden"]["pts"] == 1
        assert result["Harden"]["ftm"] == 1
        assert result["Harden"]["fgm"] == 0

    def test_multiple_players(self):
        """Stats tracked separately per player."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Player B",
                "play_type": "3pt_made",
                "description": "",
                "home_score": 5,
                "away_score": 0,
            },
            {
                "play_index": 3,
                "player_name": "Player A",
                "play_type": "free_throw_made",
                "description": "",
                "home_score": 6,
                "away_score": 0,
            },
        ]
        result = compute_running_player_stats(events, 3)
        assert result["Player A"]["pts"] == 3  # 2 + 1
        assert result["Player B"]["pts"] == 3
        assert result["Player A"]["fgm"] == 1
        assert result["Player B"]["fgm"] == 1

    def test_up_to_play_index(self):
        """Only includes events up to specified index."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Player",
                "play_type": "made_shot",
                "description": "",
                "home_score": 4,
                "away_score": 0,
            },
            {
                "play_index": 3,
                "player_name": "Player",
                "play_type": "made_shot",
                "description": "",
                "home_score": 6,
                "away_score": 0,
            },
        ]
        # Only first two
        result = compute_running_player_stats(events, 2)
        assert result["Player"]["pts"] == 4
        assert result["Player"]["fgm"] == 2

    def test_nba_api_format_score_based_detection(self):
        """NBA API format detected via score delta."""
        events = [
            {
                "play_index": 1,
                "player_name": "J. Tatum",
                "play_type": "2pt",
                "description": "J. Tatum Layup",
                "home_score": 0,
                "away_score": 2,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["J. Tatum"]["pts"] == 2
        assert result["J. Tatum"]["fgm"] == 1

    def test_miss_no_score_change(self):
        """Miss has no score change — 0 pts."""
        events = [
            {
                "play_index": 1,
                "player_name": "J. Tatum",
                "play_type": "2pt",
                "description": "J. Tatum Layup MISS",
                "home_score": 0,
                "away_score": 0,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["J. Tatum"]["pts"] == 0
        assert result["J. Tatum"]["fgm"] == 0

    def test_three_pointer_via_score_delta(self):
        """Score delta of 3 correctly classifies as 3-pointer."""
        events = [
            {
                "play_index": 1,
                "player_name": "Curry",
                "play_type": "3pt",
                "description": "S. Curry 3PT",
                "home_score": 3,
                "away_score": 0,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Curry"]["pts"] == 3
        assert result["Curry"]["3pm"] == 1
        assert result["Curry"]["fgm"] == 1

    def test_free_throw_via_score_delta(self):
        """Score delta of 1 correctly classifies as free throw."""
        events = [
            {
                "play_index": 1,
                "player_name": "Harden",
                "play_type": "freethrow",
                "description": "J. Harden Free Throw",
                "home_score": 1,
                "away_score": 0,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Harden"]["pts"] == 1
        assert result["Harden"]["ftm"] == 1
        assert result["Harden"]["fgm"] == 0

    def test_ncaab_offensive_rebound(self):
        """NCAAB offensive_rebound play_type counted as rebound."""
        events = [
            {
                "play_index": 1,
                "player_name": "Edey",
                "play_type": "offensive_rebound",
                "description": "",
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Edey"]["reb"] == 1

    def test_ncaab_defensive_rebound(self):
        """NCAAB defensive_rebound play_type counted as rebound."""
        events = [
            {
                "play_index": 1,
                "player_name": "Edey",
                "play_type": "defensive_rebound",
                "description": "",
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["Edey"]["reb"] == 1

    def test_assist_from_description_on_scoring_play(self):
        """Assists extracted from description on scoring plays."""
        events = [
            {
                "play_index": 1,
                "player_name": "L. Markkanen",
                "play_type": "2pt",
                "description": "L. Markkanen 26' 3PT (3 PTS) (A. Bailey 1 AST)",
                "home_score": 3,
                "away_score": 0,
            }
        ]
        result = compute_running_player_stats(events, 1)
        assert result["L. Markkanen"]["pts"] == 3
        assert result["A. Bailey"]["ast"] == 1


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
        """Home team taking lead generates correct context.

        Score format is [home, away]. Home goes from tied to leading 15-10.
        """
        result = compute_lead_context([10, 10], [15, 10], "Lakers", "Celtics")
        assert result["lead_before"] == 0
        assert result["lead_after"] == 5
        assert result["leading_team_after"] == "Lakers"
        assert result["is_lead_change"] is False  # No previous lead
        assert "take a 5 point lead" in result["margin_description"]

    def test_away_takes_lead(self):
        """Away team taking lead generates correct context.

        Score format is [home, away]. Away goes from tied to leading 10-15.
        """
        result = compute_lead_context([10, 10], [10, 15], "Lakers", "Celtics")
        assert result["lead_after"] == -5  # Negative = away leads
        assert result["leading_team_after"] == "Celtics"
        assert "take a 5 point lead" in result["margin_description"]

    def test_extend_lead(self):
        """Extending existing lead generates correct context.

        Score format is [home, away]. Home extends lead from 5 to 8.
        """
        result = compute_lead_context([15, 10], [18, 10], "Lakers", "Celtics")
        assert result["lead_before"] == 5
        assert result["lead_after"] == 8
        assert "extend the lead to 8" in result["margin_description"]

    def test_cut_deficit(self):
        """Cutting deficit generates correct context.

        Score format is [home, away]. Away leads 10-20, home cuts to 15-20.
        """
        result = compute_lead_context([10, 20], [15, 20], "Lakers", "Celtics")
        assert result["lead_before"] == -10  # Away leads by 10
        assert result["lead_after"] == -5  # Away leads by 5
        assert "cut the deficit to 5" in result["margin_description"]

    def test_lead_change(self):
        """Lead change detected correctly.

        Score format is [home, away]. Home leads 12-10, then away takes lead 12-15.
        """
        result = compute_lead_context([12, 10], [12, 15], "Lakers", "Celtics")
        assert result["is_lead_change"] is True
        assert result["leading_team_before"] == "Lakers"
        assert result["leading_team_after"] == "Celtics"

    def test_double_digits(self):
        """Double-digit lead generates special description.

        Score format is [home, away]. Home extends lead to 12 points.
        """
        result = compute_lead_context([18, 10], [22, 10], "Lakers", "Celtics")
        assert result["lead_after"] == 12
        assert "double digits" in result["margin_description"]

    def test_tie_the_game(self):
        """Tying the game generates correct description.

        Score format is [home, away]. Home down 10-15, ties it 15-15.
        """
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


class TestComputeCumulativeBoxScore:
    """Tests for cumulative box score computation with team assignment."""

    def test_empty_events(self):
        """Empty PBP returns empty box scores."""
        result = compute_cumulative_box_score([], 100, "Home Team", "Away Team")
        assert result["home"]["players"] == []
        assert result["away"]["players"] == []
        assert result["home"]["score"] == 0
        assert result["away"]["score"] == 0

    def test_abbreviation_matching_gsw(self):
        """GSW abbreviation matches correctly to Golden State Warriors."""
        events = [
            {
                "play_index": 1,
                "player_name": "Stephen Curry",
                "team_abbreviation": "GSW",
                "play_type": "3pt_made",
                "description": "3-pt shot",
                "home_score": 3,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Jayson Tatum",
                "team_abbreviation": "BOS",
                "play_type": "made_shot",
                "description": "layup",
                "home_score": 3,
                "away_score": 2,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Golden State Warriors",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="GSW",
            away_team_abbrev="BOS",
        )
        # Curry should be home, Tatum should be away
        assert len(result["home"]["players"]) == 1
        assert result["home"]["players"][0]["name"] == "Stephen Curry"
        assert result["home"]["players"][0]["pts"] == 3
        assert result["home"]["players"][0]["3pm"] == 1

        assert len(result["away"]["players"]) == 1
        assert result["away"]["players"][0]["name"] == "Jayson Tatum"
        assert result["away"]["players"][0]["pts"] == 2

    def test_abbreviation_matching_lac(self):
        """LAC abbreviation matches correctly to Los Angeles Clippers."""
        events = [
            {
                "play_index": 1,
                "player_name": "Kawhi Leonard",
                "team_abbreviation": "LAC",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "LeBron James",
                "team_abbreviation": "LAL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 2,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Los Angeles Clippers",
            "Los Angeles Lakers",
            "NBA",
            home_team_abbrev="LAC",
            away_team_abbrev="LAL",
        )
        # Kawhi should be home (LAC), LeBron should be away (LAL)
        assert len(result["home"]["players"]) == 1
        assert result["home"]["players"][0]["name"] == "Kawhi Leonard"

        assert len(result["away"]["players"]) == 1
        assert result["away"]["players"][0]["name"] == "LeBron James"

    def test_no_abbreviations_skips_players(self):
        """Players are skipped when team abbreviations are not provided."""
        events = [
            {
                "play_index": 1,
                "player_name": "Trae Young",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
        ]
        # No abbreviations provided — player can't be assigned to a side
        result = compute_cumulative_box_score(
            events,
            1,
            "Atlanta Hawks",
            "Miami Heat",
            "NBA",
        )
        assert len(result["home"]["players"]) == 0
        assert len(result["away"]["players"]) == 0

    def test_case_insensitive_matching(self):
        """Abbreviation matching is case-insensitive."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "team_abbreviation": "gsw",  # lowercase
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            1,
            "Golden State Warriors",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="GSW",  # uppercase
            away_team_abbrev="BOS",
        )
        assert len(result["home"]["players"]) == 1

    def test_multiple_players_same_team(self):
        """Multiple players on same team are assigned correctly."""
        events = [
            {
                "play_index": 1,
                "player_name": "Stephen Curry",
                "team_abbreviation": "GSW",
                "play_type": "3pt_made",
                "description": "",
                "home_score": 3,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Klay Thompson",
                "team_abbreviation": "GSW",
                "play_type": "3pt_made",
                "description": "",
                "home_score": 6,
                "away_score": 0,
            },
            {
                "play_index": 3,
                "player_name": "Draymond Green",
                "team_abbreviation": "GSW",
                "play_type": "assist",
                "description": "",
            },
        ]
        result = compute_cumulative_box_score(
            events,
            3,
            "Golden State Warriors",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="GSW",
            away_team_abbrev="BOS",
        )
        assert len(result["home"]["players"]) == 3
        player_names = {p["name"] for p in result["home"]["players"]}
        assert player_names == {"Stephen Curry", "Klay Thompson", "Draymond Green"}

    def test_players_sorted_by_contribution(self):
        """Players are sorted by contribution (pts for basketball)."""
        events = [
            {
                "play_index": 1,
                "player_name": "Low Scorer",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "High Scorer",
                "team_abbreviation": "ATL",
                "play_type": "3pt_made",
                "description": "",
                "home_score": 5,
                "away_score": 0,
            },
            {
                "play_index": 3,
                "player_name": "High Scorer",
                "team_abbreviation": "ATL",
                "play_type": "3pt_made",
                "description": "",
                "home_score": 8,
                "away_score": 0,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            3,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        # High Scorer (6 pts) should be first
        assert result["home"]["players"][0]["name"] == "High Scorer"
        assert result["home"]["players"][0]["pts"] == 6
        assert result["home"]["players"][1]["name"] == "Low Scorer"
        assert result["home"]["players"][1]["pts"] == 2

    def test_player_without_team_abbreviation_skipped(self):
        """Players without team abbreviation are skipped."""
        events = [
            {
                "play_index": 1,
                "player_name": "Unknown Player",
                "team_abbreviation": "",  # No team
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Known Player",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 4,
                "away_score": 0,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        # Only Known Player should be included
        assert len(result["home"]["players"]) == 1
        assert result["home"]["players"][0]["name"] == "Known Player"

    def test_up_to_play_index_limit(self):
        """Only includes stats up to specified play index."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
            },
            {
                "play_index": 2,
                "player_name": "Player",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 4,
            },
            {
                "play_index": 3,
                "player_name": "Player",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 6,
            },
        ]
        # Only up to play 2
        result = compute_cumulative_box_score(
            events,
            2,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        assert result["home"]["players"][0]["pts"] == 4  # 2 + 2
        assert result["home"]["score"] == 4

    def test_nhl_stats(self):
        """NHL stats are accumulated correctly."""
        events = [
            {
                "play_index": 1,
                "player_name": "David Pastrnak",
                "team_abbreviation": "BOS",
                "play_type": "goal",
                "description": "",
                "home_score": 1,
            },
            {
                "play_index": 2,
                "player_name": "Brad Marchand",
                "team_abbreviation": "BOS",
                "play_type": "assist",
                "description": "",
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Boston Bruins",
            "Toronto Maple Leafs",
            "NHL",
            home_team_abbrev="BOS",
            away_team_abbrev="TOR",
        )
        # Pastrnak should have 1 goal
        pastrnak = next(p for p in result["home"]["players"] if p["name"] == "David Pastrnak")
        assert pastrnak["goals"] == 1

        # Marchand should have 1 assist
        marchand = next(p for p in result["home"]["players"] if p["name"] == "Brad Marchand")
        assert marchand["assists"] == 1

    def test_nhl_goalie_stats(self):
        """NHL goalie stats are extracted correctly with save percentage."""
        events = [
            {
                "play_index": 1,
                "player_name": "Jeremy Swayman",
                "team_abbreviation": "BOS",
                "play_type": "save",
                "description": "",
            },
            {
                "play_index": 2,
                "player_name": "Jeremy Swayman",
                "team_abbreviation": "BOS",
                "play_type": "save",
                "description": "",
            },
            {
                "play_index": 3,
                "player_name": "Jeremy Swayman",
                "team_abbreviation": "BOS",
                "play_type": "save",
                "description": "",
            },
            {
                "play_index": 4,
                "player_name": "Jeremy Swayman",
                "team_abbreviation": "BOS",
                "play_type": "goal_against",
                "description": "",
                "away_score": 1,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            4,
            "Boston Bruins",
            "Toronto Maple Leafs",
            "NHL",
            home_team_abbrev="BOS",
            away_team_abbrev="TOR",
        )
        # Goalie should be extracted
        assert "goalie" in result["home"]
        goalie = result["home"]["goalie"]
        assert goalie["name"] == "Jeremy Swayman"
        assert goalie["saves"] == 3
        assert goalie["ga"] == 1
        # Save pct = 3 / (3 + 1) = 0.75
        assert goalie["savePct"] == 0.75

    def test_nhl_shots_on_goal(self):
        """NHL shots on goal are tracked correctly."""
        events = [
            {
                "play_index": 1,
                "player_name": "Auston Matthews",
                "team_abbreviation": "TOR",
                "play_type": "shot_on_goal",
                "description": "",
            },
            {
                "play_index": 2,
                "player_name": "Auston Matthews",
                "team_abbreviation": "TOR",
                "play_type": "sog",
                "description": "",
            },
            {
                "play_index": 3,
                "player_name": "Auston Matthews",
                "team_abbreviation": "TOR",
                "play_type": "goal",
                "description": "",
                "away_score": 1,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            3,
            "Boston Bruins",
            "Toronto Maple Leafs",
            "NHL",
            home_team_abbrev="BOS",
            away_team_abbrev="TOR",
        )
        matthews = result["away"]["players"][0]
        assert matthews["name"] == "Auston Matthews"
        assert matthews["sog"] == 2  # 2 shots on goal
        assert matthews["goals"] == 1

    def test_nhl_sorting_by_points(self):
        """NHL players are sorted by goals + assists."""
        events = [
            {
                "play_index": 1,
                "player_name": "Low Points",
                "team_abbreviation": "BOS",
                "play_type": "assist",
                "description": "",
            },
            {
                "play_index": 2,
                "player_name": "High Points",
                "team_abbreviation": "BOS",
                "play_type": "goal",
                "description": "",
                "home_score": 1,
            },
            {
                "play_index": 3,
                "player_name": "High Points",
                "team_abbreviation": "BOS",
                "play_type": "assist",
                "description": "",
            },
            {
                "play_index": 4,
                "player_name": "High Points",
                "team_abbreviation": "BOS",
                "play_type": "goal",
                "description": "",
                "home_score": 2,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            4,
            "Boston Bruins",
            "Toronto Maple Leafs",
            "NHL",
            home_team_abbrev="BOS",
            away_team_abbrev="TOR",
        )
        # High Points (2G + 1A = 3 pts) should be first
        assert result["home"]["players"][0]["name"] == "High Points"
        assert result["home"]["players"][0]["goals"] == 2
        assert result["home"]["players"][0]["assists"] == 1
        # Low Points (0G + 1A = 1 pt) should be second
        assert result["home"]["players"][1]["name"] == "Low Points"

    def test_nhl_description_fallback(self):
        """NHL stats can be parsed from description when play_type is unclear."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "team_abbreviation": "BOS",
                "play_type": "other",
                "description": "Player A scores goal",
            },
            {
                "play_index": 2,
                "player_name": "Player B",
                "team_abbreviation": "BOS",
                "play_type": "unknown",
                "description": "Player B with an assist",
            },
            {
                "play_index": 3,
                "player_name": "Player C",
                "team_abbreviation": "BOS",
                "play_type": "",
                "description": "Player C wrist shot saved",  # "saved" excludes goal detection
            },
        ]
        result = compute_cumulative_box_score(
            events,
            3,
            "Boston Bruins",
            "Toronto Maple Leafs",
            "NHL",
            home_team_abbrev="BOS",
            away_team_abbrev="TOR",
        )
        player_a = next(p for p in result["home"]["players"] if p["name"] == "Player A")
        assert player_a["goals"] == 1

        player_b = next(p for p in result["home"]["players"] if p["name"] == "Player B")
        assert player_b["assists"] == 1

        player_c = next(p for p in result["home"]["players"] if p["name"] == "Player C")
        assert player_c["sog"] == 1

    def test_basketball_rebounds_and_assists(self):
        """Basketball rebounds and assists are tracked correctly."""
        events = [
            {
                "play_index": 1,
                "player_name": "Kevin Durant",
                "team_abbreviation": "PHX",
                "play_type": "rebound",
                "description": "",
            },
            {
                "play_index": 2,
                "player_name": "Kevin Durant",
                "team_abbreviation": "PHX",
                "play_type": "rebound",
                "description": "",
            },
            {
                "play_index": 3,
                "player_name": "Chris Paul",
                "team_abbreviation": "PHX",
                "play_type": "assist",
                "description": "",
            },
            {
                "play_index": 4,
                "player_name": "Chris Paul",
                "team_abbreviation": "PHX",
                "play_type": "assist",
                "description": "",
            },
            {
                "play_index": 5,
                "player_name": "Chris Paul",
                "team_abbreviation": "PHX",
                "play_type": "assist",
                "description": "",
            },
        ]
        result = compute_cumulative_box_score(
            events,
            5,
            "Phoenix Suns",
            "Los Angeles Lakers",
            "NBA",
            home_team_abbrev="PHX",
            away_team_abbrev="LAL",
        )
        durant = next(p for p in result["home"]["players"] if p["name"] == "Kevin Durant")
        assert durant["reb"] == 2
        assert durant["pts"] == 0

        paul = next(p for p in result["home"]["players"] if p["name"] == "Chris Paul")
        assert paul["ast"] == 3
        assert paul["pts"] == 0

    def test_basketball_free_throws(self):
        """Basketball free throws are tracked correctly via score delta."""
        events = [
            {
                "play_index": 1,
                "player_name": "James Harden",
                "team_abbreviation": "LAC",
                "play_type": "free_throw_made",
                "description": "",
                "home_score": 1,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "James Harden",
                "team_abbreviation": "LAC",
                "play_type": "ft_made",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Los Angeles Clippers",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="LAC",
            away_team_abbrev="BOS",
        )
        harden = result["home"]["players"][0]
        assert harden["name"] == "James Harden"
        assert harden["ftm"] == 2
        assert harden["pts"] == 2
        assert harden["fgm"] == 0

    def test_score_based_detection(self):
        """Scoring detected via score delta regardless of description content."""
        events = [
            {
                "play_index": 1,
                "player_name": "J. Tatum",
                "team_abbreviation": "BOS",
                "play_type": "2pt",
                "description": "J. Tatum Layup",
                "home_score": 0,
                "away_score": 2,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            1,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        tatum = result["away"]["players"][0]
        assert tatum["pts"] == 2
        assert tatum["fgm"] == 1

    def test_miss_no_points(self):
        """Miss (no score change) yields 0 points."""
        events = [
            {
                "play_index": 1,
                "player_name": "J. Tatum",
                "team_abbreviation": "BOS",
                "play_type": "2pt",
                "description": "J. Tatum Layup MISS",
                "home_score": 0,
                "away_score": 0,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            1,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        tatum = result["away"]["players"][0]
        assert tatum["pts"] == 0
        assert tatum["fgm"] == 0

    def test_three_pointer_via_cumulative_score_delta(self):
        """Score delta of 3 in cumulative box correctly classifies as 3PM."""
        events = [
            {
                "play_index": 1,
                "player_name": "Curry",
                "team_abbreviation": "GSW",
                "play_type": "3pt",
                "description": "S. Curry 3PT",
                "home_score": 3,
                "away_score": 0,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            1,
            "Golden State Warriors",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="GSW",
            away_team_abbrev="BOS",
        )
        curry = result["home"]["players"][0]
        assert curry["pts"] == 3
        assert curry["3pm"] == 1
        assert curry["fgm"] == 1

    def test_ncaab_offensive_defensive_rebounds(self):
        """NCAAB offensive_rebound and defensive_rebound counted as rebounds."""
        events = [
            {
                "play_index": 1,
                "player_name": "Edey",
                "team_abbreviation": "PUR",
                "play_type": "offensive_rebound",
                "description": "",
            },
            {
                "play_index": 2,
                "player_name": "Edey",
                "team_abbreviation": "PUR",
                "play_type": "defensive_rebound",
                "description": "",
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Purdue Boilermakers",
            "UConn Huskies",
            "NCAAB",
            home_team_abbrev="PUR",
            away_team_abbrev="CONN",
        )
        edey = result["home"]["players"][0]
        assert edey["reb"] == 2

    def test_top_5_players_limit(self):
        """Only top 5 contributors per team are returned."""
        # Create 7 players with varying point totals
        events = []
        running_score = 0
        for i, pts in enumerate([10, 8, 6, 4, 2, 1, 0]):
            player_name = f"Player{i}"
            for _ in range(pts // 2):  # Each made shot = 2 pts
                running_score += 2
                events.append({
                    "play_index": len(events) + 1,
                    "player_name": player_name,
                    "team_abbreviation": "ATL",
                    "play_type": "made_shot",
                    "description": "",
                    "home_score": running_score,
                    "away_score": 0,
                })

        result = compute_cumulative_box_score(
            events,
            len(events),
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        # Should only have 5 players (top 5 scorers)
        assert len(result["home"]["players"]) == 5
        # Highest scorer should be first
        assert result["home"]["players"][0]["name"] == "Player0"
        assert result["home"]["players"][0]["pts"] == 10
        # 5th player should be Player4 (2 pts)
        assert result["home"]["players"][4]["name"] == "Player4"
        assert result["home"]["players"][4]["pts"] == 2

    def test_ncaab_uses_basketball_stats(self):
        """NCAAB uses basketball stat accumulation."""
        events = [
            {
                "play_index": 1,
                "player_name": "Zach Edey",
                "team_abbreviation": "PUR",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
            },
            {
                "play_index": 2,
                "player_name": "Zach Edey",
                "team_abbreviation": "PUR",
                "play_type": "rebound",
                "description": "",
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Purdue Boilermakers",
            "UConn Huskies",
            "NCAAB",
            home_team_abbrev="PUR",
            away_team_abbrev="CONN",
        )
        edey = result["home"]["players"][0]
        assert edey["name"] == "Zach Edey"
        assert edey["pts"] == 2
        assert edey["reb"] == 1
        # Should have basketball keys, not NHL keys
        assert "goals" not in edey
        assert "assists" not in edey


class TestComputeBlockMiniBox:
    """Tests for mini box score PRA stripping."""

    def test_mini_box_contains_only_pra_keys(self):
        """Mini box strips to PRA-only keys for basketball."""
        events = [
            {
                "play_index": 1,
                "player_name": "Trae Young",
                "team_abbreviation": "ATL",
                "play_type": "3pt",
                "description": "",
                "home_score": 3,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Trae Young",
                "team_abbreviation": "ATL",
                "play_type": "rebound",
                "description": "",
            },
            {
                "play_index": 3,
                "player_name": "Trae Young",
                "team_abbreviation": "ATL",
                "play_type": "assist",
                "description": "",
            },
        ]
        result = compute_block_mini_box(
            events,
            block_start_play_idx=1,
            block_end_play_idx=3,
            prev_block_end_play_idx=None,
            home_team="Atlanta Hawks",
            away_team="Boston Celtics",
            league_code="NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        pra_keys = {"name", "pts", "reb", "ast", "deltaPts", "deltaReb", "deltaAst"}
        for side in ["home", "away"]:
            for player in result[side]["players"]:
                assert set(player.keys()).issubset(pra_keys), (
                    f"Unexpected keys in mini box: {set(player.keys()) - pra_keys}"
                )


class TestScoreGapGuard:
    """Tests for score-gap guard that skips attribution when delta > 3."""

    def test_apply_basketball_scoring_skips_large_delta(self):
        """_apply_basketball_scoring returns False and leaves stats unchanged for delta > 3."""
        stats = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0}
        result = _apply_basketball_scoring(stats, 7)
        assert result is False
        assert stats == {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0}

    def test_apply_basketball_scoring_allows_normal_deltas(self):
        """_apply_basketball_scoring works correctly for delta 1, 2, 3."""
        # Free throw (delta 1)
        stats_ft = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0}
        assert _apply_basketball_scoring(stats_ft, 1) is True
        assert stats_ft == {"pts": 1, "fgm": 0, "3pm": 0, "ftm": 1}

        # Two-pointer (delta 2)
        stats_2pt = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0}
        assert _apply_basketball_scoring(stats_2pt, 2) is True
        assert stats_2pt == {"pts": 2, "fgm": 1, "3pm": 0, "ftm": 0}

        # Three-pointer (delta 3)
        stats_3pt = {"pts": 0, "fgm": 0, "3pm": 0, "ftm": 0}
        assert _apply_basketball_scoring(stats_3pt, 3) is True
        assert stats_3pt == {"pts": 3, "fgm": 1, "3pm": 1, "ftm": 0}

    def test_score_gap_skips_attribution_running_stats(self):
        """compute_running_player_stats skips attribution when score gap > 3."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "play_type": "made_shot",
                "description": "",
                "home_score": 50,
                "away_score": 40,
            },
            {
                "play_index": 2,
                "player_name": "Player B",
                "play_type": "made_shot",
                "description": "",
                "home_score": 58,  # +8 gap — dropped plays
                "away_score": 40,
            },
        ]
        result = compute_running_player_stats(events, 2)
        # Player B should get 0 pts because delta of 8 exceeds max
        assert result["Player B"]["pts"] == 0
        assert result["Player B"]["fgm"] == 0
        assert result["Player B"]["3pm"] == 0
        assert result["Player B"]["ftm"] == 0

    def test_score_gap_skips_attribution_cumulative_box(self):
        """compute_cumulative_box_score skips attribution when score gap > 3."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 50,
                "away_score": 40,
            },
            {
                "play_index": 2,
                "player_name": "Player B",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 57,  # +7 gap — dropped plays
                "away_score": 40,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        player_b = next(
            p for p in result["home"]["players"] if p["name"] == "Player B"
        )
        assert player_b["pts"] == 0
        assert player_b["fgm"] == 0
        assert player_b["3pm"] == 0
        assert player_b["ftm"] == 0

    def test_normal_scoring_after_gap(self):
        """After a gap event, normal scoring is attributed correctly."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "play_type": "made_shot",
                "description": "",
                "home_score": 50,
                "away_score": 40,
            },
            {
                "play_index": 2,
                "player_name": "Player B",
                "play_type": "made_shot",
                "description": "",
                "home_score": 58,  # +8 gap — skipped
                "away_score": 40,
            },
            {
                "play_index": 3,
                "player_name": "Player C",
                "play_type": "made_shot",
                "description": "",
                "home_score": 60,  # +2 from 58 — normal play
                "away_score": 40,
            },
        ]
        result = compute_running_player_stats(events, 3)
        # Player C should get normal 2-pt attribution
        assert result["Player C"]["pts"] == 2
        assert result["Player C"]["fgm"] == 1
        # Player B should still have 0
        assert result["Player B"]["pts"] == 0


class TestComputeSingleTeamDelta:
    """Tests for _compute_single_team_delta helper."""

    def test_only_home_scored(self):
        """When only home score increases, return home delta."""
        assert _compute_single_team_delta(5, 0, 3, 0) == 2

    def test_only_away_scored(self):
        """When only away score increases, return away delta."""
        assert _compute_single_team_delta(0, 5, 0, 3) == 2

    def test_no_score_change(self):
        """When neither score changes, return 0."""
        assert _compute_single_team_delta(10, 10, 10, 10) == 0

    def test_both_changed_with_home_team_match(self):
        """When both changed and team matches home, return home delta."""
        result = _compute_single_team_delta(
            12, 8, 10, 5,
            team_abbreviation="ATL",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        assert result == 2  # home_delta only

    def test_both_changed_with_away_team_match(self):
        """When both changed and team matches away, return away delta."""
        result = _compute_single_team_delta(
            12, 8, 10, 5,
            team_abbreviation="BOS",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        assert result == 3  # away_delta only

    def test_both_changed_no_team_info(self):
        """When both changed and no team info, return 0 (conservative skip)."""
        assert _compute_single_team_delta(12, 8, 10, 5) == 0

    def test_both_changed_case_insensitive(self):
        """Team matching is case-insensitive."""
        result = _compute_single_team_delta(
            12, 8, 10, 5,
            team_abbreviation="atl",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        assert result == 2


class TestCrossTeamScoring:
    """Tests for correct per-team score attribution (the core bug fix)."""

    def test_alternating_home_away_running_stats(self):
        """Interleaved home/away scoring should attribute correctly to each player."""
        events = [
            {
                "play_index": 1,
                "player_name": "Home Player",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Away Player",
                "play_type": "made_shot",
                "description": "",
                "home_score": 2,
                "away_score": 3,
            },
            {
                "play_index": 3,
                "player_name": "Home Player",
                "play_type": "made_shot",
                "description": "",
                "home_score": 5,
                "away_score": 3,
            },
        ]
        result = compute_running_player_stats(events, 3)
        # Home Player: 2 + 3 = 5 pts
        assert result["Home Player"]["pts"] == 5
        # Away Player: 3 pts (only away delta)
        assert result["Away Player"]["pts"] == 3

    def test_both_teams_change_running_stats_conservative_skip(self):
        """When both scores change simultaneously, running stats skip attribution."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "play_type": "made_shot",
                "description": "",
                "home_score": 10,
                "away_score": 10,
            },
            {
                # Both scores changed — ambiguous without team info
                "play_index": 2,
                "player_name": "Player B",
                "play_type": "made_shot",
                "description": "",
                "home_score": 12,
                "away_score": 13,
            },
        ]
        result = compute_running_player_stats(events, 2)
        # Player B should get 0 — both teams changed, no team info available
        assert result["Player B"]["pts"] == 0

    def test_both_teams_change_cumulative_box_with_team_match(self):
        """When both scores change, cumulative box uses team matching to attribute."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 10,
                "away_score": 10,
            },
            {
                # Both scores changed — but we know Player B is on ATL (home)
                "play_index": 2,
                "player_name": "Player B",
                "team_abbreviation": "ATL",
                "play_type": "made_shot",
                "description": "",
                "home_score": 12,
                "away_score": 13,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            2,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        player_b = next(
            p for p in result["home"]["players"] if p["name"] == "Player B"
        )
        # Should get home_delta=2, NOT combined delta of 5
        assert player_b["pts"] == 2

    def test_alternating_home_away_cumulative_box(self):
        """Alternating scoring attributes correctly in cumulative box."""
        events = [
            {
                "play_index": 1,
                "player_name": "Trae Young",
                "team_abbreviation": "ATL",
                "play_type": "3pt_made",
                "description": "",
                "home_score": 3,
                "away_score": 0,
            },
            {
                "play_index": 2,
                "player_name": "Jayson Tatum",
                "team_abbreviation": "BOS",
                "play_type": "made_shot",
                "description": "",
                "home_score": 3,
                "away_score": 2,
            },
            {
                "play_index": 3,
                "player_name": "Trae Young",
                "team_abbreviation": "ATL",
                "play_type": "free_throw_made",
                "description": "",
                "home_score": 4,
                "away_score": 2,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            3,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        trae = result["home"]["players"][0]
        assert trae["name"] == "Trae Young"
        assert trae["pts"] == 4  # 3 + 1, NOT 3+2+1=6

        tatum = result["away"]["players"][0]
        assert tatum["name"] == "Jayson Tatum"
        assert tatum["pts"] == 2

    def test_score_zero_not_treated_as_missing(self):
        """Score of 0 should not be treated as missing (falsy)."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "play_type": "made_shot",
                "description": "",
                "home_score": 0,  # Explicitly 0, not missing
                "away_score": 2,
            },
        ]
        result = compute_running_player_stats(events, 1)
        # Away scored 2 — should be attributed
        assert result["Player A"]["pts"] == 2

    def test_score_zero_cumulative_not_treated_as_missing(self):
        """Score of 0 in cumulative box should not be overwritten with prev."""
        events = [
            {
                "play_index": 1,
                "player_name": "Player A",
                "team_abbreviation": "BOS",
                "play_type": "made_shot",
                "description": "",
                "home_score": 0,
                "away_score": 2,
            },
        ]
        result = compute_cumulative_box_score(
            events,
            1,
            "Atlanta Hawks",
            "Boston Celtics",
            "NBA",
            home_team_abbrev="ATL",
            away_team_abbrev="BOS",
        )
        player = result["away"]["players"][0]
        assert player["pts"] == 2
        # Home score should be 0, not some prev value
        assert result["home"]["score"] == 0
