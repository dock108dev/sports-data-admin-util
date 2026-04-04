"""Tests for consensus lineup prediction in lineup_fetcher."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analytics.services.lineup_fetcher import fetch_consensus_lineup


def _make_lineup(*names):
    """Create a lineup list from player names (uses name as external_ref)."""
    return [{"external_ref": n, "name": n} for n in names]


# The reconstruct function is imported inside fetch_consensus_lineup,
# so we patch it at its definition site.
_RECONSTRUCT_PATH = (
    "app.analytics.services.lineup_reconstruction.reconstruct_lineup_from_pbp"
)
_RECENT_PATH = "app.analytics.services.lineup_fetcher.fetch_recent_lineup"


class TestFetchConsensusLineup:
    """Tests for fetch_consensus_lineup."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_games(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        result = await fetch_consensus_lineup(db, team_id=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_consensus_picks_most_frequent_starters(self):
        """Players who appear in more games should be in the consensus."""
        db = AsyncMock()

        core_8 = ["A", "B", "C", "D", "E", "F", "G", "H"]
        lineups = [
            _make_lineup(*core_8, "Platoon1"),
            _make_lineup(*core_8, "Platoon1"),
            _make_lineup(*core_8, "Platoon1"),
            _make_lineup(*core_8, "Platoon2"),
            _make_lineup(*core_8, "Platoon2"),
        ]

        game_ids = [101, 102, 103, 104, 105]
        game_result_mock = MagicMock()
        game_result_mock.scalars.return_value.all.return_value = game_ids
        db.execute.return_value = game_result_mock

        with patch(
            _RECONSTRUCT_PATH,
            new_callable=AsyncMock,
        ) as mock_reconstruct:
            mock_reconstruct.side_effect = [
                {"batters": lineups[i]} for i in range(5)
            ]

            result = await fetch_consensus_lineup(db, team_id=1, num_games=5)

        assert result is not None
        assert len(result) == 9
        refs = [b["external_ref"] for b in result]
        for player in core_8:
            assert player in refs
        assert "Platoon1" in refs

    @pytest.mark.asyncio
    async def test_preserves_batting_order_from_frequency(self):
        """Players should be placed in their most common batting position."""
        db = AsyncMock()

        lineups = [
            _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("B", "A", "C", "D", "E", "F", "G", "H", "I"),
        ]

        game_ids = list(range(5))
        game_result_mock = MagicMock()
        game_result_mock.scalars.return_value.all.return_value = game_ids
        db.execute.return_value = game_result_mock

        with patch(
            _RECONSTRUCT_PATH,
            new_callable=AsyncMock,
        ) as mock_reconstruct:
            mock_reconstruct.side_effect = [
                {"batters": lineups[i]} for i in range(5)
            ]

            result = await fetch_consensus_lineup(db, team_id=1, num_games=5)

        assert result is not None
        assert result[0]["external_ref"] == "A"
        assert result[1]["external_ref"] == "B"

    @pytest.mark.asyncio
    async def test_fallback_to_recent_when_few_games(self):
        """Falls back to fetch_recent_lineup when < 3 games have data."""
        db = AsyncMock()

        # Only 2 game IDs
        game_ids = [101, 102]
        game_result_mock = MagicMock()
        game_result_mock.scalars.return_value.all.return_value = game_ids
        db.execute.return_value = game_result_mock

        with (
            patch(
                _RECONSTRUCT_PATH,
                new_callable=AsyncMock,
                return_value={"batters": _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I")},
            ),
            patch(
                _RECENT_PATH,
                new_callable=AsyncMock,
                return_value=_make_lineup("X", "Y", "Z", "A", "B", "C", "D", "E", "F"),
            ) as mock_recent,
        ):
            result = await fetch_consensus_lineup(db, team_id=1, num_games=7)

        # With only 2 games (< 3 threshold), should fall back
        mock_recent.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_slot_conflicts(self):
        """When two players want the same slot, higher frequency wins."""
        db = AsyncMock()

        lineups = [
            _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("A", "B", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("B", "A", "C", "D", "E", "F", "G", "H", "I"),
            _make_lineup("B", "A", "C", "D", "E", "F", "G", "H", "I"),
        ]

        game_ids = list(range(5))
        game_result_mock = MagicMock()
        game_result_mock.scalars.return_value.all.return_value = game_ids
        db.execute.return_value = game_result_mock

        with patch(
            _RECONSTRUCT_PATH,
            new_callable=AsyncMock,
        ) as mock_reconstruct:
            mock_reconstruct.side_effect = [
                {"batters": lineups[i]} for i in range(5)
            ]

            result = await fetch_consensus_lineup(db, team_id=1, num_games=5)

        assert result is not None
        assert len(result) == 9
        assert result[0]["external_ref"] == "A"
        assert result[1]["external_ref"] == "B"
