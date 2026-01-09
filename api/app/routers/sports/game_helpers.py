"""Shared helper utilities for sports game endpoints."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import Select
from sqlalchemy.sql import or_

from ... import db_models
from ...celery_client import get_celery_app
from ...game_metadata.models import GameContext, StandingsEntry, TeamRatings
from .schemas import JobResponse, ScrapeRunConfig, SocialPostEntry

logger = logging.getLogger(__name__)

PREVIEW_TOP25_ELO_THRESHOLD = 1600.0
PREVIEW_TOP_RATED_SEED_THRESHOLD = 4
PREVIEW_BIG_NAME_SEED_THRESHOLD = 5
PREVIEW_SEEDING_BATTLE_SEED_THRESHOLD = 8
PREVIEW_NATIONAL_ELO_THRESHOLD = 1650.0
PREVIEW_ELO_SPREAD_DIVISOR = 30.0
PREVIEW_TOTAL_BASE = 135.0
PREVIEW_TOTAL_ELO_BASELINE = 1500.0
PREVIEW_TOTAL_ELO_DIVISOR = 20.0
PREVIEW_TOTAL_MIN = 100.0
PREVIEW_TOTAL_MAX = 180.0


def apply_game_filters(
    stmt: Select[tuple[db_models.SportsGame]],
    leagues: Sequence[str] | None,
    season: int | None,
    team: str | None,
    start_date: date | None,
    end_date: date | None,
    missing_boxscore: bool,
    missing_player_stats: bool,
    missing_odds: bool,
    missing_social: bool,
    missing_any: bool,
) -> Select[tuple[db_models.SportsGame]]:
    """Apply filtering options for list endpoints."""
    if leagues:
        league_codes = [code.upper() for code in leagues]
        stmt = stmt.where(db_models.SportsGame.league.has(db_models.SportsLeague.code.in_(league_codes)))

    if season is not None:
        stmt = stmt.where(db_models.SportsGame.season == season)

    if team:
        pattern = f"%{team}%"
        stmt = stmt.where(
            or_(
                db_models.SportsGame.home_team.has(db_models.SportsTeam.name.ilike(pattern)),
                db_models.SportsGame.away_team.has(db_models.SportsTeam.name.ilike(pattern)),
                db_models.SportsGame.home_team.has(db_models.SportsTeam.short_name.ilike(pattern)),
                db_models.SportsGame.away_team.has(db_models.SportsTeam.short_name.ilike(pattern)),
                db_models.SportsGame.home_team.has(db_models.SportsTeam.abbreviation.ilike(pattern)),
                db_models.SportsGame.away_team.has(db_models.SportsTeam.abbreviation.ilike(pattern)),
            )
        )

    if start_date:
        start_dt = datetime.combine(start_date, datetime.min.time())
        stmt = stmt.where(db_models.SportsGame.game_date >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, datetime.max.time())
        stmt = stmt.where(db_models.SportsGame.game_date <= end_dt)

    if missing_boxscore:
        stmt = stmt.where(~db_models.SportsGame.team_boxscores.any())
    if missing_player_stats:
        stmt = stmt.where(~db_models.SportsGame.player_boxscores.any())
    if missing_odds:
        stmt = stmt.where(~db_models.SportsGame.odds.any())
    if missing_social:
        stmt = stmt.where(~db_models.SportsGame.social_posts.any())
    if missing_any:
        stmt = stmt.where(
            or_(
                ~db_models.SportsGame.team_boxscores.any(),
                ~db_models.SportsGame.player_boxscores.any(),
                ~db_models.SportsGame.odds.any(),
            )
        )
    return stmt


def clamp_score(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    """Clamp scores to a consistent 0-100 range."""
    return max(minimum, min(maximum, value))


def normalize_score(value: float) -> int:
    """Normalize score values for API responses."""
    return int(round(clamp_score(value)))


def resolve_team_key(team: db_models.SportsTeam) -> str:
    """Resolve the identifier used by ratings/standings feeds."""
    if team.external_ref:
        return team.external_ref
    for code in team.external_codes.values():
        if isinstance(code, str) and code.strip():
            return code
    return str(team.id)


def select_preview_entry(
    entries: Sequence[StandingsEntry] | Sequence[TeamRatings],
    team_key: str,
    fallback_index: int,
    entry_label: str,
) -> StandingsEntry | TeamRatings:
    """Select rating/standings entry for a team or fallback entry."""
    for entry in entries:
        if entry.team_id == team_key:
            return entry
    if entries and 0 <= fallback_index < len(entries):
        logger.warning(
            "Preview score falling back to mock %s data",
            entry_label,
            extra={"team_key": team_key, "fallback_index": fallback_index},
        )
        return entries[fallback_index]
    raise ValueError(f"Preview score missing {entry_label} data")


def projected_spread(home_rating: TeamRatings, away_rating: TeamRatings) -> float:
    """Estimate point spread based on ELO."""
    return (home_rating.elo - away_rating.elo) / PREVIEW_ELO_SPREAD_DIVISOR


def projected_total(home_rating: TeamRatings, away_rating: TeamRatings) -> float:
    """Estimate total based on average ELO."""
    average_elo = (home_rating.elo + away_rating.elo) / 2
    raw_total = PREVIEW_TOTAL_BASE + (
        (average_elo - PREVIEW_TOTAL_ELO_BASELINE) / PREVIEW_TOTAL_ELO_DIVISOR
    )
    return clamp_score(raw_total, PREVIEW_TOTAL_MIN, PREVIEW_TOTAL_MAX)


def preview_tags(
    home_rating: TeamRatings,
    away_rating: TeamRatings,
    home_standing: StandingsEntry,
    away_standing: StandingsEntry,
) -> list[str]:
    """Build preview tags based on ratings + standings context."""
    tags: set[str] = set()
    top_two = max(home_standing.conference_rank, away_standing.conference_rank) <= 2
    if top_two:
        tags.update({"conference_lead", "top_two_conference"})

    if min(home_rating.elo, away_rating.elo) >= PREVIEW_TOP25_ELO_THRESHOLD:
        tags.add("top25_matchup")

    seeds = [seed for seed in (home_rating.projected_seed, away_rating.projected_seed) if seed is not None]
    if len(seeds) == 2:
        if max(seeds) <= PREVIEW_TOP_RATED_SEED_THRESHOLD:
            tags.update({"top_rated", "tournament_preview"})
        if max(seeds) <= PREVIEW_SEEDING_BATTLE_SEED_THRESHOLD:
            tags.add("seeding_battle")

    return sorted(tags)


def build_preview_context(
    game: db_models.SportsGame,
    home_rating: TeamRatings,
    away_rating: TeamRatings,
) -> GameContext:
    """Assemble a GameContext to generate preview scores."""
    rivalry = home_rating.conference == away_rating.conference
    projected_spread_value = projected_spread(home_rating, away_rating)
    projected_total_value = projected_total(home_rating, away_rating)
    has_big_name_players = any(
        seed is not None and seed <= PREVIEW_BIG_NAME_SEED_THRESHOLD
        for seed in (home_rating.projected_seed, away_rating.projected_seed)
    )
    playoff_implications = all(
        seed is not None for seed in (home_rating.projected_seed, away_rating.projected_seed)
    )
    national_broadcast = (home_rating.elo + away_rating.elo) / 2 >= PREVIEW_NATIONAL_ELO_THRESHOLD

    return GameContext(
        game_id=str(game.id),
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        league=game.league.code if game.league else "UNKNOWN",
        start_time=game.game_date,
        rivalry=rivalry,
        projected_spread=projected_spread_value,
        has_big_name_players=has_big_name_players,
        coach_vs_former_team=False,
        playoff_implications=playoff_implications,
        national_broadcast=national_broadcast,
        projected_total=projected_total_value,
    )


def summarize_game(game: db_models.SportsGame) -> "GameSummary":
    """Summarize game fields for list responses."""
    from .schemas import GameSummary

    has_boxscore = bool(game.team_boxscores)
    has_player_stats = bool(game.player_boxscores)
    has_odds = bool(game.odds)
    social_posts = getattr(game, "social_posts", []) or []
    has_social = bool(social_posts)
    social_post_count = len(social_posts)
    plays = getattr(game, "plays", []) or []
    has_pbp = bool(plays)
    play_count = len(plays)
    return GameSummary(
        id=game.id,
        league_code=game.league.code if game.league else "UNKNOWN",
        game_date=game.game_date,
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        home_score=game.home_score,
        away_score=game.away_score,
        has_boxscore=has_boxscore,
        has_player_stats=has_player_stats,
        has_odds=has_odds,
        has_social=has_social,
        has_pbp=has_pbp,
        play_count=play_count,
        social_post_count=social_post_count,
        has_required_data=has_boxscore and has_odds,
        scrape_version=getattr(game, "scrape_version", None),
        last_scraped_at=game.last_scraped_at,
        last_ingested_at=game.last_ingested_at,
        last_pbp_at=game.last_pbp_at,
        last_social_at=game.last_social_at,
    )


def resolve_team_abbreviation(game: db_models.SportsGame, post: db_models.GameSocialPost) -> str:
    """Resolve a team's abbreviation for a social post entry."""
    if hasattr(post, "team") and post.team and post.team.abbreviation:
        return post.team.abbreviation
    if hasattr(post, "team_id"):
        if game.home_team and game.home_team.id == post.team_id:
            return game.home_team.abbreviation
        if game.away_team and game.away_team.id == post.team_id:
            return game.away_team.abbreviation
    return "UNK"


def serialize_social_posts(
    game: db_models.SportsGame,
    posts: Sequence[db_models.GameSocialPost],
) -> list[SocialPostEntry]:
    """Serialize social posts for API responses."""
    entries: list[SocialPostEntry] = []
    for post in posts:
        entries.append(
            SocialPostEntry(
                id=post.id,
                post_url=post.post_url,
                posted_at=post.posted_at,
                has_video=post.has_video,
                team_abbreviation=resolve_team_abbreviation(game, post),
                tweet_text=post.tweet_text,
                video_url=post.video_url,
                image_url=post.image_url,
                source_handle=post.source_handle,
                media_type=post.media_type,
            )
        )
    return entries


async def enqueue_single_game_run(
    session: "AsyncSession",
    game: db_models.SportsGame,
    *,
    include_boxscores: bool,
    include_odds: bool,
    scraper_type: str,
) -> JobResponse:
    """Create a scrape run and enqueue it for a single game."""

    await session.refresh(game, attribute_names=["league"])
    if not game.league:
        raise HTTPException(status_code=400, detail="League missing for game")

    config = ScrapeRunConfig(
        league_code=game.league.code,
        season=game.season,
        season_type=getattr(game, "season_type", "regular"),
        start_date=game.game_date.date(),
        end_date=game.game_date.date(),
        boxscores=include_boxscores,
        odds=include_odds,
        social=False,
        pbp=False,
        only_missing=False,
        updated_before=None,
        include_books=None,
    )

    run = db_models.SportsScrapeRun(
        scraper_type=scraper_type,
        league_id=game.league_id,
        season=game.season,
        season_type=getattr(game, "season_type", "regular"),
        start_date=datetime.combine(game.game_date.date(), datetime.min.time()),
        end_date=datetime.combine(game.game_date.date(), datetime.min.time()),
        status="pending",
        requested_by="admin_boxscore_viewer",
        config=config.model_dump(by_alias=False),
    )
    session.add(run)
    await session.flush()

    worker_payload = config.to_worker_payload()
    celery_app = get_celery_app()
    async_result = celery_app.send_task(
        "run_scrape_job",
        args=[run.id, worker_payload],
        queue="bets-scraper",
        routing_key="bets-scraper",
    )
    run.job_id = async_result.id

    return JobResponse(run_id=run.id, job_id=async_result.id, message="Job enqueued")
