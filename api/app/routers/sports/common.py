"""Shared helpers for sports admin routes."""

from __future__ import annotations

import re
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select

from ... import db_models
from ...db import AsyncSession
from ...utils.reveal_utils import contains_explicit_score
from .schemas import (
    NHLGoalieStat,
    NHLSkaterStat,
    PlayEntry,
    PlayerStat,
    ScrapeRunResponse,
    TeamStat,
)


def serialize_play_entry(play: db_models.SportsGamePlay) -> PlayEntry:
    """Serialize a play record to API response format."""
    return PlayEntry(
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


_URL_PATTERN = re.compile(r"https?://\S+")


def post_contains_score(text: str | None) -> bool:
    """Detect explicit score references in a social post."""
    return contains_explicit_score(text)


def normalize_post_text(text: str | None) -> str | None:
    """Normalize post text for deduplication."""
    if not text:
        return None
    cleaned = _URL_PATTERN.sub("", text.lower())
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def dedupe_social_posts(posts: Sequence[db_models.GameSocialPost]) -> list[db_models.GameSocialPost]:
    """Deduplicate social posts by normalized text and team id."""
    seen: set[tuple[str, int]] = set()
    deduped: list[db_models.GameSocialPost] = []
    for post in posts:
        normalized = normalize_post_text(post.tweet_text) or post.post_url
        key = (normalized, post.team_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(post)
    return deduped


async def get_league(session: AsyncSession, code: str) -> db_models.SportsLeague:
    """Fetch league by code or raise 404."""
    stmt = select(db_models.SportsLeague).where(db_models.SportsLeague.code == code.upper())
    result = await session.execute(stmt)
    league = result.scalar_one_or_none()
    if not league:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"League {code} not found")
    return league


def serialize_run(run: db_models.SportsScrapeRun, league_code: str) -> ScrapeRunResponse:
    """Serialize scrape run to API response."""
    return ScrapeRunResponse(
        id=run.id,
        league_code=league_code,
        status=run.status,
        scraper_type=run.scraper_type,
        job_id=run.job_id,
        season=run.season,
        start_date=run.start_date.date() if run.start_date else None,
        end_date=run.end_date.date() if run.end_date else None,
        summary=run.summary,
        error_details=run.error_details,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        requested_by=run.requested_by,
        config=run.config,
    )


def serialize_team_stat(box: db_models.SportsTeamBoxscore) -> TeamStat:
    """Serialize team boxscore from JSONB stats column."""
    return TeamStat(
        team=box.team.name if box.team else "Unknown",
        is_home=box.is_home,
        stats=box.stats or {},
        source=box.source,
        updated_at=box.updated_at,
    )


def _extract_minutes(stats: dict[str, Any]) -> float | None:
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
    return float(minutes_val) if isinstance(minutes_val, (int, float)) else None


def _get_int_stat(stats: dict[str, Any], normalized_key: str, raw_key: str) -> int | None:
    value = stats.get(normalized_key) or stats.get(raw_key)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def serialize_player_stat(player: db_models.SportsPlayerBoxscore) -> PlayerStat:
    """Serialize player boxscore, flattening stats for frontend display."""
    stats = player.stats or {}
    minutes_val = _extract_minutes(stats)

    return PlayerStat(
        team=player.team.name if player.team else "Unknown",
        player_name=player.player_name,
        minutes=round(minutes_val, 1) if minutes_val is not None else None,
        points=_get_int_stat(stats, "points", "pts"),
        rebounds=_get_int_stat(stats, "rebounds", "trb"),
        assists=_get_int_stat(stats, "assists", "ast"),
        yards=_get_int_stat(stats, "yards", "yds"),
        touchdowns=_get_int_stat(stats, "touchdowns", "td"),
        raw_stats=stats,
        source=player.source,
        updated_at=player.updated_at,
    )


def _extract_toi(stats: dict[str, Any]) -> str | None:
    """Extract time-on-ice, preserving MM:SS format for NHL."""
    toi = stats.get("toi") or stats.get("time_on_ice")
    if isinstance(toi, str) and ":" in toi:
        return toi
    # If stored as seconds, convert to MM:SS
    if isinstance(toi, (int, float)):
        minutes = int(toi) // 60
        seconds = int(toi) % 60
        return f"{minutes}:{seconds:02d}"
    return None


def serialize_nhl_skater(player: db_models.SportsPlayerBoxscore) -> NHLSkaterStat:
    """Serialize NHL skater boxscore with hockey-specific fields."""
    stats = player.stats or {}
    return NHLSkaterStat(
        team=player.team.name if player.team else "Unknown",
        player_name=player.player_name,
        toi=_extract_toi(stats),
        goals=_get_int_stat(stats, "goals", "g"),
        assists=_get_int_stat(stats, "assists", "a"),
        points=_get_int_stat(stats, "points", "pts"),
        shots_on_goal=_get_int_stat(stats, "shots_on_goal", "sog"),
        plus_minus=_get_int_stat(stats, "plus_minus", "+/-"),
        penalty_minutes=_get_int_stat(stats, "penalty_minutes", "pim"),
        hits=_get_int_stat(stats, "hits", "hit"),
        blocked_shots=_get_int_stat(stats, "blocked_shots", "blk"),
        raw_stats=stats,
        source=player.source,
        updated_at=player.updated_at,
    )


def _get_float_stat(stats: dict[str, Any], normalized_key: str, raw_key: str) -> float | None:
    """Extract float stat from raw or normalized key."""
    value = stats.get(normalized_key) or stats.get(raw_key)
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def serialize_nhl_goalie(player: db_models.SportsPlayerBoxscore) -> NHLGoalieStat:
    """Serialize NHL goalie boxscore with goaltender-specific fields."""
    stats = player.stats or {}
    return NHLGoalieStat(
        team=player.team.name if player.team else "Unknown",
        player_name=player.player_name,
        toi=_extract_toi(stats),
        shots_against=_get_int_stat(stats, "shots_against", "sa"),
        saves=_get_int_stat(stats, "saves", "sv"),
        goals_against=_get_int_stat(stats, "goals_against", "ga"),
        save_percentage=_get_float_stat(stats, "save_percentage", "sv_pct"),
        raw_stats=stats,
        source=player.source,
        updated_at=player.updated_at,
    )
