"""SQLAlchemy models for sports-data-admin."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import text


class Base(DeclarativeBase):
    pass


class SportsLeague(Base):
    """Sports leagues (NFL, NCAAF, NBA, NCAAB, MLB, NHL)."""

    __tablename__ = "sports_leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    teams: Mapped[list["SportsTeam"]] = relationship("SportsTeam", back_populates="league", cascade="all, delete-orphan")
    games: Mapped[list["SportsGame"]] = relationship("SportsGame", back_populates="league", cascade="all, delete-orphan")
    scrape_runs: Mapped[list["SportsScrapeRun"]] = relationship("SportsScrapeRun", back_populates="league")


class SportsTeam(Base):
    """Sports teams with external provider mappings."""

    __tablename__ = "sports_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    x_handle: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    external_codes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    league: Mapped[SportsLeague] = relationship("SportsLeague", back_populates="teams")
    home_games: Mapped[list["SportsGame"]] = relationship("SportsGame", foreign_keys="[SportsGame.home_team_id]", back_populates="home_team")
    away_games: Mapped[list["SportsGame"]] = relationship("SportsGame", foreign_keys="[SportsGame.away_team_id]", back_populates="away_team")

    __table_args__ = (
        Index("idx_sports_teams_league_name", "league_id", "name", unique=True),
        Index("idx_sports_teams_league_name_lower", "league_id", text("lower(name)")),
    )


class CompactModeThreshold(Base):
    """Compact mode threshold configuration per sport."""

    __tablename__ = "compact_mode_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    thresholds: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    league: Mapped[SportsLeague] = relationship("SportsLeague")


class GameStatus(str, Enum):
    scheduled = "scheduled"
    completed = "completed"
    postponed = "postponed"
    canceled = "canceled"


class SportsGame(Base):
    """Individual games with unique constraints to prevent duplicates."""

    __tablename__ = "sports_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    season_type: Mapped[str] = mapped_column(String(50), nullable=False)
    game_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    home_team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    away_team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=GameStatus.scheduled, nullable=False, index=True)
    source_game_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    scrape_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    league: Mapped[SportsLeague] = relationship("SportsLeague", back_populates="games")
    home_team: Mapped[SportsTeam] = relationship("SportsTeam", foreign_keys=[home_team_id], back_populates="home_games")
    away_team: Mapped[SportsTeam] = relationship("SportsTeam", foreign_keys=[away_team_id], back_populates="away_games")
    team_boxscores: Mapped[list["SportsTeamBoxscore"]] = relationship("SportsTeamBoxscore", back_populates="game", cascade="all, delete-orphan")
    player_boxscores: Mapped[list["SportsPlayerBoxscore"]] = relationship("SportsPlayerBoxscore", back_populates="game", cascade="all, delete-orphan")
    odds: Mapped[list["SportsGameOdds"]] = relationship("SportsGameOdds", back_populates="game", cascade="all, delete-orphan")
    social_posts: Mapped[list["GameSocialPost"]] = relationship("GameSocialPost", back_populates="game", cascade="all, delete-orphan")
    plays: Mapped[list["SportsGamePlay"]] = relationship("SportsGamePlay", back_populates="game", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("league_id", "season", "game_date", "home_team_id", "away_team_id", name="uq_game_identity"),
        Index("idx_games_league_season_date", "league_id", "season", "game_date"),
        Index("idx_games_teams", "home_team_id", "away_team_id"),
    )


class SportsTeamBoxscore(Base):
    """Team-level boxscore data stored as JSONB for flexibility across sports."""

    __tablename__ = "sports_team_boxscores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column("raw_stats_json", JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    game: Mapped[SportsGame] = relationship("SportsGame", back_populates="team_boxscores")
    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_team_boxscore_game_team"),
    )


class SportsPlayerBoxscore(Base):
    """Player-level boxscores stored as JSONB for flexibility across sports."""

    __tablename__ = "sports_player_boxscores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    player_external_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    player_name: Mapped[str] = mapped_column(String(200), nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column("raw_stats_json", JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    game: Mapped[SportsGame] = relationship("SportsGame", back_populates="player_boxscores")
    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint("game_id", "team_id", "player_external_ref", name="uq_player_boxscore_identity"),
    )


class SportsGameOdds(Base):
    """Odds data for games (multiple books/markets per game)."""

    __tablename__ = "sports_game_odds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    book: Mapped[str] = mapped_column(String(50), nullable=False)
    market_type: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_closing_line: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    game: Mapped[SportsGame] = relationship("SportsGame", back_populates="odds")

    __table_args__ = (
        Index(
            "uq_sports_game_odds_identity",
            "game_id",
            "book",
            "market_type",
            "side",
            "is_closing_line",
            unique=True,
        ),
    )


class SportsGamePlay(Base):
    """Play-by-play events for games."""

    __tablename__ = "sports_game_plays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    game_clock: Mapped[str | None] = mapped_column(String(10), nullable=True)
    play_index: Mapped[int] = mapped_column(Integer, nullable=False)
    play_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    team_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sports_teams.id"), nullable=True)
    player_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    player_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped["SportsGame"] = relationship("SportsGame", back_populates="plays")

    __table_args__ = (
        Index("idx_game_plays_game", "game_id"),
        UniqueConstraint("game_id", "play_index", name="uq_game_play_index"),
    )


class SportsScrapeRun(Base):
    """Tracks ingestion/scrape job runs."""

    __tablename__ = "sports_scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scraper_type: Mapped[str] = mapped_column(String(50), nullable=False)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    season_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    league: Mapped[SportsLeague] = relationship("SportsLeague", back_populates="scrape_runs")

    __table_args__ = (
        Index("idx_scrape_runs_league_status", "league_id", "status"),
        Index("idx_scrape_runs_created", "created_at"),
    )


class GameSocialPost(Base):
    """Social media posts linked to games for timeline display."""

    __tablename__ = "game_social_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    # Column is named tweet_url in DB for backwards compatibility, but we use post_url in code
    post_url: Mapped[str] = mapped_column("tweet_url", Text, nullable=False, unique=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    has_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tweet_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped[SportsGame] = relationship("SportsGame", back_populates="social_posts")
    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        Index("idx_social_posts_game", "game_id"),
        Index("idx_social_posts_team", "team_id"),
        Index("idx_social_posts_posted_at", "posted_at"),
        Index("idx_social_posts_media_type", "media_type"),
    )

