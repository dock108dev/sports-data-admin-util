"""Shared helpers for sports admin routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select

from ... import db_models
from ...db import AsyncSession
from ...utils.datetime_utils import now_utc
from ...utils.reveal_utils import contains_explicit_score
from .schemas import (
    CompactMoment,
    CompactMomentsResponse,
    PlayEntry,
    ScoreChip,
    ScrapeRunResponse,
    TeamStat,
    PlayerStat,
)

COMPACT_CACHE_TTL = timedelta(seconds=30)


@dataclass
class _CompactCacheEntry:
    response: CompactMomentsResponse
    expires_at: datetime


_compact_cache: dict[int, _CompactCacheEntry] = {}


def get_compact_cache(game_id: int) -> CompactMomentsResponse | None:
    """Return cached compact moments response when still fresh."""
    entry = _compact_cache.get(game_id)
    if not entry:
        return None
    if entry.expires_at <= now_utc():
        _compact_cache.pop(game_id, None)
        return None
    return entry.response


def store_compact_cache(game_id: int, response: CompactMomentsResponse) -> None:
    """Store compact moments response for brief reuse."""
    _compact_cache[game_id] = _CompactCacheEntry(
        response=response,
        expires_at=now_utc() + COMPACT_CACHE_TTL,
    )


def build_compact_hint(play: db_models.SportsGamePlay, moment_type: str) -> str | None:
    """Create a short hint for compact moment listing."""
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


_SCORE_CHIP_LABELS = {
    1: "End Q1",
    2: "Halftime",
    3: "End Q3",
}


def build_score_chips(plays: Sequence[db_models.SportsGamePlay]) -> list[ScoreChip]:
    """Build score chips that mark quarter boundaries and current score."""
    score_chips: list[ScoreChip] = []
    boundary_play_indices: set[int] = set()

    for index, play in enumerate(plays[:-1]):
        quarter = play.quarter
        if quarter not in _SCORE_CHIP_LABELS:
            continue
        next_quarter = plays[index + 1].quarter
        if next_quarter is None or next_quarter == quarter:
            continue
        if play.home_score is None or play.away_score is None:
            continue
        score_chips.append(
            ScoreChip(
                playIndex=play.play_index,
                label=_SCORE_CHIP_LABELS[quarter],
                homeScore=play.home_score,
                awayScore=play.away_score,
            )
        )
        boundary_play_indices.add(play.play_index)

    last_scored_play = next(
        (
            play
            for play in reversed(plays)
            if play.home_score is not None and play.away_score is not None
        ),
        None,
    )
    if last_scored_play and last_scored_play.play_index not in boundary_play_indices:
        score_chips.append(
            ScoreChip(
                playIndex=last_scored_play.play_index,
                label="Current score",
                homeScore=last_scored_play.home_score,
                awayScore=last_scored_play.away_score,
            )
        )

    return score_chips


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


def find_compact_moment_bounds(
    moments: Sequence[CompactMoment],
    moment_id: int,
) -> tuple[int, int | None]:
    """Return start/end play indices for the requested compact moment."""
    for index, moment in enumerate(moments):
        if moment.play_index == moment_id:
            next_play_index = moments[index + 1].play_index if index + 1 < len(moments) else None
            end_index = next_play_index - 1 if next_play_index is not None else None
            return moment.play_index, end_index
    raise ValueError(f"Moment not found for play_index={moment_id}")


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
