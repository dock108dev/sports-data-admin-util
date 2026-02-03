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
from uuid import UUID

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
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import text


class Base(DeclarativeBase):
    pass


class SportsLeague(Base):
    """Sports leagues (NFL, NCAAF, NBA, NCAAB, MLB, NHL)."""

    __tablename__ = "sports_leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    teams: Mapped[list["SportsTeam"]] = relationship(
        "SportsTeam", back_populates="league", cascade="all, delete-orphan"
    )
    games: Mapped[list["SportsGame"]] = relationship(
        "SportsGame", back_populates="league", cascade="all, delete-orphan"
    )
    scrape_runs: Mapped[list["SportsScrapeRun"]] = relationship(
        "SportsScrapeRun", back_populates="league"
    )


class SportsTeam(Base):
    """Sports teams with external provider mappings."""

    __tablename__ = "sports_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    x_handle: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    external_codes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    league: Mapped[SportsLeague] = relationship("SportsLeague", back_populates="teams")
    home_games: Mapped[list["SportsGame"]] = relationship(
        "SportsGame",
        foreign_keys="[SportsGame.home_team_id]",
        back_populates="home_team",
    )
    away_games: Mapped[list["SportsGame"]] = relationship(
        "SportsGame",
        foreign_keys="[SportsGame.away_team_id]",
        back_populates="away_team",
    )
    social_accounts: Mapped[list["TeamSocialAccount"]] = relationship(
        "TeamSocialAccount", back_populates="team", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_sports_teams_league_name", "league_id", "name", unique=True),
        Index("idx_sports_teams_league_name_lower", "league_id", text("lower(name)")),
    )


class SportsPlayer(Base):
    """Master player records linked to PBP and boxscores."""

    __tablename__ = "sports_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sweater_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    league: Mapped[SportsLeague] = relationship("SportsLeague")
    team: Mapped[SportsTeam | None] = relationship("SportsTeam")
    plays: Mapped[list["SportsGamePlay"]] = relationship(
        "SportsGamePlay", back_populates="player_ref"
    )

    __table_args__ = (
        Index("idx_players_external_id", "external_id"),
        Index("idx_players_name", "name"),
        Index("uq_player_identity", "league_id", "external_id", unique=True),
    )


class CompactModeThreshold(Base):
    """Compact mode threshold configuration per sport."""

    __tablename__ = "compact_mode_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    thresholds: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    league: Mapped[SportsLeague] = relationship("SportsLeague")


class GameStatus(str, Enum):
    """Canonical game status lifecycle."""

    scheduled = "scheduled"
    live = "live"
    final = "final"
    postponed = "postponed"
    canceled = "canceled"


class SportsGame(Base):
    """Individual games with unique constraints to prevent duplicates."""

    __tablename__ = "sports_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    season_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # game_date is the calendar date at midnight UTC (used for matching/deduplication)
    game_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # tip_time is the actual scheduled start time (from Odds API commence_time or NBA Live gameEt)
    tip_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # end_time is calculated from last PBP play when game is final
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    home_team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    away_team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=GameStatus.scheduled, nullable=False, index=True
    )
    # source_game_key is the external ID from the data provider
    source_game_key: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )
    scrape_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_pbp_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_social_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    league: Mapped[SportsLeague] = relationship("SportsLeague", back_populates="games")
    home_team: Mapped[SportsTeam] = relationship(
        "SportsTeam", foreign_keys=[home_team_id], back_populates="home_games"
    )
    away_team: Mapped[SportsTeam] = relationship(
        "SportsTeam", foreign_keys=[away_team_id], back_populates="away_games"
    )
    team_boxscores: Mapped[list["SportsTeamBoxscore"]] = relationship(
        "SportsTeamBoxscore", back_populates="game", cascade="all, delete-orphan"
    )
    player_boxscores: Mapped[list["SportsPlayerBoxscore"]] = relationship(
        "SportsPlayerBoxscore", back_populates="game", cascade="all, delete-orphan"
    )
    odds: Mapped[list["SportsGameOdds"]] = relationship(
        "SportsGameOdds", back_populates="game", cascade="all, delete-orphan"
    )
    social_posts: Mapped[list["GameSocialPost"]] = relationship(
        "GameSocialPost", back_populates="game", cascade="all, delete-orphan"
    )
    plays: Mapped[list["SportsGamePlay"]] = relationship(
        "SportsGamePlay", back_populates="game", cascade="all, delete-orphan"
    )
    timeline_artifacts: Mapped[list["SportsGameTimelineArtifact"]] = relationship(
        "SportsGameTimelineArtifact",
        back_populates="game",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "league_id",
            "season",
            "game_date",
            "home_team_id",
            "away_team_id",
            name="uq_game_identity",
        ),
        Index("idx_games_league_season_date", "league_id", "season", "game_date"),
        Index("idx_games_teams", "home_team_id", "away_team_id"),
        Index("idx_games_league_status", "league_id", "status"),
    )

    @property
    def is_final(self) -> bool:
        """Check if game is in a final state."""
        return self.status == GameStatus.final.value

    @property
    def start_time(self) -> datetime:
        """Return actual game start time, preferring tip_time over game_date.

        tip_time is the actual scheduled start from Odds API commence_time.
        game_date is often just midnight UTC (date only, no time component).
        """
        return self.tip_time if self.tip_time else self.game_date

    @property
    def has_reliable_start_time(self) -> bool:
        """Return True if we have an actual tip time, not just a date."""
        return self.tip_time is not None


class SportsTeamBoxscore(Base):
    """Team-level boxscore data stored as JSONB for flexibility across sports."""

    __tablename__ = "sports_team_boxscores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(
        "raw_stats_json", JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    game: Mapped[SportsGame] = relationship(
        "SportsGame", back_populates="team_boxscores"
    )
    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_team_boxscore_game_team"),
    )


class SportsPlayerBoxscore(Base):
    """Player-level boxscores stored as JSONB for flexibility across sports."""

    __tablename__ = "sports_player_boxscores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_external_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    player_name: Mapped[str] = mapped_column(String(200), nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(
        "raw_stats_json", JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    game: Mapped[SportsGame] = relationship(
        "SportsGame", back_populates="player_boxscores"
    )
    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "team_id",
            "player_external_ref",
            name="uq_player_boxscore_identity",
        ),
    )


class SportsGameOdds(Base):
    """Odds data for games (multiple books/markets per game)."""

    __tablename__ = "sports_game_odds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book: Mapped[str] = mapped_column(String(50), nullable=False)
    market_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Side can be team name, "Over"/"Under", etc. Must support long team names.
    side: Mapped[str | None] = mapped_column(String(100), nullable=True)
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_closing_line: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

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


class FairbetGameOddsWork(Base):
    """FairBet work table: derived, disposable, upserted odds for comparison.

    This table stores one row per (bet × book) for non-completed games.
    It enables FairBet to compare odds across many books for each bet definition.

    Bet identity: (game_id, market_key, selection_key, line_value)
    Books are variants, not schema - each book is a separate row.

    This table is NOT historical - rows are overwritten per book per bet.
    Only populated for non-final games (scheduled, live).

    Note: line_value uses 0 as sentinel for NULL (moneyline has no line).
    """

    __tablename__ = "fairbet_game_odds_work"

    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    market_key: Mapped[str] = mapped_column(
        String(50), primary_key=True, nullable=False
    )
    selection_key: Mapped[str] = mapped_column(
        Text, primary_key=True, nullable=False
    )
    line_value: Mapped[float] = mapped_column(
        Float, primary_key=True, nullable=False, default=0.0
    )
    book: Mapped[str] = mapped_column(
        String(50), primary_key=True, nullable=False
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    game: Mapped[SportsGame] = relationship("SportsGame")

    __table_args__ = (
        Index("idx_fairbet_odds_game", "game_id"),
        Index("idx_fairbet_odds_observed", "observed_at"),
    )


class SportsGamePlay(Base):
    """Play-by-play events for games."""

    __tablename__ = "sports_game_plays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    game_clock: Mapped[str | None] = mapped_column(String(10), nullable=True)
    play_index: Mapped[int] = mapped_column(Integer, nullable=False)
    play_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sports_teams.id"), nullable=True
    )
    player_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    player_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    player_ref_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sports_players.id"),
        nullable=True,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    game: Mapped["SportsGame"] = relationship("SportsGame", back_populates="plays")
    team: Mapped["SportsTeam | None"] = relationship(
        "SportsTeam", foreign_keys=[team_id]
    )
    player_ref: Mapped["SportsPlayer | None"] = relationship(
        "SportsPlayer", back_populates="plays"
    )

    __table_args__ = (
        Index("idx_game_plays_game", "game_id"),
        UniqueConstraint("game_id", "play_index", name="uq_game_play_index"),
    )


class SportsScrapeRun(Base):
    """Tracks ingestion/scrape job runs."""

    __tablename__ = "sports_scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scraper_type: Mapped[str] = mapped_column(String(50), nullable=False)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    season_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    requested_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    league: Mapped[SportsLeague] = relationship(
        "SportsLeague", back_populates="scrape_runs"
    )

    __table_args__ = (
        Index("idx_scrape_runs_league_status", "league_id", "status"),
        Index("idx_scrape_runs_created", "created_at"),
    )


class SportsJobRun(Base):
    """Tracks phase-level job execution for monitoring."""

    __tablename__ = "sports_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    leagues: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_job_runs_phase_started", "phase", "started_at"),)


class SportsGameConflict(Base):
    """Conflict records for duplicate or ambiguous game identity."""

    __tablename__ = "sports_game_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conflict_game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    conflict_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "conflict_game_id",
            "external_id",
            "source",
            name="uq_game_conflict",
        ),
        Index("idx_game_conflicts_league_created", "league_id", "created_at"),
    )


class SportsMissingPbp(Base):
    """Records games missing play-by-play data when status requires it."""

    __tablename__ = "sports_missing_pbp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("idx_missing_pbp_league_status", "league_id", "status"),)


class GameSocialPost(Base):
    """Social media posts linked to games for timeline display."""

    __tablename__ = "game_social_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    post_url: Mapped[str] = mapped_column(
        "tweet_url", Text, nullable=False, unique=True
    )
    platform: Mapped[str] = mapped_column(
        String(20), server_default="x", nullable=False
    )
    external_post_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    has_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tweet_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reveal_risk: Mapped[bool] = mapped_column(
        "spoiler_risk", Boolean, default=False, nullable=False
    )
    reveal_reason: Mapped[str | None] = mapped_column(
        "spoiler_reason", String(200), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame", back_populates="social_posts")
    team: Mapped[SportsTeam] = relationship("SportsTeam")

    __table_args__ = (
        Index("idx_social_posts_game", "game_id"),
        Index("idx_social_posts_team", "team_id"),
        Index("idx_social_posts_posted_at", "posted_at"),
        Index("idx_social_posts_media_type", "media_type"),
        Index("idx_social_posts_external_id", "external_post_id"),
        UniqueConstraint(
            "platform", "external_post_id", name="uq_social_posts_platform_external_id"
        ),
    )


class SportsGameTimelineArtifact(Base):
    """Finalized timeline artifacts for games."""

    __tablename__ = "sports_game_timeline_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sport: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeline_version: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timeline_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    game_analysis_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Audit columns for tracking generation source
    generated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    game: Mapped[SportsGame] = relationship(
        "SportsGame", back_populates="timeline_artifacts"
    )

    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "sport",
            "timeline_version",
            name="uq_game_timeline_artifact_version",
        ),
        Index("idx_game_timeline_artifacts_game", "game_id"),
    )


class TeamSocialAccount(Base):
    """Registry of official team social accounts."""

    __tablename__ = "team_social_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    handle: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    team: Mapped[SportsTeam] = relationship(
        "SportsTeam", back_populates="social_accounts"
    )
    league: Mapped[SportsLeague] = relationship("SportsLeague")

    __table_args__ = (
        UniqueConstraint(
            "platform", "handle", name="uq_team_social_accounts_platform_handle"
        ),
        UniqueConstraint(
            "team_id", "platform", name="uq_team_social_accounts_team_platform"
        ),
        Index("idx_team_social_accounts_league", "league_id"),
    )


class SocialAccountPoll(Base):
    """Cache metadata for social polling requests."""

    __tablename__ = "social_account_polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    handle: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    posts_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limited_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "handle",
            "window_start",
            "window_end",
            name="uq_social_account_poll_window",
        ),
        Index(
            "idx_social_account_polls_handle_window",
            "handle",
            "window_start",
            "window_end",
        ),
    )


class GameReadingPosition(Base):
    """Tracks a user's last-read position for a game timeline."""

    __tablename__ = "game_reading_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    moment: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    scroll_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    game: Mapped[SportsGame] = relationship("SportsGame")

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_reading_position_user_game"),
        Index("idx_reading_positions_user_game", "user_id", "game_id"),
    )


# =============================================================================
# GAME PIPELINE MODELS
# =============================================================================
# These models support the replayable game pipeline that decouples
# data scraping from moment generation.


class PipelineStage(str, Enum):
    """Pipeline stages for game processing.

    Each stage has clear input/output contracts:
    - NORMALIZE_PBP: Build normalized PBP events with phases
    - GENERATE_MOMENTS: Partition game into narrative moments
    - VALIDATE_MOMENTS: Run validation checks
    - RENDER_NARRATIVES: Generate narrative text using OpenAI
    - FINALIZE_MOMENTS: Persist final story artifact
    """

    NORMALIZE_PBP = "NORMALIZE_PBP"
    GENERATE_MOMENTS = "GENERATE_MOMENTS"
    VALIDATE_MOMENTS = "VALIDATE_MOMENTS"
    RENDER_NARRATIVES = "RENDER_NARRATIVES"
    FINALIZE_MOMENTS = "FINALIZE_MOMENTS"


class PipelineRunStatus(str, Enum):
    """Status of a pipeline run."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"


class PipelineStageStatus(str, Enum):
    """Status of a pipeline stage execution."""

    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"


class PipelineTrigger(str, Enum):
    """Who/what triggered the pipeline run."""

    prod_auto = "prod_auto"  # Automatic production trigger
    admin = "admin"  # Admin UI trigger
    manual = "manual"  # Manual/CLI trigger
    backfill = "backfill"  # Backfill operation


class GamePipelineRun(Base):
    """Tracks a pipeline execution for a single game.

    A pipeline run represents one attempt to process a game through the
    moment generation pipeline. Each run has multiple stage executions.

    Key behaviors:
    - auto_chain=True: Automatically proceeds to next stage on success
    - auto_chain=False: Pauses after each stage, requires explicit continue
    - Admin/manual triggers always set auto_chain=False
    """

    __tablename__ = "sports_game_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    auto_chain: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    current_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending", index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    game: Mapped[SportsGame] = relationship("SportsGame")
    stages: Mapped[list["GamePipelineStage"]] = relationship(
        "GamePipelineStage", back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_pipeline_runs_uuid", "run_uuid", unique=True),)

    @property
    def is_complete(self) -> bool:
        """Check if the pipeline run has completed (success or failure)."""
        return self.status in (
            PipelineRunStatus.completed.value,
            PipelineRunStatus.failed.value,
        )

    @property
    def can_continue(self) -> bool:
        """Check if the pipeline can be continued."""
        return self.status in (
            PipelineRunStatus.pending.value,
            PipelineRunStatus.paused.value,
            PipelineRunStatus.running.value,
        )


class GamePipelineStage(Base):
    """Tracks execution of a single stage within a pipeline run.

    Each stage stores:
    - output_json: Stage-specific output data for the next stage
    - logs_json: Array of log entries with timestamps
    - error_details: Error message if stage failed

    The output_json format varies by stage but is consumed by the next stage.
    """

    __tablename__ = "sports_game_pipeline_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_game_pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending", index=True
    )
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    logs_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, server_default=text("'[]'::jsonb")
    )
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[GamePipelineRun] = relationship(
        "GamePipelineRun", back_populates="stages"
    )

    __table_args__ = (
        UniqueConstraint("run_id", "stage", name="uq_pipeline_stages_run_stage"),
    )

    @property
    def is_complete(self) -> bool:
        """Check if the stage has completed (success or failure)."""
        return self.status in (
            PipelineStageStatus.success.value,
            PipelineStageStatus.failed.value,
            PipelineStageStatus.skipped.value,
        )

    def add_log(self, message: str, level: str = "info") -> None:
        """Add a log entry to this stage."""
        from datetime import datetime, timezone

        if self.logs_json is None:
            self.logs_json = []
        self.logs_json.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "message": message,
            }
        )


class BulkStoryJobStatus(str, Enum):
    """Status of a bulk story generation job."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class BulkStoryGenerationJob(Base):
    """Tracks bulk story generation jobs.

    This table persists bulk job state so it survives worker restarts
    and is consistent across multiple worker processes.
    """

    __tablename__ = "bulk_story_generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending", index=True
    )
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    leagues: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    force_regenerate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    max_games: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    total_games: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_game: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    triggered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (Index("idx_bulk_story_jobs_uuid", "job_uuid", unique=True),)


class PBPSnapshotType(str, Enum):
    """Type of PBP snapshot."""

    raw = "raw"  # Raw PBP as received from source
    normalized = "normalized"  # After normalization (phases, timestamps)
    resolved = "resolved"  # After team/player resolution


class PBPSnapshot(Base):
    """Snapshot of play-by-play data for inspectability.

    This table stores PBP data at different processing stages:

    - RAW: Original data from the source (NBA Live API, NHL API, etc.)
    - NORMALIZED: After phase assignment and timestamp computation
    - RESOLVED: After team and player ID resolution

    Snapshots are tied to either a scrape run (for raw) or a pipeline run
    (for normalized/resolved), enabling full auditability.

    EDGE CASES DOCUMENTED:

    1. Missing Teams (resolution_stats.teams_unresolved):
       - Team abbreviation in PBP doesn't match any team in database
       - team_id will be null, team_abbreviation preserved
       - Common cause: Abbreviation mismatches (e.g., "PHX" vs "PHO")

    2. Missing Players (resolution_stats.players_unresolved):
       - Player ID or name not found in player database
       - player_id preserved as string, player_name from source
       - Note: We don't have a players table; player resolution is name-only

    3. Missing Scores (resolution_stats.plays_without_score):
       - Some plays don't update the score (timeouts, substitutions)
       - home_score/away_score may be null for non-scoring plays
       - Score is carried forward from last scoring play

    4. Clock Parsing Failures (resolution_stats.clock_parse_failures):
       - Game clock couldn't be parsed (e.g., malformed "12:3" instead of "12:03")
       - Falls back to play_index ordering
    """

    __tablename__ = "sports_pbp_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sports_game_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scrape_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sports_scrape_runs.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plays_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'::jsonb")
    )
    resolution_stats: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame")
    pipeline_run: Mapped[GamePipelineRun | None] = relationship("GamePipelineRun")
    scrape_run: Mapped["SportsScrapeRun | None"] = relationship("SportsScrapeRun")

    __table_args__ = (Index("idx_pbp_snapshots_game_type", "game_id", "snapshot_type"),)


class ResolutionStatus(str, Enum):
    """Status of entity resolution."""

    success = "success"  # Entity resolved successfully
    failed = "failed"  # Resolution failed (no match)
    ambiguous = "ambiguous"  # Multiple candidates, picked one
    partial = "partial"  # Partial resolution (e.g., name but no ID)


class EntityResolution(Base):
    """Tracks how teams and players are resolved from source identifiers.

    This table enables full auditability of the resolution process:

    1. TEAM RESOLUTION
       - Source: team_abbreviation from PBP data (e.g., "LAL", "BOS")
       - Target: team_id in sports_teams table
       - Methods: exact_match, abbreviation_lookup, fuzzy_match

    2. PLAYER RESOLUTION
       - Source: player_name from PBP data
       - Target: Currently just name normalization (no player table)
       - Methods: exact_match, name_normalization

    EDGE CASES:

    1. UNRESOLVED TEAMS (resolution_status = 'failed')
       - team_abbreviation doesn't match any known team
       - Common cause: Abbreviation variations (PHX vs PHO)
       - Action: Check source_identifier and compare with sports_teams

    2. AMBIGUOUS TEAMS (resolution_status = 'ambiguous')
       - Multiple teams match the abbreviation
       - Common cause: Same abbrev in different leagues
       - Action: Check candidates field for alternatives

    3. UNRESOLVED PLAYERS (resolution_status = 'failed')
       - Player name couldn't be normalized
       - Note: We don't have a players table, so this is rare

    4. PARTIAL RESOLUTION (resolution_status = 'partial')
       - Some information resolved but not all
       - Example: Team name found but team_id missing
    """

    __tablename__ = "sports_entity_resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sports_game_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # "team" or "player"

    # Source identifiers
    source_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    source_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Resolution result
    resolved_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    resolution_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Failure/ambiguity details
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )

    # Occurrence tracking
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_play_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_play_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame")
    pipeline_run: Mapped[GamePipelineRun | None] = relationship("GamePipelineRun")

    __table_args__ = (
        Index("idx_entity_resolutions_game_type", "game_id", "entity_type"),
    )


class FrontendPayloadVersion(Base):
    """Immutable versioned frontend payloads.

    This table stores immutable snapshots of exactly what the frontend receives.
    Each pipeline run creates a NEW version - payloads are NEVER mutated.

    IMMUTABILITY GUARANTEE
    ======================
    Once a FrontendPayloadVersion is created, it is NEVER modified:
    - No UPDATE operations on this table
    - New pipeline runs create new versions
    - Historical versions preserved forever

    VERSIONING
    ==========
    - version_number: Auto-incremented per game (1, 2, 3, ...)
    - is_active: Exactly ONE version per game is active at any time
    - When a new version is created, the old active is deactivated

    CHANGE DETECTION
    ================
    - payload_hash: SHA-256 of (timeline_json + moments_json + summary_json)
    - diff_from_previous: Summary of what changed from the previous version

    FRONTEND CONTRACT
    =================
    The frontend expects exactly this structure:
    - timeline_json: Array of timeline events (PBP + social)
    - moments_json: Array of moment objects
    - summary_json: Game summary object

    These fields match what SportsGameTimelineArtifact provides but with
    full version history and immutability guarantees.
    """

    __tablename__ = "sports_frontend_payload_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sports_game_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Version tracking
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), index=True
    )

    # Payload content (IMMUTABLE once created)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    timeline_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    moments_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Metadata
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    moment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Change tracking
    diff_from_previous: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    # Timestamps (NO updated_at - payloads are IMMUTABLE)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame")
    pipeline_run: Mapped[GamePipelineRun | None] = relationship("GamePipelineRun")

    __table_args__ = (
        Index("idx_frontend_payload_version", "game_id", "version_number"),
    )

    @property
    def is_latest(self) -> bool:
        """Check if this is the active version."""
        return self.is_active


class SportsGameStory(Base):
    """AI-generated game stories as condensed moments.

    This table stores AI-generated narrative content for games.
    Stories consist of ordered moments, each with a narrative.

    CONTENT STRUCTURE
    - moments_json: Ordered list of condensed moments with narratives
    - moment_count: Number of moments
    - validated_at: When pipeline validation passed

    HAS_STORY DETERMINATION
    - moments_json IS NOT NULL
    """

    __tablename__ = "sports_game_stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sport: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    story_version: Mapped[str] = mapped_column(String(20), nullable=False)

    # Moments-based Story (condensed moments format)
    moments_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    moment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Blocks-based Story (Phase 1: 4-7 narrative blocks)
    blocks_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    block_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocks_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blocks_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Generation metadata
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ai_model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_ai_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    game: Mapped[SportsGame] = relationship("SportsGame")

    __table_args__ = (
        UniqueConstraint("game_id", "story_version", name="uq_game_story_version"),
        Index("idx_game_stories_game_id", "game_id"),
        Index("idx_game_stories_sport", "sport"),
        Index("idx_game_stories_generated_at", "generated_at"),
    )


class OpenAIResponseCache(Base):
    """Cache for OpenAI API responses to avoid redundant calls during testing.

    Stores responses keyed by game_id + batch_key (hash of moment indices).
    This allows re-running pipelines without hitting OpenAI again.
    """

    __tablename__ = "openai_response_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sports_games.id", ondelete="CASCADE"), nullable=False
    )
    # Identifies which batch of moments this response is for
    batch_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # The prompt sent to OpenAI (truncated for storage)
    prompt_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full response from OpenAI
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Model used
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped[SportsGame] = relationship("SportsGame")

    __table_args__ = (
        UniqueConstraint("game_id", "batch_key", name="uq_openai_cache_game_batch"),
        Index("idx_openai_cache_game_id", "game_id"),
    )
