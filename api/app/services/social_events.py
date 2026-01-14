"""
Social event processing for timeline generation.

This module handles:
1. Social post role assignment (heuristic + AI-enhanced)
2. Phase assignment for social posts
3. Building social timeline events

Related modules:
- timeline_generator.py: Main timeline assembly
- ai_client.py: AI classification for role assignment

See docs/SOCIAL_EVENT_ROLES.md for role taxonomy.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable, Sequence

from .. import db_models
from .ai_client import classify_social_role, is_ai_available

logger = logging.getLogger(__name__)


# =============================================================================
# ROLE PATTERNS
# Compiled regex patterns for heuristic role assignment
# =============================================================================

_ROLE_PATTERNS = {
    # Pregame patterns
    "context": [
        re.compile(
            r"\b(starting|lineup|injury|out tonight|questionable|doubtful|inactive)\b",
            re.I,
        ),
        re.compile(r"\b(report|update|status)\b", re.I),
    ],
    "hype": [
        re.compile(
            r"\b(game\s*day|let'?s\s*go|tip[- ]?off|ready|tonight)\b", re.I
        ),
        re.compile(r"🔥|💪|⬆️|🏀", re.I),
    ],
    # In-game patterns
    "momentum": [
        re.compile(r"\d+-\d+\s*(run|lead|up\s+by)", re.I),
        re.compile(r"\b(run|streak|straight)\b", re.I),
    ],
    "milestone": [
        re.compile(
            r"\b(triple[- ]?double|double[- ]?double|career[- ]?high)\b", re.I
        ),
        re.compile(
            r"\b(\d+th|first|record)\b.*\b(of the season|in franchise)\b", re.I
        ),
    ],
    # Postgame patterns
    "result": [
        re.compile(r"\b(final|win|loss|victory|defeat)\b", re.I),
        re.compile(r"\bGG\b", re.I),
        re.compile(r"\d+\s*-\s*\d+\s*(final|$)", re.I),
    ],
    "reflection": [
        re.compile(r"\b(on to the next|tough loss|great win|back at it)\b", re.I),
        re.compile(r"\b(next game|wednesday|tomorrow)\b", re.I),
    ],
    # Universal patterns
    "highlight": [
        re.compile(r"👀|🎥|📹|watch|replay", re.I),
    ],
    "ambient": [
        re.compile(r"\b(crowd|arena|atmosphere|loud)\b", re.I),
    ],
}


# =============================================================================
# ROLE ASSIGNMENT
# =============================================================================


def assign_social_role_heuristic(
    text: str | None, phase: str, has_media: bool = False
) -> tuple[str, float]:
    """
    Assign a narrative role to a social post using pattern matching.

    Returns:
        Tuple of (role, confidence) where confidence is 0.0-1.0.
        High confidence (>=0.8) means AI fallback will be skipped.

    Roles define WHY a post is in the timeline:
    - hype: Build anticipation (pregame)
    - context: Provide information (pregame, early game)
    - reaction: Respond to action (in-game)
    - momentum: Mark a shift (in-game)
    - milestone: Celebrate achievement (any)
    - highlight: Share video/clip (any)
    - commentary: General observation (in-game)
    - result: Announce outcome (postgame)
    - reflection: Post-game takeaway (postgame)
    - ambient: Atmosphere content (any)

    See docs/SOCIAL_EVENT_ROLES.md for the full taxonomy.
    """
    # If no text, use media type or ambient (high confidence)
    if not text or not text.strip():
        return ("highlight", 0.9) if has_media else ("ambient", 0.9)

    # Check for media/highlight first (highest priority, high confidence)
    if has_media:
        for pattern in _ROLE_PATTERNS.get("highlight", []):
            if pattern.search(text):
                return ("highlight", 0.95)

    # Phase-specific refinements
    if phase == "pregame":
        # Check context patterns (high confidence)
        for pattern in _ROLE_PATTERNS.get("context", []):
            if pattern.search(text):
                return ("context", 0.85)
        # Default to hype for pregame (medium confidence)
        return ("hype", 0.7)

    elif phase == "postgame":
        # Check result patterns (high confidence)
        for pattern in _ROLE_PATTERNS.get("result", []):
            if pattern.search(text):
                return ("result", 0.9)
        # Check reflection patterns
        for pattern in _ROLE_PATTERNS.get("reflection", []):
            if pattern.search(text):
                return ("reflection", 0.85)
        # Default to result (medium confidence)
        return ("result", 0.7)

    else:
        # In-game phases (q1, q2, q3, q4, halftime, ot)
        # Check milestone first (high confidence)
        for pattern in _ROLE_PATTERNS.get("milestone", []):
            if pattern.search(text):
                return ("milestone", 0.9)

        # Check momentum (high confidence)
        for pattern in _ROLE_PATTERNS.get("momentum", []):
            if pattern.search(text):
                return ("momentum", 0.85)

        # Short exclamatory posts are reactions (high confidence)
        if len(text) < 30 and (
            text.endswith("!") or "!" in text or any(c in text for c in "🔥💪👏🙌")
        ):
            return ("reaction", 0.85)

        # Default to commentary for longer in-game posts (medium confidence)
        if len(text) > 50:
            return ("commentary", 0.6)

        # Default reaction (lower confidence - good candidate for AI)
        return ("reaction", 0.5)


async def assign_social_role_with_ai(
    text: str | None,
    phase: str,
    has_media: bool = False,
    sport: str = "NBA",
) -> str:
    """
    Assign a narrative role to a social post, with AI fallback.

    Flow:
    1. Fast heuristic pass - if confidence >= 0.8, return immediately
    2. Otherwise, call AI for classification (cached)

    AI is used ONLY for interpretation, not ordering or filtering.
    """
    # Fast heuristic pass
    role, confidence = assign_social_role_heuristic(text, phase, has_media)

    # If high confidence or AI unavailable, use heuristic
    if confidence >= 0.8 or not is_ai_available():
        return role

    # AI classification (with caching)
    try:
        ai_role = await classify_social_role(
            text=text or "",
            phase=phase,
            sport=sport,
            heuristic_role=role,
            heuristic_confidence=confidence,
        )
        return ai_role
    except Exception as e:
        logger.warning(
            "social_role_ai_fallback",
            extra={"error": str(e), "heuristic_role": role},
        )
        return role


def assign_social_role(text: str | None, phase: str, has_media: bool = False) -> str:
    """
    Synchronous role assignment (heuristic only).

    Use assign_social_role_with_ai for AI-enhanced classification.
    This is kept for backwards compatibility with sync code paths.
    """
    role, _ = assign_social_role_heuristic(text, phase, has_media)
    return role


# =============================================================================
# PHASE ASSIGNMENT
# =============================================================================


def assign_social_phase(
    posted_at: datetime, boundaries: dict[str, tuple[datetime, datetime]]
) -> str:
    """
    Assign a social post to a narrative phase based on posting time.

    Phase determines ordering. Timestamp is secondary.
    """
    for phase in [
        "pregame",
        "q1",
        "q2",
        "halftime",
        "q3",
        "q4",
        "ot1",
        "ot2",
        "postgame",
    ]:
        if phase not in boundaries:
            continue
        start, end = boundaries[phase]
        if start <= posted_at < end:
            return phase

    # Fallback: if before all phases, pregame; if after all, postgame
    earliest_start = min(b[0] for b in boundaries.values())
    if posted_at < earliest_start:
        return "pregame"
    return "postgame"


# =============================================================================
# EVENT BUILDING
# =============================================================================


def build_social_events(
    posts: Iterable[db_models.GameSocialPost],
    phase_boundaries: dict[str, tuple[datetime, datetime]],
) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Build social events with phase and role assignment (heuristic only).

    For AI-enhanced role classification, use build_social_events_async.

    Each event gets:
    - phase: The narrative phase - controls ordering
    - role: The narrative intent - why it's in the timeline
    - intra_phase_order: Sort key within phase
    - synthetic_timestamp: The actual posted_at time

    Events with null or empty text are DROPPED (not included in timeline).
    See docs/SOCIAL_EVENT_ROLES.md for role taxonomy.
    """
    events: list[tuple[datetime, dict[str, Any]]] = []
    dropped_count = 0

    for post in posts:
        # Filter: Drop posts with null or empty text
        text = post.tweet_text
        if text is None or text.strip() == "":
            dropped_count += 1
            logger.debug(
                "social_post_dropped_empty_text",
                extra={
                    "post_id": getattr(post, "id", None),
                    "author": post.source_handle,
                },
            )
            continue

        event_time = post.posted_at
        phase = assign_social_phase(event_time, phase_boundaries)

        # Assign role based on phase and content (heuristic)
        has_media = bool(getattr(post, "media_type", None))
        role = assign_social_role(text, phase, has_media)

        # Compute intra-phase order as seconds since phase start
        if phase in phase_boundaries:
            phase_start = phase_boundaries[phase][0]
            intra_phase_order = (event_time - phase_start).total_seconds()
        else:
            intra_phase_order = 0

        event_payload = {
            "event_type": "tweet",
            "phase": phase,
            "role": role,
            "intra_phase_order": intra_phase_order,
            "author": post.source_handle,
            "handle": post.source_handle,
            "text": text,
            "synthetic_timestamp": event_time.isoformat(),
        }
        events.append((event_time, event_payload))

    if dropped_count > 0:
        logger.info(
            "social_posts_filtered",
            extra={"dropped_empty_text": dropped_count, "included": len(events)},
        )

    return events


async def build_social_events_async(
    posts: Sequence[db_models.GameSocialPost],
    phase_boundaries: dict[str, tuple[datetime, datetime]],
    sport: str = "NBA",
) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Build social events with AI-enhanced role classification.

    Uses async AI client for role classification with caching.
    """
    events: list[tuple[datetime, dict[str, Any]]] = []
    dropped_count = 0

    for post in posts:
        # Filter: Drop posts with null or empty text
        text = post.tweet_text
        if text is None or text.strip() == "":
            dropped_count += 1
            logger.debug(
                "social_post_dropped_empty_text",
                extra={
                    "post_id": getattr(post, "id", None),
                    "author": post.source_handle,
                },
            )
            continue

        event_time = post.posted_at
        phase = assign_social_phase(event_time, phase_boundaries)

        # Assign role with AI enhancement
        has_media = bool(getattr(post, "media_type", None))
        role = await assign_social_role_with_ai(text, phase, has_media, sport)

        # Compute intra-phase order as seconds since phase start
        if phase in phase_boundaries:
            phase_start = phase_boundaries[phase][0]
            intra_phase_order = (event_time - phase_start).total_seconds()
        else:
            intra_phase_order = 0

        event_payload = {
            "event_type": "tweet",
            "phase": phase,
            "role": role,
            "intra_phase_order": intra_phase_order,
            "author": post.source_handle,
            "handle": post.source_handle,
            "text": text,
            "synthetic_timestamp": event_time.isoformat(),
        }
        events.append((event_time, event_payload))

    if dropped_count > 0:
        logger.info(
            "social_posts_filtered",
            extra={"dropped_empty_text": dropped_count, "included": len(events)},
        )

    return events
