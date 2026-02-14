"""Timeline generation service for missing game moments.

This service identifies games with play-by-play data but missing timeline artifacts,
and triggers timeline generation via the API's timeline generator.
"""

from __future__ import annotations

import httpx
import time
from datetime import datetime, timedelta
from sqlalchemy import exists
from sqlalchemy.orm import Session, aliased
from typing import Sequence

from ..api_client import get_api_headers
from ..config import settings
from ..db import db_models, get_session
from ..logging import logger
from ..utils.datetime_utils import now_utc


# Default window for scheduled timeline generation (matches scheduler.py)
SCHEDULED_DAYS_BACK = 4  # 96 hours back

# Must match api/app/services/timeline_types.py DEFAULT_TIMELINE_VERSION
TIMELINE_VERSION = "v1"


def find_games_missing_timelines(
    session: Session,
    league_code: str,
    days_back: int | None = None,
) -> Sequence[tuple[int, datetime, str, str]]:
    """
    Find completed games with PBP data but missing timeline artifacts.
    
    Args:
        session: Database session
        league_code: League to check (e.g., "NBA", "NHL")
        days_back: How many days back to check (None = ALL games, no limit)
        
    Returns:
        List of (game_id, game_date, home_team, away_team) tuples
    """
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == league_code
    ).first()
    
    if not league:
        logger.warning("timeline_gen_unknown_league", league=league_code)
        return []
    
    # Find games that:
    # 1. Are completed/final
    # 2. Have play-by-play data
    # 3. Don't have timeline artifacts
    from sqlalchemy.orm import aliased
    HomeTeam = aliased(db_models.SportsTeam)
    AwayTeam = aliased(db_models.SportsTeam)
    
    query = (
        session.query(
            db_models.SportsGame.id,
            db_models.SportsGame.game_date,
            HomeTeam.name.label("home_team"),
            AwayTeam.name.label("away_team"),
        )
        .join(
            HomeTeam,
            db_models.SportsGame.home_team_id == HomeTeam.id,
        )
        .join(
            AwayTeam,
            db_models.SportsGame.away_team_id == AwayTeam.id,
        )
        .filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.status == db_models.GameStatus.final.value,
        )
        .filter(
            # Has PBP data
            exists().where(
                db_models.SportsGamePlay.game_id == db_models.SportsGame.id
            )
        )
        .filter(
            # Missing timeline artifact
            ~exists().where(
                db_models.SportsGameTimelineArtifact.game_id == db_models.SportsGame.id
            )
        )
        .order_by(db_models.SportsGame.game_date.desc())
    )
    
    # Apply date filter only if days_back is specified
    if days_back is not None:
        cutoff_date = now_utc() - timedelta(days=days_back)
        query = query.filter(db_models.SportsGame.game_date >= cutoff_date)
    
    results = query.all()
    
    logger.info(
        "timeline_gen_games_found",
        league=league_code,
        days_back=days_back if days_back else "ALL",
        count=len(results),
    )
    
    return results


def find_games_needing_regeneration(
    session: Session,
    league_code: str,
    days_back: int | None = None,
) -> Sequence[tuple[int, datetime, str, str, str]]:
    """
    Find games with stale timelines that need regeneration.
    
    A game needs regeneration if:
    - It has a timeline artifact
    - The game's PBP data was updated AFTER the timeline was generated
    - OR the game's social data was updated AFTER the timeline was generated
    
    Args:
        session: Database session
        league_code: League to check (e.g., "NBA", "NHL")
        days_back: How many days back to check (None = ALL games, no limit)
        
    Returns:
        List of (game_id, game_date, home_team, away_team, reason) tuples
    """
    league = session.query(db_models.SportsLeague).filter(
        db_models.SportsLeague.code == league_code
    ).first()
    
    if not league:
        logger.warning("timeline_regen_unknown_league", league=league_code)
        return []
    
    HomeTeam = aliased(db_models.SportsTeam)
    AwayTeam = aliased(db_models.SportsTeam)
    
    # Subquery to get latest timeline artifact for each game
    from sqlalchemy import func, select
    latest_timeline = (
        select(
            db_models.SportsGameTimelineArtifact.game_id,
            func.max(db_models.SportsGameTimelineArtifact.generated_at).label("latest_generated_at"),
        )
        .group_by(db_models.SportsGameTimelineArtifact.game_id)
        .subquery()
    )
    
    # Find games where PBP or social was updated after timeline was generated
    query = (
        session.query(
            db_models.SportsGame.id,
            db_models.SportsGame.game_date,
            HomeTeam.name.label("home_team"),
            AwayTeam.name.label("away_team"),
            db_models.SportsGame.last_pbp_at,
            db_models.SportsGame.last_social_at,
            latest_timeline.c.latest_generated_at,
        )
        .join(HomeTeam, db_models.SportsGame.home_team_id == HomeTeam.id)
        .join(AwayTeam, db_models.SportsGame.away_team_id == AwayTeam.id)
        .join(latest_timeline, db_models.SportsGame.id == latest_timeline.c.game_id)
        .filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.status == db_models.GameStatus.final.value,
        )
        .filter(
            # Either PBP or social was updated after timeline was generated
            (
                (db_models.SportsGame.last_pbp_at.isnot(None)) &
                (db_models.SportsGame.last_pbp_at > latest_timeline.c.latest_generated_at)
            ) |
            (
                (db_models.SportsGame.last_social_at.isnot(None)) &
                (db_models.SportsGame.last_social_at > latest_timeline.c.latest_generated_at)
            )
        )
        .order_by(db_models.SportsGame.game_date.desc())
    )
    
    # Apply date filter only if days_back is specified
    if days_back is not None:
        cutoff_date = now_utc() - timedelta(days=days_back)
        query = query.filter(db_models.SportsGame.game_date >= cutoff_date)
    
    raw_results = query.all()
    
    # Build results with reason for regeneration
    results = []
    for game_id, game_date, home_team, away_team, last_pbp, last_social, timeline_gen in raw_results:
        reasons = []
        if last_pbp and last_pbp > timeline_gen:
            reasons.append("pbp_updated")
        if last_social and last_social > timeline_gen:
            reasons.append("social_updated")
        reason = ",".join(reasons) if reasons else "data_changed"
        results.append((game_id, game_date, home_team, away_team, reason))
    
    logger.info(
        "timeline_regen_games_found",
        league=league_code,
        days_back=days_back if days_back else "ALL",
        count=len(results),
    )
    
    return results


def find_all_games_needing_timelines(
    session: Session,
    league_code: str,
    days_back: int | None = None,
) -> Sequence[tuple[int, datetime, str, str, str]]:
    """
    Find all games that need timeline generation or regeneration.
    
    Combines:
    - Games missing timelines entirely
    - Games with stale timelines (data updated after generation)
    
    Args:
        session: Database session
        league_code: League to check (e.g., "NBA", "NHL")
        days_back: How many days back to check (None = ALL games, no limit)
        
    Returns:
        List of (game_id, game_date, home_team, away_team, reason) tuples
    """
    # Get games missing timelines
    missing = find_games_missing_timelines(session, league_code, days_back)
    missing_with_reason = [
        (game_id, game_date, home_team, away_team, "missing")
        for game_id, game_date, home_team, away_team in missing
    ]
    
    # Get games needing regeneration
    stale = find_games_needing_regeneration(session, league_code, days_back)
    
    # Combine and dedupe by game_id (prefer missing over stale if somehow both)
    seen_ids = set()
    combined = []
    
    for item in missing_with_reason:
        if item[0] not in seen_ids:
            combined.append(item)
            seen_ids.add(item[0])
    
    for item in stale:
        if item[0] not in seen_ids:
            combined.append(item)
            seen_ids.add(item[0])
    
    logger.info(
        "timeline_all_games_needing_timelines",
        league=league_code,
        days_back=days_back if days_back else "ALL",
        missing_count=len(missing_with_reason),
        stale_count=len(stale),
        total_count=len(combined),
    )
    
    return combined


def generate_timeline_for_game(
    game_id: int,
    timeline_version: str = TIMELINE_VERSION,
    api_base_url: str | None = None,
    reason: str = "scheduled",
) -> bool:
    """
    Generate timeline artifact for a single game via API call.
    
    Args:
        game_id: Game ID to generate timeline for
        timeline_version: Timeline version identifier
        api_base_url: Base URL for API (defaults to settings)
        
    Returns:
        True if successful, False otherwise
    """
    if api_base_url is None:
        # Use internal API URL if available, otherwise localhost
        api_base_url = getattr(settings, "api_internal_url", "http://localhost:8000")
    
    url = f"{api_base_url}/api/admin/sports/timelines/generate/{game_id}"
    
    try:
        with httpx.Client(timeout=120.0, headers=get_api_headers()) as client:
            response = client.post(
                url,
                json={"timeline_version": timeline_version},
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(
                "timeline_gen_success",
                game_id=game_id,
                timeline_version=timeline_version,
                result=result,
            )
            return True
            
    except httpx.HTTPStatusError as exc:
        logger.error(
            "timeline_gen_http_error",
            game_id=game_id,
            status_code=exc.response.status_code,
            error=str(exc),
        )
        return False
    except Exception as exc:
        logger.exception(
            "timeline_gen_error",
            game_id=game_id,
            error=str(exc),
        )
        return False


def generate_missing_timelines(
    league_code: str,
    days_back: int | None = None,
    max_games: int | None = None,
    timeline_version: str = TIMELINE_VERSION,
) -> dict[str, int]:
    """
    Find and generate timelines for games missing artifacts.
    
    Args:
        league_code: League to process (required)
        days_back: How many days back to check (None = ALL games)
        max_games: Maximum number of games to process (None = all)
        timeline_version: Timeline version identifier
        
    Returns:
        Summary dict with counts of processed/successful/failed games
    """
    logger.info(
        "timeline_gen_batch_start",
        league=league_code,
        days_back=days_back if days_back else "ALL",
        max_games=max_games,
    )
    
    with get_session() as session:
        games = find_games_missing_timelines(session, league_code, days_back)
    
    if not games:
        logger.info("timeline_gen_no_games_found", league=league_code)
        return {
            "games_found": 0,
            "games_processed": 0,
            "games_successful": 0,
            "games_failed": 0,
        }
    
    # Limit number of games if specified
    games_to_process = games[:max_games] if max_games else games
    
    successful = 0
    failed = 0
    
    for game_id, game_date, home_team, away_team in games_to_process:
        logger.info(
            "timeline_gen_processing",
            game_id=game_id,
            game_date=str(game_date),
            matchup=f"{away_team} @ {home_team}",
        )
        
        if generate_timeline_for_game(game_id, timeline_version):
            successful += 1
        else:
            failed += 1
        
        # Throttle requests to stay under rate limit (120 req/60s = 2/sec)
        time.sleep(0.6)
    
    summary = {
        "games_found": len(games),
        "games_processed": len(games_to_process),
        "games_successful": successful,
        "games_failed": failed,
    }
    
    logger.info("timeline_gen_batch_complete", **summary)
    
    return summary


def generate_all_needed_timelines(
    league_code: str,
    days_back: int | None = None,
    max_games: int | None = None,
    timeline_version: str = TIMELINE_VERSION,
) -> dict[str, int]:
    """
    Find and generate/regenerate timelines for all games that need them.
    
    This includes:
    - Games missing timeline artifacts entirely
    - Games with stale timelines (PBP or social updated after timeline was generated)
    
    Args:
        league_code: League to process (required)
        days_back: How many days back to check (None = ALL games)
        max_games: Maximum number of games to process (None = all)
        timeline_version: Timeline version identifier
        
    Returns:
        Summary dict with counts of processed/successful/failed games by reason
    """
    logger.info(
        "timeline_gen_all_batch_start",
        league=league_code,
        days_back=days_back if days_back else "ALL",
        max_games=max_games,
    )
    
    with get_session() as session:
        games = find_all_games_needing_timelines(session, league_code, days_back)
    
    if not games:
        logger.info("timeline_gen_all_no_games_found", league=league_code)
        return {
            "games_found": 0,
            "games_missing": 0,
            "games_stale": 0,
            "games_processed": 0,
            "games_successful": 0,
            "games_failed": 0,
        }
    
    # Count by reason
    missing_count = sum(1 for g in games if g[4] == "missing")
    stale_count = len(games) - missing_count
    
    # Limit number of games if specified
    games_to_process = games[:max_games] if max_games else games
    
    successful = 0
    failed = 0
    
    for game_id, game_date, home_team, away_team, reason in games_to_process:
        logger.info(
            "timeline_gen_processing",
            game_id=game_id,
            game_date=str(game_date),
            matchup=f"{away_team} @ {home_team}",
            reason=reason,
        )
        
        if generate_timeline_for_game(game_id, timeline_version, reason=reason):
            successful += 1
        else:
            failed += 1
        
        # Throttle requests to stay under rate limit (120 req/60s = 2/sec)
        time.sleep(0.6)
    
    summary = {
        "games_found": len(games),
        "games_missing": missing_count,
        "games_stale": stale_count,
        "games_processed": len(games_to_process),
        "games_successful": successful,
        "games_failed": failed,
    }
    
    logger.info("timeline_gen_all_batch_complete", **summary)
    
    return summary
