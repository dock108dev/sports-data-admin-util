"""Recap generation service for game snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re

from .. import db_models
from ..utils.reveal_utils import classify_reveal_risk, redact_scores
from .reveal_levels import RevealLevel

_OUTCOME_PATTERN = re.compile(
    r"\b(win|wins|won|defeat|defeats|defeated|beat|beats|victory|loss|loses|lost)\b",
    re.IGNORECASE,
)
_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class RecapResult:
    available: bool
    reveal_level: RevealLevel
    summary: str | None
    reason: str | None


def _sanitize_pre_reveal(text: str) -> str:
    cleaned = redact_scores(text)
    cleaned = _OUTCOME_PATTERN.sub("", cleaned)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned


def _momentum_sentence(plays: Iterable[db_models.SportsGamePlay]) -> str:
    play_types = {play.play_type or "" for play in plays}
    if any(term in play_type for play_type in play_types for term in ("turnover", "interception", "fumble", "giveaway")):
        return "Momentum swung after a turnover-heavy stretch."
    if any(term in play_type for play_type in play_types for term in ("shot", "goal", "touchdown", "score")):
        return "Scoring bursts kept the tempo high."
    if any(term in play_type for play_type in play_types for term in ("timeout", "challenge", "review")):
        return "A reset in play shifted the rhythm."
    return "Both sides traded possessions as the pace settled."


def _period_sentences(
    plays: list[db_models.SportsGamePlay],
    reveal_level: RevealLevel,
) -> list[str]:
    periods: dict[int | None, list[db_models.SportsGamePlay]] = {}
    for play in plays:
        periods.setdefault(play.quarter, []).append(play)

    sentences: list[str] = []
    for period, period_plays in sorted(periods.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        descriptions = [play.description for play in period_plays if play.description]
        if not descriptions:
            continue
        first = descriptions[0]
        last = descriptions[-1] if descriptions[-1] != first else None
        if reveal_level == RevealLevel.pre:
            first = _sanitize_pre_reveal(first)
            if last:
                last = _sanitize_pre_reveal(last)
        if not first:
            continue
        label = f"Period {period}" if period is not None else "Early action"
        if last:
            sentences.append(f"{label} featured {first} Later, {last}".strip())
        else:
            sentences.append(f"{label} featured {first}".strip())
    return sentences


def _social_sentence(
    posts: list[db_models.GameSocialPost],
    reveal_level: RevealLevel,
) -> str | None:
    if not posts:
        return None
    if reveal_level == RevealLevel.pre:
        safe_posts = [post for post in posts if not _post_reveal_risk(post)]
        if not safe_posts:
            return None
        post = safe_posts[0]
        content = _sanitize_pre_reveal(post.tweet_text or "")
    else:
        post = posts[0]
        content = (post.tweet_text or "").strip()
    if not content:
        return None
    return f"Social spotlight: {content}"


def _post_reveal_risk(post: db_models.GameSocialPost) -> bool:
    if post.reveal_risk:
        return True
    classification = classify_reveal_risk(post.tweet_text)
    return classification.reveal_risk


def build_recap(
    game: db_models.SportsGame,
    plays: list[db_models.SportsGamePlay],
    social_posts: list[db_models.GameSocialPost],
    reveal_level: RevealLevel,
) -> RecapResult:
    if not plays:
        return RecapResult(
            available=False,
            reveal_level=reveal_level,
            summary=None,
            reason="pbp_missing",
        )

    home_name = game.home_team.name if game.home_team else "Home"
    away_name = game.away_team.name if game.away_team else "Away"

    summary_parts: list[str] = []
    summary_parts.append(f"{away_name} at {home_name} featured stretches of back-and-forth play.")
    summary_parts.append(_momentum_sentence(plays))
    summary_parts.extend(_period_sentences(plays, reveal_level))

    social_sentence = _social_sentence(social_posts, reveal_level)
    if social_sentence:
        summary_parts.append(social_sentence)

    if reveal_level == RevealLevel.post:
        if game.home_score is not None and game.away_score is not None:
            summary_parts.append(
                f"Final score: {home_name} {game.home_score}, {away_name} {game.away_score}."
            )
        else:
            summary_parts.append("Final score was unavailable.")

    summary = " ".join(part for part in summary_parts if part)
    if reveal_level == RevealLevel.pre:
        summary = _sanitize_pre_reveal(summary)
    if summary and summary[-1] not in ".!?":
        summary = f"{summary}."

    return RecapResult(
        available=True,
        reveal_level=reveal_level,
        summary=summary,
        reason=None,
    )
