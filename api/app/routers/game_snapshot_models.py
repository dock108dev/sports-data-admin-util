"""Shared Pydantic models and helpers for game snapshot routes."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

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


class RecapResponse(BaseModel):
    """Recap response for a game."""

    game_id: int
    reveal: RevealLevel
    available: bool
    summary: str | None = None
    reason: str | None = None


def team_snapshot(team: db_models.SportsTeam | None, fallback_id: int | None = None) -> TeamSnapshot:
    """Return a minimal team snapshot with safe defaults."""
    if team is None:
        return TeamSnapshot(
            id=fallback_id or 0,
            name="Unknown",
            abbreviation=None,
        )
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
        for period, events in sorted(periods.items(), key=lambda item: (item[0] is None, item[0] or 0))
    ]


def post_reveal_level(post: db_models.GameSocialPost) -> RevealLevel:
    """Resolve the reveal level for a social post snapshot."""
    if post.reveal_risk:
        return RevealLevel.post
    classification = classify_reveal_risk(post.tweet_text)
    if classification.reveal_risk:
        return RevealLevel.post
    return RevealLevel.pre
