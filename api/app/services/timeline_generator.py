"""Timeline artifact generation for finalized games."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import db_models
from ..db import AsyncSession
from ..utils.datetime_utils import now_utc

logger = logging.getLogger(__name__)

NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_PREGAME_REAL_SECONDS = 10 * 60
NBA_OVERTIME_PADDING_SECONDS = 30 * 60
DEFAULT_TIMELINE_VERSION = "v1"


@dataclass(frozen=True)
class TimelineArtifactPayload:
    game_id: int
    sport: str
    timeline_version: str
    generated_at: datetime
    timeline: list[dict[str, Any]]
    summary: dict[str, Any]


class TimelineGenerationError(Exception):
    """Raised when timeline generation fails due to invalid input."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _parse_clock_to_seconds(clock: str | None) -> int | None:
    if not clock:
        return None
    parts = clock.split(":")
    if len(parts) != 2:
        return None
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
    except ValueError:
        return None
    if minutes < 0 or seconds < 0 or seconds >= 60:
        return None
    return minutes * 60 + seconds


def _progress_from_index(index: int, total: int) -> float:
    if total <= 1:
        return 0.5
    return index / (total - 1)


def _nba_block_for_quarter(quarter: int | None) -> str:
    if quarter is None:
        return "pregame"
    if quarter == 1:
        return "q1"
    if quarter == 2:
        return "q2"
    if quarter == 3:
        return "q3"
    if quarter == 4:
        return "q4"
    return "postgame"


def _nba_quarter_start(game_start: datetime, quarter: int) -> datetime:
    halftime_offset = NBA_HALFTIME_REAL_SECONDS if quarter >= 3 else 0
    return game_start + timedelta(seconds=(quarter - 1) * NBA_QUARTER_REAL_SECONDS + halftime_offset)


def _nba_regulation_end(game_start: datetime) -> datetime:
    return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS)


def _nba_game_end(game_start: datetime, plays: Sequence[db_models.SportsGamePlay]) -> datetime:
    has_overtime = any((play.quarter or 0) > 4 for play in plays)
    end_time = _nba_regulation_end(game_start)
    if has_overtime:
        end_time += timedelta(seconds=NBA_OVERTIME_PADDING_SECONDS)
    return end_time


def _build_pbp_events(
    plays: Sequence[db_models.SportsGamePlay],
    game_start: datetime,
) -> list[tuple[datetime, dict[str, Any]]]:
    grouped: dict[int | None, list[db_models.SportsGamePlay]] = {}
    for play in plays:
        grouped.setdefault(play.quarter, []).append(play)

    events: list[tuple[datetime, dict[str, Any]]] = []
    for quarter, quarter_plays in sorted(grouped.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        sorted_plays = sorted(quarter_plays, key=lambda play: play.play_index)
        block = _nba_block_for_quarter(quarter)

        if quarter is None:
            window_start = game_start - timedelta(seconds=NBA_PREGAME_REAL_SECONDS)
            window_seconds = NBA_PREGAME_REAL_SECONDS
        elif quarter <= 4:
            window_start = _nba_quarter_start(game_start, quarter)
            window_seconds = NBA_QUARTER_REAL_SECONDS
        else:
            window_start = _nba_regulation_end(game_start)
            window_seconds = NBA_OVERTIME_PADDING_SECONDS

        for index, play in enumerate(sorted_plays):
            remaining_seconds = _parse_clock_to_seconds(play.game_clock)
            if quarter and quarter <= 4 and remaining_seconds is not None:
                progress = (NBA_QUARTER_GAME_SECONDS - remaining_seconds) / NBA_QUARTER_GAME_SECONDS
            else:
                progress = _progress_from_index(index, len(sorted_plays))

            progress = min(max(progress, 0.0), 1.0)
            event_time = window_start + timedelta(seconds=window_seconds * progress)
            event_payload = {
                "event_type": "pbp",
                "play_index": play.play_index,
                "quarter": play.quarter,
                "game_clock": play.game_clock,
                "play_type": play.play_type,
                "team_id": play.team_id,
                "player_id": play.player_id,
                "player_name": play.player_name,
                "description": play.description,
                "home_score": play.home_score,
                "away_score": play.away_score,
                "synthetic_timestamp": event_time.isoformat(),
                "timeline_block": block,
            }
            events.append((event_time, event_payload))

    return events


def _build_social_events(posts: Iterable[db_models.GameSocialPost]) -> list[tuple[datetime, dict[str, Any]]]:
    events: list[tuple[datetime, dict[str, Any]]] = []
    for post in posts:
        event_time = post.posted_at
        event_payload = {
            "event_type": "tweet",
            "id": post.id,
            "post_url": post.post_url,
            "tweet_text": post.tweet_text,
            "posted_at": post.posted_at.isoformat(),
            "team_id": post.team_id,
            "source_handle": post.source_handle,
            "media_type": post.media_type,
            "synthetic_timestamp": event_time.isoformat(),
        }
        events.append((event_time, event_payload))
    return events


def build_nba_summary(
    game: db_models.SportsGame,
) -> dict[str, Any]:
    home_name = game.home_team.name if game.home_team else "Home"
    away_name = game.away_team.name if game.away_team else "Away"
    home_score = game.home_score
    away_score = game.away_score

    flow = "unknown"
    if home_score is not None and away_score is not None:
        diff = abs(home_score - away_score)
        if diff <= 5:
            flow = "close"
        elif diff <= 12:
            flow = "competitive"
        elif diff <= 20:
            flow = "comfortable"
        else:
            flow = "blowout"

    return {
        "teams": {
            "home": {"id": game.home_team_id, "name": home_name},
            "away": {"id": game.away_team_id, "name": away_name},
        },
        "final_score": {"home": home_score, "away": away_score},
        "flow": flow,
    }


def build_nba_timeline(
    game: db_models.SportsGame,
    plays: Sequence[db_models.SportsGamePlay],
    social_posts: Sequence[db_models.GameSocialPost],
) -> tuple[list[dict[str, Any]], dict[str, Any], datetime]:
    game_start = game.start_time
    game_end = _nba_game_end(game_start, plays)

    pbp_events = _build_pbp_events(plays, game_start)
    social_events = _build_social_events(social_posts)
    merged = pbp_events + social_events

    def sort_key(item: tuple[datetime, dict[str, Any]]) -> tuple[datetime, int, int]:
        event_time, payload = item
        type_order = 0 if payload.get("event_type") == "pbp" else 1
        play_index = payload.get("play_index") or 0
        return (event_time, type_order, play_index)

    timeline = [payload for _, payload in sorted(merged, key=sort_key)]
    summary = build_nba_summary(game)
    return timeline, summary, game_end


async def generate_timeline_artifact(
    session: AsyncSession,
    game_id: int,
    timeline_version: str = DEFAULT_TIMELINE_VERSION,
) -> TimelineArtifactPayload:
    result = await session.execute(
        select(db_models.SportsGame)
        .options(
            selectinload(db_models.SportsGame.league),
            selectinload(db_models.SportsGame.home_team),
            selectinload(db_models.SportsGame.away_team),
        )
        .where(db_models.SportsGame.id == game_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise TimelineGenerationError("Game not found", status_code=404)

    league_code = game.league.code if game.league else ""
    if league_code != "NBA":
        raise TimelineGenerationError("Timeline generation only supported for NBA", status_code=422)

    plays_result = await session.execute(
        select(db_models.SportsGamePlay)
        .where(db_models.SportsGamePlay.game_id == game_id)
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays = plays_result.scalars().all()

    game_start = game.start_time
    game_end = _nba_game_end(game_start, plays)

    posts_result = await session.execute(
        select(db_models.GameSocialPost)
        .where(
            db_models.GameSocialPost.game_id == game_id,
            db_models.GameSocialPost.posted_at >= game_start,
            db_models.GameSocialPost.posted_at <= game_end,
        )
        .order_by(db_models.GameSocialPost.posted_at)
    )
    posts = posts_result.scalars().all()

    timeline, summary, _ = build_nba_timeline(game, plays, posts)
    generated_at = now_utc()

    artifact_result = await session.execute(
        select(db_models.SportsGameTimelineArtifact).where(
            db_models.SportsGameTimelineArtifact.game_id == game_id,
            db_models.SportsGameTimelineArtifact.sport == "NBA",
            db_models.SportsGameTimelineArtifact.timeline_version == timeline_version,
        )
    )
    artifact = artifact_result.scalar_one_or_none()

    if artifact is None:
        artifact = db_models.SportsGameTimelineArtifact(
            game_id=game_id,
            sport="NBA",
            timeline_version=timeline_version,
            generated_at=generated_at,
            timeline_json=timeline,
            summary_json=summary,
        )
        session.add(artifact)
    else:
        artifact.generated_at = generated_at
        artifact.timeline_json = timeline
        artifact.summary_json = summary

    await session.flush()

    logger.info(
        "timeline_artifact_generated",
        extra={
            "game_id": game_id,
            "timeline_version": timeline_version,
            "timeline_events": len(timeline),
            "social_posts": len(posts),
            "plays": len(plays),
        },
    )

    return TimelineArtifactPayload(
        game_id=game_id,
        sport="NBA",
        timeline_version=timeline_version,
        generated_at=generated_at,
        timeline=timeline,
        summary=summary,
    )
