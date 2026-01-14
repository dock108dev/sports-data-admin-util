"""
Moment summary generation service.

Generates template-based narrative summaries for individual game moments
(sequences of plays). Uses play types and descriptions to construct
readable sentences about what happened.

Note: This is NOT AI-powered. Summaries are built from templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
from typing import Sequence

from sqlalchemy import func, select

from .. import db_models
from ..db import AsyncSession
from ..utils.datetime_utils import now_utc
from ..utils.reveal_utils import redact_scores

logger = logging.getLogger(__name__)

_SUMMARY_CACHE_TTL = timedelta(minutes=10)


@dataclass
class _MomentSummaryCacheEntry:
    summary: str
    expires_at: datetime


_moment_summary_cache: dict[tuple[int, int], _MomentSummaryCacheEntry] = {}


_FINAL_SCORE_PATTERN = re.compile(r"\bfinal\s+score\b", re.IGNORECASE)
_BANNED_PHRASES_PATTERN = re.compile(
    r"\b(game\s*winner|game-winner|final\s+drive)\b", re.IGNORECASE
)
_WHITESPACE_PATTERN = re.compile(r"\s+")


async def summarize_moment(
    game_id: int, moment_id: int, session: AsyncSession
) -> str:
    """
    Generate a template-based summary for a game moment.

    Args:
        game_id: The game ID
        moment_id: The play index to summarize
        session: Database session

    Returns:
        A narrative summary string

    Raises:
        ValueError: If the moment is not found
    """
    cache_key = (game_id, moment_id)
    cached = _get_cached_summary(cache_key)
    if cached:
        return cached

    play = await _get_play_by_index(game_id, moment_id, session)
    if not play:
        raise ValueError(f"Moment not found for play_index={moment_id}")

    plays = await _fetch_moment_plays(play, session)
    summary = _build_summary(plays)

    _store_cached_summary(cache_key, summary)
    logger.debug(
        "moment_summary_generated",
        extra={"game_id": game_id, "moment_id": moment_id, "play_count": len(plays)},
    )
    return summary


# =============================================================================
# CACHE
# =============================================================================


def _get_cached_summary(cache_key: tuple[int, int]) -> str | None:
    entry = _moment_summary_cache.get(cache_key)
    if not entry:
        return None
    if entry.expires_at <= now_utc():
        _moment_summary_cache.pop(cache_key, None)
        return None
    return entry.summary


def _store_cached_summary(cache_key: tuple[int, int], summary: str) -> None:
    _moment_summary_cache[cache_key] = _MomentSummaryCacheEntry(
        summary=summary,
        expires_at=now_utc() + _SUMMARY_CACHE_TTL,
    )


def _clear_summary_cache() -> None:
    """Clear the summary cache. Useful for testing."""
    _moment_summary_cache.clear()


# =============================================================================
# DATABASE
# =============================================================================


async def _get_play_by_index(
    game_id: int,
    moment_id: int,
    session: AsyncSession,
) -> db_models.SportsGamePlay | None:
    stmt = select(db_models.SportsGamePlay).where(
        db_models.SportsGamePlay.game_id == game_id,
        db_models.SportsGamePlay.play_index == moment_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _fetch_moment_plays(
    play: db_models.SportsGamePlay,
    session: AsyncSession,
) -> list[db_models.SportsGamePlay]:
    """Fetch the play and any immediately following plays in the same moment."""
    start_index = play.play_index
    next_index_stmt = select(func.min(db_models.SportsGamePlay.play_index)).where(
        db_models.SportsGamePlay.game_id == play.game_id,
        db_models.SportsGamePlay.play_index > start_index,
    )
    next_index = (await session.execute(next_index_stmt)).scalar_one_or_none()
    end_index = (next_index - 1) if next_index is not None else start_index
    if end_index < start_index:
        return []

    plays_stmt = (
        select(db_models.SportsGamePlay)
        .where(
            db_models.SportsGamePlay.game_id == play.game_id,
            db_models.SportsGamePlay.play_index >= start_index,
            db_models.SportsGamePlay.play_index <= end_index,
        )
        .order_by(db_models.SportsGamePlay.play_index)
    )
    plays_result = await session.execute(plays_stmt)
    return plays_result.scalars().all()


# =============================================================================
# SUMMARY GENERATION (TEMPLATE-BASED)
# =============================================================================


def _build_summary(plays: Sequence[db_models.SportsGamePlay]) -> str:
    """Build a template-based summary from plays."""
    if not plays:
        return "Moment recap unavailable."

    sentences: list[str] = []

    # Primary play description
    primary_play = _find_primary_play(plays)
    if primary_play:
        description = _describe_play(primary_play)
        if description:
            sentences.append(description)

    # Momentum sentence based on play types
    momentum = _build_momentum_sentence(plays)
    if momentum:
        sentences.append(momentum)

    # Strategy sentence
    strategy = _build_strategy_sentence(plays)
    if strategy:
        sentences.append(strategy)

    if not sentences:
        return "Momentum swung as the sequence unfolded."

    summary = " ".join(sentences[:3])
    return _redact_reveal_content(summary)


def _find_primary_play(
    plays: Sequence[db_models.SportsGamePlay],
) -> db_models.SportsGamePlay | None:
    for play in plays:
        if play.description:
            return play
    return plays[0] if plays else None


def _describe_play(play: db_models.SportsGamePlay) -> str | None:
    if play.description:
        sanitized = _sanitize_text(play.description)
        return _limit_to_sentence(sanitized)

    play_type = play.play_type.replace("_", " ") if play.play_type else "play"
    team_abbr = None
    if isinstance(play.raw_data, dict):
        team_abbr = play.raw_data.get("team_abbreviation")
    if team_abbr:
        return f"{team_abbr} initiated a {play_type} to set the tone."
    return f"A {play_type} set the tone for the moment."


def _build_momentum_sentence(plays: Sequence[db_models.SportsGamePlay]) -> str | None:
    play_types = {play.play_type or "" for play in plays}

    if _contains_type(play_types, {"turnover", "interception", "fumble", "giveaway"}):
        return "A turnover shifted possession and tilted the momentum."
    if _contains_type(play_types, {"timeout", "challenge", "review"}):
        return "A pause in play reset the tempo and forced adjustments."
    if _contains_type(play_types, {"foul", "penalty"}):
        return "Stops in play slowed the pace and shaped the next approach."
    if _contains_type(play_types, {"shot", "goal", "touchdown", "score"}):
        return "A strong push sparked the momentum shift."
    return None


def _build_strategy_sentence(plays: Sequence[db_models.SportsGamePlay]) -> str | None:
    descriptions = [play.description for play in plays if play.description]
    if not descriptions:
        return "Defensive pressure influenced the next look." if plays else None
    return "Execution focused on pressure and spacing to create the next opening."


def _contains_type(play_types: set[str], targets: set[str]) -> bool:
    return any(target in pt for pt in play_types for target in targets)


# =============================================================================
# TEXT SANITIZATION
# =============================================================================


def _sanitize_text(text: str) -> str:
    return _redact_reveal_content(text)


def _redact_reveal_content(text: str) -> str:
    """Remove score and outcome-revealing content."""
    cleaned = redact_scores(text)
    cleaned = _FINAL_SCORE_PATTERN.sub("", cleaned)
    cleaned = _BANNED_PHRASES_PATTERN.sub("", cleaned)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    if cleaned and cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    return cleaned


def _limit_to_sentence(text: str | None) -> str | None:
    if not text:
        return None
    parts = re.split(r"(?<=[.!?])\s+", text)
    return parts[0].strip() if parts else text.strip()
