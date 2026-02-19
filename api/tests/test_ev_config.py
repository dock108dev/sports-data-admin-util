"""Tests for EV strategy configuration module."""

import pytest

from app.services.ev_config import (
    EXCLUDED_BOOKS,
    INCLUDED_BOOKS,
    MAINLINE_DISAGREEMENT_MAX_POINTS,
    MAX_EXTRAPOLATED_PROB_DIVERGENCE,
    MAX_EXTRAPOLATION_HALF_POINTS,
    SHARP_REF_MAX_AGE_SECONDS,
    ConfidenceTier,
    EligibilityResult,
    EVStrategyConfig,
    get_strategy,
    get_fairbet_debug_game_ids,
)


class TestBookLists:
    """Tests for EXCLUDED_BOOKS and INCLUDED_BOOKS."""

    def test_excluded_books_is_frozenset(self) -> None:
        assert isinstance(EXCLUDED_BOOKS, frozenset)

    def test_included_books_is_frozenset(self) -> None:
        assert isinstance(INCLUDED_BOOKS, frozenset)

    def test_excluded_books_not_empty(self) -> None:
        assert len(EXCLUDED_BOOKS) > 0

    def test_included_books_not_empty(self) -> None:
        assert len(INCLUDED_BOOKS) > 0

    def test_pinnacle_in_included(self) -> None:
        assert "Pinnacle" in INCLUDED_BOOKS

    def test_pinnacle_not_in_excluded(self) -> None:
        assert "Pinnacle" not in EXCLUDED_BOOKS

    def test_excluded_and_included_do_not_overlap(self) -> None:
        overlap = EXCLUDED_BOOKS & INCLUDED_BOOKS
        assert len(overlap) == 0, f"Books cannot be both excluded and included: {overlap}"


class TestConfidenceTier:
    """Tests for ConfidenceTier enum."""

    def test_high_value(self) -> None:
        assert ConfidenceTier.HIGH.value == "high"

    def test_medium_value(self) -> None:
        assert ConfidenceTier.MEDIUM.value == "medium"

    def test_low_value(self) -> None:
        assert ConfidenceTier.LOW.value == "low"


class TestEVStrategyConfig:
    """Tests for EVStrategyConfig frozen dataclass."""

    def test_create_config(self) -> None:
        config = EVStrategyConfig(
            strategy_name="test",
            eligible_sharp_books=("Pinnacle",),
            min_qualifying_books=3,
            max_reference_staleness_seconds=3600,
            confidence_tier=ConfidenceTier.HIGH,
            allow_longshots=False,
            max_fair_odds_divergence=150,
        )
        assert config.strategy_name == "test"
        assert config.min_qualifying_books == 3

    def test_config_is_frozen(self) -> None:
        config = EVStrategyConfig(
            strategy_name="test",
            eligible_sharp_books=("Pinnacle",),
            min_qualifying_books=3,
            max_reference_staleness_seconds=3600,
            confidence_tier=ConfidenceTier.HIGH,
            allow_longshots=False,
            max_fair_odds_divergence=150,
        )
        with pytest.raises(AttributeError):
            config.strategy_name = "modified"  # type: ignore[misc]


class TestEligibilityResult:
    """Tests for EligibilityResult frozen dataclass."""

    def test_eligible_result(self) -> None:
        result = EligibilityResult(
            eligible=True,
            strategy_config=None,
            disabled_reason=None,
            ev_method="pinnacle_devig",
            confidence_tier="high",
        )
        assert result.eligible is True
        assert result.disabled_reason is None

    def test_disabled_result(self) -> None:
        result = EligibilityResult(
            eligible=False,
            strategy_config=None,
            disabled_reason="no_strategy",
            ev_method=None,
            confidence_tier=None,
        )
        assert result.eligible is False
        assert result.disabled_reason == "no_strategy"


class TestGetStrategy:
    """Tests for get_strategy() lookup."""

    def test_nba_mainline_returns_high(self) -> None:
        config = get_strategy("NBA", "mainline")
        assert config is not None
        assert config.confidence_tier == ConfidenceTier.HIGH
        assert config.max_reference_staleness_seconds == 3600

    def test_nhl_mainline_returns_high(self) -> None:
        config = get_strategy("NHL", "mainline")
        assert config is not None
        assert config.confidence_tier == ConfidenceTier.HIGH
        assert config.max_reference_staleness_seconds == 3600

    def test_ncaab_mainline_returns_medium(self) -> None:
        config = get_strategy("NCAAB", "mainline")
        assert config is not None
        assert config.confidence_tier == ConfidenceTier.MEDIUM
        assert config.max_reference_staleness_seconds == 1800

    def test_player_prop_returns_low(self) -> None:
        for league in ("NBA", "NHL", "NCAAB"):
            config = get_strategy(league, "player_prop")
            assert config is not None
            assert config.confidence_tier == ConfidenceTier.LOW

    def test_team_prop_returns_medium(self) -> None:
        for league in ("NBA", "NHL", "NCAAB"):
            config = get_strategy(league, "team_prop")
            assert config is not None
            assert config.confidence_tier == ConfidenceTier.MEDIUM

    def test_alternate_returns_low(self) -> None:
        for league in ("NBA", "NHL", "NCAAB"):
            config = get_strategy(league, "alternate")
            assert config is not None
            assert config.confidence_tier == ConfidenceTier.LOW

    def test_period_returns_none(self) -> None:
        for league in ("NBA", "NHL", "NCAAB"):
            assert get_strategy(league, "period") is None

    def test_game_prop_returns_none(self) -> None:
        for league in ("NBA", "NHL", "NCAAB"):
            assert get_strategy(league, "game_prop") is None

    def test_unknown_league_returns_none(self) -> None:
        assert get_strategy("NFL", "mainline") is None

    def test_unknown_category_returns_none(self) -> None:
        assert get_strategy("NBA", "unknown_market") is None

    def test_case_insensitive_league(self) -> None:
        config = get_strategy("nba", "mainline")
        assert config is not None

    def test_all_strategies_have_pinnacle(self) -> None:
        """Every non-None strategy uses Pinnacle as eligible sharp book."""
        for league in ("NBA", "NHL", "NCAAB"):
            for cat in ("mainline", "player_prop", "team_prop", "alternate"):
                config = get_strategy(league, cat)
                assert config is not None
                assert "Pinnacle" in config.eligible_sharp_books

    def test_all_strategies_have_min_books_3(self) -> None:
        """All strategies start with min_qualifying_books = 3."""
        for league in ("NBA", "NHL", "NCAAB"):
            for cat in ("mainline", "player_prop", "team_prop", "alternate"):
                config = get_strategy(league, cat)
                assert config is not None
                assert config.min_qualifying_books == 3

    def test_all_strategy_names_are_pinnacle_devig(self) -> None:
        for league in ("NBA", "NHL", "NCAAB"):
            for cat in ("mainline", "player_prop", "team_prop", "alternate"):
                config = get_strategy(league, cat)
                assert config is not None
                assert config.strategy_name == "pinnacle_devig"


class TestExtrapolationConfig:
    """Tests for extrapolation constants."""

    def test_nba_half_point_limits(self) -> None:
        assert MAX_EXTRAPOLATION_HALF_POINTS["NBA"]["spreads"] == 6
        assert MAX_EXTRAPOLATION_HALF_POINTS["NBA"]["totals"] == 6
        assert MAX_EXTRAPOLATION_HALF_POINTS["NBA"]["team_totals"] == 4

    def test_ncaab_half_point_limits(self) -> None:
        assert MAX_EXTRAPOLATION_HALF_POINTS["NCAAB"]["spreads"] == 6
        assert MAX_EXTRAPOLATION_HALF_POINTS["NCAAB"]["totals"] == 6
        assert MAX_EXTRAPOLATION_HALF_POINTS["NCAAB"]["team_totals"] == 4

    def test_nhl_half_point_limits(self) -> None:
        assert MAX_EXTRAPOLATION_HALF_POINTS["NHL"]["spreads"] == 4
        assert MAX_EXTRAPOLATION_HALF_POINTS["NHL"]["totals"] == 4
        assert MAX_EXTRAPOLATION_HALF_POINTS["NHL"]["team_totals"] == 4

    def test_max_extrapolated_prob_divergence(self) -> None:
        assert MAX_EXTRAPOLATED_PROB_DIVERGENCE == 0.10

    def test_mainline_disagreement_max_points(self) -> None:
        assert MAINLINE_DISAGREEMENT_MAX_POINTS == 2.0

    def test_sharp_ref_max_age_seconds(self) -> None:
        assert SHARP_REF_MAX_AGE_SECONDS == 3600

    def test_get_fairbet_debug_game_ids_empty(self) -> None:
        import os
        os.environ.pop("FAIRBET_DEBUG_GAME_IDS", None)
        assert get_fairbet_debug_game_ids() == frozenset()

    def test_get_fairbet_debug_game_ids_set(self) -> None:
        import os
        os.environ["FAIRBET_DEBUG_GAME_IDS"] = "123,456"
        try:
            assert get_fairbet_debug_game_ids() == frozenset({123, 456})
        finally:
            os.environ.pop("FAIRBET_DEBUG_GAME_IDS", None)
