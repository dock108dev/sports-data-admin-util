"""
OpenAI client for sports timeline enrichment.

=============================================================================
DESIGN PHILOSOPHY
=============================================================================

OpenAI is a NARRATIVE RENDERER, not a decision engine.

AI's job:
- Write headlines + summaries with energy
- Capture momentum, pressure, swings
- Call the game as it unfolds

AI NEVER:
- Decides moment boundaries (Lead Ladder does that)
- Decides importance (MomentType does that)
- Decides ordering (chronology does that)
- Infers outcomes (spoiler-safe)

If OpenAI fails → the build fails. No silent fallbacks. No templates.

=============================================================================
BATCH ENRICHMENT
=============================================================================

One OpenAI call per game. All moments enriched together for:
- Consistent tone across moments
- Shared game context
- Lower cost
- Deterministic retries
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================


class AIEnrichmentError(Exception):
    """Raised when AI enrichment fails. No fallback."""
    pass


class AIConfigurationError(Exception):
    """Raised when OpenAI is not configured."""
    pass


class AIValidationError(Exception):
    """Raised when AI output fails validation."""
    pass


# =============================================================================
# TYPE DEFINITIONS
# =============================================================================


@dataclass(frozen=True)
class GameContext:
    """Game-level context for AI enrichment."""
    home_team: str
    away_team: str
    final_score_home: int
    final_score_away: int
    sport: str = "NBA"


@dataclass(frozen=True)
class MomentEnrichmentInput:
    """Single moment input for batch enrichment.
    
    PHASE 3: Now includes narrative context for AI awareness.
    """
    id: str
    type: str  # LEAD_BUILD, CUT, TIE, FLIP, CLOSING_CONTROL, HIGH_IMPACT, NEUTRAL
    score_before: str  # "45-42"
    score_after: str   # "52-48"
    time_window: str   # "Q1 12:00-11:18"
    reason: dict[str, Any]  # {trigger, control_shift, narrative_delta}
    team_in_control: str | None = None
    run_info: dict[str, Any] | None = None
    key_plays: list[str] = field(default_factory=list)
    context: dict[str, Any] | None = None  # PHASE 3: Narrative context from Prompt 2


@dataclass
class MomentEnrichmentOutput:
    """Single moment output from AI."""
    id: str
    headline: str  # max 60 chars
    summary: str   # max 150 chars


@dataclass
class GameEnrichmentOutput:
    """Complete game enrichment output."""
    game_headline: str   # max 80 chars
    game_subhead: str    # max 120 chars
    moments: list[MomentEnrichmentOutput]


# =============================================================================
# FORBIDDEN WORDS (Spoiler Protection)
# =============================================================================

# Forbidden words that reveal outcomes (spoilers)
# Note: "final" is allowed in context ("final quarter", "final minute")
# but these phrases are forbidden as they imply outcome knowledge
FORBIDDEN_WORDS = frozenset({
    "wins", "won", "winner", "winning",
    "loses", "lost", "loser", "losing",
    "sealed", "clinched", "secured",
    "dagger", "decisive", "decided",
    "finals",  # "final" alone is ok for "final quarter"
    "finale",
    "victory", "victorious",
    "defeat", "defeated",
    "champion", "championship",
    "eliminated",
    "proved to be", "turned out to be",
    "would go on to", "went on to",
    "in the end", "ultimately",
    "game over", "it's over",
    "seals the deal", "puts it away",
})

FORBIDDEN_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in FORBIDDEN_WORDS) + r')\b',
    re.IGNORECASE
)


def _check_forbidden_words(text: str) -> list[str]:
    """Return list of forbidden words found in text."""
    matches = FORBIDDEN_PATTERN.findall(text)
    return list(set(m.lower() for m in matches))


# =============================================================================
# OPENAI CLIENT
# =============================================================================

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Get or create the OpenAI client. Raises if not configured."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise AIConfigurationError(
                "OPENAI_API_KEY is not configured. "
                "AI enrichment is required - no fallback available."
            )
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def require_ai_available() -> None:
    """Raise if AI is not configured. Call at startup to fail fast."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise AIConfigurationError("OPENAI_API_KEY is required for timeline generation.")


def is_ai_available() -> bool:
    """
    Check if AI is configured (for non-critical features like social classification).
    
    Note: For moment enrichment (critical), use require_ai_available() instead.
    This function is for features that can gracefully fall back to heuristics.
    """
    settings = get_settings()
    return bool(settings.openai_api_key)


# =============================================================================
# CACHE
# =============================================================================

_enrichment_cache: dict[str, GameEnrichmentOutput] = {}


def _cache_key(game_id: int, timeline_version: str) -> str:
    """Generate cache key for game enrichment."""
    return f"enrich:{game_id}:{timeline_version}"


def clear_enrichment_cache() -> int:
    """Clear the enrichment cache. Returns count cleared."""
    global _enrichment_cache
    count = len(_enrichment_cache)
    _enrichment_cache = {}
    logger.info("enrichment_cache_cleared", extra={"count": count})
    return count


# =============================================================================
# THE SPORTSCENTER PROMPT
# =============================================================================

ENRICHMENT_SYSTEM_PROMPT = """You are a SportsCenter-style game narrator with FULL MEMORY of what happened before.

You are describing moments AS THEY HAPPEN, not after the game ends.
The reader is discovering the game through these moments.
They do NOT know the final outcome yet.

Your job is to capture momentum, pressure, and swings in control
with energy and clarity — without revealing how the game ends.

---

PHASE 3: NARRATIVE AWARENESS RULES

You now receive CONTEXT for each moment. Use it to write coherent, non-repetitive narration.

1. CONTINUITY AWARENESS
   - If context.is_continuation = true:
     → This is the NEXT PARAGRAPH, not a new chapter
     → Do NOT reintroduce the situation
     → Use continuation language: "continues", "extends", "keeps", "still"
   
   - If context.is_continuation = false:
     → This REVERSES or SHIFTS the previous narrative
     → Acknowledge the change: "but", "however", "answers back"

2. PHASE SENSITIVITY
   - If context.game_phase = "opening":
     → NO urgency language ("crucial", "must-have", "desperate")
     → NO comeback language (it's Q1, nothing to come back from yet)
     → Focus on "early", "to start", "opening minutes"
   
   - If context.game_phase = "middle":
     → Focus on control, momentum, or stability
     → Describe WHO is dictating pace
     → Avoid premature resolution language
   
   - If context.game_phase = "closing":
     → Resolution language allowed ONLY if context supports it
     → Check context.volatility_phase before declaring control
     → If still volatile, describe tension, not resolution

3. VOLATILITY CONSTRAINTS
   - If context.recent_flip_tie_count >= 3:
     → Describe the SEQUENCE, not each flip as isolated drama
     → Use: "back-and-forth", "trading leads", "another lead change"
     → Do NOT treat each flip as shocking
   
   - If context.volatility_phase = "stable":
     → AVOID: "swing", "surge", "momentum shift", "suddenly"
     → USE: "extends", "maintains", "steady", "in control"

4. CONTROL MEMORY
   - If context.control_duration >= 2:
     → This team has had control for multiple moments
     → Use: "continues to", "extends", "keeps building", "still in command"
     → Do NOT describe as "new control" or "takes over"
   
   - Do NOT describe multiple "comebacks" in succession
   - A comeback must CHANGE narrative state, not just margin

5. LATE-GAME FALSE DRAMA GUARD
   - In closing phase:
     - If margin remains tier >= 2
     - AND context.controlling_team unchanged
     → Language must DOWNSHIFT
     → Use: "cuts into", "trims", "narrows" (not "threatens", "surges back")

---

HARD CONSTRAINTS (VIOLATIONS = GENERATION FAILURE)

You MUST NOT:
- Use "comeback" twice in a row
- Describe urgency in opening phase (game_phase = "opening")
- Describe a "shift" if context.tier_stability = "stable"
- Describe resolution if game_phase != "closing"
- Say who wins, use hindsight, or reveal final outcomes
- Use words: wins, won, decisive, dagger, sealed, clinched, final, victory, defeat

---

TONE:
- Energetic, confident, broadcast-style
- Short, punchy sentences
- Feels like live highlights, not a recap
- CONTEXT-AWARE: knows what already happened

---

FORMAT RULES:
- game_headline: max 80 characters
- game_subhead: max 120 characters
- moment headline: max 60 characters
- moment summary: max 150 characters
- One clear idea per moment
- Interpret the moment — do not restate raw data

---

OUTPUT:
Return VALID JSON ONLY. No markdown, no explanation, just JSON:

{"game_headline": "...", "game_subhead": "...", "moments": [{"id": "...", "headline": "...", "summary": "..."}]}"""


def _derive_narrative_intent(context: dict[str, Any] | None, moment_type: str) -> str:
    """Derive narrative intent hint from context.
    
    PHASE 3: Single-line hint to guide AI narrative framing.
    This is NOT shown to user, only used internally by AI.
    """
    if not context:
        return "Narrative intent: isolated moment (no context)"
    
    # Extract context fields
    is_continuation = context.get("is_continuation", False)
    volatility_phase = context.get("volatility_phase", "stable")
    control_duration = context.get("control_duration", 0)
    game_phase = context.get("game_phase", "middle")
    
    # Derive intent from context signals
    if is_continuation and control_duration >= 2:
        controlling_team = context.get("controlling_team", "team")
        return f"Narrative intent: continuation of {controlling_team} control"
    
    if volatility_phase == "back_and_forth":
        return "Narrative intent: volatile exchange with no sustained control"
    
    if game_phase == "opening":
        return "Narrative intent: early scoring without lasting impact"
    
    if game_phase == "closing" and volatility_phase == "stable":
        return "Narrative intent: closing resolution moment"
    
    if not is_continuation and control_duration <= 1:
        return "Narrative intent: shift in game control"
    
    return "Narrative intent: mid-game development"


def _build_enrichment_prompt(
    game_context: GameContext,
    moments: list[MomentEnrichmentInput],
) -> str:
    """Build the user prompt with game and moment data.
    
    PHASE 3: Now includes narrative context for each moment.
    """
    game_json = {
        "home_team": game_context.home_team,
        "away_team": game_context.away_team,
        "final_score": f"{game_context.final_score_home}-{game_context.final_score_away}",
        "sport": game_context.sport,
    }
    
    moments_json = []
    for m in moments:
        moment_data = {
            "id": m.id,
            "type": m.type,
            "score_swing": f"{m.score_before} → {m.score_after}",
            "time_window": m.time_window,
            "reason": m.reason,
        }
        if m.team_in_control:
            moment_data["team_in_control"] = m.team_in_control
        if m.run_info:
            moment_data["run_context"] = m.run_info
        if m.key_plays:
            moment_data["key_plays"] = m.key_plays[:3]  # Limit
        
        # PHASE 3: Include narrative context
        if m.context:
            moment_data["context"] = m.context
            # Add narrative intent hint (internal guidance for AI)
            moment_data["_narrative_intent"] = _derive_narrative_intent(m.context, m.type)
        
        moments_json.append(moment_data)
    
    return f"""GAME CONTEXT:
{json.dumps(game_json, indent=2)}

MOMENTS (chronological order, {len(moments)} total):
{json.dumps(moments_json, indent=2)}

IMPORTANT: Each moment has a 'context' field with narrative awareness signals.
Use these to write coherent, non-repetitive narration that flows naturally."""


# =============================================================================
# CONTENT LINTING (Post-AI quality checks)
# =============================================================================

# Patterns that indicate low-quality AI output
HALLUCINATION_PATTERNS = [
    re.compile(r'\bwould later\b', re.I),
    re.compile(r'\beventually\b', re.I),
    re.compile(r'\bwould go on\b', re.I),
    re.compile(r'\bturned out\b', re.I),
    re.compile(r'\bproved to be\b', re.I),
    re.compile(r'\bin hindsight\b', re.I),
    re.compile(r'\blooking back\b', re.I),
    re.compile(r'\bas we now know\b', re.I),
]

# Pattern for verbatim score restating (e.g., "107-102", "the score was 56-54")
SCORE_VERBATIM_PATTERN = re.compile(r'\b\d{1,3}[-–]\d{1,3}\b')


def _lint_content(text: str, context: str = "") -> list[str]:
    """
    Lint AI-generated content for quality issues.
    
    Returns list of issues found (empty = passed).
    """
    issues = []
    
    # Check for hallucination patterns (future knowledge)
    for pattern in HALLUCINATION_PATTERNS:
        if pattern.search(text):
            match = pattern.search(text)
            issues.append(f"Hallucination pattern found: '{match.group()}'")
    
    # Check for verbatim score restating
    # Scores in the output are acceptable in context phrases like "tied at 50"
    # but not as raw score pairs like "107-102" which is just restating data
    score_matches = SCORE_VERBATIM_PATTERN.findall(text)
    # Allow single-digit ties like "4-4" but flag score pairs with larger numbers
    for match in score_matches:
        parts = re.split(r'[-–]', match)
        if len(parts) == 2:
            try:
                a, b = int(parts[0]), int(parts[1])
                # Flag if it's a large score pair (not a tie or small number)
                if a > 10 or b > 10:
                    issues.append(f"Verbatim score restating: '{match}' - interpret, don't restate")
            except ValueError:
                pass
    
    return issues


def _lint_moment_content(
    headline: str, 
    summary: str, 
    moment_id: str,
    context: dict[str, Any] | None = None,
) -> list[str]:
    """
    Lint a single moment's content.
    
    PHASE 3: Now includes context-aware constraint validation.
    
    Returns list of issues found (empty = passed).
    """
    issues = []
    
    # Check headline quality
    if len(headline) < 10:
        issues.append(f"Headline too short ({len(headline)} chars)")
    
    # Check summary quality
    if len(summary) < 20:
        issues.append(f"Summary too short ({len(summary)} chars)")
    
    # Check for content issues
    full_text = f"{headline} {summary}"
    content_issues = _lint_content(full_text, moment_id)
    issues.extend(content_issues)
    
    # PHASE 3: Context-aware constraint validation
    if context:
        combined = full_text.lower()
        game_phase = context.get("game_phase", "middle")
        tier_stability = context.get("tier_stability", "stable")
        volatility_phase = context.get("volatility_phase", "stable")
        
        # Check for urgency in opening phase
        if game_phase == "opening":
            urgency_words = ["crucial", "must-have", "desperate", "critical", "vital", "pivotal"]
            for word in urgency_words:
                if word in combined:
                    issues.append(f"urgency_in_opening: '{word}' used in Q1")
        
        # Check for shift language with stable tiers
        if tier_stability == "stable" and volatility_phase == "stable":
            shift_words = ["swing", "surge", "momentum shift", "suddenly"]
            for word in shift_words:
                if word in combined:
                    issues.append(f"shift_language_with_stable_game: '{word}'")
        
        # Check for resolution language outside closing phase
        if game_phase != "closing":
            resolution_words = ["seals", "puts away", "locks up", "secures the"]
            for word in resolution_words:
                if word in combined:
                    issues.append(f"resolution_outside_closing: '{word}'")
    
    return issues


# =============================================================================
# VALIDATION
# =============================================================================


def _validate_enrichment_output(
    raw_output: dict[str, Any],
    expected_moment_ids: list[str],
    moments_input: list[MomentEnrichmentInput] | None = None,
) -> GameEnrichmentOutput:
    """
    Validate and parse AI output. Raises AIValidationError if invalid.
    
    PHASE 3: Now validates context-aware constraints.
    """
    # Check required fields
    if "game_headline" not in raw_output:
        raise AIValidationError("Missing 'game_headline' in AI output")
    if "game_subhead" not in raw_output:
        raise AIValidationError("Missing 'game_subhead' in AI output")
    if "moments" not in raw_output or not isinstance(raw_output["moments"], list):
        raise AIValidationError("Missing or invalid 'moments' array in AI output")
    
    # Validate game headline/subhead
    game_headline = str(raw_output["game_headline"])[:80]
    game_subhead = str(raw_output["game_subhead"])[:120]
    
    # Check for forbidden words in game copy
    forbidden_in_headline = _check_forbidden_words(game_headline)
    if forbidden_in_headline:
        raise AIValidationError(
            f"Forbidden words in game_headline: {forbidden_in_headline}"
        )
    forbidden_in_subhead = _check_forbidden_words(game_subhead)
    if forbidden_in_subhead:
        raise AIValidationError(
            f"Forbidden words in game_subhead: {forbidden_in_subhead}"
        )
    
    # Validate moments
    output_moments: list[MomentEnrichmentOutput] = []
    output_ids = set()
    
    for m in raw_output["moments"]:
        if not isinstance(m, dict):
            continue
        
        moment_id = m.get("id", "")
        if not moment_id:
            raise AIValidationError("Moment missing 'id' field")
        
        output_ids.add(moment_id)
        
        headline = str(m.get("headline", ""))[:60]
        summary = str(m.get("summary", ""))[:150]
        
        # Check for forbidden words (FAIL)
        forbidden = _check_forbidden_words(headline + " " + summary)
        if forbidden:
            raise AIValidationError(
                f"Forbidden words in moment {moment_id}: {forbidden}"
            )
        
        # PHASE 3: Get context for this moment
        moment_context = None
        if moments_input:
            for input_moment in moments_input:
                if input_moment.id == moment_id:
                    moment_context = input_moment.context
                    break
        
        # Content linting (WARN) - now context-aware
        lint_issues = _lint_moment_content(headline, summary, moment_id, moment_context)
        if lint_issues:
            logger.warning(
                "moment_content_lint_issues",
                extra={"moment_id": moment_id, "issues": lint_issues},
            )
        
        output_moments.append(MomentEnrichmentOutput(
            id=moment_id,
            headline=headline,
            summary=summary,
        ))
    
    # Verify all expected moments are present
    missing_ids = set(expected_moment_ids) - output_ids
    if missing_ids:
        raise AIValidationError(
            f"AI output missing moments: {missing_ids}"
        )
    
    return GameEnrichmentOutput(
        game_headline=game_headline,
        game_subhead=game_subhead,
        moments=output_moments,
    )


# =============================================================================
# BATCH ENRICHMENT (The Main Function)
# =============================================================================


async def enrich_game_moments(
    game_id: int,
    timeline_version: str,
    game_context: GameContext,
    moments: list[MomentEnrichmentInput],
    retry_on_validation_error: bool = True,
) -> GameEnrichmentOutput:
    """
    Enrich ALL moments for a game in a single OpenAI call.
    
    This is the ONLY AI entry point for timeline generation.
    
    Args:
        game_id: Game identifier (for caching/logging)
        timeline_version: Version string (for cache invalidation)
        game_context: Game-level context
        moments: All moments to enrich
        retry_on_validation_error: If True, retry once on validation failure
        
    Returns:
        GameEnrichmentOutput with headlines/summaries for game and all moments
        
    Raises:
        AIConfigurationError: If OpenAI is not configured
        AIEnrichmentError: If API call fails
        AIValidationError: If output fails validation (after retry)
    """
    # Check cache first
    cache_key = _cache_key(game_id, timeline_version)
    if cached := _enrichment_cache.get(cache_key):
        logger.debug("enrichment_cache_hit", extra={"game_id": game_id})
        return cached
    
    # Get client (raises if not configured)
    client = _get_client()
    settings = get_settings()
    
    # Build prompts
    user_prompt = _build_enrichment_prompt(game_context, moments)
    expected_ids = [m.id for m in moments]
    
    logger.info(
        "enrichment_api_call_starting",
        extra={
            "game_id": game_id,
            "moment_count": len(moments),
            "model": settings.openai_model_summary,
        },
    )
    
    # Make API call
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model_summary,
            messages=[
                {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,  # Some creativity but consistent
            max_tokens=2000,  # Enough for ~30 moments
            response_format={"type": "json_object"},  # Force JSON
        )
    except Exception as e:
        logger.error(
            "enrichment_api_call_failed",
            extra={"game_id": game_id, "error": str(e)},
        )
        raise AIEnrichmentError(f"OpenAI API call failed: {e}") from e
    
    # Parse response
    content = response.choices[0].message.content
    if not content:
        raise AIEnrichmentError("OpenAI returned empty response")
    
    try:
        raw_output = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(
            "enrichment_json_parse_failed",
            extra={"game_id": game_id, "content": content[:500]},
        )
        raise AIEnrichmentError(f"Failed to parse AI JSON: {e}") from e
    
    # Validate output
    try:
        result = _validate_enrichment_output(raw_output, expected_ids, moments)  # PHASE 3: Pass moments for context
    except AIValidationError as e:
        if retry_on_validation_error:
            logger.warning(
                "enrichment_validation_failed_retrying",
                extra={"game_id": game_id, "error": str(e)},
            )
            # Retry once with stricter temperature
            try:
                response = await client.chat.completions.create(
                    model=settings.openai_model_summary,
                    messages=[
                        {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,  # More deterministic
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if content:
                    raw_output = json.loads(content)
                    result = _validate_enrichment_output(raw_output, expected_ids, moments)  # PHASE 3: Pass moments
                else:
                    raise AIEnrichmentError("Retry returned empty response")
            except (AIValidationError, json.JSONDecodeError, Exception) as retry_e:
                logger.error(
                    "enrichment_retry_failed",
                    extra={"game_id": game_id, "error": str(retry_e)},
                )
                raise AIEnrichmentError(
                    f"AI enrichment failed after retry: {retry_e}"
                ) from retry_e
        else:
            raise
    
    # Cache result
    _enrichment_cache[cache_key] = result
    
    logger.info(
        "enrichment_complete",
        extra={
            "game_id": game_id,
            "moments_enriched": len(result.moments),
            "headline": result.game_headline[:50],
        },
    )
    
    return result


# =============================================================================
# SOCIAL ROLE CLASSIFICATION (Unchanged - still uses heuristics + AI)
# =============================================================================

SOCIAL_ROLE_PROMPT = """Classify this sports social media post into exactly one role:
- hype (pregame excitement)
- context (pregame info, lineup, injury)
- reaction (in-game response)
- momentum (run commentary)
- notable (notable play)
- result (score update)
- reflection (postgame)
- ambient (atmosphere, general)

Sport: {sport}
Phase: {phase}
Post: "{text}"

Reply with ONLY the role name."""


async def classify_social_role(
    text: str,
    phase: str,
    sport: str = "NBA",
    heuristic_role: str | None = None,
    heuristic_confidence: float = 0.0,
) -> str:
    """
    Classify social post role. Uses heuristic if confidence >= 0.8.
    
    This is NOT part of the main enrichment pipeline.
    Failures here fall back to heuristic (social classification is not critical).
    """
    # High-confidence heuristic bypasses AI
    if heuristic_confidence >= 0.8 and heuristic_role:
        return heuristic_role
    
    settings = get_settings()
    if not settings.enable_ai_social_roles:
        return heuristic_role or "ambient"
    
    try:
        client = _get_client()
    except AIConfigurationError:
        return heuristic_role or "ambient"
    
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model_classification,
            messages=[{
                "role": "user",
                "content": SOCIAL_ROLE_PROMPT.format(
                    sport=sport,
                    phase=phase,
                    text=text[:500],
                ),
            }],
            temperature=0,
            max_tokens=5,
        )
        
        role = response.choices[0].message.content.strip().lower()
        valid_roles = {"hype", "context", "reaction", "momentum", "notable", "result", "reflection", "ambient"}
        
        if role in valid_roles:
            return role
        return heuristic_role or "ambient"
        
    except Exception as e:
        logger.warning("social_role_classification_failed", extra={"error": str(e)})
        return heuristic_role or "ambient"
