"""Helper functions for PBP admin endpoints."""

from __future__ import annotations

from typing import Any

from ...db.sports import SportsGamePlay
from .pbp_models import PlayDetail, PlaySummary


def build_resolution_summary(plays: list[SportsGamePlay]) -> dict[str, Any]:
    """Build resolution summary from plays."""
    total = len(plays)
    if total == 0:
        return {
            "total_plays": 0,
            "teams_resolved": 0,
            "teams_unresolved": 0,
            "team_resolution_rate": 0,
            "players_with_name": 0,
            "players_without_name": 0,
            "plays_with_score": 0,
            "plays_without_score": 0,
        }

    teams_resolved = sum(1 for p in plays if p.team_id is not None)
    teams_unresolved = sum(
        1 for p in plays if p.team_id is None and (p.description or "").strip()
    )
    players_with_name = sum(1 for p in plays if p.player_name)
    plays_with_score = sum(1 for p in plays if p.home_score is not None)

    return {
        "total_plays": total,
        "teams_resolved": teams_resolved,
        "teams_unresolved": teams_unresolved,
        "team_resolution_rate": round(teams_resolved / total * 100, 1)
        if total > 0
        else 0,
        "players_with_name": players_with_name,
        "players_without_name": total - players_with_name,
        "plays_with_score": plays_with_score,
        "plays_without_score": total - plays_with_score,
    }


def play_to_summary(play: SportsGamePlay) -> PlaySummary:
    """Convert a play to summary format."""
    return PlaySummary(
        play_index=play.play_index,
        quarter=play.quarter,
        game_clock=play.game_clock,
        play_type=play.play_type,
        team_abbreviation=play.team.abbreviation if play.team else None,
        team_id=play.team_id,
        team_resolved=play.team_id is not None,
        player_name=play.player_name,
        player_id=play.player_id,
        description=play.description,
        home_score=play.home_score,
        away_score=play.away_score,
        has_raw_data=bool(play.raw_data),
    )


def play_to_detail(play: SportsGamePlay) -> PlayDetail:
    """Convert a play to detail format."""
    return PlayDetail(
        play_index=play.play_index,
        quarter=play.quarter,
        game_clock=play.game_clock,
        play_type=play.play_type,
        team_abbreviation=play.team.abbreviation if play.team else None,
        team_id=play.team_id,
        team_name=play.team.name if play.team else None,
        player_name=play.player_name,
        player_id=play.player_id,
        description=play.description,
        home_score=play.home_score,
        away_score=play.away_score,
        raw_data=play.raw_data or {},
        created_at=play.created_at.isoformat(),
        updated_at=play.updated_at.isoformat(),
    )
