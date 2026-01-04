"""Admin endpoints for sports data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, desc, exists, func, select
from sqlalchemy.orm import selectinload

from sqlalchemy.sql import or_

from .. import db_models
from ..celery_client import get_celery_app
from ..db import AsyncSession, get_db
from ..services.derived_metrics import compute_derived_metrics
from ..utils.datetime_utils import now_utc

router = APIRouter(prefix="/api/admin/sports", tags=["sports-data"])

COMPACT_CACHE_TTL = timedelta(seconds=30)


@dataclass
class _CompactCacheEntry:
    response: "CompactMomentsResponse"
    expires_at: datetime


_compact_cache: dict[int, _CompactCacheEntry] = {}


class ScrapeRunConfig(BaseModel):
    """Simplified scraper configuration."""
    model_config = ConfigDict(populate_by_name=True)

    league_code: str = Field(..., alias="leagueCode")
    season: int | None = Field(None, alias="season")
    season_type: str = Field("regular", alias="seasonType")
    start_date: date | None = Field(None, alias="startDate")
    end_date: date | None = Field(None, alias="endDate")

    # Data type toggles
    boxscores: bool = Field(True, alias="boxscores")
    odds: bool = Field(True, alias="odds")
    social: bool = Field(False, alias="social")
    pbp: bool = Field(False, alias="pbp")

    # Shared filters
    only_missing: bool = Field(False, alias="onlyMissing")
    updated_before: date | None = Field(None, alias="updatedBefore")

    # Optional book filter
    include_books: list[str] | None = Field(None, alias="books")

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "league_code": self.league_code.upper(),
            "season": self.season,
            "season_type": self.season_type,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "boxscores": self.boxscores,
            "odds": self.odds,
            "social": self.social,
            "pbp": self.pbp,
            "only_missing": self.only_missing,
            "updated_before": self.updated_before.isoformat() if self.updated_before else None,
            "include_books": self.include_books,
        }


class ScrapeRunCreateRequest(BaseModel):
    config: ScrapeRunConfig
    requested_by: str | None = Field(None, alias="requestedBy")


class ScrapeRunResponse(BaseModel):
    id: int
    league_code: str
    status: str
    scraper_type: str
    season: int | None
    start_date: date | None
    end_date: date | None
    summary: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    requested_by: str | None
    config: dict[str, Any] | None = None


class GameSummary(BaseModel):
    id: int
    league_code: str
    game_date: datetime
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    has_boxscore: bool
    has_player_stats: bool
    has_odds: bool
    has_social: bool
    has_pbp: bool
    play_count: int
    social_post_count: int
    has_required_data: bool
    scrape_version: int | None
    last_scraped_at: datetime | None


class GameListResponse(BaseModel):
    games: list[GameSummary]
    total: int
    next_offset: int | None
    with_boxscore_count: int | None = 0
    with_player_stats_count: int | None = 0
    with_odds_count: int | None = 0
    with_social_count: int | None = 0
    with_pbp_count: int | None = 0


class TeamStat(BaseModel):
    team: str
    is_home: bool
    stats: dict[str, Any]
    source: str | None = None
    updated_at: datetime | None = None


class PlayerStat(BaseModel):
    team: str
    player_name: str
    # Flattened common stats for frontend display
    minutes: float | None = None
    points: int | None = None
    rebounds: int | None = None
    assists: int | None = None
    yards: int | None = None
    touchdowns: int | None = None
    # Full raw stats dict for detail view
    raw_stats: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    updated_at: datetime | None = None


class OddsEntry(BaseModel):
    book: str
    market_type: str
    side: str | None
    line: float | None
    price: float | None
    is_closing_line: bool
    observed_at: datetime | None


class GameMeta(BaseModel):
    id: int
    league_code: str
    season: int
    season_type: str | None
    game_date: datetime
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    status: str
    scrape_version: int | None
    last_scraped_at: datetime | None
    has_boxscore: bool
    has_player_stats: bool
    has_odds: bool
    has_social: bool
    has_pbp: bool
    play_count: int
    social_post_count: int
    home_team_x_handle: str | None = None
    away_team_x_handle: str | None = None


class SocialPostEntry(BaseModel):
    id: int
    post_url: str
    posted_at: datetime
    has_video: bool
    team_abbreviation: str
    tweet_text: str | None = None
    video_url: str | None = None
    image_url: str | None = None
    source_handle: str | None = None
    media_type: str | None = None


class PlayEntry(BaseModel):
    play_index: int
    quarter: int | None = None
    game_clock: str | None = None
    play_type: str | None = None
    team_abbreviation: str | None = None
    player_name: str | None = None
    description: str | None = None
    home_score: int | None = None
    away_score: int | None = None


class CompactMoment(BaseModel):
    play_index: int = Field(alias="playIndex")
    quarter: int | None = None
    game_clock: str | None = Field(None, alias="gameClock")
    moment_type: str = Field(alias="momentType")
    hint: str | None = None


class CompactMomentsResponse(BaseModel):
    moments: list[CompactMoment]
    moment_types: list[str] = Field(alias="momentTypes")


class GameDetailResponse(BaseModel):
    game: GameMeta
    team_stats: list[TeamStat]
    player_stats: list[PlayerStat]
    odds: list[OddsEntry]
    social_posts: list[SocialPostEntry]
    plays: list["PlayEntry"]
    derived_metrics: dict[str, Any]
    raw_payloads: dict[str, Any]


class JobResponse(BaseModel):
    run_id: int
    job_id: str | None
    message: str


def _get_compact_cache(game_id: int) -> CompactMomentsResponse | None:
    entry = _compact_cache.get(game_id)
    if not entry:
        return None
    if entry.expires_at <= now_utc():
        _compact_cache.pop(game_id, None)
        return None
    return entry.response


def _store_compact_cache(game_id: int, response: CompactMomentsResponse) -> None:
    _compact_cache[game_id] = _CompactCacheEntry(
        response=response,
        expires_at=now_utc() + COMPACT_CACHE_TTL,
    )


def _build_compact_hint(play: db_models.SportsGamePlay, moment_type: str) -> str | None:
    hint_parts: list[str] = []
    if isinstance(play.raw_data, dict):
        team_abbr = play.raw_data.get("team_abbreviation")
        if team_abbr:
            hint_parts.append(str(team_abbr))
    if play.player_name:
        hint_parts.append(play.player_name)
    if not hint_parts and moment_type != "unknown":
        hint_parts.append(moment_type.replace("_", " ").title())
    return " - ".join(hint_parts) if hint_parts else None


async def _get_league(session: AsyncSession, code: str) -> db_models.SportsLeague:
    stmt = select(db_models.SportsLeague).where(db_models.SportsLeague.code == code.upper())
    result = await session.execute(stmt)
    league = result.scalar_one_or_none()
    if not league:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"League {code} not found")
    return league


def _serialize_run(run: db_models.SportsScrapeRun, league_code: str) -> ScrapeRunResponse:
    """Serialize scrape run to API response."""
    from ..utils.serialization import serialize_datetime, serialize_date
    
    return ScrapeRunResponse(
        id=run.id,
        league_code=league_code,
        status=run.status,
        scraper_type=run.scraper_type,
        season=run.season,
        start_date=run.start_date.date() if run.start_date else None,
        end_date=run.end_date.date() if run.end_date else None,
        summary=run.summary,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        requested_by=run.requested_by,
        config=run.config,
    )


@router.post("/scraper/runs", response_model=ScrapeRunResponse)
async def create_scrape_run(payload: ScrapeRunCreateRequest, session: AsyncSession = Depends(get_db)) -> ScrapeRunResponse:
    league = await _get_league(session, payload.config.league_code)

    def _to_datetime(value: date | None) -> datetime | None:
        if not value:
            return None
        return datetime.combine(value, datetime.min.time())

    config_dict = payload.config.model_dump(by_alias=False)
    if config_dict.get("start_date") and isinstance(config_dict["start_date"], date):
        config_dict["start_date"] = config_dict["start_date"].isoformat()
    if config_dict.get("end_date") and isinstance(config_dict["end_date"], date):
        config_dict["end_date"] = config_dict["end_date"].isoformat()
    
    run = db_models.SportsScrapeRun(
        scraper_type="scrape",  # Simplified - no longer configurable
        league_id=league.id,
        season=payload.config.season,
        season_type=payload.config.season_type,
        start_date=_to_datetime(payload.config.start_date),
        end_date=_to_datetime(payload.config.end_date),
        status="pending",
        requested_by=payload.requested_by,
        config=config_dict,
    )
    session.add(run)
    await session.flush()

    worker_payload = payload.config.to_worker_payload()
    try:
        celery_app = get_celery_app()
        async_result = celery_app.send_task(
            "run_scrape_job",
            args=[run.id, worker_payload],
            queue="bets-scraper",
            routing_key="bets-scraper",
        )
        run.job_id = async_result.id
    except Exception as exc:  # pragma: no cover
        from ..logging_config import get_logger

        logger = get_logger(__name__)
        logger.error("failed_to_enqueue_scrape: %s", str(exc), exc_info=True)
        run.status = "error"
        run.error_details = f"Failed to enqueue scrape: {exc}"
        raise HTTPException(status_code=500, detail="Failed to enqueue scrape job") from exc

    return _serialize_run(run, league.code)


@router.get("/scraper/runs", response_model=list[ScrapeRunResponse])
async def list_scrape_runs(
    league: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[ScrapeRunResponse]:
    stmt: Select[tuple[db_models.SportsScrapeRun]] = select(db_models.SportsScrapeRun).order_by(desc(db_models.SportsScrapeRun.created_at)).limit(limit)
    if league:
        league_obj = await _get_league(session, league)
        stmt = stmt.where(db_models.SportsScrapeRun.league_id == league_obj.id)
    if status_filter:
        stmt = stmt.where(db_models.SportsScrapeRun.status == status_filter)

    results = await session.execute(stmt)
    runs = results.scalars().all()

    league_map: dict[int, str] = {}
    if runs:
        stmt_leagues = select(db_models.SportsLeague.id, db_models.SportsLeague.code).where(
            db_models.SportsLeague.id.in_({run.league_id for run in runs})
        )
        league_rows = await session.execute(stmt_leagues)
        league_map = {row.id: row.code for row in league_rows}

    return [_serialize_run(run, league_map.get(run.league_id, "UNKNOWN")) for run in runs]


@router.get("/scraper/runs/{run_id}", response_model=ScrapeRunResponse)
async def fetch_run(run_id: int, session: AsyncSession = Depends(get_db)) -> ScrapeRunResponse:
    result = await session.execute(
        select(db_models.SportsScrapeRun)
        .options(selectinload(db_models.SportsScrapeRun.league))
        .where(db_models.SportsScrapeRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    league_code = run.league.code if run.league else "UNKNOWN"
    return _serialize_run(run, league_code)


@router.post("/scraper/runs/{run_id}/cancel", response_model=ScrapeRunResponse)
async def cancel_scrape_run(run_id: int, session: AsyncSession = Depends(get_db)) -> ScrapeRunResponse:
    result = await session.execute(
        select(db_models.SportsScrapeRun)
        .options(selectinload(db_models.SportsScrapeRun.league))
        .where(db_models.SportsScrapeRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if run.status not in {"pending", "running"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending or running jobs can be canceled",
        )

    if run.job_id:
        celery_app = get_celery_app()
        try:
            celery_app.control.revoke(run.job_id, terminate=True)
        except Exception as exc:  # pragma: no cover - best-effort logging
            from ..logging_config import get_logger

            logger = get_logger(__name__)
            logger.warning("failed_to_revoke_scrape_job", run_id=run.id, job_id=run.job_id, error=str(exc))

    cancel_message = "Canceled by user via admin UI"
    now = now_utc()
    run.status = "canceled"
    run.finished_at = now
    run.summary = f"{run.summary} | {cancel_message}" if run.summary else cancel_message
    run.error_details = cancel_message
    await session.commit()
    league_code = run.league.code if run.league else "UNKNOWN"
    return _serialize_run(run, league_code)


def _apply_game_filters(
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


def _summarize_game(game: db_models.SportsGame) -> GameSummary:
    has_boxscore = bool(game.team_boxscores)
    has_player_stats = bool(game.player_boxscores)
    has_odds = bool(game.odds)
    social_posts = getattr(game, "social_posts", []) or []
    has_social = bool(social_posts)
    social_post_count = len(social_posts)
    plays = getattr(game, "plays", []) or []
    has_pbp = bool(plays)
    play_count = len(plays)
    season_type = getattr(game, "season_type", None)
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
    )


@router.get("/games", response_model=GameListResponse)
async def list_games(
    session: AsyncSession = Depends(get_db),
    league: list[str] | None = Query(None),
    season: int | None = Query(None),
    team: str | None = Query(None),
    startDate: date | None = Query(None, alias="startDate"),
    endDate: date | None = Query(None, alias="endDate"),
    missingBoxscore: bool = Query(False, alias="missingBoxscore"),
    missingPlayerStats: bool = Query(False, alias="missingPlayerStats"),
    missingOdds: bool = Query(False, alias="missingOdds"),
    missingSocial: bool = Query(False, alias="missingSocial"),
    missingAny: bool = Query(False, alias="missingAny"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> GameListResponse:
    base_stmt = select(db_models.SportsGame).options(
        selectinload(db_models.SportsGame.league),
        selectinload(db_models.SportsGame.home_team),
        selectinload(db_models.SportsGame.away_team),
        selectinload(db_models.SportsGame.team_boxscores),
        selectinload(db_models.SportsGame.player_boxscores),
        selectinload(db_models.SportsGame.odds),
        selectinload(db_models.SportsGame.social_posts),
        selectinload(db_models.SportsGame.plays),
    )

    base_stmt = _apply_game_filters(
        base_stmt,
        leagues=league,
        season=season,
        team=team,
        start_date=startDate,
        end_date=endDate,
        missing_boxscore=missingBoxscore,
        missing_player_stats=missingPlayerStats,
        missing_odds=missingOdds,
        missing_social=missingSocial,
        missing_any=missingAny,
    )

    stmt = base_stmt.order_by(desc(db_models.SportsGame.game_date)).offset(offset).limit(limit)
    results = await session.execute(stmt)
    games = results.scalars().unique().all()

    count_stmt = select(func.count(db_models.SportsGame.id))
    count_stmt = _apply_game_filters(
        count_stmt,
        leagues=league,
        season=season,
        team=team,
        start_date=startDate,
        end_date=endDate,
        missing_boxscore=missingBoxscore,
        missing_player_stats=missingPlayerStats,
        missing_odds=missingOdds,
        missing_social=missingSocial,
        missing_any=missingAny,
    )
    total = (await session.execute(count_stmt)).scalar_one()

    with_boxscore_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id))
    )
    with_player_stats_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsPlayerBoxscore.game_id == db_models.SportsGame.id))
    )
    with_odds_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsGameOdds.game_id == db_models.SportsGame.id))
    )
    with_social_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.GameSocialPost.game_id == db_models.SportsGame.id))
    )
    with_pbp_count_stmt = count_stmt.where(
        exists(select(1).where(db_models.SportsGamePlay.game_id == db_models.SportsGame.id))
    )

    with_boxscore_count = (await session.execute(with_boxscore_count_stmt)).scalar_one()
    with_player_stats_count = (await session.execute(with_player_stats_count_stmt)).scalar_one()
    with_odds_count = (await session.execute(with_odds_count_stmt)).scalar_one()
    with_social_count = (await session.execute(with_social_count_stmt)).scalar_one()
    with_pbp_count = (await session.execute(with_pbp_count_stmt)).scalar_one()

    next_offset = offset + limit if offset + limit < total else None
    summaries = [_summarize_game(game) for game in games]

    return GameListResponse(
        games=summaries,
        total=total,
        next_offset=next_offset,
        with_boxscore_count=with_boxscore_count,
        with_player_stats_count=with_player_stats_count,
        with_odds_count=with_odds_count,
        with_social_count=with_social_count,
        with_pbp_count=with_pbp_count,
    )


def _serialize_team_stat(box: db_models.SportsTeamBoxscore) -> TeamStat:
    """Serialize team boxscore from JSONB stats column."""
    return TeamStat(
        team=box.team.name if box.team else "Unknown",
        is_home=box.is_home,
        stats=box.stats or {},
        source=box.source,
        updated_at=box.updated_at,
    )


def _serialize_player_stat(player: db_models.SportsPlayerBoxscore) -> PlayerStat:
    """Serialize player boxscore, flattening stats for frontend display."""
    stats = player.stats or {}
    
    # Parse minutes from various formats (e.g., "30:18" -> 30.3, or direct float)
    minutes_val = stats.get("minutes") or stats.get("mp")
    if isinstance(minutes_val, str) and ":" in minutes_val:
        parts = minutes_val.split(":")
        try:
            minutes_val = int(parts[0]) + int(parts[1]) / 60
        except (ValueError, IndexError):
            minutes_val = None
    elif isinstance(minutes_val, str):
        try:
            minutes_val = float(minutes_val)
        except ValueError:
            minutes_val = None
    
    # Helper to get int stat from either normalized or raw key
    def get_int(normalized_key: str, raw_key: str) -> int | None:
        val = stats.get(normalized_key) or stats.get(raw_key)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    
    return PlayerStat(
        team=player.team.name if player.team else "Unknown",
        player_name=player.player_name,
        minutes=round(minutes_val, 1) if minutes_val else None,
        points=get_int("points", "pts"),
        rebounds=get_int("rebounds", "trb"),
        assists=get_int("assists", "ast"),
        yards=get_int("yards", "yds"),
        touchdowns=get_int("touchdowns", "td"),
        raw_stats=stats,
        source=player.source,
        updated_at=player.updated_at,
    )


@router.get("/games/{game_id}/compact", response_model=CompactMomentsResponse)
async def get_game_compact(game_id: int, session: AsyncSession = Depends(get_db)) -> CompactMomentsResponse:
    cached = _get_compact_cache(game_id)
    if cached:
        return cached

    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = plays_result.scalars().all()

    moments: list[CompactMoment] = []
    moment_types: list[str] = []

    for play in plays:
        moment_type = play.play_type or "unknown"
        if moment_type not in moment_types:
            moment_types.append(moment_type)
        moments.append(
            CompactMoment(
                playIndex=play.play_index,
                quarter=play.quarter,
                gameClock=play.game_clock,
                momentType=moment_type,
                hint=_build_compact_hint(play, moment_type),
            )
        )

    response = CompactMomentsResponse(moments=moments, momentTypes=moment_types)
    _store_compact_cache(game_id, response)
    return response


@router.get("/games/{game_id}", response_model=GameDetailResponse)
async def get_game(game_id: int, session: AsyncSession = Depends(get_db)) -> GameDetailResponse:
    result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.league),
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
            selectinload(db_models.SportsGame.team_boxscores).selectinload(db_models.SportsTeamBoxscore.team),
            selectinload(db_models.SportsGame.player_boxscores).selectinload(db_models.SportsPlayerBoxscore.team),
            selectinload(db_models.SportsGame.odds),
            selectinload(db_models.SportsGame.social_posts),
            selectinload(db_models.SportsGame.plays),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    team_stats = [_serialize_team_stat(box) for box in game.team_boxscores]
    player_stats = [_serialize_player_stat(player) for player in game.player_boxscores]
    odds_entries = [
        OddsEntry(
            book=odd.book,
            market_type=odd.market_type,
            side=odd.side,
            line=odd.line,
            price=odd.price,
            is_closing_line=odd.is_closing_line,
            observed_at=odd.observed_at,
        )
        for odd in game.odds
    ]

    plays_entries: list[PlayEntry] = []
    for play in sorted(game.plays, key=lambda p: p.play_index):
        plays_entries.append(
            PlayEntry(
                play_index=play.play_index,
                quarter=play.quarter,
                game_clock=play.game_clock,
                play_type=play.play_type,
                team_abbreviation=play.raw_data.get("team_abbreviation") if isinstance(play.raw_data, dict) else None,
                player_name=play.player_name,
                description=play.description,
                home_score=play.home_score,
                away_score=play.away_score,
            )
        )

    meta = GameMeta(
        id=game.id,
        league_code=game.league.code if game.league else "UNKNOWN",
        season=game.season,
        season_type=getattr(game, "season_type", None),
        game_date=game.game_date,
        home_team=game.home_team.name if game.home_team else "Unknown",
        away_team=game.away_team.name if game.away_team else "Unknown",
        home_score=game.home_score,
        away_score=game.away_score,
        status=game.status,
        scrape_version=getattr(game, "scrape_version", None),
        last_scraped_at=game.last_scraped_at,
        has_boxscore=bool(game.team_boxscores),
        has_player_stats=bool(game.player_boxscores),
        has_odds=bool(game.odds),
        has_social=bool(game.social_posts),
        has_pbp=bool(game.plays),
        play_count=len(game.plays) if game.plays else 0,
        social_post_count=len(game.social_posts) if game.social_posts else 0,
        home_team_x_handle=game.home_team.x_handle if game.home_team else None,
        away_team_x_handle=game.away_team.x_handle if game.away_team else None,
    )

    # Serialize social posts
    social_posts_entries = []
    for post in (game.social_posts or []):
        # Get team abbreviation - need to load team relationship
        team_abbr = "UNK"
        if hasattr(post, "team") and post.team:
            team_abbr = post.team.abbreviation
        elif hasattr(post, "team_id"):
            # Try to find team from game's teams
            if game.home_team and game.home_team.id == post.team_id:
                team_abbr = game.home_team.abbreviation
            elif game.away_team and game.away_team.id == post.team_id:
                team_abbr = game.away_team.abbreviation
        
        social_posts_entries.append(SocialPostEntry(
            id=post.id,
            post_url=post.post_url,
            posted_at=post.posted_at,
            has_video=post.has_video,
            team_abbreviation=team_abbr,
            tweet_text=post.tweet_text,
            video_url=post.video_url,
            image_url=post.image_url,
            source_handle=post.source_handle,
            media_type=post.media_type,
        ))

    derived = compute_derived_metrics(game, game.odds)
    raw_payloads = {
        "team_boxscores": [
            {
                "team": box.team.name if box.team else "Unknown",
                "stats": box.stats,
                "source": box.source,
            }
            for box in game.team_boxscores
            if box.stats
        ],
        "player_boxscores": [
            {
                "team": player.team.name if player.team else "Unknown",
                "player": player.player_name,
                "stats": player.stats,
            }
            for player in game.player_boxscores
            if player.stats
        ],
        "odds": [
            {
                "book": odd.book,
                "market_type": odd.market_type,
                "raw": odd.raw_payload,
            }
            for odd in game.odds
            if odd.raw_payload
        ],
    }

    return GameDetailResponse(
        game=meta,
        team_stats=team_stats,
        player_stats=player_stats,
        odds=odds_entries,
        social_posts=social_posts_entries,
        plays=plays_entries,
        derived_metrics=derived,
        raw_payloads=raw_payloads,
    )


async def _enqueue_single_game_run(
    session: AsyncSession,
    game: db_models.SportsGame,
    *,
    include_boxscores: bool,
    include_odds: bool,
    scraper_type: str,
) -> JobResponse:
    # Ensure league is loaded without triggering lazy load in async context
    await session.refresh(game, attribute_names=["league"])
    if not game.league:
        raise HTTPException(status_code=400, detail="League missing for game")

    config = ScrapeRunConfig(
        league_code=game.league.code,
        scraper_type=scraper_type,
        season=game.season,
        season_type=getattr(game, "season_type", "regular"),
        start_date=game.game_date.date(),
        end_date=game.game_date.date(),
        include_boxscores=include_boxscores,
        include_odds=include_odds,
        rescrape_existing=True,
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


@router.post("/games/{game_id}/rescrape", response_model=JobResponse)
async def rescrape_game(game_id: int, session: AsyncSession = Depends(get_db)) -> JobResponse:
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return await _enqueue_single_game_run(
        session,
        game,
        include_boxscores=True,
        include_odds=False,
        scraper_type="game_rescrape",
    )


@router.post("/games/{game_id}/resync-odds", response_model=JobResponse)
async def resync_game_odds(game_id: int, session: AsyncSession = Depends(get_db)) -> JobResponse:
    game = await session.get(db_models.SportsGame, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return await _enqueue_single_game_run(
        session,
        game,
        include_boxscores=False,
        include_odds=True,
        scraper_type="odds_resync",
    )


# ────────────────────────────────────────────────────────────────────────────────
# Teams endpoints
# ────────────────────────────────────────────────────────────────────────────────


class TeamSummary(BaseModel):
    """Team summary for list view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str = Field(alias="shortName")
    abbreviation: str
    league_code: str = Field(alias="leagueCode")
    games_count: int = Field(alias="gamesCount")


class TeamListResponse(BaseModel):
    """Response for teams list endpoint."""

    teams: list[TeamSummary]
    total: int


class TeamGameSummary(BaseModel):
    """Game summary for team detail."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    game_date: str = Field(alias="gameDate")
    opponent: str
    is_home: bool = Field(alias="isHome")
    score: str
    result: str


class TeamDetail(BaseModel):
    """Team detail with recent games."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str = Field(alias="shortName")
    abbreviation: str
    league_code: str = Field(alias="leagueCode")
    location: str | None
    external_ref: str | None = Field(alias="externalRef")
    x_handle: str | None = Field(None, alias="xHandle")
    x_profile_url: str | None = Field(None, alias="xProfileUrl")
    recent_games: list[TeamGameSummary] = Field(alias="recentGames")


@router.get("/teams", response_model=TeamListResponse)
async def list_teams(
    league: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    session: AsyncSession = Depends(get_db),
) -> TeamListResponse:
    """List teams with optional league filter and search."""

    # Base query with game count subquery
    games_as_home = (
        select(func.count())
        .where(db_models.SportsGame.home_team_id == db_models.SportsTeam.id)
        .correlate(db_models.SportsTeam)
        .scalar_subquery()
    )
    games_as_away = (
        select(func.count())
        .where(db_models.SportsGame.away_team_id == db_models.SportsTeam.id)
        .correlate(db_models.SportsTeam)
        .scalar_subquery()
    )

    stmt = (
        select(
            db_models.SportsTeam,
            db_models.SportsLeague.code.label("league_code"),
            (games_as_home + games_as_away).label("games_count"),
        )
        .join(db_models.SportsLeague, db_models.SportsTeam.league_id == db_models.SportsLeague.id)
    )

    if league:
        stmt = stmt.where(func.upper(db_models.SportsLeague.code) == league.upper())

    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                db_models.SportsTeam.name.ilike(search_pattern),
                db_models.SportsTeam.short_name.ilike(search_pattern),
                db_models.SportsTeam.abbreviation.ilike(search_pattern),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # Apply pagination and ordering
    stmt = stmt.order_by(db_models.SportsTeam.name).offset(offset).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    teams = [
        TeamSummary(
            id=row.SportsTeam.id,
            name=row.SportsTeam.name,
            shortName=row.SportsTeam.short_name,
            abbreviation=row.SportsTeam.abbreviation,
            leagueCode=row.league_code,
            gamesCount=row.games_count or 0,
        )
        for row in rows
    ]

    return TeamListResponse(teams=teams, total=total)


@router.get("/teams/{team_id}", response_model=TeamDetail)
async def get_team(team_id: int, session: AsyncSession = Depends(get_db)) -> TeamDetail:
    """Get team detail with recent games."""

    team = await session.get(db_models.SportsTeam, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    league = await session.get(db_models.SportsLeague, team.league_id)

    # Get recent games
    home_games = (
        select(db_models.SportsGame)
        .where(db_models.SportsGame.home_team_id == team_id)
        .options(selectinload(db_models.SportsGame.away_team))
    )
    away_games = (
        select(db_models.SportsGame)
        .where(db_models.SportsGame.away_team_id == team_id)
        .options(selectinload(db_models.SportsGame.home_team))
    )

    home_result = await session.execute(home_games.order_by(desc(db_models.SportsGame.game_date)).limit(10))
    away_result = await session.execute(away_games.order_by(desc(db_models.SportsGame.game_date)).limit(10))

    recent_games: list[TeamGameSummary] = []

    for game in home_result.scalars():
        score = f"{game.home_score or 0}-{game.away_score or 0}"
        result = "W" if (game.home_score or 0) > (game.away_score or 0) else "L" if (game.home_score or 0) < (game.away_score or 0) else "-"
        recent_games.append(
            TeamGameSummary(
                id=game.id,
                gameDate=game.game_date.isoformat() if game.game_date else "",
                opponent=game.away_team.name if game.away_team else "Unknown",
                isHome=True,
                score=score,
                result=result,
            )
        )

    for game in away_result.scalars():
        score = f"{game.away_score or 0}-{game.home_score or 0}"
        result = "W" if (game.away_score or 0) > (game.home_score or 0) else "L" if (game.away_score or 0) < (game.home_score or 0) else "-"
        recent_games.append(
            TeamGameSummary(
                id=game.id,
                gameDate=game.game_date.isoformat() if game.game_date else "",
                opponent=game.home_team.name if game.home_team else "Unknown",
                isHome=False,
                score=score,
                result=result,
            )
        )

    # Sort by date descending and limit to 20
    recent_games.sort(key=lambda g: g.game_date, reverse=True)
    recent_games = recent_games[:20]

    return TeamDetail(
        id=team.id,
        name=team.name,
        shortName=team.short_name,
        abbreviation=team.abbreviation,
        leagueCode=league.code if league else "UNK",
        location=team.location,
        externalRef=team.external_ref,
        xHandle=team.x_handle,
        xProfileUrl=f"https://x.com/{team.x_handle}" if team.x_handle else None,
        recentGames=recent_games,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Team Social Info
# ────────────────────────────────────────────────────────────────────────────────


class TeamSocialInfo(BaseModel):
    """Team social media information."""

    team_id: int = Field(..., alias="teamId")
    abbreviation: str
    x_handle: str | None = Field(None, alias="xHandle")
    x_profile_url: str | None = Field(None, alias="xProfileUrl")


@router.get("/teams/{team_id}/social", response_model=TeamSocialInfo)
async def get_team_social_info(team_id: int, session: AsyncSession = Depends(get_db)) -> TeamSocialInfo:
    """Get team's social media info including X handle."""
    team = await session.get(db_models.SportsTeam, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    return TeamSocialInfo(
        teamId=team.id,
        abbreviation=team.abbreviation or "",
        xHandle=team.x_handle,
        xProfileUrl=f"https://x.com/{team.x_handle}" if team.x_handle else None,
    )
