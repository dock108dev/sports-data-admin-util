"""Season data audit endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, exists, func, select, union

from ...config_sports import LEAGUE_CONFIG
from ...db import AsyncSession, get_db
from ...db.flow import SportsGameFlow
from ...db.odds import SportsGameOdds
from ...db.social import TeamSocialPost
from ...db.sports import (
    SportsGame,
    SportsGamePlay,
    SportsLeague,
    SportsPlayerBoxscore,
    SportsTeamBoxscore,
)
from .schemas.season_audit import SeasonAuditResponse

router = APIRouter()


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole > 0 else 0.0


@router.get("/season-audit", response_model=SeasonAuditResponse)
async def season_audit(
    league: str = Query(..., description="League code (e.g. NBA, MLB)"),
    season: int = Query(..., description="Season year"),
    season_type: str = Query("regular", alias="seasonType"),
    session: AsyncSession = Depends(get_db),
) -> SeasonAuditResponse:
    # Resolve league
    league_upper = league.upper()
    league_row = (
        await session.execute(
            select(SportsLeague).where(SportsLeague.code == league_upper)
        )
    ).scalar_one_or_none()

    if not league_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"League '{league_upper}' not found in database",
        )

    # Base filter: all games for this league/season/season_type
    base = select(SportsGame.id).where(
        SportsGame.league_id == league_row.id,
        SportsGame.season == season,
        SportsGame.season_type == season_type,
    )

    # Total games
    total_games: int = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    # Coverage sub-counts (existence checks against the base set)
    game_id_col = SportsGame.id

    base_count = (
        select(func.count(game_id_col))
        .where(
            SportsGame.league_id == league_row.id,
            SportsGame.season == season,
            SportsGame.season_type == season_type,
        )
    )

    with_boxscore = (
        await session.execute(
            base_count.where(
                exists(select(1).where(SportsTeamBoxscore.game_id == game_id_col))
            )
        )
    ).scalar_one()

    with_player_stats = (
        await session.execute(
            base_count.where(
                exists(select(1).where(SportsPlayerBoxscore.game_id == game_id_col))
            )
        )
    ).scalar_one()

    with_odds = (
        await session.execute(
            base_count.where(
                exists(select(1).where(SportsGameOdds.game_id == game_id_col))
            )
        )
    ).scalar_one()

    with_pbp = (
        await session.execute(
            base_count.where(
                exists(select(1).where(SportsGamePlay.game_id == game_id_col))
            )
        )
    ).scalar_one()

    with_social = (
        await session.execute(
            base_count.where(
                exists(
                    select(1).where(
                        TeamSocialPost.game_id == game_id_col,
                        TeamSocialPost.mapping_status == "mapped",
                    )
                )
            )
        )
    ).scalar_one()

    with_flow = (
        await session.execute(
            base_count.where(
                exists(
                    select(1).where(
                        SportsGameFlow.game_id == game_id_col,
                        SportsGameFlow.moments_json.isnot(None),
                    )
                )
            )
        )
    ).scalar_one()

    with_advanced_stats = (
        await session.execute(
            base_count.where(SportsGame.last_advanced_stats_at.isnot(None))
        )
    ).scalar_one()

    # Distinct teams appearing in games
    home_teams = select(SportsGame.home_team_id.label("tid")).where(
        SportsGame.league_id == league_row.id,
        SportsGame.season == season,
        SportsGame.season_type == season_type,
        SportsGame.home_team_id.isnot(None),
    )
    away_teams = select(SportsGame.away_team_id.label("tid")).where(
        SportsGame.league_id == league_row.id,
        SportsGame.season == season,
        SportsGame.season_type == season_type,
        SportsGame.away_team_id.isnot(None),
    )
    all_teams = union(home_teams, away_teams).subquery()
    teams_with_games: int = (
        await session.execute(select(func.count()).select_from(all_teams))
    ).scalar_one()

    # Config baselines
    cfg = LEAGUE_CONFIG.get(league_upper)
    expected_games = cfg.expected_regular_season_games if cfg else None
    expected_teams = cfg.expected_teams if cfg else None

    coverage_pct = _pct(total_games, expected_games) if expected_games else None

    return SeasonAuditResponse(
        league_code=league_upper,
        season=season,
        season_type=season_type,
        total_games=total_games,
        expected_games=expected_games,
        coverage_pct=coverage_pct,
        with_boxscore=with_boxscore,
        with_player_stats=with_player_stats,
        with_odds=with_odds,
        with_pbp=with_pbp,
        with_social=with_social,
        with_flow=with_flow,
        with_advanced_stats=with_advanced_stats,
        boxscore_pct=_pct(with_boxscore, total_games),
        player_stats_pct=_pct(with_player_stats, total_games),
        odds_pct=_pct(with_odds, total_games),
        pbp_pct=_pct(with_pbp, total_games),
        social_pct=_pct(with_social, total_games),
        flow_pct=_pct(with_flow, total_games),
        advanced_stats_pct=_pct(with_advanced_stats, total_games),
        teams_with_games=teams_with_games,
        expected_teams=expected_teams,
    )
