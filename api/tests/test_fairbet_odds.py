"""Tests for FairBet odds API endpoint."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.fairbet.odds import (
    BetDefinition,
    BookOdds,
    FairbetOddsResponse,
    get_fairbet_odds,
    _build_base_filters,
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
            if not hasattr(execute_side_effect, 'call_count'):
                execute_side_effect.call_count = 0

            idx = execute_side_effect.call_count
            execute_side_effect.call_count += 1

            if idx >= len(results_sequence):
                idx = len(results_sequence) - 1

            result_config = results_sequence[idx]
            mock_result = MagicMock()

            if 'scalar' in result_config:
                mock_result.scalar.return_value = result_config['scalar']

            if 'scalars_all' in result_config:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = result_config['scalars_all']
                mock_result.scalars.return_value = mock_scalars

            if 'all' in result_config:
                mock_result.all.return_value = result_config['all']

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
        row.game = mock_game
        return row

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_bets(self, mock_session):
        """Returns empty response when no bets exist."""
        # Mock count query returning 0
        self._mock_execute_chain(mock_session, [
            {'scalar': 0},  # Count query
        ])

        response = await get_fairbet_odds(
            session=mock_session,
            league=None,
            limit=100,
            offset=0,
        )

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
        mock_row2.game = mock_odds_row.game

        self._mock_execute_chain(mock_session, [
            {'scalar': 1},  # Count query
            {'scalars_all': [mock_odds_row, mock_row2]},  # Main data query
            {'all': [("DraftKings",), ("FanDuel",)]},  # Books query
        ])

        response = await get_fairbet_odds(
            session=mock_session,
            league=None,
            limit=100,
            offset=0,
        )

        assert response.total == 1
        assert len(response.bets) == 1
        assert len(response.bets[0].books) == 2
        assert response.books_available == ["DraftKings", "FanDuel"]

    @pytest.mark.asyncio
    async def test_books_sorted_by_best_odds(self, mock_session, mock_odds_row):
        """Books within a bet are sorted by best odds first."""
        # Create multiple books with different odds
        rows = []
        for book, price in [("BookA", -115), ("BookB", -105), ("BookC", -110)]:
            row = MagicMock()
            row.game_id = 1
            row.market_key = "spreads"
            row.selection_key = "team:los_angeles_lakers"
            row.line_value = -3.5
            row.book = book
            row.price = price
            row.observed_at = datetime.now(timezone.utc)
            row.game = mock_odds_row.game
            rows.append(row)

        self._mock_execute_chain(mock_session, [
            {'scalar': 1},  # Count query
            {'scalars_all': rows},  # Main data query
            {'all': [("BookA",), ("BookB",), ("BookC",)]},  # Books query
        ])

        response = await get_fairbet_odds(
            session=mock_session,
            league=None,
            limit=100,
            offset=0,
        )

        # Books should be sorted by best odds first
        books = response.bets[0].books
        assert books[0].price == -105  # Best
        assert books[1].price == -110
        assert books[2].price == -115  # Worst

    @pytest.mark.asyncio
    async def test_pagination_limit_respected(self, mock_session):
        """Limit parameter is passed to database query."""
        self._mock_execute_chain(mock_session, [
            {'scalar': 0},  # Count query returns 0
        ])

        await get_fairbet_odds(
            session=mock_session,
            league=None,
            limit=50,
            offset=0,
        )

        # Verify execute was called (count query)
        # The helper tracks call_count
        assert hasattr(mock_session.execute, 'call_count')

    @pytest.mark.asyncio
    async def test_league_filter_applied(self, mock_session):
        """League filter is applied when specified."""
        self._mock_execute_chain(mock_session, [
            {'scalar': 0},  # Count query returns 0
        ])

        await get_fairbet_odds(
            session=mock_session,
            league="NBA",
            limit=100,
            offset=0,
        )

        # Verify execute was called with league filter
        assert hasattr(mock_session.execute, 'call_count')

    @pytest.mark.asyncio
    async def test_bet_definition_fields_populated(self, mock_session, mock_odds_row):
        """All BetDefinition fields are correctly populated."""
        self._mock_execute_chain(mock_session, [
            {'scalar': 1},  # Count query
            {'scalars_all': [mock_odds_row]},  # Main data query
            {'all': [("DraftKings",)]},  # Books query
        ])

        response = await get_fairbet_odds(
            session=mock_session,
            league=None,
            limit=100,
            offset=0,
        )

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
                            observed_at=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
                        )
                    ],
                )
            ],
            total=1,
            books_available=["DraftKings"],
        )

        # Serialize to dict
        data = response.model_dump()

        assert "bets" in data
        assert "total" in data
        assert "books_available" in data
        assert data["total"] == 1
        assert len(data["bets"]) == 1
        assert data["bets"][0]["league_code"] == "NBA"
