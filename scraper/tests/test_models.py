"""Comprehensive tests for models/schemas.py module."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

from sports_scraper.models import (
    TeamIdentity,
    GameIdentification,
    NormalizedGame,
    NormalizedTeamBoxscore,
    NormalizedPlayerBoxscore,
    NormalizedOddsSnapshot,
    NormalizedPlay,
    NormalizedPlayByPlay,
    IngestionConfig,
)


# ============================================================================
# TeamIdentity Tests
# ============================================================================

class TestTeamIdentity:
    """Tests for TeamIdentity model."""

    def test_create_minimal(self):
        team = TeamIdentity(
            league_code="NBA",
            name="Boston Celtics",
        )
        assert team.league_code == "NBA"
        assert team.name == "Boston Celtics"
        assert team.short_name is None
        assert team.abbreviation is None

    def test_create_full(self):
        team = TeamIdentity(
            league_code="NHL",
            name="Tampa Bay Lightning",
            short_name="Lightning",
            abbreviation="TBL",
            external_ref="14",
        )
        assert team.league_code == "NHL"
        assert team.name == "Tampa Bay Lightning"
        assert team.short_name == "Lightning"
        assert team.abbreviation == "TBL"
        assert team.external_ref == "14"

    def test_invalid_league_code(self):
        with pytest.raises(ValidationError):
            TeamIdentity(
                league_code="INVALID",  # Not a valid SportCode
                name="Test Team",
            )

    def test_valid_league_codes(self):
        for code in ["NBA", "NFL", "NCAAF", "NCAAB", "MLB", "NHL"]:
            team = TeamIdentity(league_code=code, name="Test")
            assert team.league_code == code


# ============================================================================
# GameIdentification Tests
# ============================================================================

class TestGameIdentification:
    """Tests for GameIdentification model."""

    def test_create_game_id(self):
        home = TeamIdentity(league_code="NBA", name="Boston Celtics")
        away = TeamIdentity(league_code="NBA", name="Los Angeles Lakers")

        game_id = GameIdentification(
            league_code="NBA",
            season=2024,
            game_date=datetime(2024, 1, 15, 19, 0),
            home_team=home,
            away_team=away,
        )

        assert game_id.league_code == "NBA"
        assert game_id.season == 2024
        assert game_id.season_type == "regular"  # Default
        assert game_id.source_game_key is None

    def test_with_source_game_key(self):
        home = TeamIdentity(league_code="NBA", name="Boston Celtics")
        away = TeamIdentity(league_code="NBA", name="Los Angeles Lakers")

        game_id = GameIdentification(
            league_code="NBA",
            season=2024,
            season_type="playoffs",
            game_date=datetime(2024, 5, 15, 19, 0),
            home_team=home,
            away_team=away,
            source_game_key="0042400201",
        )

        assert game_id.season_type == "playoffs"
        assert game_id.source_game_key == "0042400201"


# ============================================================================
# NormalizedTeamBoxscore Tests
# ============================================================================

class TestNormalizedTeamBoxscore:
    """Tests for NormalizedTeamBoxscore model."""

    def test_create_basketball_boxscore(self):
        team = TeamIdentity(league_code="NBA", name="Boston Celtics")

        boxscore = NormalizedTeamBoxscore(
            team=team,
            is_home=True,
            points=110,
            rebounds=45,
            assists=25,
            turnovers=12,
        )

        assert boxscore.team.name == "Boston Celtics"
        assert boxscore.is_home is True
        assert boxscore.points == 110
        assert boxscore.rebounds == 45

    def test_create_hockey_boxscore(self):
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning")

        boxscore = NormalizedTeamBoxscore(
            team=team,
            is_home=True,
            shots_on_goal=35,
            penalty_minutes=10,
        )

        assert boxscore.shots_on_goal == 35
        assert boxscore.penalty_minutes == 10

    def test_raw_stats_default(self):
        team = TeamIdentity(league_code="NBA", name="Test")
        boxscore = NormalizedTeamBoxscore(team=team, is_home=True)
        assert boxscore.raw_stats == {}

    def test_raw_stats_with_data(self):
        team = TeamIdentity(league_code="NBA", name="Test")
        boxscore = NormalizedTeamBoxscore(
            team=team,
            is_home=True,
            raw_stats={"fg_pct": 0.485, "three_pt_pct": 0.380},
        )
        assert boxscore.raw_stats["fg_pct"] == 0.485


# ============================================================================
# NormalizedPlayerBoxscore Tests
# ============================================================================

class TestNormalizedPlayerBoxscore:
    """Tests for NormalizedPlayerBoxscore model."""

    def test_create_basketball_player(self):
        team = TeamIdentity(league_code="NBA", name="Boston Celtics")

        player = NormalizedPlayerBoxscore(
            player_id="1628369",
            player_name="Jayson Tatum",
            team=team,
            position="SF",
            minutes=38.5,
            points=30,
            rebounds=10,
            assists=5,
        )

        assert player.player_id == "1628369"
        assert player.player_name == "Jayson Tatum"
        assert player.points == 30

    def test_create_hockey_skater(self):
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning")

        player = NormalizedPlayerBoxscore(
            player_id="8478010",
            player_name="Brayden Point",
            team=team,
            player_role="skater",
            position="C",
            sweater_number=21,
            minutes=20.5,
            goals=2,
            assists=1,
            shots_on_goal=5,
            plus_minus=2,
        )

        assert player.player_role == "skater"
        assert player.goals == 2
        assert player.plus_minus == 2

    def test_create_hockey_goalie(self):
        team = TeamIdentity(league_code="NHL", name="Tampa Bay Lightning")

        player = NormalizedPlayerBoxscore(
            player_id="8476883",
            player_name="Andrei Vasilevskiy",
            team=team,
            player_role="goalie",
            position="G",
            sweater_number=88,
            minutes=60.0,
            saves=28,
            goals_against=2,
            shots_against=30,
            save_percentage=0.933,
        )

        assert player.player_role == "goalie"
        assert player.saves == 28
        assert player.save_percentage == 0.933


# ============================================================================
# NormalizedGame Tests
# ============================================================================

class TestNormalizedGame:
    """Tests for NormalizedGame model."""

    def test_create_game(self):
        home = TeamIdentity(league_code="NBA", name="Boston Celtics")
        away = TeamIdentity(league_code="NBA", name="Los Angeles Lakers")

        identity = GameIdentification(
            league_code="NBA",
            season=2024,
            game_date=datetime(2024, 1, 15, 19, 0),
            home_team=home,
            away_team=away,
        )

        home_box = NormalizedTeamBoxscore(team=home, is_home=True, points=110)
        away_box = NormalizedTeamBoxscore(team=away, is_home=False, points=105)

        game = NormalizedGame(
            identity=identity,
            status="completed",
            home_score=110,
            away_score=105,
            team_boxscores=[home_box, away_box],
        )

        assert game.status == "completed"
        assert game.home_score == 110
        assert len(game.team_boxscores) == 2

    def test_game_requires_team_boxscores(self):
        home = TeamIdentity(league_code="NBA", name="Boston Celtics")
        away = TeamIdentity(league_code="NBA", name="Los Angeles Lakers")

        identity = GameIdentification(
            league_code="NBA",
            season=2024,
            game_date=datetime(2024, 1, 15, 19, 0),
            home_team=home,
            away_team=away,
        )

        # Empty team_boxscores should raise
        with pytest.raises(ValidationError):
            NormalizedGame(
                identity=identity,
                team_boxscores=[],
            )


# ============================================================================
# NormalizedOddsSnapshot Tests
# ============================================================================

class TestNormalizedOddsSnapshot:
    """Tests for NormalizedOddsSnapshot model."""

    def test_create_spread_odds(self):
        home = TeamIdentity(league_code="NBA", name="Boston Celtics")
        away = TeamIdentity(league_code="NBA", name="Los Angeles Lakers")

        odds = NormalizedOddsSnapshot(
            league_code="NBA",
            book="Pinnacle",
            market_type="spread",
            side="Boston Celtics",
            line=-5.5,
            price=-110,
            observed_at=datetime(2024, 1, 15, 22, 0, tzinfo=timezone.utc),
            home_team=home,
            away_team=away,
            game_date=datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc),
        )

        assert odds.market_type == "spread"
        assert odds.line == -5.5
        assert odds.price == -110

    def test_create_moneyline_odds(self):
        home = TeamIdentity(league_code="NBA", name="Boston Celtics")
        away = TeamIdentity(league_code="NBA", name="Los Angeles Lakers")

        odds = NormalizedOddsSnapshot(
            league_code="NBA",
            book="FanDuel",
            market_type="moneyline",
            side="Boston Celtics",
            price=-180,
            observed_at=datetime(2024, 1, 15, 22, 0, tzinfo=timezone.utc),
            home_team=home,
            away_team=away,
            game_date=datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc),
        )

        assert odds.market_type == "moneyline"
        assert odds.line is None
        assert odds.price == -180

    def test_create_total_odds(self):
        home = TeamIdentity(league_code="NBA", name="Boston Celtics")
        away = TeamIdentity(league_code="NBA", name="Los Angeles Lakers")

        odds = NormalizedOddsSnapshot(
            league_code="NBA",
            book="DraftKings",
            market_type="total",
            side="Over",
            line=220.5,
            price=-110,
            observed_at=datetime(2024, 1, 15, 22, 0, tzinfo=timezone.utc),
            home_team=home,
            away_team=away,
            game_date=datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc),
        )

        assert odds.market_type == "total"
        assert odds.side == "Over"
        assert odds.line == 220.5


# ============================================================================
# NormalizedPlay Tests
# ============================================================================

class TestNormalizedPlay:
    """Tests for NormalizedPlay model."""

    def test_create_play(self):
        play = NormalizedPlay(
            play_index=10067,
            quarter=1,
            game_clock="16:00",
            play_type="GOAL",
            team_abbreviation="TBL",
            player_id="8478010",
            player_name="Brayden Point",
            description="Goal (wrist shot)",
            home_score=1,
            away_score=0,
        )

        assert play.play_index == 10067
        assert play.quarter == 1
        assert play.play_type == "GOAL"
        assert play.home_score == 1

    def test_play_with_raw_data(self):
        play = NormalizedPlay(
            play_index=100,
            play_type="SHOT",
            raw_data={"shot_type": "wrist", "zone": "offensive"},
        )

        assert play.raw_data["shot_type"] == "wrist"

    def test_play_minimal(self):
        play = NormalizedPlay(play_index=1)
        assert play.play_index == 1
        assert play.quarter is None
        assert play.raw_data == {}


# ============================================================================
# NormalizedPlayByPlay Tests
# ============================================================================

class TestNormalizedPlayByPlay:
    """Tests for NormalizedPlayByPlay model."""

    def test_create_pbp(self):
        plays = [
            NormalizedPlay(play_index=1, play_type="FACEOFF"),
            NormalizedPlay(play_index=2, play_type="SHOT"),
            NormalizedPlay(play_index=3, play_type="GOAL", home_score=1, away_score=0),
        ]

        pbp = NormalizedPlayByPlay(
            source_game_key="2025020001",
            plays=plays,
        )

        assert pbp.source_game_key == "2025020001"
        assert len(pbp.plays) == 3

    def test_empty_plays(self):
        pbp = NormalizedPlayByPlay(source_game_key="123")
        assert pbp.plays == []


# ============================================================================
# IngestionConfig Tests
# ============================================================================

class TestIngestionConfig:
    """Tests for IngestionConfig model."""

    def test_create_minimal(self):
        config = IngestionConfig(league_code="NBA")

        assert config.league_code == "NBA"
        assert config.boxscores is True
        assert config.odds is True
        assert config.social is False
        assert config.pbp is False
        assert config.batch_live_feed is False
        assert config.only_missing is False

    def test_create_with_dates(self):
        config = IngestionConfig(
            league_code="NHL",
            season=2024,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 20),
        )

        assert config.start_date == date(2024, 1, 15)
        assert config.end_date == date(2024, 1, 20)

    def test_create_with_toggles(self):
        config = IngestionConfig(
            league_code="NBA",
            boxscores=True,
            odds=False,
            social=True,
            pbp=True,
            batch_live_feed=True,
            only_missing=True,
        )

        assert config.boxscores is True
        assert config.odds is False
        assert config.social is True
        assert config.pbp is True
        assert config.batch_live_feed is True

    def test_with_book_filter(self):
        config = IngestionConfig(
            league_code="NBA",
            include_books=["pinnacle", "fanduel"],
        )

        assert config.include_books == ["pinnacle", "fanduel"]

    def test_invalid_league_code(self):
        with pytest.raises(ValidationError):
            IngestionConfig(league_code="INVALID")

    def test_season_type(self):
        config = IngestionConfig(
            league_code="NBA",
            season_type="playoffs",
        )
        assert config.season_type == "playoffs"
