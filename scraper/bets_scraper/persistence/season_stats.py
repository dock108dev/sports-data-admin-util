"""Season stat persistence helpers."""

from __future__ import annotations

import json
from typing import Sequence

from sqlalchemy import cast, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from ..models import NormalizedPlayerSeasonStats, NormalizedTeamSeasonStats
from ..utils.db_queries import get_league_id
from ..utils.datetime_utils import now_utc
from .teams import _upsert_team


def _build_team_season_stats(payload: NormalizedTeamSeasonStats) -> dict:
    stats: dict[str, object] = {}
    if payload.games_played is not None:
        stats["games_played"] = payload.games_played
    if payload.wins is not None:
        stats["wins"] = payload.wins
    if payload.losses is not None:
        stats["losses"] = payload.losses
    if payload.overtime_losses is not None:
        stats["overtime_losses"] = payload.overtime_losses
    if payload.points is not None:
        stats["points"] = payload.points
    if payload.goals_for is not None:
        stats["goals_for"] = payload.goals_for
    if payload.goals_against is not None:
        stats["goals_against"] = payload.goals_against
    if payload.goal_diff is not None:
        stats["goal_diff"] = payload.goal_diff
    if payload.shots_for is not None:
        stats["shots_for"] = payload.shots_for
    if payload.shots_against is not None:
        stats["shots_against"] = payload.shots_against
    if payload.penalty_minutes is not None:
        stats["penalty_minutes"] = payload.penalty_minutes
    if payload.power_play_pct is not None:
        stats["power_play_pct"] = payload.power_play_pct
    if payload.penalty_kill_pct is not None:
        stats["penalty_kill_pct"] = payload.penalty_kill_pct
    if payload.raw_stats:
        stats.update(payload.raw_stats)
    return stats


def _build_player_season_stats(payload: NormalizedPlayerSeasonStats) -> dict:
    stats: dict[str, object] = {}
    if payload.games_played is not None:
        stats["games_played"] = payload.games_played
    if payload.goals is not None:
        stats["goals"] = payload.goals
    if payload.assists is not None:
        stats["assists"] = payload.assists
    if payload.points is not None:
        stats["points"] = payload.points
    if payload.time_on_ice is not None:
        stats["time_on_ice"] = payload.time_on_ice
    if payload.player_type:
        stats["player_type"] = payload.player_type
    if payload.raw_stats:
        stats.update(payload.raw_stats)
    return stats


def upsert_team_season_stats(
    session: Session, payloads: Sequence[NormalizedTeamSeasonStats]
) -> int:
    updated = 0
    for payload in payloads:
        league_id = get_league_id(session, payload.team.league_code)
        team_id = _upsert_team(session, league_id, payload.team)
        stats = _build_team_season_stats(payload)
        stats_json = cast(text(f"'{json.dumps(stats)}'"), JSONB)
        stmt = insert(db_models.SportsTeamSeasonStat).values(
            team_id=team_id,
            season=payload.season,
            season_type=payload.season_type,
            raw_stats_json=stats,
            source="sports_reference",
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_team_season_stat_identity",
            set_={
                "raw_stats_json": stats_json,
                "updated_at": now_utc(),
            },
            where=stmt.excluded.raw_stats_json.is_distinct_from(
                db_models.SportsTeamSeasonStat.__table__.c.raw_stats_json
            ),
        )
        result = session.execute(stmt)
        if result.rowcount:
            updated += 1
    logger.info("team_season_stats_upserted", updated=updated)
    return updated


def upsert_player_season_stats(
    session: Session, payloads: Sequence[NormalizedPlayerSeasonStats]
) -> int:
    updated = 0
    for payload in payloads:
        league_code = payload.team.league_code if payload.team else "NHL"
        league_id = get_league_id(session, league_code)
        team_id = None
        if payload.team:
            team_id = _upsert_team(session, league_id, payload.team)
        team_abbreviation = payload.team_abbreviation or (
            payload.team.abbreviation if payload.team else None
        )

        stats = _build_player_season_stats(payload)
        stats_json = cast(text(f"'{json.dumps(stats)}'"), JSONB)
        stmt = insert(db_models.SportsPlayerSeasonStat).values(
            league_id=league_id,
            team_id=team_id,
            team_abbreviation=team_abbreviation,
            player_external_ref=payload.player_id,
            player_name=payload.player_name,
            position=payload.position,
            season=payload.season,
            season_type=payload.season_type,
            raw_stats_json=stats,
            source="sports_reference",
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_player_season_stat_identity",
            set_={
                "raw_stats_json": stats_json,
                "player_name": payload.player_name,
                "position": payload.position,
                "team_id": team_id,
                "updated_at": now_utc(),
            },
            where=stmt.excluded.raw_stats_json.is_distinct_from(
                db_models.SportsPlayerSeasonStat.__table__.c.raw_stats_json
            ),
        )
        result = session.execute(stmt)
        if result.rowcount:
            updated += 1
    logger.info("player_season_stats_upserted", updated=updated)
    return updated
