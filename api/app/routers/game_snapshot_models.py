"""Shared Pydantic models and helpers for game snapshot routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from pydantic import BaseModel

from .. import db_models
from ..services.reveal_levels import RevealLevel
from ..utils.reveal_utils import classify_reveal_risk


class TeamSnapshot(BaseModel):
    """Minimal team identity for snapshot responses."""

    id: int
    name: str
    abbreviation: str | None


class GameSnapshot(BaseModel):
    """Minimal game record for app snapshots."""

    id: int
    league: str
    status: str
    start_time: datetime
    home_team: TeamSnapshot
    away_team: TeamSnapshot
    has_pbp: bool
    has_social: bool
    has_story: bool
    last_updated_at: datetime


class GameSnapshotResponse(BaseModel):
    """List response for snapshot games."""

    range: str
    games: list[GameSnapshot]


class PbpEvent(BaseModel):
    """Play-by-play entry with raw description."""

    index: int
    clock: str | None
    description: str | None
    play_type: str | None


class PbpPeriod(BaseModel):
    """Play-by-play entries grouped by period."""

    period: int | None
    events: list[PbpEvent]


class PbpResponse(BaseModel):
    """Response wrapper for grouped play-by-play."""

    periods: list[PbpPeriod]


class SocialPostSnapshot(BaseModel):
    """Social post entry with reveal classification."""

    id: int
    team: TeamSnapshot
    content: str | None
    posted_at: datetime
    reveal_level: RevealLevel


class SocialResponse(BaseModel):
    """Response wrapper for social posts."""

    posts: list[SocialPostSnapshot]


class TimelineArtifactResponse(BaseModel):
    """Finalized timeline artifact response."""

    game_id: int
    sport: str
    timeline_version: str
    generated_at: datetime
    timeline: list[dict[str, Any]]
    summary: dict[str, Any]
    game_analysis: dict[str, Any]


class TimelineArtifactStoredResponse(BaseModel):
    """Stored timeline artifact payload for read-only responses."""

    game_id: int
    sport: str
    timeline_version: str
    generated_at: datetime
    timeline_json: list[dict[str, Any]]
    game_analysis_json: dict[str, Any]
    summary_json: dict[str, Any]


def team_snapshot(team: db_models.SportsTeam) -> TeamSnapshot:
    """
    Return a minimal team snapshot.

    Raises:
        ValueError: If team is None
    """
    if team is None:
        raise ValueError("Team cannot be None")
    return TeamSnapshot(
        id=team.id,
        name=team.name,
        abbreviation=team.abbreviation,
    )


def chunk_plays_by_period(plays: Iterable[db_models.SportsGamePlay]) -> list[PbpPeriod]:
    """Group play-by-play rows by period for responses."""
    periods: dict[int | None, list[PbpEvent]] = {}
    for play in plays:
        period_key = play.quarter
        periods.setdefault(period_key, []).append(
            PbpEvent(
                index=play.play_index,
                clock=play.game_clock,
                description=play.description,
                play_type=play.play_type,
            )
        )
    return [
        PbpPeriod(period=period, events=events)
        for period, events in sorted(
            periods.items(), key=lambda item: (item[0] is None, item[0] or 0)
        )
    ]


def post_reveal_level(post: db_models.GameSocialPost) -> RevealLevel:
    """Resolve the reveal level for a social post snapshot."""
    if post.reveal_risk:
        return RevealLevel.post
    classification = classify_reveal_risk(post.tweet_text)
    if classification.reveal_risk:
        return RevealLevel.post
    return RevealLevel.pre


class TimelineDiagnosticResponse(BaseModel):
    """Diagnostic breakdown of timeline artifact contents."""

    game_id: int
    sport: str
    timeline_version: str
    generated_at: datetime
    total_events: int
    event_type_counts: dict[str, int]
    first_5_events: list[dict[str, Any]]
    last_5_events: list[dict[str, Any]]
    tweet_timestamps: list[str]
    pbp_timestamp_range: dict[str, str | None]


class CompactTimelineResponse(BaseModel):
    """Compact timeline with semantic compression applied."""

    game_id: int
    sport: str
    timeline_version: str
    compression_level: int
    original_event_count: int
    compressed_event_count: int
    retention_rate: float
    timeline_json: list[dict[str, Any]]
    summary_json: dict[str, Any] | None


class MomentSnapshot(BaseModel):
    """A single condensed moment from the game story."""

    period: int
    start_clock: str | None
    end_clock: str | None
    score_before: dict[str, int]
    score_after: dict[str, int]
    narrative: str
    play_count: int


class GameStorySnapshot(BaseModel):
    """Read-only game story for app consumption.

    Stories consist of ordered moments, each with a narrative
    that describes the key plays in that moment.
    """

    game_id: int
    sport: str
    story_version: str
    moments: list[MomentSnapshot]
    moment_count: int
    generated_at: datetime | None
    has_story: bool
