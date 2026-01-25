"""Registry helpers for official team social accounts."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..db import db_models


@dataclass(frozen=True)
class TeamSocialAccountEntry:
    team_id: int
    league_id: int
    platform: str
    handle: str


def fetch_team_accounts(
    session: Session,
    *,
    team_ids: list[int],
    platform: str,
    active_only: bool = True,
) -> dict[int, TeamSocialAccountEntry]:
    query = session.query(db_models.TeamSocialAccount).filter(
        db_models.TeamSocialAccount.team_id.in_(team_ids),
        db_models.TeamSocialAccount.platform == platform,
    )
    if active_only:
        query = query.filter(db_models.TeamSocialAccount.is_active.is_(True))

    accounts = query.all()
    return {
        account.team_id: TeamSocialAccountEntry(
            team_id=account.team_id,
            league_id=account.league_id,
            platform=account.platform,
            handle=account.handle,
        )
        for account in accounts
    }
