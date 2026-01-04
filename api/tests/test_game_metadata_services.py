"""Tests for game metadata services."""

from __future__ import annotations

import unittest

from api.app.game_metadata.services import RatingsService, StandingsService


class TestGameMetadataServices(unittest.TestCase):
    def setUp(self) -> None:
        self.standings_service = StandingsService()
        self.ratings_service = RatingsService()

    def test_get_standings_returns_entries(self) -> None:
        standings = self.standings_service.get_standings("NCAA")

        self.assertGreaterEqual(len(standings), 1)
        self.assertEqual(standings[0].team_id, "team-001")
        self.assertIsInstance(standings[0].wins, int)

    def test_get_ratings_returns_entries(self) -> None:
        ratings = self.ratings_service.get_ratings("NCAA")

        self.assertGreaterEqual(len(ratings), 1)
        self.assertEqual(ratings[0].team_id, "team-001")
        self.assertIsInstance(ratings[0].elo, float)

    def test_get_standings_requires_league(self) -> None:
        with self.assertRaises(ValueError):
            self.standings_service.get_standings("")

    def test_get_ratings_requires_league(self) -> None:
        with self.assertRaises(ValueError):
            self.ratings_service.get_ratings("")


if __name__ == "__main__":
    unittest.main()
