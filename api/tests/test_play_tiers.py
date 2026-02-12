"""Tests for app.services.play_tiers."""

from app.routers.sports.schemas import PlayEntry, TieredPlayGroup
from app.services.play_tiers import classify_all_tiers, group_tier3_plays


def _play(
    play_index: int,
    *,
    quarter: int = 1,
    game_clock: str | None = "10:00",
    play_type: str | None = None,
    home_score: int | None = None,
    away_score: int | None = None,
) -> PlayEntry:
    return PlayEntry(
        play_index=play_index,
        quarter=quarter,
        game_clock=game_clock,
        play_type=play_type,
        home_score=home_score,
        away_score=away_score,
    )


# ---------------------------------------------------------------------------
# classify_all_tiers
# ---------------------------------------------------------------------------


class TestClassifyAllTiers:
    def test_empty(self):
        assert classify_all_tiers([], "NBA") == []

    def test_scoring_in_final_period_is_tier1(self):
        plays = [
            _play(1, quarter=4, home_score=100, away_score=98),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers == [1]

    def test_non_scoring_foul_is_tier2_nba(self):
        plays = [
            _play(1, quarter=1, play_type="foul"),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers == [2]

    def test_non_scoring_foul_is_tier2_ncaab(self):
        plays = [
            _play(1, quarter=1, play_type="personal_foul"),
        ]
        tiers = classify_all_tiers(plays, "NCAAB")
        assert tiers == [2]

    def test_routine_play_is_tier3(self):
        plays = [
            _play(1, quarter=1, play_type="rebound"),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers == [3]

    def test_lead_change_is_tier1(self):
        plays = [
            _play(1, quarter=1, home_score=10, away_score=8),
            _play(2, quarter=1, home_score=10, away_score=11),  # away takes lead
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers[1] == 1

    def test_new_tie_is_tier1(self):
        plays = [
            _play(1, quarter=1, home_score=10, away_score=8),
            _play(2, quarter=1, home_score=10, away_score=10),  # tied
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers[1] == 1

    def test_clutch_time_scoring_is_tier1(self):
        # NBA: final period = 4, clutch = under 2 minutes
        plays = [
            _play(1, quarter=4, game_clock="1:30", home_score=0, away_score=2),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers == [1]

    def test_ncaab_final_period_threshold(self):
        # NCAAB: final period = 2 (halves)
        plays = [
            _play(1, quarter=2, home_score=50, away_score=48),
        ]
        tiers = classify_all_tiers(plays, "NCAAB")
        assert tiers == [1]

    def test_nhl_tier2_types(self):
        plays = [
            _play(1, quarter=1, play_type="penalty"),
            _play(2, quarter=1, play_type="hit"),
            _play(3, quarter=1, play_type="takeaway"),
        ]
        tiers = classify_all_tiers(plays, "NHL")
        assert tiers == [2, 2, 2]

    def test_mixed_tiers(self):
        plays = [
            _play(1, quarter=1, play_type="rebound"),                          # tier 3
            _play(2, quarter=1, play_type="foul"),                             # tier 2
            _play(3, quarter=4, home_score=100, away_score=98),                # tier 1 (scoring in final period)
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers == [3, 2, 1]

    def test_lead_change_away_to_home(self):
        # Away was leading, home takes lead (exercises prev_lead="AWAY" branch)
        plays = [
            _play(1, quarter=1, home_score=5, away_score=10),
            _play(2, quarter=1, home_score=12, away_score=10),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers[1] == 1

    def test_score_goes_to_tie_from_away_lead(self):
        plays = [
            _play(1, quarter=1, home_score=5, away_score=10),
            _play(2, quarter=1, home_score=10, away_score=10),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers[1] == 1

    def test_malformed_clock_treated_as_non_clutch(self):
        # Bad clock format should not crash, just not be treated as clutch
        plays = [
            _play(1, quarter=4, game_clock="bad", home_score=0, away_score=2),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        # Still tier 1 because it's scoring in the final period
        assert tiers == [1]

    def test_empty_clock_parsed_as_none(self):
        plays = [
            _play(1, quarter=4, game_clock="", home_score=0, away_score=2),
        ]
        tiers = classify_all_tiers(plays, "NBA")
        assert tiers == [1]


# ---------------------------------------------------------------------------
# group_tier3_plays
# ---------------------------------------------------------------------------


class TestGroupTier3Plays:
    def test_empty(self):
        assert group_tier3_plays([], []) == []

    def test_no_tier3_no_groups(self):
        plays = [_play(10), _play(20)]
        tiers = [1, 2]
        groups = group_tier3_plays(plays, tiers)
        assert groups == []

    def test_consecutive_tier3_grouped(self):
        plays = [_play(10, play_type="rebound"), _play(20, play_type="pass")]
        tiers = [3, 3]
        groups = group_tier3_plays(plays, tiers)
        assert len(groups) == 1
        assert groups[0].start_index == 10
        assert groups[0].end_index == 20
        assert groups[0].play_indices == [10, 20]

    def test_single_tier3_still_grouped(self):
        plays = [_play(5, play_type="rebound")]
        tiers = [3]
        groups = group_tier3_plays(plays, tiers)
        assert len(groups) == 1
        assert groups[0].play_indices == [5]

    def test_uses_play_index_not_list_position(self):
        plays = [
            _play(100, play_type="rebound"),
            _play(200, play_type="pass"),
            _play(300, play_type="dribble"),
        ]
        tiers = [3, 3, 3]
        groups = group_tier3_plays(plays, tiers)
        assert len(groups) == 1
        assert groups[0].start_index == 100
        assert groups[0].end_index == 300
        assert groups[0].play_indices == [100, 200, 300]

    def test_multiple_groups_split_by_non_tier3(self):
        plays = [
            _play(1, play_type="rebound"),
            _play(2, play_type="pass"),
            _play(3, play_type="foul"),       # tier 2 splits
            _play(4, play_type="rebound"),
            _play(5, play_type="pass"),
        ]
        tiers = [3, 3, 2, 3, 3]
        groups = group_tier3_plays(plays, tiers)
        assert len(groups) == 2
        assert groups[0].play_indices == [1, 2]
        assert groups[1].play_indices == [4, 5]

    def test_summary_label_contains_play_types(self):
        plays = [
            _play(1, play_type="rebound"),
            _play(2, play_type="pass"),
            _play(3, play_type="rebound"),
        ]
        tiers = [3, 3, 3]
        groups = group_tier3_plays(plays, tiers)
        assert "3 plays" in groups[0].summary_label
        assert "rebound" in groups[0].summary_label
        assert "pass" in groups[0].summary_label
