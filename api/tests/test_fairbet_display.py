"""Tests for fairbet_display service functions."""

from __future__ import annotations

from app.services.fairbet_display import (
    book_abbreviation,
    confidence_display_label,
    ev_method_display_name,
    ev_method_explanation,
    fair_american_odds,
    market_display_name,
    selection_display,
)


class TestFairAmericanOdds:
    def test_even_money(self) -> None:
        # 50% probability -> -100
        result = fair_american_odds(0.5)
        assert result == -100

    def test_underdog(self) -> None:
        # ~33% probability -> +200
        result = fair_american_odds(1 / 3)
        assert result == 200

    def test_favorite(self) -> None:
        # ~67% probability -> -200
        result = fair_american_odds(2 / 3)
        assert result == -200

    def test_none_input(self) -> None:
        assert fair_american_odds(None) is None

    def test_degenerate_input(self) -> None:
        # prob <= 0 or >= 1 returns None (implied_to_american returns 0.0)
        assert fair_american_odds(0.0) is None
        assert fair_american_odds(1.0) is None


class TestMarketDisplayName:
    def test_known_keys(self) -> None:
        assert market_display_name("spreads") == "Spread"
        assert market_display_name("totals") == "Total"
        assert market_display_name("h2h") == "Moneyline"
        assert market_display_name("player_points") == "Player Points"
        assert market_display_name("team_totals") == "Team Total"

    def test_unknown_key_fallback(self) -> None:
        assert market_display_name("some_new_market") == "Some New Market"


class TestBookAbbreviation:
    def test_known_books(self) -> None:
        assert book_abbreviation("DraftKings") == "DK"
        assert book_abbreviation("FanDuel") == "FD"
        assert book_abbreviation("Pinnacle") == "PIN"
        assert book_abbreviation("BetMGM") == "MGM"

    def test_unknown_book_fallback(self) -> None:
        assert book_abbreviation("SomeNewBook") == "SOM"


class TestConfidenceDisplayLabel:
    def test_known_tiers(self) -> None:
        assert confidence_display_label("full") == "Sharp"
        assert confidence_display_label("decent") == "Market"
        assert confidence_display_label("thin") == "Thin"

    def test_none_input(self) -> None:
        assert confidence_display_label(None) is None

    def test_unknown_tier_fallback(self) -> None:
        assert confidence_display_label("unknown_tier") == "Unknown_Tier"


class TestSelectionDisplay:
    def test_team_spread(self) -> None:
        result = selection_display(
            "team:bos:home", "spreads",
            home_team="Boston Celtics", line_value=-3.5,
        )
        assert result == "Boston Celtics -3.5"

    def test_game_total(self) -> None:
        result = selection_display("total:over", "totals", line_value=215.5)
        assert result == "Over 215.5"

    def test_player_prop(self) -> None:
        result = selection_display(
            "player:lebron_james:over", "player_points",
            player_name="LeBron James", line_value=25.5,
        )
        assert result == "LeBron James Over 25.5"

    def test_moneyline(self) -> None:
        result = selection_display(
            "team:bos:home", "h2h",
            home_team="Boston Celtics",
        )
        assert result == "Boston Celtics ML"

    def test_team_total(self) -> None:
        result = selection_display(
            "total:bos:over", "team_totals",
            line_value=110.5,
        )
        assert result == "Bos Over 110.5"

    def test_empty_selection_key(self) -> None:
        result = selection_display("", "spreads")
        assert result == "Spread"

    def test_player_prop_no_name_fallback(self) -> None:
        result = selection_display(
            "player:lebron_james:over", "player_points",
            line_value=25.5,
        )
        assert result == "Lebron James Over 25.5"


class TestEvMethodDisplay:
    def test_known_method(self) -> None:
        assert ev_method_display_name("pinnacle_devig") == "Pinnacle Devig"
        assert ev_method_display_name("pinnacle_extrapolated") == "Pinnacle Extrapolated"

    def test_unknown_method_fallback(self) -> None:
        assert ev_method_display_name("some_method") == "Some Method"

    def test_none_input(self) -> None:
        assert ev_method_display_name(None) is None

    def test_explanation(self) -> None:
        result = ev_method_explanation("pinnacle_devig")
        assert result is not None
        assert "Pinnacle" in result

    def test_explanation_unknown(self) -> None:
        assert ev_method_explanation("unknown") is None

    def test_explanation_none(self) -> None:
        assert ev_method_explanation(None) is None
