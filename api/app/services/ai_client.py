"""
OpenAI client wrapper with caching for sports timeline AI features.

=============================================================================
DESIGN PHILOSOPHY (2026-01 Refactor)
=============================================================================

AI is PURELY DESCRIPTIVE. It cannot affect:
- Moment boundaries (determined by Lead Ladder)
- Importance (determined by MomentType)
- Ordering (determined by chronology)
- What gets shown (determined by Compact Mode)

AI ONLY writes copy:
- headline: One-line game description
- subhead: Brief supporting context

This is enforced by:
1. Structured Moment input only (no raw timeline)
2. No structural fields in output
3. Deterministic fallbacks for all paths
4. Graceful degradation when AI unavailable

=============================================================================
CACHING
=============================================================================

All outputs are:
- Idempotent (same input → same output)
- Cached aggressively (no AI on read paths)
- Regenerable only on version bump or cache miss
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# TYPE DEFINITIONS
# =============================================================================

# Valid social roles for classification
SOCIAL_ROLES = Literal[
    "hype", "context", "reaction", "momentum",
    "highlight", "result", "reflection", "ambient"
]


@dataclass(frozen=True)
class MomentSummaryInput:
    """
    Structured input for AI moment summarization.
    
    This is EXACTLY what AI receives - no more, no less.
    AI cannot infer structure from this; it can only describe.
    """
    moment_type: str      # e.g., "FLIP", "LEAD_BUILD"
    score_before: str     # e.g., "45-42"
    score_after: str      # e.g., "52-48"
    team_in_control: str | None  # "home", "away", or None
    note: str | None      # e.g., "12-0 run"


@dataclass(frozen=True)
class GameSummaryInput:
    """
    Structured input for AI game headline/subhead generation.
    
    This is the ONLY data AI receives about the game.
    It cannot affect structure - only describe what happened.
    """
    home_team: str
    away_team: str
    final_score_home: int
    final_score_away: int
    flow: str  # "close", "competitive", "comfortable", "blowout"
    has_overtime: bool
    moment_types: list[str]  # e.g., ["OPENER", "LEAD_BUILD", "FLIP", "CLOSING_CONTROL"]
    notable_count: int  # Number of notable moments


@dataclass(frozen=True)
class AIHeadlineOutput:
    """
    What AI returns. ONLY headline and subhead.
    
    No structural fields. No importance. No ordering.
    AI writes copy, nothing else.
    """
    headline: str  # One-line summary (max 80 chars)
    subhead: str   # Supporting context (max 120 chars)


# =============================================================================
# IN-MEMORY CACHE (Production should use Redis)
# =============================================================================

_role_cache: dict[str, str] = {}
_headline_cache: dict[str, AIHeadlineOutput] = {}


def _cache_key_role(text: str, phase: str) -> str:
    """Generate cache key for social role classification."""
    content = f"{text}:{phase}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _cache_key_headline(game_id: int, timeline_version: str) -> str:
    """Generate cache key for headline generation."""
    return f"hl:{game_id}:{timeline_version}"


# =============================================================================
# OPENAI CLIENT
# =============================================================================

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


# =============================================================================
# DETERMINISTIC FALLBACKS
# =============================================================================

def generate_fallback_headline(input_data: GameSummaryInput) -> AIHeadlineOutput:
    """
    Generate deterministic headline when AI is unavailable.
    
    This function produces consistent, reasonable output
    without any AI involvement. It's the safety net.
    """
    # Determine winner
    if input_data.final_score_home > input_data.final_score_away:
        winner = input_data.home_team
        loser = input_data.away_team
        winner_score = input_data.final_score_home
        loser_score = input_data.final_score_away
    elif input_data.final_score_away > input_data.final_score_home:
        winner = input_data.away_team
        loser = input_data.home_team
        winner_score = input_data.final_score_away
        loser_score = input_data.final_score_home
    else:
        # Tie (rare in most sports)
        return AIHeadlineOutput(
            headline=f"{input_data.home_team} and {input_data.away_team} end in a draw",
            subhead=f"Final: {input_data.final_score_home}-{input_data.final_score_away}",
        )
    
    # Generate headline based on flow
    if input_data.flow == "blowout":
        headline = f"{winner} rolls past {loser}"
    elif input_data.flow == "comfortable":
        headline = f"{winner} handles {loser}"
    elif input_data.flow == "competitive":
        headline = f"{winner} holds off {loser}"
    elif input_data.flow == "close":
        if input_data.has_overtime:
            headline = f"{winner} survives {loser} in OT"
        else:
            headline = f"{winner} edges {loser} in a tight one"
    else:
        headline = f"{winner} defeats {loser}"
    
    # Generate subhead
    score_text = f"Final: {winner_score}-{loser_score}"
    if input_data.has_overtime:
        score_text += " (OT)"
    
    # Add moment context if available
    if "FLIP" in input_data.moment_types:
        subhead = f"{score_text}. Lead changed hands."
    elif "CLOSING_CONTROL" in input_data.moment_types:
        subhead = f"{score_text}. Decided late."
    elif input_data.notable_count >= 3:
        subhead = f"{score_text}. Several key swings."
    else:
        subhead = score_text
    
    return AIHeadlineOutput(
        headline=headline[:80],
        subhead=subhead[:120],
    )


def generate_fallback_moment_label(moment_type: str, note: str | None) -> str:
    """
    Generate deterministic moment label when AI is unavailable.
    """
    labels = {
        "LEAD_BUILD": "Lead extended",
        "CUT": "Opponent cuts in",
        "TIE": "Game tied",
        "FLIP": "Lead changes hands",
        "CLOSING_CONTROL": "Game control locked",
        "HIGH_IMPACT": "High-impact moment",
        "OPENER": "Period begins",
        "NEUTRAL": "Back and forth",
    }
    base_label = labels.get(moment_type, moment_type)
    
    if note:
        return f"{base_label}: {note}"
    return base_label


# =============================================================================
# SOCIAL ROLE CLASSIFICATION
# =============================================================================

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
    
    AI classifies the role but cannot affect:
    - When the post appears in timeline (chronological)
    - Whether the post is shown (always shown)
    - The post's importance (determined by phase)
    """
    settings = get_settings()

    # Skip AI if disabled or high-confidence heuristic
    if not settings.enable_ai_social_roles or not is_ai_available():
        return heuristic_role or "ambient"

    if heuristic_confidence >= 0.8 and heuristic_role:
        return heuristic_role

    # Check cache
    cache_key = _cache_key_role(text, phase)
    if cached := _role_cache.get(cache_key):
        return cached

    # Call OpenAI
    try:
        client = _get_client()
        prompt = ROLE_CLASSIFICATION_PROMPT.format(
            sport=sport,
            phase=phase,
            tweet_text=text[:500],
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
        return role

    except Exception as e:
        logger.error("ai_social_role_error", extra={"error": str(e)})
        return heuristic_role or "ambient"


# =============================================================================
# HEADLINE GENERATION (Primary AI Use Case)
# =============================================================================

HEADLINE_GENERATION_PROMPT = """Write a headline and subhead for this game.

RULES:
- Headline: ONE sentence, max 80 characters
- Subhead: ONE sentence, max 120 characters
- Be direct and specific
- NO: pivotal, critical, defining, crucial, dramatic, dynamic, momentum shifts
- NO: em-dashes, exclamation points
- State what happened, not what it meant

GAME DATA:
{home_team} vs {away_team}
Final: {final_score_home}-{final_score_away}
Flow: {flow}
Overtime: {has_overtime}
Key moments: {moment_types}

JSON only:
{{"headline": "...", "subhead": "..."}}"""


async def generate_headline(
    game_id: int,
    timeline_version: str,
    input_data: GameSummaryInput,
) -> AIHeadlineOutput:
    """
    Generate headline and subhead for a game using AI.
    
    AI ONLY WRITES COPY. It cannot affect:
    - Moment boundaries (from Lead Ladder)
    - Moment importance (from MomentType)
    - What gets shown (from Compact Mode)
    - Timeline ordering (chronological)
    
    Args:
        game_id: Game identifier (for caching)
        timeline_version: Version string (for cache invalidation)
        input_data: Structured game data
        
    Returns:
        AIHeadlineOutput with headline and subhead
    """
    settings = get_settings()
    
    # Fallback if AI disabled
    if not getattr(settings, 'enable_ai_summary', True) or not is_ai_available():
        logger.info(
            "ai_headline_fallback",
            extra={"game_id": game_id, "reason": "ai_unavailable"},
        )
        return generate_fallback_headline(input_data)
    
    # Check cache
    cache_key = _cache_key_headline(game_id, timeline_version)
    if cached := _headline_cache.get(cache_key):
        logger.debug("ai_headline_cache_hit", extra={"game_id": game_id})
        return cached
    
    # Build prompt with structured data only
    try:
        client = _get_client()
        prompt = HEADLINE_GENERATION_PROMPT.format(
            home_team=input_data.home_team,
            away_team=input_data.away_team,
            final_score_home=input_data.final_score_home,
            final_score_away=input_data.final_score_away,
            flow=input_data.flow,
            has_overtime="Yes" if input_data.has_overtime else "No",
            moment_types=", ".join(input_data.moment_types[:5]),  # Limit
        )
        
        response = await client.chat.completions.create(
            model=settings.openai_model_summary,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,  # Moderate creativity
            max_tokens=100,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        
        result = json.loads(content)
        
        # Validate and sanitize
        headline = result.get("headline", "")[:80]
        subhead = result.get("subhead", "")[:120]
        
        if not headline:
            # AI returned empty headline - use fallback
            return generate_fallback_headline(input_data)
        
        output = AIHeadlineOutput(headline=headline, subhead=subhead)
        
        # Cache result
        _headline_cache[cache_key] = output
        
        logger.info(
            "ai_headline_generated",
            extra={
                "game_id": game_id,
                "headline_len": len(headline),
            },
        )
        
        return output
        
    except Exception as e:
        logger.error(
            "ai_headline_error",
            extra={"error": str(e), "game_id": game_id},
        )
        return generate_fallback_headline(input_data)


# =============================================================================
# CACHE MANAGEMENT (for testing/admin)
# =============================================================================

def clear_cache(cache_type: str | None = None) -> dict[str, int]:
    """
    Clear AI caches. For testing/admin use.
    """
    global _role_cache, _headline_cache
    cleared = {}

    if cache_type in (None, "role"):
        cleared["role"] = len(_role_cache)
        _role_cache = {}

    if cache_type in (None, "headline"):
        cleared["headline"] = len(_headline_cache)
        _headline_cache = {}

    logger.info("ai_cache_cleared", extra={"cleared": cleared})
    return cleared


def get_cache_stats() -> dict[str, int]:
    """Get current cache sizes."""
    return {
        "role": len(_role_cache),
        "headline": len(_headline_cache),
    }
