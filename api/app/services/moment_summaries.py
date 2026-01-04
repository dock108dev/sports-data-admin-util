"""Moment summary generation service."""

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

logger = logging.getLogger(__name__)

_SUMMARY_CACHE_TTL = timedelta(minutes=10)


@dataclass
class _MomentSummaryCacheEntry:
    summary: str
    expires_at: datetime


_moment_summary_cache: dict[tuple[int, int], _MomentSummaryCacheEntry] = {}


_SCORE_PATTERN = re.compile(r"\b\d{1,3}\s*[-–:]\s*\d{1,3}\b")
_SCORE_AT_PATTERN = re.compile(r"\b\d{1,3}\s*(?:to|at)\s*\d{1,3}\b", re.IGNORECASE)
_FINAL_SCORE_PATTERN = re.compile(r"\bfinal\s+score\b", re.IGNORECASE)
_BANNED_PHRASES_PATTERN = re.compile(r"\b(game\s*winner|game-winner|final\s+drive)\b", re.IGNORECASE)
_WHITESPACE_PATTERN = re.compile(r"\s+")


async def summarize_moment(game_id: int, moment_id: int, session: AsyncSession) -> str:
    """Summarize a single moment by play index."""
    cache_key = (game_id, moment_id)
    cached = _get_cached_summary(cache_key)
    if cached:
        logger.info(
            "moment_summary_cache_hit",
            extra={"game_id": game_id, "moment_id": moment_id},
        )
        return cached

    logger.info(
        "moment_summary_cache_miss",
        extra={"game_id": game_id, "moment_id": moment_id},
    )

    plays: Sequence[db_models.SportsGamePlay] = []
    try:
        play = await _get_play_by_index(game_id, moment_id, session)
        if not play:
            raise ValueError(f"Moment not found for play_index={moment_id}")

        plays = await _fetch_moment_plays(play, session)
        try:
            logger.info(
                "moment_summary_ai_used",
                extra={
                    "game_id": game_id,
                    "moment_id": moment_id,
                    "play_count": len(plays),
                },
            )
            summary = _generate_ai_summary(plays)
        except Exception as exc:  # pragma: no cover - safety net
            logger.warning(
                "moment_summary_ai_failed: %s",
                str(exc),
                exc_info=True,
                extra={"game_id": game_id, "moment_id": moment_id},
            )
            summary = _fallback_summary(plays)

        _store_cached_summary(cache_key, summary)
        return summary
    except ValueError:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        logger.error(
            "moment_summary_unexpected_error: %s",
            str(exc),
            exc_info=True,
            extra={"game_id": game_id, "moment_id": moment_id},
        )
        return _fallback_summary(plays)


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


def _generate_ai_summary(plays: Sequence[db_models.SportsGamePlay]) -> str:
    if not plays:
        raise ValueError("No plays available for summary")
    summary = _build_summary_from_plays(plays)
    if not summary:
        raise ValueError("Failed to build summary")
    return summary


def _fallback_summary(plays: Sequence[db_models.SportsGamePlay]) -> str:
    if plays:
        return "Momentum swung as the sequence unfolded, with each possession shaping the pace."
    return "Moment recap unavailable."


def _build_summary_from_plays(plays: Sequence[db_models.SportsGamePlay]) -> str:
    primary_play = _find_primary_play(plays)
    sentences: list[str] = []
    if primary_play:
        description = _describe_play(primary_play)
        if description:
            sentences.append(description)

    momentum_sentence = _build_momentum_sentence(plays)
    if momentum_sentence:
        sentences.append(momentum_sentence)

    strategy_sentence = _build_strategy_sentence(plays)
    if strategy_sentence:
        sentences.append(strategy_sentence)

    sentences = [sentence for sentence in sentences if sentence]
    return " ".join(sentences[:3])


def _find_primary_play(plays: Sequence[db_models.SportsGamePlay]) -> db_models.SportsGamePlay | None:
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
        return _limit_to_sentence(_sanitize_text(f"{team_abbr} initiated a {play_type} to set the tone."))
    return _limit_to_sentence(_sanitize_text(f"A {play_type} set the tone for the moment."))


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
    return "Both sides traded possessions as the tempo settled."


def _build_strategy_sentence(plays: Sequence[db_models.SportsGamePlay]) -> str | None:
    descriptions = [play.description for play in plays if play.description]
    if not descriptions:
        return "Defensive pressure influenced the next look." if plays else None
    return "Execution focused on pressure and spacing to create the next opening."


def _contains_type(play_types: set[str], targets: set[str]) -> bool:
    return any(target in play_type for play_type in play_types for target in targets)


def _sanitize_text(text: str) -> str:
    cleaned = _SCORE_PATTERN.sub("", text)
    cleaned = _SCORE_AT_PATTERN.sub("", cleaned)
    cleaned = _FINAL_SCORE_PATTERN.sub("", cleaned)
    cleaned = _BANNED_PHRASES_PATTERN.sub("", cleaned)
    cleaned = cleaned.replace("  ", " ")
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    if cleaned and cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    return cleaned


def _limit_to_sentence(text: str | None) -> str | None:
    if not text:
        return None
    parts = re.split(r"(?<=[.!?])\\s+", text)
    return parts[0].strip() if parts else text.strip()


def _clear_summary_cache() -> None:
    _moment_summary_cache.clear()
