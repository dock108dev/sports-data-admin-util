"""Tests for game metadata helpers."""

from __future__ import annotations

import unittest
from datetime import datetime

from api.app.game_metadata.models import GameContext, StandingsEntry, TeamRatings
from api.app.game_metadata.nuggets import DEFAULT_NUGGET, _normalize_tags, generate_nugget
from api.app.game_metadata.scoring import _normalize, excitement_score, quality_score
from api.app.routers.sports.games import _normalize_score, _select_preview_entry


class TestGameMetadataHelpers(unittest.TestCase):
    def test_normalize_tags_strips_and_formats(self) -> None:
        tags = [" Playoff Implications ", "High Total", "", None, "star power"]

        normalized = _normalize_tags(tags)

        self.assertEqual(
            normalized,
            {"playoff_implications", "high_total", "star_power"},
        )

    def test_score_ranges_clamp_to_zero_to_hundred(self) -> None:
        context = GameContext(
            game_id="game-1",
            home_team="Alpha",
            away_team="Beta",
            league="NCAAB",
            start_time=datetime(2024, 1, 1),
            rivalry=True,
            projected_spread=1000.0,
            projected_total=1000.0,
            has_big_name_players=True,
            coach_vs_former_team=True,
            playoff_implications=True,
            national_broadcast=True,
        )
        home_rating = TeamRatings(
            team_id="home",
            conference="Atlantic",
            elo=2500.0,
            kenpom_adj_eff=80.0,
            projected_seed=0,
        )
        away_rating = TeamRatings(
            team_id="away",
            conference="Atlantic",
            elo=1100.0,
            kenpom_adj_eff=-30.0,
            projected_seed=30,
        )
        home_standing = StandingsEntry(
            team_id="home",
            conference_rank=0,
            wins=25,
            losses=1,
        )
        away_standing = StandingsEntry(
            team_id="away",
            conference_rank=40,
            wins=10,
            losses=12,
        )

        excitement = excitement_score(context)
        quality = quality_score(home_rating, away_rating, home_standing, away_standing)

        self.assertGreaterEqual(excitement, 0.0)
        self.assertLessEqual(excitement, 100.0)
        self.assertGreaterEqual(quality, 0.0)
        self.assertLessEqual(quality, 100.0)

        self.assertEqual(_normalize_score(-5.0), 0)
        self.assertEqual(_normalize_score(120.1), 100)
        self.assertEqual(_normalize_score(55.6), 56)

    def test_generate_nugget_prefers_context_tags(self) -> None:
        context = GameContext(
            game_id="game-2",
            home_team="Alpha",
            away_team="Beta",
            league="NCAAB",
            start_time=datetime(2024, 1, 1),
            rivalry=True,
            playoff_implications=True,
        )

        nugget = generate_nugget(context, tags=[])

        self.assertEqual(nugget, "Rivalry matchup with postseason positioning at stake.")

    def test_generate_nugget_uses_tag_normalization_or_defaults(self) -> None:
        context = GameContext(
            game_id="game-3",
            home_team="Alpha",
            away_team="Beta",
            league="NCAAB",
            start_time=datetime(2024, 1, 1),
        )

        nugget = generate_nugget(context, tags=[" Top Rated ", "Tournament Preview "])

        self.assertEqual(
            nugget,
            "Projected tournament preview between two top-rated teams.",
        )

        fallback = generate_nugget(context, tags=[])

        self.assertEqual(fallback, DEFAULT_NUGGET)

    def test_select_preview_entry_falls_back_or_errors(self) -> None:
        entries = [
            StandingsEntry(team_id="team-1", conference_rank=1, wins=10, losses=2),
            StandingsEntry(team_id="team-2", conference_rank=2, wins=9, losses=3),
        ]

        fallback = _select_preview_entry(
            entries,
            team_key="missing",
            fallback_index=1,
            entry_label="standings",
        )

        self.assertEqual(fallback.team_id, "team-2")

        with self.assertRaises(ValueError):
            _select_preview_entry(
                [],
                team_key="missing",
                fallback_index=0,
                entry_label="standings",
            )

    def test_normalize_guardrails(self) -> None:
        self.assertEqual(_normalize(10.0, 0.0, 20.0), 0.5)
        self.assertEqual(_normalize(-5.0, 0.0, 20.0), 0.0)
        self.assertEqual(_normalize(30.0, 0.0, 20.0), 1.0)

        with self.assertRaises(ValueError):
            _normalize(1.0, 10.0, 10.0)


if __name__ == "__main__":
    unittest.main()
