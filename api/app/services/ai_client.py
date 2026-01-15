"""
OpenAI client wrapper with caching for sports timeline AI features.

Design Principle:
    OpenAI is used ONLY for interpretation and narration — never for
    ordering, filtering, or correctness decisions.

Three AI Use Cases:
    1. Social Role Classification - Improve role accuracy beyond heuristics
    2. Segment Enrichment - Label game segments more naturally
    3. Summary Generation - Produce timeline "reading guide" text

All outputs are:
    - Idempotent (same input → same output)
    - Cached aggressively (no AI on read paths)
    - Regenerable only on version bump or cache miss
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

from openai import AsyncOpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)

# Valid social roles for classification
SOCIAL_ROLES = Literal[
    "hype", "context", "reaction", "momentum",
    "highlight", "result", "reflection", "ambient"
]

# Valid segment tones
SEGMENT_TONES = Literal["calm", "tense", "decisive", "flat"]


# ---------------------------------------------------------------------------
# In-Memory Cache (Production should use Redis)
# ---------------------------------------------------------------------------
# TTL: 30 days for roles, permanent for summaries/segments
# In production, replace with Redis-backed cache

_role_cache: dict[str, str] = {}
_segment_cache: dict[str, dict[str, str]] = {}
_summary_cache: dict[str, dict[str, Any]] = {}


def _cache_key_role(text: str, phase: str) -> str:
    """Generate cache key for social role classification."""
    content = f"{text}:{phase}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _cache_key_segment(game_id: int, segment_id: str) -> str:
    """Generate cache key for segment enrichment."""
    return f"seg:{game_id}:{segment_id}"


def _cache_key_summary(game_id: int, timeline_version: str) -> str:
    """Generate cache key for summary generation."""
    return f"sum:{game_id}:{timeline_version}"


# ---------------------------------------------------------------------------
# OpenAI Client
# ---------------------------------------------------------------------------

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Get or create the OpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def is_ai_available() -> bool:
    """Check if OpenAI is configured and available."""
    settings = get_settings()
    return bool(settings.openai_api_key)


# ---------------------------------------------------------------------------
# Social Role Classification
# ---------------------------------------------------------------------------

ROLE_CLASSIFICATION_PROMPT = """You are classifying a sports-related social media post.

Context:
- Sport: {sport}
- Game phase: {phase}
- This post is from an official team or league account

Choose exactly one role from:
- hype (pregame excitement, anticipation)
- context (pregame info, injury news, lineup)
- reaction (in-game response to play)
- momentum (run/swing commentary)
- highlight (notable play reference)
- result (final score, outcome)
- reflection (postgame thoughts, analysis)
- ambient (atmosphere, crowd, general)

Post text:
"{tweet_text}"

Respond with ONLY the role name, nothing else."""


async def classify_social_role(
    text: str,
    phase: str,
    sport: str = "NBA",
    heuristic_role: str | None = None,
    heuristic_confidence: float = 0.0,
) -> str:
    """
    Classify social post role using AI, with caching.

    Args:
        text: The tweet/post text
        phase: Narrative phase (pregame, q1, q2, halftime, q3, q4, postgame)
        sport: Sport name for context
        heuristic_role: Role from heuristic classification (if available)
        heuristic_confidence: Confidence of heuristic (0.0-1.0)

    Returns:
        Role string (one of SOCIAL_ROLES)
    """
    settings = get_settings()

    # Skip AI if disabled or high-confidence heuristic
    if not settings.enable_ai_social_roles or not is_ai_available():
        logger.debug(
            "ai_social_role_skipped",
            extra={"reason": "disabled_or_unavailable"},
        )
        return heuristic_role or "ambient"

    if heuristic_confidence >= 0.8 and heuristic_role:
        logger.debug(
            "ai_social_role_skipped",
            extra={"reason": "high_confidence_heuristic", "role": heuristic_role},
        )
        return heuristic_role

    # Check cache
    cache_key = _cache_key_role(text, phase)
    if cached := _role_cache.get(cache_key):
        logger.debug("ai_social_role_cache_hit", extra={"role": cached})
        return cached

    # Call OpenAI
    try:
        client = _get_client()
        prompt = ROLE_CLASSIFICATION_PROMPT.format(
            sport=sport,
            phase=phase,
            tweet_text=text[:500],  # Truncate for safety
        )

        response = await client.chat.completions.create(
            model=settings.openai_model_classification,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=5,
        )

        role = response.choices[0].message.content.strip().lower()

        # Validate response
        valid_roles = {
            "hype", "context", "reaction", "momentum",
            "highlight", "result", "reflection", "ambient"
        }
        if role not in valid_roles:
            logger.warning(
                "ai_social_role_invalid",
                extra={"returned": role, "fallback": heuristic_role or "ambient"},
            )
            role = heuristic_role or "ambient"

        # Cache result
        _role_cache[cache_key] = role
        logger.info("ai_social_role_classified", extra={"role": role})
        return role

    except Exception as e:
        logger.error("ai_social_role_error", extra={"error": str(e)})
        return heuristic_role or "ambient"


# ---------------------------------------------------------------------------
# Segment Enrichment
# ---------------------------------------------------------------------------

SEGMENT_ENRICHMENT_PROMPT = """You are labeling stretches of an {sport} game for a timeline-based app.

Each segment already has:
- start phase
- end phase
- segment_type (run, swing, steady, etc.)

Your job:
- Add a short, neutral label describing what this stretch *felt like*
- Do NOT invent events
- Do NOT restate scores
- Do NOT use flowery language

Segment type: {segment_type}
Phases: {start_phase} → {end_phase}
Play count: {play_count}

Respond with valid JSON only:
{{"label": "short phrase", "tone": "calm | tense | decisive | flat"}}"""


async def enrich_segment(
    game_id: int,
    segment_id: str,
    segment_type: str,
    start_phase: str,
    end_phase: str,
    play_count: int,
    sport: str = "NBA",
) -> dict[str, str]:
    """
    Enrich a game segment with AI-generated label and tone.

    Args:
        game_id: Game identifier
        segment_id: Unique segment identifier
        segment_type: Type of segment (run, swing, steady, etc.)
        start_phase: Starting phase
        end_phase: Ending phase
        play_count: Number of plays in segment
        sport: Sport name

    Returns:
        Dict with 'label' and 'tone' keys
    """
    settings = get_settings()
    default = {"label": segment_type.replace("_", " ").title(), "tone": "calm"}

    # Skip AI if disabled
    if not settings.enable_ai_segment_enrichment or not is_ai_available():
        return default

    # Check cache
    cache_key = _cache_key_segment(game_id, segment_id)
    if cached := _segment_cache.get(cache_key):
        logger.debug("ai_segment_cache_hit", extra={"segment_id": segment_id})
        return cached

    # Call OpenAI
    try:
        client = _get_client()
        prompt = SEGMENT_ENRICHMENT_PROMPT.format(
            sport=sport,
            segment_type=segment_type,
            start_phase=start_phase,
            end_phase=end_phase,
            play_count=play_count,
        )

        response = await client.chat.completions.create(
            model=settings.openai_model_classification,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=50,
        )

        content = response.choices[0].message.content.strip()
        result = json.loads(content)

        # Validate
        if "label" not in result or "tone" not in result:
            raise ValueError("Invalid response structure")

        valid_tones = {"calm", "tense", "decisive", "flat"}
        if result["tone"] not in valid_tones:
            result["tone"] = "calm"

        # Cache result
        _segment_cache[cache_key] = result
        logger.info(
            "ai_segment_enriched",
            extra={"segment_id": segment_id, "label": result["label"]},
        )
        return result

    except Exception as e:
        logger.error(
            "ai_segment_error",
            extra={"error": str(e), "segment_id": segment_id},
        )
        return default


# ---------------------------------------------------------------------------
# Summary Generation
# ---------------------------------------------------------------------------

SUMMARY_GENERATION_PROMPT = """Tell someone HOW to read this timeline. Not what happened.

DO NOT:
- Summarize the game
- Use words: pivotal, critical, defining, crucial, dramatic, dynamic, momentum shifts
- Make it feel complete without scrolling
- Use em-dashes

GAME DATA:
Phases: {phases}
Stretches: {segment_summaries}
Highlights: {highlights}
Social: {social_counts}

YOUR JOB:
Point to where the timeline gets interesting. Be specific about WHEN.
Examples of good guidance:
- "This stays flat until the third"
- "The first quarter is where it opens up"
- "Most of the action is late"
- "Skip to the second half if you want the real game"

Use the stretch labels to guide where to look. If there's a "swing" or "run" stretch, tell them where.
If social clusters postgame, mention it briefly.

2-3 sentences. Be direct. Each game should sound different.
2-3 attention points as quick fragments.

JSON only:
{{
  "overview": "direct guidance on how to read this timeline",
  "attention_points": ["fragment 1", "fragment 2", "fragment 3"]
}}"""


async def generate_summary(
    game_id: int,
    timeline_version: str,
    phases: list[str],
    segment_summaries: list[str],
    highlights: list[str],
    social_counts: dict[str, int],
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Generate a timeline reading guide using AI.

    Args:
        game_id: Game identifier
        timeline_version: Version string for cache keying
        phases: List of phases present in timeline
        segment_summaries: Brief descriptions of key segments
        highlights: Notable moments
        social_counts: Social activity counts by phase
        sport: Sport name

    Returns:
        Dict with 'overview' and 'attention_points' keys
    """
    settings = get_settings()
    default = {
        "overview": "Scroll through the timeline to experience the game.",
        "attention_points": [],
    }

    # Skip AI if disabled
    if not settings.enable_ai_summary or not is_ai_available():
        return default

    # Check cache
    cache_key = _cache_key_summary(game_id, timeline_version)
    if cached := _summary_cache.get(cache_key):
        logger.debug("ai_summary_cache_hit", extra={"game_id": game_id})
        return cached

    # Call OpenAI
    try:
        client = _get_client()
        prompt = SUMMARY_GENERATION_PROMPT.format(
            phases=", ".join(phases),
            segment_summaries="; ".join(segment_summaries[:5]),  # Limit
            highlights="; ".join(highlights[:5]),  # Limit
            social_counts=json.dumps(social_counts),
        )

        response = await client.chat.completions.create(
            model=settings.openai_model_summary,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,  # Higher for more variety
            max_tokens=180,
        )

        content = response.choices[0].message.content.strip()

        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        result = json.loads(content)

        # Validate structure
        if "overview" not in result:
            result["overview"] = default["overview"]
        if "attention_points" not in result:
            result["attention_points"] = []

        # Ensure attention_points is a list
        if not isinstance(result["attention_points"], list):
            result["attention_points"] = []

        # Cache result (permanent)
        _summary_cache[cache_key] = result
        logger.info(
            "ai_summary_generated",
            extra={
                "game_id": game_id,
                "overview_len": len(result["overview"]),
                "attention_points": len(result["attention_points"]),
            },
        )
        return result

    except Exception as e:
        logger.error(
            "ai_summary_error",
            extra={"error": str(e), "game_id": game_id},
        )
        return default


# ---------------------------------------------------------------------------
# Cache Management (for testing/admin)
# ---------------------------------------------------------------------------

def clear_cache(cache_type: str | None = None) -> dict[str, int]:
    """
    Clear AI caches. For testing/admin use.

    Args:
        cache_type: 'role', 'segment', 'summary', or None for all

    Returns:
        Dict with cleared counts per cache type
    """
    global _role_cache, _segment_cache, _summary_cache
    cleared = {}

    if cache_type in (None, "role"):
        cleared["role"] = len(_role_cache)
        _role_cache = {}

    if cache_type in (None, "segment"):
        cleared["segment"] = len(_segment_cache)
        _segment_cache = {}

    if cache_type in (None, "summary"):
        cleared["summary"] = len(_summary_cache)
        _summary_cache = {}

    logger.info("ai_cache_cleared", extra={"cleared": cleared})
    return cleared


def get_cache_stats() -> dict[str, int]:
    """Get current cache sizes."""
    return {
        "role": len(_role_cache),
        "segment": len(_segment_cache),
        "summary": len(_summary_cache),
    }
