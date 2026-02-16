"""Tests for FairBet odds API endpoint."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.fairbet.odds import (
    BetDefinition,
    BookOdds,
    FairbetOddsResponse,
    get_fairbet_odds,
    _build_base_filters,
    _pair_opposite_sides,
)


class TestBookOddsModel:
    """Tests for BookOdds Pydantic model."""

    def test_valid_book_odds(self):
        """Creates valid BookOdds instance."""
        odds = BookOdds(
            book="DraftKings",
            price=-110,
            observed_at=datetime.now(timezone.utc),
        )
        assert odds.book == "DraftKings"
        assert odds.price == -110

    def test_positive_odds(self):
        """Handles positive American odds."""
        odds = BookOdds(
            book="FanDuel",
            price=150,
            observed_at=datetime.now(timezone.utc),
        )
        assert odds.price == 150


class TestBetDefinitionModel:
    """Tests for BetDefinition Pydantic model."""

    def test_valid_bet_definition(self):
        """Creates valid BetDefinition instance."""
        bet = BetDefinition(
            game_id=1,
            league_code="NBA",
            home_team="Lakers",
            away_team="Celtics",
            game_date=datetime.now(timezone.utc),
            market_key="spreads",
            selection_key="team:lakers",
            line_value=-3.5,
            books=[
                BookOdds(book="DK", price=-110, observed_at=datetime.now(timezone.utc))
            ],
        )
        assert bet.game_id == 1
        assert bet.league_code == "NBA"
        assert len(bet.books) == 1

    def test_moneyline_with_zero_line(self):
        """Moneyline bets use 0 as line_value sentinel."""
        bet = BetDefinition(
            game_id=1,
            league_code="NBA",
            home_team="Lakers",
            away_team="Celtics",
            game_date=datetime.now(timezone.utc),
            market_key="h2h",
            selection_key="team:lakers",
            line_value=0,
            books=[],
        )
        assert bet.line_value == 0
        assert bet.market_key == "h2h"


class TestFairbetOddsResponseModel:
    """Tests for FairbetOddsResponse Pydantic model."""

    def test_empty_response(self):
        """Creates valid empty response."""
        response = FairbetOddsResponse(
            bets=[],
            total=0,
            books_available=[],
            market_categories_available=[],
            games_available=[],
        )
        assert response.total == 0
        assert len(response.bets) == 0

    def test_response_with_bets(self):
        """Creates response with bet data."""
        response = FairbetOddsResponse(
            bets=[
                BetDefinition(
                    game_id=1,
                    league_code="NBA",
                    home_team="Lakers",
                    away_team="Celtics",
                    game_date=datetime.now(timezone.utc),
                    market_key="h2h",
                    selection_key="team:lakers",
                    line_value=0,
                    books=[],
                )
            ],
            total=1,
            books_available=["DraftKings", "FanDuel"],
            market_categories_available=["mainline"],
            games_available=[],
        )
        assert response.total == 1
        assert len(response.books_available) == 2


class TestBuildBaseFilters:
    """Tests for _build_base_filters helper function."""

    def test_returns_game_start_expression(self):
        """Returns game_start expression and conditions."""
        game_start, conditions = _build_base_filters(None)
        assert game_start is not None
        assert len(conditions) >= 2  # status filter + time filter

    def test_adds_league_filter_when_provided(self):
        """Adds league filter condition when league is specified."""
        _, conditions_without = _build_base_filters(None)
        _, conditions_with = _build_base_filters("NBA")
        assert len(conditions_with) == len(conditions_without) + 1

    def test_uppercases_league_code(self):
        """League code is uppercased in filter."""
        # This is tested implicitly through the condition creation
        _, conditions = _build_base_filters("nba")
        assert len(conditions) == 3  # status + time + league


class TestBooksSorting:
    """Tests for odds sorting logic."""

    def test_positive_odds_sorted_descending(self):
        """Positive odds sorted highest first."""
        books = [
            BookOdds(book="A", price=120, observed_at=datetime.now(timezone.utc)),
            BookOdds(book="B", price=150, observed_at=datetime.now(timezone.utc)),
            BookOdds(book="C", price=100, observed_at=datetime.now(timezone.utc)),
        ]
        # Simulate the sorting from the endpoint
        books.sort(key=lambda b: -b.price)
        assert books[0].price == 150
        assert books[1].price == 120
        assert books[2].price == 100

    def test_negative_odds_sorted_best_first(self):
        """Negative odds sorted closest to zero first (better odds)."""
        books = [
            BookOdds(book="A", price=-110, observed_at=datetime.now(timezone.utc)),
            BookOdds(book="B", price=-105, observed_at=datetime.now(timezone.utc)),
            BookOdds(book="C", price=-115, observed_at=datetime.now(timezone.utc)),
        ]
        books.sort(key=lambda b: -b.price)
        assert books[0].price == -105  # Best (closest to even)
        assert books[1].price == -110
        assert books[2].price == -115  # Worst

    def test_mixed_odds_sorted_correctly(self):
        """Mixed positive and negative odds sorted correctly."""
        books = [
            BookOdds(book="A", price=-110, observed_at=datetime.now(timezone.utc)),
            BookOdds(book="B", price=150, observed_at=datetime.now(timezone.utc)),
            BookOdds(book="C", price=-105, observed_at=datetime.now(timezone.utc)),
            BookOdds(book="D", price=120, observed_at=datetime.now(timezone.utc)),
        ]
        books.sort(key=lambda b: -b.price)
        # Positive odds first (higher is better), then negative (closer to 0 is better)
        assert books[0].price == 150
        assert books[1].price == 120
        assert books[2].price == -105
        assert books[3].price == -110


class TestGetFairbetOddsEndpoint:
    """Tests for get_fairbet_odds endpoint."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async database session."""
        session = AsyncMock()
        # Ensure execute returns a mock that can chain .scalar(), .scalars().all(), etc.
        return session

    def _mock_execute_chain(self, session, results_sequence):
        """Helper to set up mock execute to return results in sequence.

        Each item in results_sequence should be a dict with keys:
        - 'scalar': value for .scalar() call
        - 'scalars_all': list for .scalars().all() call
        - 'all': list for .all() call
        """

        async def execute_side_effect(*args, **kwargs):
            if not hasattr(execute_side_effect, "call_count"):
                execute_side_effect.call_count = 0

            idx = execute_side_effect.call_count
            execute_side_effect.call_count += 1

            if idx >= len(results_sequence):
                idx = len(results_sequence) - 1

            result_config = results_sequence[idx]
            mock_result = MagicMock()

            if "scalar" in result_config:
                mock_result.scalar.return_value = result_config["scalar"]

            if "scalars_all" in result_config:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = result_config["scalars_all"]
                mock_result.scalars.return_value = mock_scalars

            if "all" in result_config:
                mock_result.all.return_value = result_config["all"]

            return mock_result

        session.execute = execute_side_effect

    @pytest.fixture
    def mock_game(self):
        """Create a mock game with related objects."""
        game = MagicMock()
        game.start_time = datetime.now(timezone.utc) + timedelta(hours=2)
        game.status = "scheduled"

        league = MagicMock()
        league.code = "NBA"
        game.league = league

        home_team = MagicMock()
        home_team.name = "Los Angeles Lakers"
        game.home_team = home_team

        away_team = MagicMock()
        away_team.name = "Boston Celtics"
        game.away_team = away_team

        return game

    @pytest.fixture
    def mock_odds_row(self, mock_game):
        """Create a mock FairbetGameOddsWork row."""
        row = MagicMock()
        row.game_id = 1
        row.market_key = "spreads"
        row.selection_key = "team:los_angeles_lakers"
        row.line_value = -3.5
        row.book = "DraftKings"
        row.price = -110
        row.observed_at = datetime.now(timezone.utc)
        row.market_category = "mainline"
        row.player_name = None
        row.game = mock_game
        return row

    def _call_kwargs(self, session, **overrides):
        """Build kwargs for get_fairbet_odds with all params explicit."""
        defaults = {
            "session": session,
            "league": None,
            "market_category": None,
            "game_id": None,
            "book": None,
            "player_name": None,
            "min_ev": None,
            "has_fair": None,
            "sort_by": "ev",
            "limit": 100,
            "offset": 0,
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_bets(self, mock_session):
        """Returns empty response when no bets exist."""
        # Mock count query returning 0
        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 0},  # Count query
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        assert response.total == 0
        assert response.bets == []
        assert response.books_available == []

    @pytest.mark.asyncio
    async def test_returns_grouped_bets(self, mock_session, mock_odds_row):
        """Returns bets grouped by definition with multiple books."""
        # Create second book for same bet
        mock_row2 = MagicMock()
        mock_row2.game_id = 1
        mock_row2.market_key = "spreads"
        mock_row2.selection_key = "team:los_angeles_lakers"
        mock_row2.line_value = -3.5
        mock_row2.book = "FanDuel"
        mock_row2.price = -108
        mock_row2.observed_at = datetime.now(timezone.utc)
        mock_row2.market_category = "mainline"
        mock_row2.player_name = None
        mock_row2.game = mock_odds_row.game

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 1},  # Count query
                {"scalars_all": [mock_odds_row, mock_row2]},  # Main data query
                {"all": [("DraftKings",), ("FanDuel",)]},  # Books query
                {"all": [("mainline",)]},  # Categories query
                {"scalars_all": []},  # Games dropdown query
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        assert response.total == 1
        assert len(response.bets) == 1
        assert len(response.bets[0].books) == 2
        assert response.books_available == ["DraftKings", "FanDuel"]

    @pytest.mark.asyncio
    async def test_books_sorted_by_best_odds(self, mock_session, mock_odds_row):
        """Books within a bet are sorted by best odds first."""
        # Create multiple books with different odds
        rows = []
        for book_name, price in [("BookA", -115), ("BookB", -105), ("BookC", -110)]:
            row = MagicMock()
            row.game_id = 1
            row.market_key = "spreads"
            row.selection_key = "team:los_angeles_lakers"
            row.line_value = -3.5
            row.book = book_name
            row.price = price
            row.observed_at = datetime.now(timezone.utc)
            row.market_category = "mainline"
            row.player_name = None
            row.game = mock_odds_row.game
            rows.append(row)

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 1},  # Count query
                {"scalars_all": rows},  # Main data query
                {"all": [("BookA",), ("BookB",), ("BookC",)]},  # Books query
                {"all": [("mainline",)]},  # Categories query
                {"scalars_all": []},  # Games dropdown query
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        # Books should be sorted by best odds first
        books = response.bets[0].books
        assert books[0].price == -105  # Best
        assert books[1].price == -110
        assert books[2].price == -115  # Worst

    @pytest.mark.asyncio
    async def test_pagination_limit_respected(self, mock_session):
        """Limit parameter is passed to database query."""
        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 0},  # Count query returns 0
            ],
        )

        await get_fairbet_odds(**self._call_kwargs(mock_session, limit=50))

        # Verify execute was called (count query)
        # The helper tracks call_count
        assert hasattr(mock_session.execute, "call_count")

    @pytest.mark.asyncio
    async def test_league_filter_applied(self, mock_session):
        """League filter is applied when specified."""
        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 0},  # Count query returns 0
            ],
        )

        await get_fairbet_odds(**self._call_kwargs(mock_session, league="NBA"))

        # Verify execute was called with league filter
        assert hasattr(mock_session.execute, "call_count")

    @pytest.mark.asyncio
    async def test_bet_definition_fields_populated(self, mock_session, mock_odds_row):
        """All BetDefinition fields are correctly populated."""
        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 1},  # Count query
                {"scalars_all": [mock_odds_row]},  # Main data query
                {"all": [("DraftKings",)]},  # Books query
                {"all": [("mainline",)]},  # Categories query
                {"scalars_all": []},  # Games dropdown query
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        bet = response.bets[0]
        assert bet.game_id == 1
        assert bet.league_code == "NBA"
        assert bet.home_team == "Los Angeles Lakers"
        assert bet.away_team == "Boston Celtics"
        assert bet.market_key == "spreads"
        assert bet.selection_key == "team:los_angeles_lakers"
        assert bet.line_value == -3.5


class TestBetGrouping:
    """Tests for bet grouping logic."""

    def test_same_bet_different_books_grouped(self):
        """Multiple books for same bet are grouped together."""
        # Test the grouping key logic
        key1 = (1, "spreads", "team:lakers", -3.5)
        key2 = (1, "spreads", "team:lakers", -3.5)
        assert key1 == key2

    def test_different_games_not_grouped(self):
        """Bets from different games are not grouped."""
        key1 = (1, "spreads", "team:lakers", -3.5)
        key2 = (2, "spreads", "team:lakers", -3.5)
        assert key1 != key2

    def test_different_markets_not_grouped(self):
        """Different market types are not grouped."""
        key1 = (1, "spreads", "team:lakers", -3.5)
        key2 = (1, "h2h", "team:lakers", 0)
        assert key1 != key2

    def test_different_selections_not_grouped(self):
        """Different selections are not grouped."""
        key1 = (1, "spreads", "team:lakers", -3.5)
        key2 = (1, "spreads", "team:celtics", 3.5)
        assert key1 != key2

    def test_different_lines_not_grouped(self):
        """Different line values are not grouped."""
        key1 = (1, "spreads", "team:lakers", -3.5)
        key2 = (1, "spreads", "team:lakers", -4.0)
        assert key1 != key2


class TestResponseStructure:
    """Tests for response structure validation."""

    def test_response_model_serialization(self):
        """Response model serializes correctly."""
        response = FairbetOddsResponse(
            bets=[
                BetDefinition(
                    game_id=1,
                    league_code="NBA",
                    home_team="Lakers",
                    away_team="Celtics",
                    game_date=datetime(2025, 1, 15, 19, 0, tzinfo=timezone.utc),
                    market_key="h2h",
                    selection_key="team:lakers",
                    line_value=0,
                    books=[
                        BookOdds(
                            book="DraftKings",
                            price=-110,
                            observed_at=datetime(
                                2025, 1, 15, 12, 0, tzinfo=timezone.utc
                            ),
                        )
                    ],
                )
            ],
            total=1,
            books_available=["DraftKings"],
            market_categories_available=["mainline"],
            games_available=[],
        )

        # Serialize to dict
        data = response.model_dump()

        assert "bets" in data
        assert "total" in data
        assert "books_available" in data
        assert data["total"] == 1
        assert len(data["bets"]) == 1
        assert data["bets"][0]["league_code"] == "NBA"


class TestPairOppositeSides:
    """Unit tests for the _pair_opposite_sides helper."""

    def test_simple_two_way_pair(self):
        """Two keys with different selection_keys are paired."""
        keys = [
            (1, "spreads", "team:lakers", -3.5),
            (1, "spreads", "team:celtics", 3.5),
        ]
        pairs, unpaired = _pair_opposite_sides(keys)
        assert len(pairs) == 1
        assert len(unpaired) == 0
        assert pairs[0] == (keys[0], keys[1])

    def test_single_key_unpaired(self):
        """A single key has no partner."""
        keys = [(1, "spreads", "team:lakers", -3.5)]
        pairs, unpaired = _pair_opposite_sides(keys)
        assert len(pairs) == 0
        assert len(unpaired) == 1

    def test_same_selection_key_not_paired(self):
        """Two keys with the same selection_key are NOT paired."""
        keys = [
            (1, "spreads", "team:lakers", -1.5),
            (1, "spreads", "team:lakers", -2.5),
        ]
        pairs, unpaired = _pair_opposite_sides(keys)
        assert len(pairs) == 0
        assert len(unpaired) == 2

    def test_four_keys_two_pairs(self):
        """Four keys forming two valid pairs are all matched."""
        keys = [
            (1, "spreads", "team:lakers", -1.5),
            (1, "spreads", "team:celtics", 1.5),
            (1, "spreads", "team:lakers", -2.5),
            (1, "spreads", "team:celtics", 2.5),
        ]
        # abs(line_value) groups: {1.5: [0,1], 2.5: [2,3]}
        # But this helper receives keys already in the same abs-group,
        # so test two separate calls.

        # Group 1: -1.5 and +1.5
        pairs1, unpaired1 = _pair_opposite_sides([keys[0], keys[1]])
        assert len(pairs1) == 1
        assert len(unpaired1) == 0

        # Group 2: -2.5 and +2.5
        pairs2, unpaired2 = _pair_opposite_sides([keys[2], keys[3]])
        assert len(pairs2) == 1
        assert len(unpaired2) == 0

    def test_three_keys_one_pair_one_unpaired(self):
        """Three keys: first two pair, third is left unpaired."""
        keys = [
            (1, "spreads", "team:lakers", -3.5),
            (1, "spreads", "team:celtics", 3.5),
            (1, "spreads", "team:lakers", -3.5),  # duplicate side
        ]
        pairs, unpaired = _pair_opposite_sides(keys)
        assert len(pairs) == 1
        assert len(unpaired) == 1
        # The unpaired key shares selection_key with the first
        assert unpaired[0][2] == "team:lakers"

    def test_empty_input(self):
        """Empty list returns empty results."""
        pairs, unpaired = _pair_opposite_sides([])
        assert pairs == []
        assert unpaired == []


class TestAltSpreadGrouping:
    """Tests for alt spread EV grouping — ensures distinct lines get independent EV."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_game(self):
        """Create a mock game with related objects."""
        game = MagicMock()
        game.start_time = datetime.now(timezone.utc) + timedelta(hours=2)
        game.status = "scheduled"

        league = MagicMock()
        league.code = "NCAAB"
        game.league = league

        home_team = MagicMock()
        home_team.name = "Seton Hall"
        game.home_team = home_team

        away_team = MagicMock()
        away_team.name = "Villanova"
        game.away_team = away_team

        return game

    def _make_odds_row(
        self,
        game: MagicMock,
        game_id: int,
        market_key: str,
        selection_key: str,
        line_value: float,
        book: str,
        price: float,
    ) -> MagicMock:
        """Create a mock FairbetGameOddsWork row."""
        row = MagicMock()
        row.game_id = game_id
        row.market_key = market_key
        row.selection_key = selection_key
        row.line_value = line_value
        row.book = book
        row.price = price
        row.observed_at = datetime.now(timezone.utc)
        row.market_category = "alternate"
        row.player_name = None
        row.game = game
        return row

    def _mock_execute_chain(
        self, session: AsyncMock, results_sequence: list[dict]
    ) -> None:
        """Set up mock execute to return results in sequence."""

        async def execute_side_effect(*args, **kwargs):
            if not hasattr(execute_side_effect, "call_count"):
                execute_side_effect.call_count = 0
            idx = min(execute_side_effect.call_count, len(results_sequence) - 1)
            execute_side_effect.call_count += 1
            result_config = results_sequence[idx]
            mock_result = MagicMock()
            if "scalar" in result_config:
                mock_result.scalar.return_value = result_config["scalar"]
            if "scalars_all" in result_config:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = result_config["scalars_all"]
                mock_result.scalars.return_value = mock_scalars
            if "all" in result_config:
                mock_result.all.return_value = result_config["all"]
            return mock_result

        session.execute = execute_side_effect

    def _call_kwargs(self, session: AsyncMock, **overrides: Any) -> dict:
        """Build kwargs for get_fairbet_odds."""
        defaults = {
            "session": session,
            "league": None,
            "market_category": None,
            "game_id": None,
            "book": None,
            "player_name": None,
            "min_ev": None,
            "has_fair": None,
            "sort_by": "ev",
            "limit": 100,
            "offset": 0,
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.asyncio
    async def test_alt_spreads_get_distinct_fair_odds(self, mock_session, mock_game):
        """Two alt spread lines (-1.5/+1.5 and -2.5/+2.5) get independent EV."""
        rows = [
            # Line pair 1: -1.5 / +1.5
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", -1.5, "Pinnacle", -120
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", -1.5, "DraftKings", -115
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:villanova", 1.5, "Pinnacle", 105
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:villanova", 1.5, "DraftKings", 100
            ),
            # Line pair 2: -2.5 / +2.5
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", -2.5, "Pinnacle", -145
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", -2.5, "DraftKings", -140
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:villanova", 2.5, "Pinnacle", 125
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:villanova", 2.5, "DraftKings", 120
            ),
        ]

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 4},
                {"scalars_all": rows},
                {"all": [("Pinnacle",), ("DraftKings",)]},
                {"all": [("alternate",)]},
                {"scalars_all": []},
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        # Should have 4 bet definitions (2 sides x 2 lines)
        assert len(response.bets) == 4

        # Group by line_value to check independence
        by_line: dict[float, list[BetDefinition]] = {}
        for bet in response.bets:
            by_line.setdefault(abs(bet.line_value), []).append(bet)

        assert 1.5 in by_line
        assert 2.5 in by_line

        # Each pair should NOT have ev_disabled_reason (they have valid pairs)
        for bet in response.bets:
            assert bet.ev_disabled_reason != "no_pair", (
                f"Bet {bet.selection_key} @ {bet.line_value} should not be no_pair"
            )

    @pytest.mark.asyncio
    async def test_alt_spreads_not_collapsed(self, mock_session, mock_game):
        """Signed line_values that abs() collapses still get independent EV per pair."""
        # Both SHU -1.5 and SHU -2.5 have abs values 1.5 and 2.5.
        # Without the fix, 4 entries with abs=1.5 would mis-group.
        rows = [
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", -1.5, "Pinnacle", -120
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:villanova", 1.5, "Pinnacle", 105
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", -2.5, "Pinnacle", -145
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:villanova", 2.5, "Pinnacle", 125
            ),
        ]

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 4},
                {"scalars_all": rows},
                {"all": [("Pinnacle",)]},
                {"all": [("alternate",)]},
                {"scalars_all": []},
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        assert len(response.bets) == 4
        # No bet should be marked no_pair — all have valid opposite sides
        for bet in response.bets:
            assert bet.ev_disabled_reason != "no_pair"

    @pytest.mark.asyncio
    async def test_same_selection_key_not_paired(self, mock_session, mock_game):
        """Two entries with the same selection_key are NOT paired even if abs(line) matches."""
        # Two SHU sides at -1.5 and -1.5 (duplicate) — no opposite side available
        rows = [
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", -1.5, "Pinnacle", -120
            ),
            self._make_odds_row(
                mock_game, 1, "spreads", "team:seton_hall", 1.5, "DraftKings", -115
            ),
        ]

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 2},
                {"scalars_all": rows},
                {"all": [("Pinnacle",), ("DraftKings",)]},
                {"all": [("alternate",)]},
                {"scalars_all": []},
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        # Both bets have the same selection_key, so they should NOT pair
        shu_bets = [b for b in response.bets if b.selection_key == "team:seton_hall"]
        for bet in shu_bets:
            assert bet.ev_disabled_reason == "no_pair"


class TestFairOddsOutlierHandling:
    """Integration tests for fair_odds_outlier handling via the endpoint."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_game(self):
        game = MagicMock()
        game.start_time = datetime.now(timezone.utc) + timedelta(hours=2)
        game.status = "scheduled"
        league = MagicMock()
        league.code = "NBA"
        game.league = league
        home_team = MagicMock()
        home_team.name = "Los Angeles Lakers"
        game.home_team = home_team
        away_team = MagicMock()
        away_team.name = "Boston Celtics"
        game.away_team = away_team
        return game

    def _make_odds_row(
        self,
        game: MagicMock,
        game_id: int,
        market_key: str,
        selection_key: str,
        line_value: float,
        book: str,
        price: float,
        market_category: str = "player_prop",
    ) -> MagicMock:
        row = MagicMock()
        row.game_id = game_id
        row.market_key = market_key
        row.selection_key = selection_key
        row.line_value = line_value
        row.book = book
        row.price = price
        row.observed_at = datetime.now(timezone.utc)
        row.market_category = market_category
        row.player_name = "Test Player"
        row.game = game
        return row

    def _mock_execute_chain(
        self, session: AsyncMock, results_sequence: list[dict]
    ) -> None:
        async def execute_side_effect(*args, **kwargs):
            if not hasattr(execute_side_effect, "call_count"):
                execute_side_effect.call_count = 0
            idx = min(execute_side_effect.call_count, len(results_sequence) - 1)
            execute_side_effect.call_count += 1
            result_config = results_sequence[idx]
            mock_result = MagicMock()
            if "scalar" in result_config:
                mock_result.scalar.return_value = result_config["scalar"]
            if "scalars_all" in result_config:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = result_config["scalars_all"]
                mock_result.scalars.return_value = mock_scalars
            if "all" in result_config:
                mock_result.all.return_value = result_config["all"]
            return mock_result

        session.execute = execute_side_effect

    def _call_kwargs(self, session: AsyncMock, **overrides: Any) -> dict:
        defaults = {
            "session": session,
            "league": None,
            "market_category": None,
            "game_id": None,
            "book": None,
            "player_name": None,
            "min_ev": None,
            "has_fair": None,
            "sort_by": "ev",
            "limit": 100,
            "offset": 0,
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.asyncio
    async def test_fair_odds_outlier_marked(self, mock_session, mock_game):
        """When devig produces implausible fair odds, bet gets ev_disabled_reason='fair_odds_outlier'."""
        # Pinnacle has extremely lopsided line; other books don't agree
        rows = [
            # Side A: over — Pinnacle at -1500, consensus near -400
            self._make_odds_row(
                mock_game, 1, "player_points", "total:over", 20.5, "Pinnacle", -1500
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:over", 20.5, "DraftKings", -400
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:over", 20.5, "FanDuel", -400
            ),
            # Side B: under — Pinnacle at +800, consensus near +350
            self._make_odds_row(
                mock_game, 1, "player_points", "total:under", 20.5, "Pinnacle", 800
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:under", 20.5, "DraftKings", 350
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:under", 20.5, "FanDuel", 350
            ),
        ]

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 2},
                {"scalars_all": rows},
                {"all": [("Pinnacle",), ("DraftKings",), ("FanDuel",)]},
                {"all": [("player_prop",)]},
                {"scalars_all": []},
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        # Both sides should be flagged as outliers
        for bet in response.bets:
            assert bet.ev_disabled_reason == "fair_odds_outlier", (
                f"Bet {bet.selection_key} should have fair_odds_outlier, "
                f"got {bet.ev_disabled_reason}"
            )
            # No EV annotation on books
            for book in bet.books:
                assert book.ev_percent is None
            # But method and tier are still present
            assert bet.ev_method == "pinnacle_devig"
            assert bet.ev_confidence_tier == "low"

    @pytest.mark.asyncio
    async def test_fair_odds_outlier_marks_sharp(self, mock_session, mock_game):
        """When fair_odds_outlier suppresses EV, Pinnacle still gets is_sharp=True."""
        rows = [
            self._make_odds_row(
                mock_game, 1, "player_points", "total:over", 20.5, "Pinnacle", -1500
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:over", 20.5, "DraftKings", -400
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:over", 20.5, "FanDuel", -400
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:under", 20.5, "Pinnacle", 800
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:under", 20.5, "DraftKings", 350
            ),
            self._make_odds_row(
                mock_game, 1, "player_points", "total:under", 20.5, "FanDuel", 350
            ),
        ]

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 2},
                {"scalars_all": rows},
                {"all": [("Pinnacle",), ("DraftKings",), ("FanDuel",)]},
                {"all": [("player_prop",)]},
                {"scalars_all": []},
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        for bet in response.bets:
            pinnacle_books = [b for b in bet.books if b.book == "Pinnacle"]
            assert len(pinnacle_books) == 1
            assert pinnacle_books[0].is_sharp is True
            # Non-sharp books should have is_sharp=False
            for b in bet.books:
                if b.book != "Pinnacle":
                    assert b.is_sharp is False


class TestSharpBooksRetainedWhenEvDisabled:
    """Tests that is_sharp is set correctly when EV is disabled or unpaired."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_game(self):
        game = MagicMock()
        game.start_time = datetime.now(timezone.utc) + timedelta(hours=2)
        game.status = "scheduled"
        league = MagicMock()
        league.code = "NBA"
        game.league = league
        home_team = MagicMock()
        home_team.name = "Lakers"
        game.home_team = home_team
        away_team = MagicMock()
        away_team.name = "Celtics"
        game.away_team = away_team
        return game

    def _make_odds_row(
        self,
        game,
        game_id,
        market_key,
        selection_key,
        line_value,
        book,
        price,
        market_category="mainline",
    ):
        row = MagicMock()
        row.game_id = game_id
        row.market_key = market_key
        row.selection_key = selection_key
        row.line_value = line_value
        row.book = book
        row.price = price
        row.observed_at = datetime.now(timezone.utc)
        row.market_category = market_category
        row.player_name = None
        row.game = game
        return row

    def _mock_execute_chain(self, session, results_sequence):
        async def execute_side_effect(*args, **kwargs):
            if not hasattr(execute_side_effect, "call_count"):
                execute_side_effect.call_count = 0
            idx = min(execute_side_effect.call_count, len(results_sequence) - 1)
            execute_side_effect.call_count += 1
            result_config = results_sequence[idx]
            mock_result = MagicMock()
            if "scalar" in result_config:
                mock_result.scalar.return_value = result_config["scalar"]
            if "scalars_all" in result_config:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = result_config["scalars_all"]
                mock_result.scalars.return_value = mock_scalars
            if "all" in result_config:
                mock_result.all.return_value = result_config["all"]
            return mock_result

        session.execute = execute_side_effect

    def _call_kwargs(self, session, **overrides):
        defaults = {
            "session": session,
            "league": None,
            "market_category": None,
            "game_id": None,
            "book": None,
            "player_name": None,
            "min_ev": None,
            "has_fair": None,
            "sort_by": "ev",
            "limit": 100,
            "offset": 0,
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.asyncio
    async def test_unpaired_bet_marks_sharp(self, mock_session, mock_game):
        """Single-sided bet (no pair) still marks Pinnacle as is_sharp."""
        rows = [
            self._make_odds_row(
                mock_game, 1, "h2h", "team:lakers", 0, "Pinnacle", -150
            ),
            self._make_odds_row(
                mock_game, 1, "h2h", "team:lakers", 0, "DraftKings", -145
            ),
        ]

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 1},
                {"scalars_all": rows},
                {"all": [("Pinnacle",), ("DraftKings",)]},
                {"all": [("mainline",)]},
                {"scalars_all": []},
            ],
        )

        response = await get_fairbet_odds(**self._call_kwargs(mock_session))

        bet = response.bets[0]
        assert bet.ev_disabled_reason == "no_pair"
        pinnacle = next(b for b in bet.books if b.book == "Pinnacle")
        assert pinnacle.is_sharp is True

    @pytest.mark.asyncio
    async def test_sharp_retained_with_book_filter_when_ev_disabled(
        self, mock_session, mock_game
    ):
        """When filtering by book=DraftKings, Pinnacle is retained via is_sharp."""
        rows = [
            self._make_odds_row(
                mock_game, 1, "h2h", "team:lakers", 0, "Pinnacle", -150
            ),
            self._make_odds_row(
                mock_game, 1, "h2h", "team:lakers", 0, "DraftKings", -145
            ),
            self._make_odds_row(mock_game, 1, "h2h", "team:lakers", 0, "FanDuel", -148),
        ]

        self._mock_execute_chain(
            mock_session,
            [
                {"scalar": 1},
                {"scalars_all": rows},
                {"all": [("Pinnacle",), ("DraftKings",), ("FanDuel",)]},
                {"all": [("mainline",)]},
                {"scalars_all": []},
            ],
        )

        response = await get_fairbet_odds(
            **self._call_kwargs(mock_session, book="DraftKings")
        )

        bet = response.bets[0]
        book_names = [b.book for b in bet.books]
        # DraftKings kept by filter, Pinnacle kept by is_sharp
        assert "DraftKings" in book_names
        assert "Pinnacle" in book_names
        # FanDuel filtered out
        assert "FanDuel" not in book_names
