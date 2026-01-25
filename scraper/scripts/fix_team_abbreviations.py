#!/usr/bin/env python3
"""Fix team abbreviations using normalization mappings.

Updates all teams in the database to use correct abbreviations from the normalization module.
This fixes teams that were created with wrong abbreviations (e.g., "NEW YO" instead of "NYK").

Usage:
    python scripts/fix_team_abbreviations.py [--league NBA] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

# Add parent directory to path to import scraper modules
script_dir = Path(__file__).resolve().parent
scraper_dir = script_dir.parent
sys.path.insert(0, str(scraper_dir))

# Add sports-data-admin API to path for db_models
api_dir = scraper_dir.parent.parent / "api"
if str(api_dir) not in sys.path:
    sys.path.append(str(api_dir))

from sports_scraper.db import db_models, get_session
from sports_scraper.logging import logger
from sports_scraper.normalization import normalize_team_name

SportsLeague = db_models.SportsLeague
SportsTeam = db_models.SportsTeam


def fix_team_abbreviations(league_code: str | None = None, dry_run: bool = False) -> None:
    """Fix team abbreviations using normalization mappings.
    
    Args:
        league_code: Optional league code to filter by (e.g., "NBA")
        dry_run: If True, only log changes without updating database
    """
    with get_session() as session:
        # Get league ID if specified
        league_id = None
        if league_code:
            stmt = select(SportsLeague.id).where(SportsLeague.code == league_code)
            league_id = session.execute(stmt).scalar()
            if not league_id:
                logger.error("league_not_found", league=league_code)
                return
        
        # Get all teams for the league
        if league_id:
            stmt = select(SportsTeam).where(SportsTeam.league_id == league_id)
        else:
            stmt = select(SportsTeam)
        teams = session.execute(stmt).scalars().all()
        
        logger.info(
            "fix_abbreviations_start",
            league=league_code or "all",
            total_teams=len(teams),
            dry_run=dry_run,
        )
        
        updated_count = 0
        unchanged_count = 0
        error_count = 0
        
        for team in teams:
            try:
                # Get league code for normalization
                league_code_for_norm = team.league.code  # type: ignore
                
                # Get correct abbreviation from normalization
                canonical_name, correct_abbr = normalize_team_name(league_code_for_norm, team.name)
                
                # Check if abbreviation needs updating
                if team.abbreviation != correct_abbr:
                    logger.info(
                        "abbreviation_update",
                        team_id=team.id,
                        team_name=team.name,
                        old_abbreviation=team.abbreviation,
                        new_abbreviation=correct_abbr,
                        league=league_code_for_norm,
                    )
                    
                    if not dry_run:
                        team.abbreviation = correct_abbr
                        # Also update name to canonical if different
                        if team.name != canonical_name:
                            logger.debug(
                                "name_update",
                                team_id=team.id,
                                old_name=team.name,
                                new_name=canonical_name,
                            )
                            team.name = canonical_name
                    
                    updated_count += 1
                else:
                    unchanged_count += 1
                    
            except Exception as exc:
                logger.error(
                    "abbreviation_fix_error",
                    team_id=team.id,
                    team_name=team.name,
                    error=str(exc),
                )
                error_count += 1
        
        if not dry_run:
            session.commit()
            logger.info(
                "fix_abbreviations_complete",
                league=league_code or "all",
                updated=updated_count,
                unchanged=unchanged_count,
                errors=error_count,
            )
        else:
            logger.info(
                "fix_abbreviations_dry_run",
                league=league_code or "all",
                would_update=updated_count,
                unchanged=unchanged_count,
                errors=error_count,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix team abbreviations using normalization mappings")
    parser.add_argument(
        "--league",
        type=str,
        help="League code to fix (e.g., NBA, NFL). If not specified, fixes all leagues.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without updating the database",
    )
    
    args = parser.parse_args()
    
    fix_team_abbreviations(league_code=args.league, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

