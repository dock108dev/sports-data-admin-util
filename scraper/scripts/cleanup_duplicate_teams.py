#!/usr/bin/env python3
"""One-time script to merge duplicate teams in the database.

Identifies duplicate teams (same league, similar names) and merges them by:
1. Keeping the team with the most games/boxscores
2. Updating all foreign key references to point to the canonical team
3. Deleting duplicate team records

Usage:
    python scripts/cleanup_duplicate_teams.py [--league NBA] [--dry-run]
"""

from __future__ import annotations

import argparse

# Add parent directory to path to import scraper modules
import sys
from collections import defaultdict
from pathlib import Path
from typing import Literal

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.orm import Session

script_dir = Path(__file__).resolve().parent
scraper_dir = script_dir.parent
sys.path.insert(0, str(scraper_dir))

# Add sports-data-admin API to path for db_models (same pattern as sports_scraper/db.py)
api_dir = scraper_dir.parent.parent / "api"
if str(api_dir) not in sys.path:
    sys.path.append(str(api_dir))

from sports_scraper.db import db_models, get_session
from sports_scraper.logging import logger
from sports_scraper.normalization import normalize_team_name

# Import models from db_models
SportsGame = db_models.SportsGame
SportsGameOdds = db_models.SportsGameOdds
SportsLeague = db_models.SportsLeague
SportsPlayerBoxscore = db_models.SportsPlayerBoxscore
SportsTeam = db_models.SportsTeam
SportsTeamBoxscore = db_models.SportsTeamBoxscore

SportCode = Literal["NBA", "NFL", "NCAAF", "NCAAB", "MLB", "NHL"]


def find_duplicate_teams(session: Session, league_code: str | None = None) -> dict[int, list[int]]:
    """Find duplicate teams grouped by canonical name.
    
    Returns dict mapping canonical team ID -> list of duplicate team IDs.
    """
    # Get league ID if specified
    league_id = None
    if league_code:
        stmt = select(SportsLeague.id).where(SportsLeague.code == league_code)
        league_id = session.execute(stmt).scalar()
        if not league_id:
            logger.error("league_not_found", league=league_code)
            return {}

    # Get all teams for the league
    stmt = select(SportsTeam).where(SportsTeam.league_id == league_id) if league_id else select(SportsTeam)
    teams = session.execute(stmt).scalars().all()

    # Group teams by normalized name
    teams_by_canonical: dict[str, list[SportsTeam]] = defaultdict(list)
    for team in teams:
        canonical_name, _ = normalize_team_name(team.league.code, team.name)  # type: ignore
        teams_by_canonical[canonical_name].append(team)

    # Find duplicates (groups with more than one team)
    duplicates: dict[int, list[int]] = {}
    for canonical_name, team_list in teams_by_canonical.items():
        if len(team_list) > 1:
            # Sort by: 1) matches canonical name exactly, 2) number of games
            # ALWAYS prefer teams that match the canonical full name from normalization
            team_scores = []
            for team in team_list:
                game_count = session.execute(
                    select(func.count(SportsGame.id))
                    .where(
                        (SportsGame.home_team_id == team.id) | (SportsGame.away_team_id == team.id)
                    )
                ).scalar() or 0

                # Check if this team's name matches the canonical name exactly
                # This ensures "Atlanta Hawks" wins over "Atlanta", "New York Knicks" wins over "New York", etc.
                matches_canonical = (team.name == canonical_name)

                # Score: 10000 if matches canonical name exactly, 0 otherwise, plus game count
                # Using 10000 ensures canonical names always win, even if others have 1000+ games
                score = (10000 if matches_canonical else 0) + game_count
                team_scores.append((score, game_count, team))

            # Sort by score descending (canonical matches first, then by game count)
            team_scores.sort(reverse=True, key=lambda x: x[0])
            canonical_team = team_scores[0][2]
            duplicate_ids = [t.id for _, _, t in team_scores[1:]]

            if duplicate_ids:
                duplicates[canonical_team.id] = duplicate_ids
                logger.info(
                    "duplicate_teams_found",
                    canonical=canonical_team.name,
                    canonical_id=canonical_team.id,
                    canonical_games=team_scores[0][1],
                    duplicates=[(t.id, t.name, c) for (_, c, t) in team_scores[1:]],
                )

    return duplicates


def merge_team_references(
    session: Session,
    canonical_team_id: int,
    duplicate_team_ids: list[int],
) -> dict[str, int]:
    """Update all foreign key references from duplicate teams to canonical team.
    
    Returns dict with counts of updated records.
    """
    counts = {
        "games": 0,
        "team_boxscores": 0,
        "player_boxscores": 0,
        "odds": 0,
    }

    # Update games (home_team_id and away_team_id) using bulk updates
    for duplicate_id in duplicate_team_ids:
        # Update home team references
        home_update = (
            update(SportsGame)
            .where(SportsGame.home_team_id == duplicate_id)
            .values(home_team_id=canonical_team_id)
        )
        result = session.execute(home_update)
        counts["games"] += result.rowcount

        # Update away team references
        away_update = (
            update(SportsGame)
            .where(SportsGame.away_team_id == duplicate_id)
            .values(away_team_id=canonical_team_id)
        )
        result = session.execute(away_update)
        counts["games"] += result.rowcount

        # Update team boxscores - need to handle unique constraint (game_id, team_id)
        # Find games where canonical team already has a boxscore
        canonical_game_ids = session.execute(
            select(SportsTeamBoxscore.game_id)
            .where(SportsTeamBoxscore.team_id == canonical_team_id)
        ).scalars().all()

        # Delete duplicate team boxscores for games where canonical already has one
        if canonical_game_ids:
            delete_stmt = delete(SportsTeamBoxscore).where(
                and_(
                    SportsTeamBoxscore.team_id == duplicate_id,
                    SportsTeamBoxscore.game_id.in_(canonical_game_ids)
                )
            )
            session.execute(delete_stmt)

        # Update remaining team boxscores (those for games where canonical doesn't have one)
        team_boxscore_update = (
            update(SportsTeamBoxscore)
            .where(SportsTeamBoxscore.team_id == duplicate_id)
            .values(team_id=canonical_team_id)
        )
        result = session.execute(team_boxscore_update)
        counts["team_boxscores"] += result.rowcount

        # Update player boxscores - need to handle unique constraint (game_id, team_id, player_external_ref)
        # Find player boxscores where canonical team already has one for same game+player
        canonical_player_boxscores = session.execute(
            select(SportsPlayerBoxscore.game_id, SportsPlayerBoxscore.player_external_ref)
            .where(SportsPlayerBoxscore.team_id == canonical_team_id)
        ).all()

        # Build set of (game_id, player_external_ref) tuples for fast lookup
        canonical_keys = {(gid, pref) for gid, pref in canonical_player_boxscores}

        # Find duplicate team player boxscores that would conflict
        duplicate_player_boxscores = session.execute(
            select(SportsPlayerBoxscore.id, SportsPlayerBoxscore.game_id, SportsPlayerBoxscore.player_external_ref)
            .where(SportsPlayerBoxscore.team_id == duplicate_id)
        ).all()

        # Delete conflicting player boxscores
        conflicting_ids = [
            pid for pid, gid, pref in duplicate_player_boxscores
            if (gid, pref) in canonical_keys
        ]
        if conflicting_ids:
            delete_stmt = delete(SportsPlayerBoxscore).where(
                SportsPlayerBoxscore.id.in_(conflicting_ids)
            )
            session.execute(delete_stmt)

        # Update remaining player boxscores
        player_boxscore_update = (
            update(SportsPlayerBoxscore)
            .where(SportsPlayerBoxscore.team_id == duplicate_id)
            .values(team_id=canonical_team_id)
        )
        result = session.execute(player_boxscore_update)
        counts["player_boxscores"] += result.rowcount

        # Note: Odds don't have direct team_id references, they reference games
        # So odds will be updated automatically when games are updated

    return counts


def delete_duplicate_teams(session: Session, duplicate_team_ids: list[int]) -> None:
    """Delete duplicate team records."""
    for team_id in duplicate_team_ids:
        stmt = select(SportsTeam).where(SportsTeam.id == team_id)
        team = session.execute(stmt).scalar_one()
        session.delete(team)
        logger.info("deleted_duplicate_team", team_id=team_id, team_name=team.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge duplicate teams in database")
    parser.add_argument("--league", type=str, help="League code (NBA, NFL, etc.) - if not specified, processes all leagues")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    with get_session() as session:
        duplicates = find_duplicate_teams(session, args.league)

        if not duplicates:
            logger.info("no_duplicates_found", league=args.league or "all")
            return

        total_merges = len(duplicates)
        logger.info("cleanup_start", total_merges=total_merges, dry_run=args.dry_run)

        total_counts = {
            "games": 0,
            "team_boxscores": 0,
            "player_boxscores": 0,
            "odds": 0,
        }
        total_deleted = 0

        for canonical_id, duplicate_ids in duplicates.items():
            canonical_team = session.get(SportsTeam, canonical_id)
            logger.info(
                "merging_teams",
                canonical_id=canonical_id,
                canonical_name=canonical_team.name if canonical_team else "?",
                duplicate_ids=duplicate_ids,
            )

            if not args.dry_run:
                counts = merge_team_references(session, canonical_id, duplicate_ids)
                for key in total_counts:
                    total_counts[key] += counts[key]

                delete_duplicate_teams(session, duplicate_ids)
                total_deleted += len(duplicate_ids)

                session.commit()
                logger.info(
                    "merge_complete",
                    canonical_id=canonical_id,
                    updated=counts,
                    deleted=len(duplicate_ids),
                )
            else:
                logger.info("dry_run_merge", canonical_id=canonical_id, duplicate_ids=duplicate_ids)

        if args.dry_run:
            logger.info("dry_run_complete", total_merges=total_merges, would_delete=sum(len(ids) for ids in duplicates.values()))
        else:
            logger.info(
                "cleanup_complete",
                total_merges=total_merges,
                total_updated=total_counts,
                total_deleted=total_deleted,
            )


if __name__ == "__main__":
    main()

