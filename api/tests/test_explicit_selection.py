"""Tests for explicit_selection stage."""


class TestSelectExplicitlyNarratedPlays:
    """Tests for select_explicitly_narrated_plays function."""

    def test_scoring_play_is_selected(self):
        """Scoring play is explicitly narrated."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 0, "away_score": 0},
            {"play_index": 2, "home_score": 2, "away_score": 0},  # Scoring play
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        assert 2 in result

    def test_first_play_with_score_is_scoring(self):
        """First play with non-zero score is explicitly narrated."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 3, "away_score": 0},  # First play scores
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        assert 1 in result

    def test_notable_play_selected_when_no_scoring(self):
        """Notable play is selected when no scoring plays."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 0, "away_score": 0, "play_type": "other"},
            {"play_index": 2, "home_score": 0, "away_score": 0, "play_type": "block"},
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        assert 2 in result

    def test_fallback_selects_last_play(self):
        """Last play is selected as fallback when no scoring or notable."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 0, "away_score": 0, "play_type": "other"},
            {"play_index": 2, "home_score": 0, "away_score": 0, "play_type": "other"},
            {"play_index": 3, "home_score": 0, "away_score": 0, "play_type": "other"},
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        assert result == [3]

    def test_max_two_explicit_plays(self):
        """At most MAX_EXPLICIT_PLAYS_PER_MOMENT (2) plays selected."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 0, "away_score": 0},
            {"play_index": 2, "home_score": 2, "away_score": 0},  # Scoring
            {"play_index": 3, "home_score": 2, "away_score": 3},  # Scoring
            {"play_index": 4, "home_score": 5, "away_score": 3},  # Scoring
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        assert len(result) <= 2

    def test_scoring_plays_preferred_over_notable(self):
        """Scoring plays are preferred over notable plays."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 0, "away_score": 0, "play_type": "block"},
            {"play_index": 2, "home_score": 2, "away_score": 0, "play_type": "other"},
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        # Scoring play (2) should be included
        assert 2 in result

    def test_moment_starting_mid_game(self):
        """Moment starting mid-game uses previous event for scoring detection."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        all_events = [
            {"play_index": 1, "home_score": 10, "away_score": 8},
            {"play_index": 2, "home_score": 12, "away_score": 8},  # Scoring play
            {"play_index": 3, "home_score": 12, "away_score": 8},
        ]
        # Moment starts at index 1
        moment_plays = all_events[1:]
        result = select_explicitly_narrated_plays(moment_plays, all_events, 1)
        assert 2 in result

    def test_single_play_moment(self):
        """Single play moment always selects that play."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 5, "home_score": 0, "away_score": 0, "play_type": "other"},
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        assert result == [5]

    def test_multiple_notable_plays_capped(self):
        """Multiple notable plays capped at max."""
        from app.services.pipeline.stages.explicit_selection import (
            select_explicitly_narrated_plays,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 0, "away_score": 0, "play_type": "block"},
            {"play_index": 2, "home_score": 0, "away_score": 0, "play_type": "steal"},
            {"play_index": 3, "home_score": 0, "away_score": 0, "play_type": "block"},
        ]
        all_events = moment_plays
        result = select_explicitly_narrated_plays(moment_plays, all_events, 0)
        assert len(result) <= 2


class TestCountExplicitPlaysIfAdded:
    """Tests for count_explicit_plays_if_added function."""

    def test_adding_scoring_play(self):
        """Adding a scoring play increases explicit count."""
        from app.services.pipeline.stages.explicit_selection import (
            count_explicit_plays_if_added,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 0, "away_score": 0, "play_type": "other"},
        ]
        new_play = {"play_index": 2, "home_score": 2, "away_score": 0}
        all_events = moment_plays + [new_play]

        count = count_explicit_plays_if_added(moment_plays, new_play, all_events, 0)
        assert count >= 1

    def test_adding_non_notable_play(self):
        """Adding non-notable, non-scoring play may not increase count."""
        from app.services.pipeline.stages.explicit_selection import (
            count_explicit_plays_if_added,
        )

        moment_plays = [
            {"play_index": 1, "home_score": 2, "away_score": 0, "play_type": "other"},
        ]
        new_play = {"play_index": 2, "home_score": 2, "away_score": 0, "play_type": "other"}
        all_events = moment_plays + [new_play]

        count = count_explicit_plays_if_added(moment_plays, new_play, all_events, 0)
        # Should be at least 1 (fallback to last play)
        assert count >= 1

    def test_empty_moment_adding_play(self):
        """Adding first play to empty moment."""
        from app.services.pipeline.stages.explicit_selection import (
            count_explicit_plays_if_added,
        )

        moment_plays: list[dict] = []
        new_play = {"play_index": 1, "home_score": 0, "away_score": 0, "play_type": "other"}
        all_events = [new_play]

        count = count_explicit_plays_if_added(moment_plays, new_play, all_events, 0)
        assert count == 1
