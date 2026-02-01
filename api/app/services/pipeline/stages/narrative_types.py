"""Narrative types, enums, and constants for render_narratives stage.

This module contains all shared type definitions and constants used across
the narrative rendering pipeline.
"""

from __future__ import annotations

import re
from enum import Enum


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

    # Multi-sentence validation failures
    INSUFFICIENT_SENTENCES = "insufficient_sentences"
    FORBIDDEN_LANGUAGE_DETECTED = "forbidden_language_detected"
    MISSING_EXPLICIT_PLAY_REFERENCE = "missing_explicit_play_reference"

    # Pipeline state issues
    UNEXPECTED_PIPELINE_STATE = "unexpected_pipeline_state"


class CoverageResolution(str, Enum):
    """Resolution method for explicit play coverage.

    Tracks how coverage requirements were satisfied.
    """

    INITIAL_PASS = "initial_pass"  # AI covered all explicit plays
    REGENERATION_PASS = "regeneration_pass"  # Retry satisfied coverage
    INJECTION_REQUIRED = "injection_required"  # Deterministic injection was needed


class StyleViolationType(str, Enum):
    """Types of style violations detected in narratives.

    These are soft warnings (not failures) to track AI prose quality.
    """

    REPEATED_OPENER = "repeated_opener"  # Multiple sentences start the same way
    UNIFORM_LENGTH = "uniform_length"  # All sentences same length (robotic)
    METRIC_FIRST = "metric_first"  # Leads with statistics instead of action
    TEMPLATE_REPETITION = "template_repetition"  # Same sentence pattern repeated


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
    # Subjective adjectives (must remain neutral)
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
    # Crowd/atmosphere references
    r"\bcrowd erupted\b",
    r"\bcrowd went\b",
    r"\bfans\b",
    r"\batmosphere\b",
    r"\benergy in\b",
    r"\bbuilding\b.*\brocked\b",
    # Metaphorical/narrative flourish
    r"\btook over\b",
    r"\btook control\b",
    r"\bcaught fire\b",
    r"\bon fire\b",
    r"\bheat(ed|ing)? up\b",
    r"\bin the zone\b",
    r"\bowned\b",
    # Intent/psychology speculation
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
# Larger batches = fewer API calls but more tokens per call
# Max output: 16,384 tokens / 250 per moment ≈ 65 moments max
# Using 50 for safety margin (12,500 tokens max output)
MOMENTS_PER_BATCH = 50
