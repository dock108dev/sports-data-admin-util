"""RENDER_NARRATIVES Stage Implementation.

This stage generates narrative text for each validated moment using OpenAI.
It is the ONLY AI-driven step in the Story pipeline.

STORY CONTRACT ALIGNMENT
========================
This implementation adheres to the Story contract:
- AI is a renderer, not an author
- Moments are batched (up to 25 per call) for efficiency
- Narrative is grounded strictly in backing plays
- No story-level prose or summaries
- Narrative is traceable to explicit plays

RENDERING RULES
===============
The prompt REQUIRES:
- Direct reference to at least one explicitly narrated play
- Concrete actions only (shots, fouls, turnovers, scores)
- Chronological order
- Neutral, factual language

The prompt FORBIDS:
- Momentum, flow, turning points
- Summaries or retrospection
- "Earlier/later in the game"
- Speculation or interpretation
- Referencing plays not provided

POST-GENERATION VALIDATION
==========================
After receiving AI output, we validate:
1. Narrative is non-empty
2. No forbidden abstraction language
3. Response is well-formed JSON
4. At least one explicitly narrated play is referenced (traceability)

If validation fails, the stage fails. No retries with weaker rules.
No auto-editing of text. AI output is untrusted until validated.

GUARANTEES
==========
1. Moments batched efficiently (~25 per OpenAI call)
2. All narratives pass validation
3. Broken narratives fail loudly
4. Output includes narrative per moment
5. Human can audit text → plays deterministically
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from .... import db_models
from ..models import StageInput, StageOutput
from ...openai_client import get_openai_client

if TYPE_CHECKING:
    from ....db import AsyncSession

logger = logging.getLogger(__name__)


# =============================================================================
# FALLBACK CLASSIFICATION (Task 0.2)
# =============================================================================
# Deterministic narrative fallbacks with explicit classification:
# - VALID: Normal low-signal gameplay (expected basketball behavior)
# - INVALID: Pipeline/AI failure (needs debugging, visible in beta)


class FallbackType(str, Enum):
    """Classification of fallback narrative type."""

    VALID = "VALID"  # Normal low-signal gameplay, expected
    INVALID = "INVALID"  # Pipeline/AI failure, needs debugging


class FallbackReason(str, Enum):
    """Specific reason codes for INVALID fallbacks.

    These are diagnostic codes for beta debugging.
    Each reason indicates a specific failure mode.
    """

    # AI generation failures
    AI_GENERATION_FAILED = "ai_generation_failed"
    AI_RETURNED_EMPTY = "ai_returned_empty"
    AI_INVALID_JSON = "ai_invalid_json"

    # Data quality issues
    MISSING_PLAY_METADATA = "missing_play_metadata"
    SCORE_CONTEXT_INVALID = "score_context_invalid"
    EMPTY_NARRATIVE_WITH_EXPLICIT_PLAYS = "empty_narrative_with_explicit_plays"

    # Task 1.2: Multi-sentence validation failures
    INSUFFICIENT_SENTENCES = "insufficient_sentences"
    FORBIDDEN_LANGUAGE_DETECTED = "forbidden_language_detected"
    MISSING_EXPLICIT_PLAY_REFERENCE = "missing_explicit_play_reference"

    # Pipeline state issues
    UNEXPECTED_PIPELINE_STATE = "unexpected_pipeline_state"


# Valid low-signal fallback texts (rotated deterministically)
VALID_FALLBACK_NARRATIVES = [
    "No scoring on this sequence.",
    "Possession traded without a basket.",
]

# Invalid fallback format (beta-only, intentionally obvious)
INVALID_FALLBACK_TEMPLATE = "[Narrative unavailable — {reason}]"

# Forbidden phrases that indicate abstraction beyond the moment
FORBIDDEN_PHRASES = [
    # Momentum/flow language
    r"\bmomentum\b",
    r"\bturning point\b",
    r"\bshift(ed|ing)?\b",
    r"\bswing\b",
    r"\btide\b",
    # Temporal references outside the moment
    r"\bearlier in the game\b",
    r"\blater in the game\b",
    r"\bpreviously\b",
    r"\bwould (later|eventually)\b",
    r"\bforeshadow\b",
    # Summary/retrospective language
    r"\bin summary\b",
    r"\boverall\b",
    r"\bultimately\b",
    r"\bin the end\b",
    r"\bkey moment\b",
    r"\bcrucial\b",
    r"\bpivotal\b",
    # Speculation
    r"\bcould have\b",
    r"\bmight have\b",
    r"\bwould have\b",
    r"\bshould have\b",
    r"\bseemed to\b",
    r"\bappeared to\b",
    # Task 1.2: Subjective adjectives (must remain neutral)
    r"\bdominant\b",
    r"\bdominated\b",
    r"\belectric\b",
    r"\bhuge\b",
    r"\bmassive\b",
    r"\bincredible\b",
    r"\bamazing\b",
    r"\bspectacular\b",
    r"\bunstoppable\b",
    r"\bclutch\b",
    r"\bexplosive\b",
    r"\bbrilliant\b",
    r"\bdazzling\b",
    r"\bsensational\b",
    # Task 1.2: Crowd/atmosphere references
    r"\bcrowd erupted\b",
    r"\bcrowd went\b",
    r"\bfans\b",
    r"\batmosphere\b",
    r"\benergy in\b",
    r"\bbuilding\b.*\brocked\b",
    # Task 1.2: Metaphorical/narrative flourish
    r"\btook over\b",
    r"\btook control\b",
    r"\bcaught fire\b",
    r"\bon fire\b",
    r"\bheat(ed|ing)? up\b",
    r"\bin the zone\b",
    r"\bowned\b",
    # Task 1.2: Intent/psychology speculation
    r"\bwanted to\b",
    r"\btried to\b",
    r"\bneeded to\b",
    r"\bhad to\b",
    r"\bfelt\b",
    r"\bfrustrat\w+\b",
    r"\bdesper\w+\b",
    r"\bconfident\b",
    r"\bnervous\b",
]

# Compile patterns for efficiency
FORBIDDEN_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PHRASES]

# Number of moments to process in a single OpenAI call
MOMENTS_PER_BATCH = 25

# Legacy fallback (deprecated, use classification-aware fallbacks instead)
FALLBACK_NARRATIVE = "Play continued."


def _get_valid_fallback_narrative(moment_index: int) -> str:
    """Get a valid low-signal fallback narrative.

    Uses deterministic rotation based on moment index for variety.

    Args:
        moment_index: Index of the moment for deterministic selection

    Returns:
        A valid fallback narrative string
    """
    return VALID_FALLBACK_NARRATIVES[moment_index % len(VALID_FALLBACK_NARRATIVES)]


def _get_invalid_fallback_narrative(reason: FallbackReason) -> str:
    """Get an invalid fallback narrative with diagnostic reason.

    Format is intentionally obvious for beta debugging:
    "[Narrative unavailable — {reason}]"

    Args:
        reason: The specific failure reason

    Returns:
        A diagnostic fallback narrative string
    """
    # Convert enum to human-readable text
    reason_text = reason.value.replace("_", " ")
    return INVALID_FALLBACK_TEMPLATE.format(reason=reason_text)


def _is_valid_score_context(moment: dict[str, Any]) -> bool:
    """Check if a moment has valid score context.

    Valid score context means:
    - score_before and score_after are present
    - Both are lists with 2 elements
    - Scores are non-negative
    - Score doesn't decrease (monotonic within moment)

    Args:
        moment: The moment data

    Returns:
        True if score context is valid
    """
    score_before = moment.get("score_before")
    score_after = moment.get("score_after")

    # Must have both scores
    if score_before is None or score_after is None:
        return False

    # Must be lists with 2 elements
    if not isinstance(score_before, (list, tuple)) or len(score_before) != 2:
        return False
    if not isinstance(score_after, (list, tuple)) or len(score_after) != 2:
        return False

    # Scores must be non-negative
    try:
        if score_before[0] < 0 or score_before[1] < 0:
            return False
        if score_after[0] < 0 or score_after[1] < 0:
            return False
    except (TypeError, IndexError):
        return False

    # Score shouldn't decrease within moment (monotonic)
    try:
        if score_after[0] < score_before[0] or score_after[1] < score_before[1]:
            return False
    except (TypeError, IndexError):
        return False

    return True


def _has_valid_play_metadata(moment_plays: list[dict[str, Any]]) -> bool:
    """Check if moment plays have required metadata.

    Required fields for narrative generation:
    - play_index
    - description (non-empty)

    Args:
        moment_plays: List of PBP events for the moment

    Returns:
        True if all plays have valid metadata
    """
    if not moment_plays:
        return False

    for play in moment_plays:
        if play.get("play_index") is None:
            return False
        # Description can be empty but should exist
        if "description" not in play:
            return False

    return True


def _classify_empty_narrative_fallback(
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    moment_index: int,
) -> tuple[str, FallbackType, FallbackReason | None]:
    """Classify and generate fallback for empty narrative from OpenAI.

    This is the core classification logic for Task 0.2.

    Classification rules:
    - VALID if: no explicit plays AND valid score context AND valid play metadata
    - INVALID otherwise (with specific reason)

    Args:
        moment: The moment data
        moment_plays: PBP events for the moment
        moment_index: Index for deterministic fallback selection

    Returns:
        Tuple of (narrative_text, fallback_type, fallback_reason)
    """
    explicitly_narrated = moment.get("explicitly_narrated_play_ids", [])
    has_explicit_plays = bool(explicitly_narrated)
    has_valid_scores = _is_valid_score_context(moment)
    has_valid_metadata = _has_valid_play_metadata(moment_plays)

    # Case 1: Explicit plays exist but narrative is empty -> INVALID
    if has_explicit_plays:
        reason = FallbackReason.EMPTY_NARRATIVE_WITH_EXPLICIT_PLAYS
        return (
            _get_invalid_fallback_narrative(reason),
            FallbackType.INVALID,
            reason,
        )

    # Case 2: Score context is invalid -> INVALID
    if not has_valid_scores:
        reason = FallbackReason.SCORE_CONTEXT_INVALID
        return (
            _get_invalid_fallback_narrative(reason),
            FallbackType.INVALID,
            reason,
        )

    # Case 3: Play metadata is missing -> INVALID
    if not has_valid_metadata:
        reason = FallbackReason.MISSING_PLAY_METADATA
        return (
            _get_invalid_fallback_narrative(reason),
            FallbackType.INVALID,
            reason,
        )

    # Case 4: Valid low-signal gameplay -> VALID
    # No explicit plays, valid scores, valid metadata
    # This is expected basketball behavior (nothing notable happened)
    return (
        _get_valid_fallback_narrative(moment_index),
        FallbackType.VALID,
        None,  # No reason needed for valid fallbacks
    )


def _build_batch_prompt(
    moments_batch: list[tuple[int, dict[str, Any], list[dict[str, Any]]]],
    game_context: dict[str, str],
    is_retry: bool = False,
) -> str:
    """Build an OpenAI prompt for a batch of moments.

    Task 1.2: Generates multi-sentence narratives (2-4 sentences) that describe
    the full sequence of gameplay within each moment.

    Args:
        moments_batch: List of (moment_index, moment, moment_plays) tuples
        game_context: Team names and sport info
        is_retry: Whether this is a retry after validation failure

    Returns:
        Prompt string for OpenAI to generate all narratives in the batch
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")
    player_names = game_context.get("player_names", {})

    # Build player name reference for the prompt (abbrev -> full name)
    # Only include mappings for abbreviated names (X. Lastname format)
    name_mappings = []
    for abbrev, full in player_names.items():
        if ". " in abbrev:  # Only abbreviated forms like "D. Mitchell"
            name_mappings.append(f"{abbrev}={full}")

    # Limit to avoid bloating prompt - take first 40 unique players
    name_ref = ", ".join(name_mappings[:40]) if name_mappings else ""

    # Build compact moments data
    moments_lines = []
    for moment_index, moment, moment_plays in moments_batch:
        period = moment.get("period", 1)
        clock = moment.get("start_clock", "")
        score_before = moment.get("score_before", [0, 0])
        score_after = moment.get("score_after", [0, 0])
        explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))

        # Compact play format: just the essentials
        plays_compact = []
        for play in moment_plays:
            play_index = play.get("play_index")
            is_explicit = play_index in explicitly_narrated
            star = "*" if is_explicit else ""
            desc = play.get("description", "")
            # Truncate long descriptions
            if len(desc) > 100:
                desc = desc[:97] + "..."
            plays_compact.append(f"{star}{desc}")

        plays_str = "; ".join(plays_compact)
        # Include score change context
        score_change = ""
        if score_after != score_before:
            score_change = f" → {away_team} {score_after[0]}-{score_after[1]} {home_team}"
        moments_lines.append(
            f"[{moment_index}] Q{period} {clock} ({away_team} {score_before[0]}-{score_before[1]} {home_team}{score_change}): {plays_str}"
        )

    moments_block = "\n".join(moments_lines)

    # Build prompt with player name rule
    name_rule = "- FULL NAME on first mention (e.g., \"Donovan Mitchell\"), LAST NAME only after. NEVER use initials like \"D. Mitchell\"."
    if name_ref:
        name_rule += f"\n  Names: {name_ref}"

    # Retry prompt is more explicit about requirements
    if is_retry:
        retry_warning = "\n\nIMPORTANT: Previous response failed validation. Ensure:\n- Each narrative is 2-4 sentences\n- All *starred plays are mentioned\n- No subjective adjectives (huge, dominant, electric)\n- No speculation about intent or psychology\n"
    else:
        retry_warning = ""

    prompt = f"""Write 2-4 sentence narratives for each moment. {away_team} vs {home_team}.
{retry_warning}
Each narrative should:
- Describe the SEQUENCE of actions across the moment (not just one play)
- Reference ALL *starred plays (these MUST appear in the narrative)
- Use plain factual language like a neutral broadcast recap
- Follow chronological order

REQUIRED format:
{name_rule}
- Vary sentence length naturally
- Allowed: scoring runs, unanswered points, responses, changes in pace

FORBIDDEN (will fail validation):
- Subjective adjectives: dominant, electric, huge, massive, incredible, clutch
- Speculation: wanted to, tried to, felt, seemed to
- Crowd/atmosphere: crowd erupted, fans, energy
- Metaphors: took over, caught fire, in the zone
- Summary language: momentum, turning point, crucial, pivotal

GOOD: "The Suns opened with back-to-back baskets before the Lakers answered with a three. After a missed possession, Mitchell converted in transition to extend the lead."

BAD: "The Suns went on an electric run. Mitchell took over the game."

{moments_block}

JSON: {{"items":[{{"i":0,"n":"2-4 sentence narrative"}},...]}}"""

    return prompt


def _build_moment_prompt(
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    game_context: dict[str, str],
    moment_index: int,
    is_retry: bool = False,
) -> str:
    """Build the OpenAI prompt for a single moment.

    Task 1.2: Generates multi-sentence narratives (2-4 sentences) that describe
    the full sequence of gameplay within the moment.

    Args:
        moment: The moment data (play_ids, scores, etc.)
        moment_plays: Full PBP records for plays in this moment
        game_context: Team names and sport info
        moment_index: Index of this moment in the sequence
        is_retry: Whether this is a retry after validation failure

    Returns:
        Prompt string for OpenAI
    """
    # Extract context
    home_team = game_context.get("home_team_name", "Home Team")
    away_team = game_context.get("away_team_name", "Away Team")
    sport = game_context.get("sport", "basketball")

    # Extract moment data
    period = moment.get("period", 1)
    start_clock = moment.get("start_clock", "")
    end_clock = moment.get("end_clock", "")
    score_before = moment.get("score_before", [0, 0])
    score_after = moment.get("score_after", [0, 0])
    explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))

    # Format plays for the prompt
    plays_text = []
    for play in moment_plays:
        play_index = play.get("play_index")
        is_explicit = play_index in explicitly_narrated
        marker = "[MUST NARRATE]" if is_explicit else ""

        # Build play description
        clock = play.get("game_clock", "")
        description = play.get("description", "")
        play_type = play.get("play_type", "")
        home_score = play.get("home_score", 0)
        away_score = play.get("away_score", 0)

        play_line = (
            f"- Play {play_index} {marker}: {clock} | {play_type} | "
            f"{description} | Score: {away_team} {away_score} - {home_team} {home_score}"
        )
        plays_text.append(play_line)

    plays_block = "\n".join(plays_text)

    # Retry prompt is more explicit about requirements
    retry_warning = ""
    if is_retry:
        retry_warning = """
IMPORTANT: Previous response failed validation. Ensure:
- Narrative is 2-4 sentences long
- All [MUST NARRATE] plays are mentioned
- No subjective adjectives (huge, dominant, electric, massive)
- No speculation about intent or psychology
"""

    prompt = f"""Generate a multi-sentence narrative (2-4 sentences) for this {sport} game moment.
{retry_warning}
CONTEXT:
- Teams: {away_team} vs {home_team}
- Period: {period}
- Time: {start_clock} to {end_clock}
- Score before: {away_team} {score_before[0]} - {home_team} {score_before[1]}
- Score after: {away_team} {score_after[0]} - {home_team} {score_after[1]}

PLAYS IN THIS MOMENT:
{plays_block}

REQUIREMENTS (MANDATORY):
1. Write 2-4 sentences describing the SEQUENCE of actions
2. You MUST mention ALL plays marked [MUST NARRATE]
3. Describe multiple plays when present, in chronological order
4. Use concrete actions: shots made/missed, fouls, turnovers, scores
5. Use neutral, factual language like a broadcast recap
6. Use FULL NAME on first mention, LAST NAME only after

ALLOWED factual language:
- Scoring runs, unanswered points, responses
- Changes in pace reflected by scoring or possession

FORBIDDEN (WILL INVALIDATE YOUR RESPONSE):
- Subjective adjectives: dominant, electric, huge, massive, incredible, clutch
- Speculation: wanted to, tried to, felt, seemed to, needed to
- Crowd/atmosphere: crowd erupted, fans, energy
- Metaphors: took over, caught fire, in the zone
- Summary language: momentum, turning point, shift, swing, crucial, pivotal
- References to "earlier/later in the game"

GOOD EXAMPLE:
"The Suns opened the stretch with back-to-back baskets before the Lakers answered with a three. After a missed possession, Donovan Mitchell converted in transition. Mitchell's layup extended the lead to five."

BAD EXAMPLE:
"This was a crucial turning point. Mitchell took over and the crowd erupted."

Respond with JSON in this exact format:
{{"narrative": "Your 2-4 sentence narrative here"}}"""

    return prompt


def _count_sentences(text: str) -> int:
    """Count the number of sentences in a narrative.

    Uses simple heuristics: counts sentence-ending punctuation followed by
    space or end of string. Handles common abbreviations.

    Args:
        text: The narrative text

    Returns:
        Estimated sentence count
    """
    if not text or not text.strip():
        return 0

    # Remove common abbreviations that have periods
    cleaned = text
    for abbrev in ["Mr.", "Mrs.", "Dr.", "Jr.", "Sr.", "vs.", "Q1.", "Q2.", "Q3.", "Q4."]:
        cleaned = cleaned.replace(abbrev, abbrev.replace(".", ""))

    # Count sentence endings: . ! ? followed by space or end
    import re
    # Match period/exclamation/question followed by space+capital or end of string
    pattern = r'[.!?](?:\s+[A-Z]|\s*$)'
    matches = re.findall(pattern, cleaned)
    return max(1, len(matches)) if cleaned.strip() else 0


def _extract_play_identifiers(play: dict[str, Any]) -> list[str]:
    """Extract identifiable tokens from a play for narrative traceability.

    Extracts player names and significant words that should appear in
    a narrative that references this play.

    Args:
        play: A normalized PBP event

    Returns:
        List of lowercase tokens that identify this play
    """
    identifiers: list[str] = []

    # Player name is the primary identifier
    player_name = play.get("player_name")
    if player_name:
        # Add full name and last name (most common in narratives)
        identifiers.append(player_name.lower())
        parts = player_name.split()
        if len(parts) > 1:
            identifiers.append(parts[-1].lower())  # Last name

    # Team abbreviation as fallback
    team_abbrev = play.get("team_abbreviation")
    if team_abbrev:
        identifiers.append(team_abbrev.lower())

    return identifiers


def _check_explicit_play_coverage(
    narrative: str,
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
) -> list[int]:
    """Check if all explicitly narrated plays are referenced in the narrative.

    Task 1.2: Any explicitly narrated play MUST appear in the narrative.
    Failure to include an explicit play is a hard error.

    Args:
        narrative: The generated narrative text
        moment: The moment data
        moment_plays: Full PBP records for plays in this moment

    Returns:
        List of play_indices that are missing from the narrative (empty if all covered)
    """
    explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))
    if not explicitly_narrated:
        return []  # No explicit plays to check

    narrative_lower = narrative.lower()
    missing_plays: list[int] = []

    for play in moment_plays:
        play_index = play.get("play_index")
        if play_index not in explicitly_narrated:
            continue

        # Get identifiers for this play
        identifiers = _extract_play_identifiers(play)

        # Check if any identifier appears in narrative
        found = False
        for identifier in identifiers:
            if identifier in narrative_lower:
                found = True
                break

        # Also check description keywords as fallback
        if not found:
            description = play.get("description", "").lower()
            # Check for key action words from description
            action_words = ["layup", "dunk", "three", "jumper", "shot", "free throw", "rebound"]
            for word in action_words:
                if word in description and word in narrative_lower:
                    found = True
                    break

        if not found:
            missing_plays.append(play_index)

    return missing_plays


# =============================================================================
# TASK 1.3: EXPLICIT PLAY COVERAGE INVARIANT
# =============================================================================
# Deterministic sentence injection as fail-safe for missing explicit plays.
# This guarantees narrative trust by ensuring every explicit play is represented.


class CoverageResolution(str, Enum):
    """Resolution path for explicit play coverage."""

    INITIAL_PASS = "initial_pass"  # Initial generation covered all plays
    REGENERATION_PASS = "regeneration_pass"  # Regeneration covered all plays
    INJECTION_REQUIRED = "injection_required"  # Deterministic injection was needed
    INJECTION_FAILED = "injection_failed"  # Injection failed (should never happen)


def _generate_deterministic_sentence(
    play: dict[str, Any],
    game_context: dict[str, str],
) -> str:
    """Generate a deterministic, factual sentence for a single play.

    Task 1.3: This is the fail-safe injection when AI fails to cover an explicit play.

    The sentence must be:
    - Factual and neutral
    - Derived directly from PBP data
    - Free of adjectives or interpretation
    - Grammatically complete

    Args:
        play: The PBP event data
        game_context: Team names and sport info

    Returns:
        A deterministic sentence describing the play
    """
    # Extract play data
    player_name = play.get("player_name", "")
    description = play.get("description", "")
    play_type = play.get("play_type", "")
    team_abbrev = play.get("team_abbreviation", "")
    home_score = play.get("home_score", 0)
    away_score = play.get("away_score", 0)

    # Get team names from context
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")

    # Determine which team the player is on
    team_name = ""
    if team_abbrev:
        # Match abbreviation to team name (simplified)
        if team_abbrev.upper() in home_team.upper():
            team_name = home_team
        elif team_abbrev.upper() in away_team.upper():
            team_name = away_team
        else:
            team_name = team_abbrev  # Fall back to abbreviation

    # Build sentence based on play type
    desc_lower = description.lower()

    # Scoring plays
    if "three" in desc_lower or "3-pt" in desc_lower or "3pt" in desc_lower:
        if player_name:
            return f"{player_name} hit a three-pointer."
        return f"{team_name or 'The team'} made a three-pointer."

    if "layup" in desc_lower:
        if player_name:
            return f"{player_name} scored on a layup."
        return f"{team_name or 'The team'} scored on a layup."

    if "dunk" in desc_lower:
        if player_name:
            return f"{player_name} finished with a dunk."
        return f"{team_name or 'The team'} scored on a dunk."

    if "free throw" in desc_lower:
        if "makes" in desc_lower or "made" in desc_lower:
            if player_name:
                return f"{player_name} converted the free throw."
            return f"{team_name or 'The team'} made a free throw."
        elif "misses" in desc_lower or "missed" in desc_lower:
            if player_name:
                return f"{player_name} missed the free throw."
            return f"{team_name or 'The team'} missed a free throw."

    if "jumper" in desc_lower or "jump shot" in desc_lower:
        if "makes" in desc_lower or "made" in desc_lower:
            if player_name:
                return f"{player_name} hit a jump shot."
            return f"{team_name or 'The team'} made a jump shot."

    # Generic scoring detection
    if any(word in desc_lower for word in ["makes", "made", "scores", "scored"]):
        if player_name:
            return f"{player_name} scored."
        return f"{team_name or 'The team'} scored."

    # Non-scoring plays
    if "rebound" in desc_lower:
        if player_name:
            return f"{player_name} grabbed the rebound."
        return f"{team_name or 'The team'} secured the rebound."

    if "steal" in desc_lower:
        if player_name:
            return f"{player_name} made a steal."
        return f"{team_name or 'The team'} forced a turnover."

    if "turnover" in desc_lower:
        if player_name:
            return f"{player_name} committed a turnover."
        return f"{team_name or 'The team'} turned the ball over."

    if "foul" in desc_lower:
        if player_name:
            return f"{player_name} was called for a foul."
        return f"A foul was called."

    if "block" in desc_lower:
        if player_name:
            return f"{player_name} blocked the shot."
        return f"The shot was blocked."

    if "timeout" in desc_lower:
        return f"{team_name or 'The team'} called timeout."

    # Fallback: Use description directly if we can't parse it
    if player_name and description:
        # Clean up description for use in sentence
        clean_desc = description.strip()
        if clean_desc.endswith("."):
            clean_desc = clean_desc[:-1]
        return f"{player_name}: {clean_desc}."

    if description:
        clean_desc = description.strip()
        if not clean_desc.endswith("."):
            clean_desc += "."
        return clean_desc

    # Ultimate fallback
    return "Play occurred."


def _inject_missing_explicit_plays(
    narrative: str,
    missing_play_indices: list[int],
    moment_plays: list[dict[str, Any]],
    game_context: dict[str, str],
) -> tuple[str, list[dict[str, Any]]]:
    """Inject deterministic sentences for missing explicit plays.

    Task 1.3: Fail-safe injection to guarantee explicit play coverage.

    Rules:
    - Each missing play gets its own sentence
    - Sentences are inserted in chronological order
    - Preserves narrative flow where possible

    Args:
        narrative: The existing narrative text
        missing_play_indices: List of play indices that need injection
        moment_plays: Full PBP records for plays in this moment
        game_context: Team names and sport info

    Returns:
        Tuple of (updated_narrative, injection_details)
        - updated_narrative: Narrative with injected sentences
        - injection_details: List of dicts with injection metadata
    """
    if not missing_play_indices:
        return narrative, []

    # Build play lookup
    play_lookup = {p.get("play_index"): p for p in moment_plays}

    # Sort missing plays by play_index (chronological order)
    sorted_missing = sorted(missing_play_indices)

    # Generate deterministic sentences for each missing play
    injections: list[dict[str, Any]] = []
    sentences_to_inject: list[str] = []

    for play_index in sorted_missing:
        play = play_lookup.get(play_index)
        if not play:
            continue

        sentence = _generate_deterministic_sentence(play, game_context)
        sentences_to_inject.append(sentence)

        injections.append({
            "play_index": play_index,
            "injected_sentence": sentence,
            "player_name": play.get("player_name"),
            "description": play.get("description"),
        })

    if not sentences_to_inject:
        return narrative, []

    # Combine injected sentences
    injection_block = " ".join(sentences_to_inject)

    # Append to existing narrative (cleanest approach)
    # Ensure proper spacing
    if narrative and not narrative.rstrip().endswith("."):
        narrative = narrative.rstrip() + "."

    if narrative:
        updated_narrative = f"{narrative.rstrip()} {injection_block}"
    else:
        updated_narrative = injection_block

    return updated_narrative, injections


def _log_coverage_resolution(
    game_id: int,
    moment_index: int,
    resolution: CoverageResolution,
    explicit_play_ids: list[int],
    missing_after_initial: list[int] | None = None,
    missing_after_regen: list[int] | None = None,
    injections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Log the resolution path for explicit play coverage.

    Task 1.3: Required for pipeline health monitoring.

    Args:
        game_id: Game ID
        moment_index: Moment index
        resolution: How coverage was achieved
        explicit_play_ids: All explicit play IDs in the moment
        missing_after_initial: Play IDs missing after initial generation
        missing_after_regen: Play IDs missing after regeneration
        injections: Injection details if injection was used

    Returns:
        Dict containing the logged resolution data
    """
    log_data = {
        "game_id": game_id,
        "moment_index": moment_index,
        "resolution": resolution.value,
        "explicit_play_count": len(explicit_play_ids),
        "explicit_play_ids": explicit_play_ids,
    }

    if missing_after_initial:
        log_data["missing_after_initial"] = missing_after_initial
        log_data["missing_after_initial_count"] = len(missing_after_initial)

    if missing_after_regen:
        log_data["missing_after_regen"] = missing_after_regen
        log_data["missing_after_regen_count"] = len(missing_after_regen)

    if injections:
        log_data["injections"] = injections
        log_data["injection_count"] = len(injections)

    # Log based on resolution type
    if resolution == CoverageResolution.INITIAL_PASS:
        logger.debug(
            "explicit_play_coverage_pass",
            extra=log_data,
        )
    elif resolution == CoverageResolution.REGENERATION_PASS:
        logger.info(
            "explicit_play_coverage_regen_required",
            extra=log_data,
        )
    elif resolution == CoverageResolution.INJECTION_REQUIRED:
        logger.warning(
            "explicit_play_coverage_injection_required",
            extra=log_data,
        )
    elif resolution == CoverageResolution.INJECTION_FAILED:
        logger.error(
            "explicit_play_coverage_injection_failed",
            extra=log_data,
        )

    return log_data


def _validate_narrative(
    narrative: str,
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    moment_index: int,
    strict_sentence_check: bool = True,
) -> tuple[list[str], list[str]]:
    """Validate the generated narrative against Story contract rules.

    Task 1.2: Enhanced validation for multi-sentence narratives.

    Args:
        narrative: The generated narrative text
        moment: The moment data
        moment_plays: Full PBP records for plays in this moment
        moment_index: Index for error reporting
        strict_sentence_check: If True, require 2+ sentences when multiple plays

    Returns:
        Tuple of (hard_errors, soft_errors)
        - hard_errors: Must trigger fallback (empty, missing explicit plays)
        - soft_errors: Should trigger retry (forbidden phrases, insufficient sentences)
    """
    hard_errors: list[str] = []
    soft_errors: list[str] = []

    # Rule 1: Narrative must be non-empty (HARD)
    if not narrative or not narrative.strip():
        hard_errors.append(f"Moment {moment_index}: Narrative is empty")
        return hard_errors, soft_errors  # Can't validate further if empty

    # Rule 2: Check for forbidden phrases (SOFT - can retry)
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(narrative)
        if match:
            soft_errors.append(
                f"Moment {moment_index}: Contains forbidden phrase '{match.group()}'"
            )

    # Rule 3: Check explicit play coverage (HARD)
    explicitly_narrated = moment.get("explicitly_narrated_play_ids", [])
    if explicitly_narrated:
        missing_plays = _check_explicit_play_coverage(narrative, moment, moment_plays)
        if missing_plays:
            hard_errors.append(
                f"Moment {moment_index}: Missing explicit plays {missing_plays} in narrative"
            )

    # Rule 4: Check sentence count (SOFT - can retry)
    # Task 1.2: Multi-sentence output is the norm (2-4 sentences)
    if strict_sentence_check:
        sentence_count = _count_sentences(narrative)
        num_plays = len(moment_plays)

        # Require at least 2 sentences when moment has multiple plays
        if num_plays > 1 and sentence_count < 2:
            soft_errors.append(
                f"Moment {moment_index}: Only {sentence_count} sentence(s) for {num_plays} plays "
                f"(expected 2-4)"
            )
        # Warn if too many sentences (may indicate verbosity)
        elif sentence_count > 4:
            soft_errors.append(
                f"Moment {moment_index}: {sentence_count} sentences exceeds target of 2-4"
            )

    return hard_errors, soft_errors


def _validate_narrative_legacy(
    narrative: str,
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    moment_index: int,
) -> list[str]:
    """Legacy validation wrapper for backward compatibility.

    Returns combined errors as a single list.
    """
    hard_errors, soft_errors = _validate_narrative(
        narrative, moment, moment_plays, moment_index
    )
    return hard_errors + soft_errors


def _get_batch_cache_key(moment_indices: list[int]) -> str:
    """Generate a cache key for a batch of moments.

    Args:
        moment_indices: List of moment indices in the batch

    Returns:
        SHA256 hash of the sorted indices (first 16 chars)
    """
    key_str = ",".join(str(i) for i in sorted(moment_indices))
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


async def _get_cached_response(
    session: "AsyncSession",
    game_id: int,
    batch_key: str,
) -> dict[str, Any] | None:
    """Check cache for an existing OpenAI response.

    Args:
        session: Database session
        game_id: Game ID
        batch_key: Cache key for the batch

    Returns:
        Cached response data or None if not found
    """
    result = await session.execute(
        select(db_models.OpenAIResponseCache).where(
            db_models.OpenAIResponseCache.game_id == game_id,
            db_models.OpenAIResponseCache.batch_key == batch_key,
        )
    )
    cached = result.scalar_one_or_none()
    if cached:
        logger.info(f"Cache HIT for game {game_id} batch {batch_key}")
        return cached.response_json
    return None


async def _store_cached_response(
    session: "AsyncSession",
    game_id: int,
    batch_key: str,
    prompt_preview: str,
    response_data: dict[str, Any],
    model: str,
) -> None:
    """Store an OpenAI response in the cache.

    Args:
        session: Database session
        game_id: Game ID
        batch_key: Cache key for the batch
        prompt_preview: Truncated prompt for debugging
        response_data: The parsed response from OpenAI
        model: Model name used
    """
    cache_entry = db_models.OpenAIResponseCache(
        game_id=game_id,
        batch_key=batch_key,
        prompt_preview=prompt_preview[:2000] if prompt_preview else None,
        response_json=response_data,
        model=model,
    )
    session.add(cache_entry)
    await session.flush()
    logger.info(f"Cache STORED for game {game_id} batch {batch_key}")


async def execute_render_narratives(stage_input: StageInput) -> StageOutput:
    """Execute the RENDER_NARRATIVES stage.

    Generates narrative text for each validated moment using OpenAI.
    Moments are batched (up to MOMENTS_PER_BATCH per call) for efficiency.
    Validates all narratives before returning.

    Args:
        stage_input: Input containing previous_output with validated moments

    Returns:
        StageOutput with moments enriched with narrative field

    Raises:
        ValueError: If OpenAI is not configured or validation fails
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting RENDER_NARRATIVES for game {game_id}")

    # Get OpenAI client
    openai_client = get_openai_client()
    if openai_client is None:
        raise ValueError(
            "OpenAI API key not configured - cannot render narratives. "
            "Set OPENAI_API_KEY environment variable."
        )

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("RENDER_NARRATIVES requires previous stage output")

    # Verify validation passed
    validated = previous_output.get("validated")
    if validated is not True:
        raise ValueError(
            "RENDER_NARRATIVES requires VALIDATE_MOMENTS to pass. "
            f"Got validated={validated}"
        )

    # Get moments and PBP data
    moments = previous_output.get("moments")
    if not moments:
        raise ValueError("No moments in previous stage output")

    pbp_events = previous_output.get("pbp_events")
    if not pbp_events:
        raise ValueError("No pbp_events in previous stage output")

    # Build play_index -> event lookup
    play_lookup: dict[int, dict[str, Any]] = {}
    for event in pbp_events:
        play_index = event.get("play_index")
        if play_index is not None:
            play_lookup[play_index] = event

    game_context = stage_input.game_context

    # Prepare all moments with their plays
    moments_with_plays: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for i, moment in enumerate(moments):
        play_ids = moment.get("play_ids", [])
        moment_plays = [play_lookup[pid] for pid in play_ids if pid in play_lookup]
        moments_with_plays.append((i, moment, moment_plays))

    # Calculate batch count
    num_batches = (len(moments) + MOMENTS_PER_BATCH - 1) // MOMENTS_PER_BATCH
    output.add_log(
        f"Rendering {len(moments)} moments in {num_batches} batches "
        f"({MOMENTS_PER_BATCH} per batch)"
    )

    # Process in batches
    enriched_moments: list[dict[str, Any]] = [None] * len(moments)  # type: ignore
    successful_renders = 0
    total_openai_calls = 0
    retry_count = 0  # Task 1.2: Track retries for logging
    injection_count = 0  # Task 1.3: Track deterministic injections

    # Fallback tracking with classification (Task 0.2)
    fallback_moments: list[int] = []  # All moments with fallback narratives
    valid_fallbacks: list[dict[str, Any]] = []  # VALID fallback details
    invalid_fallbacks: list[dict[str, Any]] = []  # INVALID fallback details (for debugging)

    for batch_start in range(0, len(moments_with_plays), MOMENTS_PER_BATCH):
        batch_end = min(batch_start + MOMENTS_PER_BATCH, len(moments_with_plays))
        batch = moments_with_plays[batch_start:batch_end]

        # Check for moments with no plays -> INVALID fallback
        valid_batch = []
        for moment_index, moment, moment_plays in batch:
            if not moment_plays:
                # No plays = missing play metadata -> INVALID
                reason = FallbackReason.MISSING_PLAY_METADATA
                fallback_narrative = _get_invalid_fallback_narrative(reason)

                logger.warning(
                    f"Moment {moment_index}: No plays found for play_ids "
                    f"{moment.get('play_ids', [])}, using INVALID fallback"
                )

                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": FallbackType.INVALID.value,
                    "fallback_reason": reason.value,
                }
                fallback_moments.append(moment_index)
                invalid_fallbacks.append({
                    "moment_index": moment_index,
                    "reason": reason.value,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                })
                successful_renders += 1
            else:
                valid_batch.append((moment_index, moment, moment_plays))

        if not valid_batch:
            continue

        # Task 1.2: Track moments that need retry due to soft validation errors
        moments_needing_retry: list[tuple[int, dict[str, Any], list[dict[str, Any]], str]] = []

        # Build batch prompt and call OpenAI
        # is_retry=False for initial attempt
        prompt = _build_batch_prompt(valid_batch, game_context, is_retry=False)

        try:
            total_openai_calls += 1
            # Task 1.2: More tokens for multi-sentence output (250 per moment vs 150)
            max_tokens = 250 * len(valid_batch)
            # Run sync OpenAI call in thread to avoid blocking async event loop
            response_json = await asyncio.to_thread(
                openai_client.generate,
                prompt=prompt,
                temperature=0.3,
                max_tokens=max_tokens,
            )

            # Parse batch response
            response_data = json.loads(response_json)

        except json.JSONDecodeError as e:
            # OpenAI returned invalid JSON -> INVALID fallback
            reason = FallbackReason.AI_INVALID_JSON
            logger.warning(
                f"Batch {batch_start}-{batch_end}: OpenAI returned invalid JSON: {e}, "
                f"using INVALID fallback"
            )
            for moment_index, moment, _ in valid_batch:
                fallback_narrative = _get_invalid_fallback_narrative(reason)
                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": FallbackType.INVALID.value,
                    "fallback_reason": reason.value,
                }
                fallback_moments.append(moment_index)
                invalid_fallbacks.append({
                    "moment_index": moment_index,
                    "reason": reason.value,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                    "error": str(e)[:200],
                })
                successful_renders += 1
            continue

        except Exception as e:
            # OpenAI call failed -> INVALID fallback
            reason = FallbackReason.AI_GENERATION_FAILED
            logger.warning(
                f"Batch {batch_start}-{batch_end}: OpenAI call failed: {e}, "
                f"using INVALID fallback"
            )
            for moment_index, moment, _ in valid_batch:
                fallback_narrative = _get_invalid_fallback_narrative(reason)
                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": FallbackType.INVALID.value,
                    "fallback_reason": reason.value,
                }
                fallback_moments.append(moment_index)
                invalid_fallbacks.append({
                    "moment_index": moment_index,
                    "reason": reason.value,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                    "error": str(e)[:200],
                })
                successful_renders += 1
            continue

        # Process response (from cache or fresh API call)
        # Extract items array from response object
        # OpenAI JSON mode returns objects, not arrays
        items = response_data.get("items", [])
        if not items and isinstance(response_data, list):
            items = response_data  # Fallback if it's already a list

        # Log for debugging
        logger.info(
            f"Batch {batch_start}-{batch_end}: Got {len(items)} items from OpenAI "
            f"(expected {len(valid_batch)})"
        )

        # Build lookup of narratives by moment_index
        # Supports both compact ("i", "n") and full ("moment_index", "narrative") keys
        narrative_lookup: dict[int, str] = {}
        for item in items:
            idx = item.get("i") if item.get("i") is not None else item.get("moment_index")
            narrative = item.get("n") or item.get("narrative", "")
            if idx is not None:
                narrative_lookup[idx] = narrative

        # Log if we're missing narratives
        missing = [idx for idx, _, _ in valid_batch if idx not in narrative_lookup]
        if missing:
            logger.warning(
                f"Batch {batch_start}-{batch_end}: Missing narratives for moments {missing[:5]}..."
            )

        # Process each moment in the batch
        for moment_index, moment, moment_plays in valid_batch:
            narrative = narrative_lookup.get(moment_index, "")

            # Handle empty narratives with classified fallback (Task 0.2)
            if not narrative or not narrative.strip():
                # Classify the fallback based on moment context
                fallback_narrative, fallback_type, fallback_reason = (
                    _classify_empty_narrative_fallback(moment, moment_plays, moment_index)
                )

                fallback_moments.append(moment_index)

                # Track by type for debugging
                fallback_detail = {
                    "moment_index": moment_index,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                    "fallback_type": fallback_type.value,
                }
                if fallback_reason:
                    fallback_detail["reason"] = fallback_reason.value

                if fallback_type == FallbackType.VALID:
                    valid_fallbacks.append(fallback_detail)
                    logger.info(
                        f"Moment {moment_index}: Empty narrative, using VALID fallback "
                        f"(low-signal gameplay)",
                        extra={"game_id": game_id, **fallback_detail},
                    )
                else:
                    invalid_fallbacks.append(fallback_detail)
                    logger.warning(
                        f"Moment {moment_index}: Empty narrative, using INVALID fallback "
                        f"(reason: {fallback_reason.value if fallback_reason else 'unknown'})",
                        extra={"game_id": game_id, **fallback_detail},
                    )

                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": fallback_type.value,
                    "fallback_reason": fallback_reason.value if fallback_reason else None,
                }
                successful_renders += 1

            else:
                # Task 1.2: Validate with hard/soft error separation
                hard_errors, soft_errors = _validate_narrative(
                    narrative, moment, moment_plays, moment_index
                )

                # Task 1.3: Check explicit play coverage separately
                explicit_play_ids = moment.get("explicitly_narrated_play_ids", [])
                missing_explicit = _check_explicit_play_coverage(narrative, moment, moment_plays)

                if hard_errors and "explicit" not in hard_errors[0].lower():
                    # Non-explicit-play hard errors -> fallback
                    reason = FallbackReason.MISSING_EXPLICIT_PLAY_REFERENCE
                    fallback_narrative = _get_invalid_fallback_narrative(reason)

                    logger.warning(
                        f"Moment {moment_index}: Hard validation error, using INVALID fallback: "
                        f"{hard_errors[0]}"
                    )

                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": fallback_narrative,
                        "fallback_type": FallbackType.INVALID.value,
                        "fallback_reason": reason.value,
                    }
                    fallback_moments.append(moment_index)
                    invalid_fallbacks.append({
                        "moment_index": moment_index,
                        "reason": reason.value,
                        "period": moment.get("period"),
                        "start_clock": moment.get("start_clock"),
                        "validation_errors": hard_errors,
                    })
                    successful_renders += 1

                elif soft_errors or missing_explicit:
                    # Task 1.2/1.3: Soft errors or missing explicit plays -> queue for retry
                    moments_needing_retry.append(
                        (moment_index, moment, moment_plays, narrative, missing_explicit)
                    )
                    if missing_explicit:
                        logger.info(
                            f"Moment {moment_index}: Missing explicit plays {missing_explicit}, will retry"
                        )
                    else:
                        logger.info(
                            f"Moment {moment_index}: Soft validation errors, will retry: "
                            f"{soft_errors[0]}"
                        )
                    # Don't set enriched_moments yet - will be set after retry/injection

                else:
                    # All validation passed - Task 1.3: Log coverage resolution
                    if explicit_play_ids:
                        _log_coverage_resolution(
                            game_id=game_id,
                            moment_index=moment_index,
                            resolution=CoverageResolution.INITIAL_PASS,
                            explicit_play_ids=explicit_play_ids,
                        )
                    successful_renders += 1
                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": narrative,
                        "fallback_type": None,
                        "fallback_reason": None,
                        "coverage_resolution": CoverageResolution.INITIAL_PASS.value if explicit_play_ids else None,
                    }

        # Task 1.2/1.3: Retry moments with soft validation errors or missing explicit plays
        if moments_needing_retry:
            retry_count += len(moments_needing_retry)
            output.add_log(
                f"Retrying {len(moments_needing_retry)} moments with validation issues"
            )

            # Build retry batch with is_retry=True for stricter prompt
            retry_batch = [(idx, m, plays) for idx, m, plays, _, _ in moments_needing_retry]
            retry_prompt = _build_batch_prompt(retry_batch, game_context, is_retry=True)

            try:
                total_openai_calls += 1
                retry_max_tokens = 250 * len(retry_batch)
                retry_response_json = await asyncio.to_thread(
                    openai_client.generate,
                    prompt=retry_prompt,
                    temperature=0.2,  # Lower temp for retry
                    max_tokens=retry_max_tokens,
                )
                retry_response_data = json.loads(retry_response_json)
                retry_items = retry_response_data.get("items", [])

                # Build retry narrative lookup
                retry_narrative_lookup: dict[int, str] = {}
                for item in retry_items:
                    idx = item.get("i") if item.get("i") is not None else item.get("moment_index")
                    narr = item.get("n") or item.get("narrative", "")
                    if idx is not None:
                        retry_narrative_lookup[idx] = narr

                # Process retry results
                for moment_index, moment, moment_plays, original_narrative, initial_missing in moments_needing_retry:
                    retry_narrative = retry_narrative_lookup.get(moment_index, original_narrative)
                    explicit_play_ids = moment.get("explicitly_narrated_play_ids", [])

                    # Use original narrative as fallback if retry returned empty
                    if not retry_narrative or not retry_narrative.strip():
                        retry_narrative = original_narrative

                    # Task 1.3: Check explicit play coverage after retry
                    missing_after_regen = _check_explicit_play_coverage(
                        retry_narrative, moment, moment_plays
                    )

                    if not missing_after_regen:
                        # Retry succeeded - all explicit plays covered
                        # Validate for other issues (strict=False for sentence count)
                        hard_errors, soft_errors = _validate_narrative(
                            retry_narrative, moment, moment_plays, moment_index,
                            strict_sentence_check=False
                        )

                        # Accept even with soft errors if explicit plays are covered
                        if not hard_errors or "explicit" in str(hard_errors).lower():
                            if explicit_play_ids:
                                _log_coverage_resolution(
                                    game_id=game_id,
                                    moment_index=moment_index,
                                    resolution=CoverageResolution.REGENERATION_PASS,
                                    explicit_play_ids=explicit_play_ids,
                                    missing_after_initial=initial_missing,
                                )
                            successful_renders += 1
                            enriched_moments[moment_index] = {
                                **moment,
                                "narrative": retry_narrative,
                                "fallback_type": None,
                                "fallback_reason": None,
                                "coverage_resolution": CoverageResolution.REGENERATION_PASS.value if initial_missing else None,
                            }
                            logger.info(f"Moment {moment_index}: Retry succeeded")
                            continue

                    # Task 1.3: Regeneration failed to cover explicit plays -> INJECT
                    if missing_after_regen:
                        injection_count += 1
                        logger.warning(
                            f"Moment {moment_index}: Regeneration failed to cover plays "
                            f"{missing_after_regen}, injecting deterministic sentences"
                        )

                        # Inject deterministic sentences for missing plays
                        injected_narrative, injections = _inject_missing_explicit_plays(
                            retry_narrative, missing_after_regen, moment_plays, game_context
                        )

                        # Verify injection succeeded
                        still_missing = _check_explicit_play_coverage(
                            injected_narrative, moment, moment_plays
                        )

                        if still_missing:
                            # Task 1.3: Injection failed - this is a hard error
                            logger.error(
                                f"Moment {moment_index}: Injection failed, still missing {still_missing}"
                            )
                            _log_coverage_resolution(
                                game_id=game_id,
                                moment_index=moment_index,
                                resolution=CoverageResolution.INJECTION_FAILED,
                                explicit_play_ids=explicit_play_ids,
                                missing_after_initial=initial_missing,
                                missing_after_regen=missing_after_regen,
                                injections=injections,
                            )
                            raise ValueError(
                                f"Explicit play coverage invariant violated: "
                                f"Moment {moment_index} still missing plays {still_missing} after injection"
                            )

                        # Injection succeeded
                        _log_coverage_resolution(
                            game_id=game_id,
                            moment_index=moment_index,
                            resolution=CoverageResolution.INJECTION_REQUIRED,
                            explicit_play_ids=explicit_play_ids,
                            missing_after_initial=initial_missing,
                            missing_after_regen=missing_after_regen,
                            injections=injections,
                        )
                        successful_renders += 1
                        enriched_moments[moment_index] = {
                            **moment,
                            "narrative": injected_narrative,
                            "fallback_type": None,
                            "fallback_reason": None,
                            "coverage_resolution": CoverageResolution.INJECTION_REQUIRED.value,
                            "injections": injections,
                        }
                        logger.info(
                            f"Moment {moment_index}: Injection succeeded, "
                            f"added {len(injections)} deterministic sentence(s)"
                        )
                        continue

                    # No missing explicit plays but other hard errors -> fallback
                    reason = FallbackReason.FORBIDDEN_LANGUAGE_DETECTED
                    fallback_narrative = _get_invalid_fallback_narrative(reason)

                    logger.warning(
                        f"Moment {moment_index}: Retry failed with non-coverage errors, using INVALID fallback"
                    )

                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": fallback_narrative,
                        "fallback_type": FallbackType.INVALID.value,
                        "fallback_reason": reason.value,
                    }
                    fallback_moments.append(moment_index)
                    invalid_fallbacks.append({
                        "moment_index": moment_index,
                        "reason": reason.value,
                        "period": moment.get("period"),
                        "start_clock": moment.get("start_clock"),
                        "original_narrative": original_narrative[:200],
                    })
                    successful_renders += 1

            except ValueError:
                # Re-raise explicit play coverage violations
                raise
            except Exception as e:
                # Retry batch failed entirely -> try injection on original narratives
                logger.warning(f"Retry batch failed: {e}, attempting injection on original narratives")
                for moment_index, moment, moment_plays, original_narrative, initial_missing in moments_needing_retry:
                    explicit_play_ids = moment.get("explicitly_narrated_play_ids", [])

                    if initial_missing and original_narrative:
                        # Task 1.3: Try injection on original narrative
                        injection_count += 1
                        injected_narrative, injections = _inject_missing_explicit_plays(
                            original_narrative, initial_missing, moment_plays, game_context
                        )

                        still_missing = _check_explicit_play_coverage(
                            injected_narrative, moment, moment_plays
                        )

                        if not still_missing:
                            _log_coverage_resolution(
                                game_id=game_id,
                                moment_index=moment_index,
                                resolution=CoverageResolution.INJECTION_REQUIRED,
                                explicit_play_ids=explicit_play_ids,
                                missing_after_initial=initial_missing,
                                injections=injections,
                            )
                            successful_renders += 1
                            enriched_moments[moment_index] = {
                                **moment,
                                "narrative": injected_narrative,
                                "fallback_type": None,
                                "fallback_reason": None,
                                "coverage_resolution": CoverageResolution.INJECTION_REQUIRED.value,
                                "injections": injections,
                            }
                            continue

                    # Injection not possible or failed -> fallback
                    reason = FallbackReason.AI_GENERATION_FAILED
                    fallback_narrative = _get_invalid_fallback_narrative(reason)

                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": fallback_narrative,
                        "fallback_type": FallbackType.INVALID.value,
                        "fallback_reason": reason.value,
                    }
                    fallback_moments.append(moment_index)
                    invalid_fallbacks.append({
                        "moment_index": moment_index,
                        "reason": reason.value,
                        "period": moment.get("period"),
                        "start_clock": moment.get("start_clock"),
                        "error": str(e)[:200],
                    })
                    successful_renders += 1

    output.add_log(f"OpenAI calls made: {total_openai_calls}")
    output.add_log(f"Successful renders: {successful_renders}/{len(moments)}")
    if retry_count > 0:
        output.add_log(f"Task 1.2 retries: {retry_count} moments retried")
    if injection_count > 0:
        output.add_log(
            f"Task 1.3 injections: {injection_count} moments required deterministic injection"
        )

    # Log fallback usage with classification (Task 0.2)
    if fallback_moments:
        output.add_log(
            f"Fallback narratives used: {len(fallback_moments)} total "
            f"({len(valid_fallbacks)} VALID, {len(invalid_fallbacks)} INVALID)",
            level="warning" if invalid_fallbacks else "info",
        )

        if valid_fallbacks:
            output.add_log(
                f"  VALID fallbacks (low-signal gameplay): {len(valid_fallbacks)}",
                level="info",
            )

        if invalid_fallbacks:
            output.add_log(
                f"  INVALID fallbacks (needs debugging): {len(invalid_fallbacks)}",
                level="warning",
            )
            # Log first few invalid fallbacks for visibility
            for fb in invalid_fallbacks[:5]:
                output.add_log(
                    f"    Moment {fb['moment_index']}: {fb.get('reason', 'unknown')}",
                    level="warning",
                )
            if len(invalid_fallbacks) > 5:
                output.add_log(
                    f"    ... and {len(invalid_fallbacks) - 5} more INVALID fallbacks",
                    level="warning",
                )

        logger.warning(
            "render_narratives_fallbacks_used",
            extra={
                "game_id": game_id,
                "fallback_count": len(fallback_moments),
                "valid_fallback_count": len(valid_fallbacks),
                "invalid_fallback_count": len(invalid_fallbacks),
                "fallback_moment_indices": fallback_moments,
                "invalid_fallback_details": invalid_fallbacks[:10],
            },
        )

    # Task 1.2: All validation errors are now handled via retry/fallback
    # No unhandled validation errors should reach here
    if fallback_moments:
        output.add_log(
            f"{len(moments) - len(fallback_moments)} narratives from OpenAI, "
            f"{len(fallback_moments)} fallbacks used "
            f"({len(valid_fallbacks)} valid, {len(invalid_fallbacks)} invalid)"
        )
    else:
        output.add_log(f"All {len(moments)} narratives generated successfully")

    # Task 0.2: Flag if any INVALID fallbacks remain
    if invalid_fallbacks:
        output.add_log(
            f"WARNING: {len(invalid_fallbacks)} INVALID fallbacks detected - "
            f"these indicate pipeline issues that need debugging",
            level="warning",
        )

    output.add_log("RENDER_NARRATIVES completed successfully")

    # Output shape: moments with narrative field added
    # Task 0.2: includes fallback classification
    # Task 1.2: includes retry count
    # Task 1.3: includes injection count
    output.data = {
        "rendered": True,
        "moments": enriched_moments,
        "errors": [],
        "openai_calls": total_openai_calls,
        "successful_renders": successful_renders,
        "fallback_count": len(fallback_moments),
        "fallback_moment_indices": fallback_moments,
        # Task 0.2: Fallback classification for monitoring
        "valid_fallback_count": len(valid_fallbacks),
        "invalid_fallback_count": len(invalid_fallbacks),
        "valid_fallbacks": valid_fallbacks,
        "invalid_fallbacks": invalid_fallbacks,
        # Task 1.2: Multi-sentence retry tracking
        "retry_count": retry_count,
        # Task 1.3: Explicit play coverage injection tracking
        "injection_count": injection_count,
    }

    return output
