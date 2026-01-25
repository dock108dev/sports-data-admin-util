"""Validate NHL team X handles via network calls."""

from __future__ import annotations

import httpx

from sports_scraper.db import db_models, get_session
from sports_scraper.logging import logger


def validate_nhl_handles() -> None:
    logger.info("nhl_x_handle_validation_start")
    with get_session() as session:
        league = session.query(db_models.SportsLeague).filter(db_models.SportsLeague.code == "NHL").first()
        if not league:
            logger.warning("nhl_x_handle_validation_no_league")
            return

        teams = (
            session.query(db_models.SportsTeam)
            .filter(db_models.SportsTeam.league_id == league.id)
            .filter(db_models.SportsTeam.x_handle.isnot(None))
            .all()
        )

    if not teams:
        logger.warning("nhl_x_handle_validation_no_teams")
        return

    client = httpx.Client(follow_redirects=True, timeout=15.0, headers={"User-Agent": "sports-data-admin-x/1.0"})
    valid = 0
    invalid = 0

    for team in teams:
        handle = (team.x_handle or "").lstrip("@")
        if not handle:
            continue
        url = f"https://x.com/{handle}"
        try:
            response = client.get(url)
            if response.status_code in {200, 301, 302}:
                logger.info("nhl_x_handle_valid", team=team.abbreviation, handle=handle, status=response.status_code)
                valid += 1
            else:
                logger.warning(
                    "nhl_x_handle_invalid",
                    team=team.abbreviation,
                    handle=handle,
                    status=response.status_code,
                )
                invalid += 1
        except Exception as exc:
            logger.warning(
                "nhl_x_handle_validation_failed",
                team=team.abbreviation,
                handle=handle,
                error=str(exc),
            )
            invalid += 1

    logger.info("nhl_x_handle_validation_complete", total=len(teams), valid=valid, invalid=invalid)


if __name__ == "__main__":
    validate_nhl_handles()
