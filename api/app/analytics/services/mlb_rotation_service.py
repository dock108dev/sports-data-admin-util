"""MLB rotation prediction from historical start data.

Identifies the active pitching rotation from ``MLBPitcherGameStats``
and projects the probable starter for upcoming games by cycling through
the rotation order.

Fallback chain for ``predict_probable_starter``:

1. MLB Stats API probable pitcher (works 1-2 days out)
2. Rotation cycle projection from recent starts
3. OpenAI tiebreaker when rotation is ambiguous
4. ``None`` — caller falls back to generic pitcher profile
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_team_rotation(
    db: AsyncSession,
    team_id: int,
    lookback_starts: int = 15,
) -> list[dict[str, Any]]:
    """Identify the active pitching rotation from recent starts.

    Queries the last ``lookback_starts`` starts for the team, groups by
    pitcher, and returns rotation members ordered by most recent start
    (i.e. the current position in the rotation cycle).

    Pitchers with fewer than 2 starts in the window are excluded unless
    the team has fewer than 5 qualifying pitchers.  Pitchers whose last
    start is more than 2 full rotation turns ago are considered
    inactive (IL / demoted).

    Returns:
        List of dicts ordered by most recent start (cycle position)::

            [
                {
                    "external_ref": str,
                    "name": str,
                    "starts": int,
                    "last_start": date,
                    "start_dates": [date, ...],
                },
                ...
            ]
    """
    from app.db.mlb_advanced import MLBPitcherGameStats
    from app.db.sports import SportsGame

    stmt = (
        select(
            MLBPitcherGameStats.player_external_ref,
            MLBPitcherGameStats.player_name,
            SportsGame.game_date,
        )
        .join(SportsGame, SportsGame.id == MLBPitcherGameStats.game_id)
        .where(
            MLBPitcherGameStats.team_id == team_id,
            MLBPitcherGameStats.is_starter == True,  # noqa: E712
            SportsGame.status.in_(["final", "archived"]),
        )
        .order_by(SportsGame.game_date.desc())
        .limit(lookback_starts)
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return []

    # Group by pitcher
    pitcher_data: dict[str, dict[str, Any]] = {}
    for ext_ref, name, game_date in rows:
        gd = game_date.date() if hasattr(game_date, "date") else game_date
        if ext_ref not in pitcher_data:
            pitcher_data[ext_ref] = {
                "external_ref": ext_ref,
                "name": name,
                "starts": 0,
                "last_start": gd,
                "start_dates": [],
            }
        pitcher_data[ext_ref]["starts"] += 1
        pitcher_data[ext_ref]["start_dates"].append(gd)

    pitchers = list(pitcher_data.values())

    # Determine rotation size from data
    qualified = [p for p in pitchers if p["starts"] >= 2]

    if len(qualified) < 3:
        # Early season or thin data — use everyone
        qualified = pitchers

    # Exclude pitchers whose last start is too stale.
    # "Too stale" = more than 2 full rotation turns ago.
    rotation_size = max(len(qualified), 5)
    staleness_cutoff = timedelta(days=rotation_size * 2 + 2)
    most_recent_start = max(p["last_start"] for p in qualified)

    active = [
        p for p in qualified
        if (most_recent_start - p["last_start"]) <= staleness_cutoff
    ]

    if len(active) < 3:
        active = qualified  # Don't filter too aggressively

    # Order by most recent start (most recent = just pitched)
    active.sort(key=lambda p: p["last_start"], reverse=True)

    return active


async def predict_probable_starter(
    db: AsyncSession,
    team_id: int,
    game_date: date,
    team_external_ref: str | None = None,
) -> dict[str, str] | None:
    """Predict the probable starting pitcher for a future game.

    Fallback chain:

    1. MLB Stats API (reliable 1-2 days out)
    2. Rotation cycle projection from historical starts
    3. OpenAI tiebreaker for ambiguous rotations
    4. ``None``

    Args:
        db: Async database session.
        team_id: Internal team ID.
        game_date: Date of the game to predict for.
        team_external_ref: MLB Stats API team ID for API lookup.

    Returns:
        ``{"external_ref": str, "name": str}`` or ``None``.
    """
    # 1. Try MLB Stats API first
    if team_external_ref:
        from app.analytics.services.lineup_fetcher import fetch_probable_starter

        api_result = await fetch_probable_starter(game_date, team_external_ref)
        if api_result:
            logger.info(
                "rotation_predicted_from_api",
                extra={
                    "team_id": team_id,
                    "game_date": str(game_date),
                    "pitcher": api_result.get("name"),
                },
            )
            return api_result

    # 2. Rotation cycle projection
    rotation = await get_team_rotation(db, team_id)

    if len(rotation) < 3:
        logger.info(
            "rotation_prediction_insufficient_data",
            extra={
                "team_id": team_id,
                "game_date": str(game_date),
                "rotation_size": len(rotation),
            },
        )
        # 3. Try OpenAI if rotation is too thin
        if len(rotation) > 0:
            ai_result = await _openai_rotation_tiebreaker(
                team_id, game_date, rotation,
            )
            if ai_result:
                return ai_result
        return None

    predicted = await _project_rotation_to_date(
        db, team_id, game_date, rotation,
    )

    if predicted:
        logger.info(
            "rotation_predicted_from_cycle",
            extra={
                "team_id": team_id,
                "game_date": str(game_date),
                "pitcher": predicted.get("name"),
                "rotation_size": len(rotation),
            },
        )
        return predicted

    # 3. OpenAI tiebreaker
    ai_result = await _openai_rotation_tiebreaker(
        team_id, game_date, rotation,
    )
    if ai_result:
        return ai_result

    return None


async def _project_rotation_to_date(
    db: AsyncSession,
    team_id: int,
    target_date: date,
    rotation: list[dict[str, Any]],
) -> dict[str, str] | None:
    """Project the rotation cycle forward to the target date.

    Counts scheduled game days between the last known start and the
    target date to determine which rotation slot should pitch.

    Args:
        db: Async database session.
        team_id: Internal team ID.
        target_date: Date to predict for.
        rotation: Active rotation from ``get_team_rotation()``.

    Returns:
        ``{"external_ref": str, "name": str}`` or ``None``.
    """
    from app.db.sports import SportsGame

    if not rotation:
        return None

    # The most recent starter is rotation[0].
    # They just pitched, so the next game goes to rotation[1], etc.
    last_start_date = rotation[0]["last_start"]

    # Count how many team game days exist between last_start_date and target_date
    # (exclusive of last_start_date, inclusive of target_date)
    stmt = (
        select(SportsGame.game_date)
        .where(
            (SportsGame.home_team_id == team_id)
            | (SportsGame.away_team_id == team_id),
            SportsGame.game_date > last_start_date,
            SportsGame.game_date <= target_date,
        )
        .order_by(SportsGame.game_date.asc())
    )
    result = await db.execute(stmt)
    upcoming_dates = result.scalars().all()

    if not upcoming_dates:
        # Target date might be the next game after last start
        # In this case, rotation[1] would be next
        return {
            "external_ref": rotation[1 % len(rotation)]["external_ref"],
            "name": rotation[1 % len(rotation)]["name"],
        }

    # Count unique game days (doubleheaders = 1 day, 2 starters)
    unique_game_days: list[date] = []
    seen_dates: set[date] = set()
    for gd in upcoming_dates:
        d = gd.date() if hasattr(gd, "date") else gd
        if d not in seen_dates:
            seen_dates.add(d)
            unique_game_days.append(d)

    # Find which game day index our target_date is
    games_ahead = len(unique_game_days)

    # Rotation slot: rotation[0] just pitched, so game 1 after = rotation[1],
    # game 2 after = rotation[2], etc.  Wrap around the rotation.
    rotation_size = len(rotation)
    slot_index = games_ahead % rotation_size

    predicted = rotation[slot_index]
    return {
        "external_ref": predicted["external_ref"],
        "name": predicted["name"],
    }


async def _openai_rotation_tiebreaker(
    team_id: int,
    game_date: date,
    rotation: list[dict[str, Any]],
) -> dict[str, str] | None:
    """Use OpenAI to resolve an ambiguous rotation prediction.

    Only called when the deterministic rotation cycle can't produce
    a confident answer (e.g., < 4 clear rotation members, recent
    disruptions).

    Returns:
        ``{"external_ref": str, "name": str}`` or ``None``.
    """
    try:
        from app.services.openai_client import get_openai_client

        client = get_openai_client()
        if client is None:
            return None

        # Build a structured prompt with the rotation data
        rotation_summary = []
        for p in rotation:
            dates_str = ", ".join(str(d) for d in p["start_dates"][:5])
            rotation_summary.append(
                f"- {p['name']} (ID: {p['external_ref']}): "
                f"{p['starts']} starts, last start {p['last_start']}, "
                f"dates: [{dates_str}]"
            )

        starters_block = "\n".join(rotation_summary)
        prompt = (
            f"You are an MLB rotation analyst. Based on the recent starting "
            f"pitcher history below, predict who will start on {game_date}.\n\n"
            f"Team's recent starters (ordered by most recent start):\n"
            f"{starters_block}\n\n"
            f"Consider the typical 5-day rest pattern between starts. "
            f"Return JSON with exactly these fields:\n"
            f'{{"external_ref": "<pitcher ID>", "name": "<pitcher name>", '
            f'"confidence": "<high/medium/low>", "reasoning": "<brief explanation>"}}'
        )

        response_str = client.generate(
            prompt, temperature=0.2, max_tokens=300,
        )
        data = json.loads(response_str)

        ext_ref = data.get("external_ref", "")
        name = data.get("name", "")
        confidence = data.get("confidence", "low")

        if not ext_ref or not name:
            return None

        # Verify the predicted pitcher is actually in our rotation data
        known_refs = {p["external_ref"] for p in rotation}
        if ext_ref not in known_refs:
            logger.warning(
                "openai_rotation_unknown_pitcher",
                extra={
                    "team_id": team_id,
                    "predicted_ref": ext_ref,
                    "predicted_name": name,
                },
            )
            return None

        logger.info(
            "rotation_predicted_from_openai",
            extra={
                "team_id": team_id,
                "game_date": str(game_date),
                "pitcher": name,
                "confidence": confidence,
                "reasoning": data.get("reasoning", ""),
            },
        )
        return {"external_ref": ext_ref, "name": name}

    except Exception as exc:
        logger.warning(
            "openai_rotation_tiebreaker_failed",
            extra={
                "team_id": team_id,
                "game_date": str(game_date),
                "error": str(exc),
            },
        )
        return None
