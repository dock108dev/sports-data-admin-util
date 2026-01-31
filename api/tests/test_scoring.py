"""Tests for game_metadata scoring module."""

from datetime import datetime


class TestNormalize:
    """Tests for _normalize function."""

    def test_mid_value(self):
        """Mid-range value normalizes to 0.5."""
        from app.game_metadata.scoring import _normalize

        result = _normalize(50.0, 0.0, 100.0)
        assert abs(result - 0.5) < 0.001

    def test_min_value(self):
        """Minimum value normalizes to 0."""
        from app.game_metadata.scoring import _normalize

        result = _normalize(0.0, 0.0, 100.0)
        assert result == 0.0

    def test_max_value(self):
        """Maximum value normalizes to 1."""
        from app.game_metadata.scoring import _normalize

        result = _normalize(100.0, 0.0, 100.0)
        assert result == 1.0

    def test_below_min_clamped(self):
        """Below minimum is clamped to 0."""
        from app.game_metadata.scoring import _normalize

        result = _normalize(-10.0, 0.0, 100.0)
        assert result == 0.0

    def test_above_max_clamped(self):
        """Above maximum is clamped to 1."""
        from app.game_metadata.scoring import _normalize

        result = _normalize(150.0, 0.0, 100.0)
        assert result == 1.0

    def test_invalid_range_raises(self):
        """Invalid range raises ValueError."""
        import pytest
        from app.game_metadata.scoring import _normalize

        with pytest.raises(ValueError):
            _normalize(50.0, 100.0, 0.0)  # max < min

        with pytest.raises(ValueError):
            _normalize(50.0, 100.0, 100.0)  # max == min


class TestNormalizeSeed:
    """Tests for _normalize_seed function."""

    def test_none_seed(self):
        """None seed returns 0."""
        from app.game_metadata.scoring import _normalize_seed

        assert _normalize_seed(None) == 0.0

    def test_top_seed(self):
        """Seed 1 returns highest score."""
        from app.game_metadata.scoring import _normalize_seed

        result = _normalize_seed(1)
        assert result == 1.0

    def test_worst_seed(self):
        """Seed 16 returns lowest score."""
        from app.game_metadata.scoring import _normalize_seed

        result = _normalize_seed(16)
        assert result == 0.0

    def test_mid_seed(self):
        """Mid seed returns intermediate value."""
        from app.game_metadata.scoring import _normalize_seed

        result = _normalize_seed(8)
        assert 0.4 < result < 0.7


class TestNormalizeConferenceRank:
    """Tests for _normalize_conference_rank function."""

    def test_first_place(self):
        """Rank 1 returns highest score."""
        from app.game_metadata.scoring import _normalize_conference_rank

        result = _normalize_conference_rank(1)
        assert result == 1.0

    def test_last_place(self):
        """Rank 16 returns lowest score."""
        from app.game_metadata.scoring import _normalize_conference_rank

        result = _normalize_conference_rank(16)
        assert result == 0.0


class TestNormalizeElo:
    """Tests for _normalize_elo function."""

    def test_mid_elo(self):
        """Mid-range Elo normalizes correctly."""
        from app.game_metadata.scoring import _normalize_elo, ELO_MIN, ELO_MAX

        mid_elo = (ELO_MIN + ELO_MAX) / 2
        result = _normalize_elo(mid_elo)
        assert abs(result - 0.5) < 0.001


class TestNormalizeEfficiency:
    """Tests for _normalize_efficiency function."""

    def test_mid_efficiency(self):
        """Mid-range efficiency normalizes correctly."""
        from app.game_metadata.scoring import (
            _normalize_efficiency,
            KENPOM_EFF_MIN,
            KENPOM_EFF_MAX,
        )

        mid_eff = (KENPOM_EFF_MIN + KENPOM_EFF_MAX) / 2
        result = _normalize_efficiency(mid_eff)
        assert abs(result - 0.5) < 0.001


class TestTeamStrength:
    """Tests for _team_strength function."""

    def test_with_efficiency(self):
        """Team strength uses both Elo and efficiency."""
        from app.game_metadata.scoring import _team_strength
        from app.game_metadata.models import TeamRatings

        rating = TeamRatings(
            team_id="1", conference="Big 10", elo=1600.0, kenpom_adj_eff=15.0
        )
        result = _team_strength(rating)
        assert 0.3 < result < 0.7

    def test_without_efficiency(self):
        """Team strength uses only Elo when no efficiency."""
        from app.game_metadata.scoring import _team_strength
        from app.game_metadata.models import TeamRatings

        rating = TeamRatings(
            team_id="1", conference="Big 10", elo=1600.0, kenpom_adj_eff=None
        )
        result = _team_strength(rating)
        assert 0.4 < result < 0.6


class TestCloseGameProbability:
    """Tests for _close_game_probability function."""

    def test_none_spread(self):
        """None spread returns 0."""
        from app.game_metadata.scoring import _close_game_probability

        assert _close_game_probability(None) == 0.0

    def test_zero_spread(self):
        """Zero spread returns max probability."""
        from app.game_metadata.scoring import _close_game_probability

        result = _close_game_probability(0.0)
        assert result == 1.0

    def test_large_spread(self):
        """Large spread returns low probability."""
        from app.game_metadata.scoring import _close_game_probability

        result = _close_game_probability(20.0)
        assert result == 0.0

    def test_negative_spread(self):
        """Negative spread uses absolute value."""
        from app.game_metadata.scoring import _close_game_probability

        result = _close_game_probability(-5.0)
        assert result == _close_game_probability(5.0)


class TestHighTotalScore:
    """Tests for _high_total_score function."""

    def test_none_total(self):
        """None total returns 0."""
        from app.game_metadata.scoring import _high_total_score

        assert _high_total_score(None) == 0.0

    def test_high_total(self):
        """High total returns high score."""
        from app.game_metadata.scoring import _high_total_score

        result = _high_total_score(180.0)
        assert result == 1.0

    def test_low_total(self):
        """Low total returns low score."""
        from app.game_metadata.scoring import _high_total_score

        result = _high_total_score(100.0)
        assert result == 0.0


class TestStorylineScore:
    """Tests for _storyline_score function."""

    def _make_context(self, **kwargs):
        """Create a GameContext with defaults."""
        from app.game_metadata.models import GameContext

        defaults = {
            "game_id": "123",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "league": "NBA",
            "start_time": datetime(2025, 1, 15, 19, 0, 0),
            "rivalry": False,
            "playoff_implications": False,
            "national_broadcast": False,
            "has_big_name_players": False,
            "coach_vs_former_team": False,
            "projected_spread": None,
            "projected_total": None,
        }
        defaults.update(kwargs)
        return GameContext(**defaults)

    def test_no_flags(self):
        """No storyline flags returns 0."""
        from app.game_metadata.scoring import _storyline_score

        context = self._make_context()
        result = _storyline_score(context)
        assert result == 0.0

    def test_all_flags(self):
        """All storyline flags returns max score."""
        from app.game_metadata.scoring import _storyline_score

        context = self._make_context(
            has_big_name_players=True,
            coach_vs_former_team=True,
            playoff_implications=True,
        )
        result = _storyline_score(context)
        assert result == 1.0


class TestBuzzScore:
    """Tests for _buzz_score function."""

    def _make_context(self, **kwargs):
        """Create a GameContext with defaults."""
        from app.game_metadata.models import GameContext

        defaults = {
            "game_id": "123",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "league": "NBA",
            "start_time": datetime(2025, 1, 15, 19, 0, 0),
            "rivalry": False,
            "playoff_implications": False,
            "national_broadcast": False,
            "has_big_name_players": False,
            "coach_vs_former_team": False,
            "projected_spread": None,
            "projected_total": None,
        }
        defaults.update(kwargs)
        return GameContext(**defaults)

    def test_no_buzz(self):
        """No buzz signals returns 0."""
        from app.game_metadata.scoring import _buzz_score

        context = self._make_context()
        result = _buzz_score(context)
        assert result == 0.0

    def test_national_broadcast(self):
        """National broadcast increases buzz."""
        from app.game_metadata.scoring import _buzz_score

        context = self._make_context(national_broadcast=True)
        result = _buzz_score(context)
        assert result > 0.4


class TestExcitementScore:
    """Tests for excitement_score function."""

    def _make_context(self, **kwargs):
        """Create a GameContext with defaults."""
        from app.game_metadata.models import GameContext

        defaults = {
            "game_id": "123",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "league": "NBA",
            "start_time": datetime(2025, 1, 15, 19, 0, 0),
            "rivalry": False,
            "playoff_implications": False,
            "national_broadcast": False,
            "has_big_name_players": False,
            "coach_vs_former_team": False,
            "projected_spread": None,
            "projected_total": None,
        }
        defaults.update(kwargs)
        return GameContext(**defaults)

    def test_boring_game(self):
        """Game with no flags has low excitement."""
        from app.game_metadata.scoring import excitement_score

        context = self._make_context()
        result = excitement_score(context)
        assert result < 10

    def test_exciting_game(self):
        """Game with flags has higher excitement."""
        from app.game_metadata.scoring import excitement_score

        context = self._make_context(
            rivalry=True,
            national_broadcast=True,
            projected_spread=2.0,
        )
        result = excitement_score(context)
        assert result > 40


class TestQualityScore:
    """Tests for quality_score function."""

    def test_basic_quality_score(self):
        """Quality score returns normalized value."""
        from app.game_metadata.scoring import quality_score
        from app.game_metadata.models import TeamRatings, StandingsEntry

        home_rating = TeamRatings(
            team_id="1", conference="Big 10", elo=1700.0, projected_seed=3
        )
        away_rating = TeamRatings(
            team_id="2", conference="Big 10", elo=1650.0, projected_seed=5
        )
        home_standing = StandingsEntry(
            team_id="1", conference_rank=1, wins=20, losses=5
        )
        away_standing = StandingsEntry(
            team_id="2", conference_rank=3, wins=18, losses=7
        )

        result = quality_score(home_rating, away_rating, home_standing, away_standing)
        assert 0 <= result <= 100


class TestScoreGameContext:
    """Tests for score_game_context function."""

    def _make_context(self, **kwargs):
        """Create a GameContext with defaults."""
        from app.game_metadata.models import GameContext

        defaults = {
            "game_id": "123",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "league": "NBA",
            "start_time": datetime(2025, 1, 15, 19, 0, 0),
            "rivalry": False,
            "playoff_implications": False,
            "national_broadcast": False,
            "has_big_name_players": False,
            "coach_vs_former_team": False,
            "projected_spread": None,
            "projected_total": None,
        }
        defaults.update(kwargs)
        return GameContext(**defaults)

    def test_returns_excitement_score(self):
        """score_game_context returns excitement score."""
        from app.game_metadata.scoring import score_game_context, excitement_score

        context = self._make_context(rivalry=True)
        result = score_game_context(context)
        expected = excitement_score(context)
        assert result == expected
