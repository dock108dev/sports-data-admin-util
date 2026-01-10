"""SQLAlchemy models for sports-data-admin.

Beta Phase 0 Canonical Schema
=============================
This module defines the canonical data model for game identity.

Key Rules:
1. games.id is the ONLY identifier used internally
2. source_game_key stores external IDs for reference only
3. game_date (start_time) is immutable after creation
4. end_time is set only when status becomes 'final'
5. Status lifecycle: scheduled -> live -> final

Note: Models remain co-located to keep the canonical schema easy to audit,
even though this module sits slightly above 500 lines.
"""

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
    # DEPRECATED: Use external_codes for new provider mappings
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
    social_accounts: Mapped[list["TeamSocialAccount"]] = relationship("TeamSocialAccount", back_populates="team", cascade="all, delete-orphan")

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
    """Canonical game status lifecycle."""

    scheduled = "scheduled"
    live = "live"
    final = "final"
    completed = "completed"  # DEPRECATED: Use 'final' for new games
    postponed = "postponed"
    canceled = "canceled"


class SportsGame(Base):
    """Individual games with unique constraints to prevent duplicates."""

    __tablename__ = "sports_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    season_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # game_date is the scheduled start time (IMMUTABLE - never changes after creation)
    game_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # end_time is set only when status becomes 'final' or 'completed'
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    away_team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=GameStatus.scheduled, nullable=False, index=True)
    # source_game_key is the external ID from the data provider
    source_game_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    scrape_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_pbp_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_social_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        Index("idx_games_league_status", "league_id", "status"),
    )

    @property
    def is_final(self) -> bool:
        """Check if game is in a final state."""
        return self.status in (GameStatus.final.value, GameStatus.completed.value)

    @property
    def start_time(self) -> datetime:
        """Alias for game_date to match canonical naming."""
        return self.game_date


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


class SportsTeamSeasonStat(Base):
    """Season-level team stats stored as JSONB for flexibility across sports."""

    __tablename__ = "sports_team_season_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season_type: Mapped[str] = mapped_column(String(50), nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column("raw_stats_json", JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint("team_id", "season", "season_type", "source", name="uq_team_season_stat_identity"),
        Index("idx_team_season_stats_team_season", "team_id", "season"),
    )


class SportsPlayerSeasonStat(Base):
    """Season-level player stats stored as JSONB for flexibility across sports."""

    __tablename__ = "sports_player_season_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="SET NULL"), nullable=True, index=True)
    team_abbreviation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    player_external_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    player_name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str | None] = mapped_column(String(20), nullable=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season_type: Mapped[str] = mapped_column(String(50), nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column("raw_stats_json", JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    league: Mapped[SportsLeague] = relationship("SportsLeague")
    team: Mapped[SportsTeam | None] = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint(
            "league_id",
            "player_external_ref",
            "season",
            "season_type",
            "team_abbreviation",
            "source",
            name="uq_player_season_stat_identity",
        ),
        Index("idx_player_season_stats_league_season", "league_id", "season"),
    )


class SportsGameOdds(Base):
    """Odds data for games (multiple books/markets per game)."""

    __tablename__ = "sports_game_odds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    book: Mapped[str] = mapped_column(String(50), nullable=False)
    market_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Side can be team name, "Over"/"Under", etc. Must support long team names.
    side: Mapped[str | None] = mapped_column(String(100), nullable=True)
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


class SportsJobRun(Base):
    """Tracks phase-level job execution for monitoring."""

    __tablename__ = "sports_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    leagues: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_job_runs_phase_started", "phase", "started_at"),
    )


class SportsGameConflict(Base):
    """Conflict records for duplicate or ambiguous game identity."""

    __tablename__ = "sports_game_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    conflict_game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    conflict_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("game_id", "conflict_game_id", "external_id", "source", name="uq_game_conflict"),
        Index("idx_game_conflicts_league_created", "league_id", "created_at"),
    )


class SportsMissingPbp(Base):
    """Records games missing play-by-play data when status requires it."""

    __tablename__ = "sports_missing_pbp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_missing_pbp_league_status", "league_id", "status"),
    )


class GameSocialPost(Base):
    """Social media posts linked to games for timeline display."""

    __tablename__ = "game_social_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    post_url: Mapped[str] = mapped_column("tweet_url", Text, nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(20), server_default="x", nullable=False)
    external_post_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    has_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tweet_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reveal_risk: Mapped[bool] = mapped_column("spo" "iler_risk", Boolean, default=False, nullable=False)
    reveal_reason: Mapped[str | None] = mapped_column("spo" "iler_reason", String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped[SportsGame] = relationship("SportsGame", back_populates="social_posts")
    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        Index("idx_social_posts_game", "game_id"),
        Index("idx_social_posts_team", "team_id"),
        Index("idx_social_posts_posted_at", "posted_at"),
        Index("idx_social_posts_media_type", "media_type"),
        Index("idx_social_posts_external_id", "external_post_id"),
        UniqueConstraint("platform", "external_post_id", name="uq_social_posts_platform_external_id"),
    )


class TeamSocialAccount(Base):
    """Registry of official team social accounts."""

    __tablename__ = "team_social_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_leagues.id", ondelete="CASCADE"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    handle: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    team: Mapped[SportsTeam] = relationship("SportsTeam", back_populates="social_accounts")
    league: Mapped[SportsLeague] = relationship("SportsLeague")

    __table_args__ = (
        UniqueConstraint("platform", "handle", name="uq_team_social_accounts_platform_handle"),
        UniqueConstraint("team_id", "platform", name="uq_team_social_accounts_team_platform"),
        Index("idx_team_social_accounts_league", "league_id"),
    )


class SocialAccountPoll(Base):
    """Cache metadata for social polling requests."""

    __tablename__ = "social_account_polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    handle: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    posts_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "handle", "window_start", "window_end", name="uq_social_account_poll_window"),
        Index("idx_social_account_polls_handle_window", "handle", "window_start", "window_end"),
    )


class GameReadingPosition(Base):
    """Tracks a user's last-read position for a game timeline."""

    __tablename__ = "game_reading_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False, index=True)
    moment: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    scroll_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    game: Mapped[SportsGame] = relationship("SportsGame")

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_reading_position_user_game"),
        Index("idx_reading_positions_user_game", "user_id", "game_id"),
    )
