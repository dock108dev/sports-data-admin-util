"""Dependency for resolving user score preferences on game endpoints."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select

from ..db import AsyncSession, get_db
from ..db.user_preferences import UserPreferences
from ..dependencies.roles import resolve_role
from ..services.score_masking import UserScorePreferences


async def resolve_score_preferences(
    request: Request,
    role: str = Depends(resolve_role),
    session: AsyncSession = Depends(get_db),
) -> UserScorePreferences | None:
    """Load score preferences for the current user.

    Returns None when masking should not apply:
    - Guest users (no account, no preferences)
    - Admin users (bypass masking)
    """
    if role == "admin":
        return None

    if role == "guest":
        return None

    user_id: int | None = getattr(request.state, "user_id", None)
    if user_id is None:
        return None

    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()

    if prefs is None:
        return UserScorePreferences(
            user_id=user_id,
            role=role,
            score_reveal_mode="onMarkRead",
            score_hide_leagues=[],
            score_hide_teams=[],
            revealed_game_ids=set(),
        )

    return UserScorePreferences(
        user_id=user_id,
        role=role,
        score_reveal_mode=prefs.score_reveal_mode,
        score_hide_leagues=list(prefs.score_hide_leagues or []),
        score_hide_teams=list(prefs.score_hide_teams or []),
        revealed_game_ids=set(prefs.revealed_game_ids or []),
    )
