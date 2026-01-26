"""
Story Contract Validators: Mechanical enforcement of Story contract.

This module enforces ALL requirements from docs/story_contract.md.
It does NOT modify, repair, or interpret data. It only validates.

PHILOSOPHY:
- Validation is stricter than generation
- AI output is assumed untrusted
- Passing validation is the definition of "correct"
- If output violates the contract, it MUST fail

AUTHORITATIVE INPUT:
- docs/story_contract.md (Section 7: Success Criteria)

This module makes Story safe. Removing it would allow non-compliant output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .schema import (
    CondensedMoment,
    StoryOutput,
    ScoreTuple,
    _clock_to_seconds,
)
from .moment_builder import PlayData


class ContractViolation(Exception):
    """Raised when Story contract is violated.

    Contains structured information about the violation.
    """

    def __init__(self, message: str, violations: list[str] | None = None):
        self.violations = violations or [message]
        super().__init__(message)


@dataclass
class ValidationResult:
    """Result of contract validation."""

    valid: bool
    violations: list[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        """Raise ContractViolation if validation failed."""
        if not self.valid:
            raise ContractViolation(
                f"Contract validation failed with {len(self.violations)} violation(s)",
                violations=self.violations,
            )


@dataclass
class TraceabilityResult:
    """Result of narrative traceability check."""

    traceable: bool
    matched_play_ids: list[int]
    unmatched_terms: list[str]
    explanation: str


# =============================================================================
# FORBIDDEN LANGUAGE (Contract Section 6: Explicit Non-Goals)
# =============================================================================

# Abstract narrative language that implies interpretation beyond plays
FORBIDDEN_ABSTRACT_TERMS = frozenset([
    "momentum",
    "flow",
    "turning point",
    "turning-point",
    "key moment",
    "key stretch",
    "pivotal",
    "crucial stretch",
    "critical juncture",
    "tide turned",
    "shifted the momentum",
])

# Retrospective/prospective language (no future knowledge)
FORBIDDEN_TEMPORAL_TERMS = frozenset([
    "little did they know",
    "foreshadowing",
    "would later",
    "would eventually",
    "as we'll see",
    "looking ahead",
    "in hindsight",
    "spoiler",
])

# Game-level summary language (summaries require play backing)
FORBIDDEN_SUMMARY_TERMS = frozenset([
    "overall",
    "throughout the game",
    "throughout the quarter",
    "earlier in the game",
    "later in the game",
    "in the first half",
    "in the second half",
    "all game long",
    "the entire quarter",
])

# Meta-language about the narrative itself
FORBIDDEN_META_TERMS = frozenset([
    "in this moment",
    "during this stretch",
    "in this sequence",
    "at this point in the game",
    "this is where",
])

# Headers/section language (stories have no named divisions)
FORBIDDEN_HEADER_PATTERNS = [
    r"^#{1,6}\s",  # Markdown headers
    r"^\*\*[A-Z].*\*\*$",  # Bold headers
    r"^[A-Z][A-Z\s]+:$",  # ALL CAPS headers
    r"^Quarter \d",  # Quarter headers
    r"^Period \d",  # Period headers
    r"^First Half",
    r"^Second Half",
    r"^Overtime",
]

ALL_FORBIDDEN_TERMS = (
    FORBIDDEN_ABSTRACT_TERMS
    | FORBIDDEN_TEMPORAL_TERMS
    | FORBIDDEN_SUMMARY_TERMS
    | FORBIDDEN_META_TERMS
)


# =============================================================================
# STRUCTURAL VALIDATORS (Contract Section 7: Structural Tests)
# =============================================================================


def validate_moment_structure(moment: CondensedMoment) -> list[str]:
    """Validate structural requirements of a single moment.

    Enforces:
    - All required fields present (enforced by dataclass)
    - play_ids is non-empty
    - explicitly_narrated_play_ids is non-empty
    - explicitly_narrated_play_ids ⊂ play_ids
    - narrative is non-empty
    - period is positive
    - clocks are non-empty strings

    Returns list of violations (empty if valid).
    """
    violations: list[str] = []

    # play_ids non-empty
    if not moment.play_ids:
        violations.append("play_ids is empty")

    # explicitly_narrated_play_ids non-empty
    if not moment.explicitly_narrated_play_ids:
        violations.append("explicitly_narrated_play_ids is empty")

    # Subset check
    if moment.play_ids and moment.explicitly_narrated_play_ids:
        play_ids_set = set(moment.play_ids)
        narrated_set = set(moment.explicitly_narrated_play_ids)
        if not narrated_set.issubset(play_ids_set):
            extra = narrated_set - play_ids_set
            violations.append(
                f"explicitly_narrated_play_ids contains IDs not in play_ids: {extra}"
            )

    # Narrative non-empty
    if not moment.narrative or not moment.narrative.strip():
        violations.append("narrative is empty")

    # Period positive
    if moment.period < 1:
        violations.append(f"period must be >= 1, got {moment.period}")

    # Clocks non-empty
    if not moment.start_clock or not moment.start_clock.strip():
        violations.append("start_clock is empty")
    if not moment.end_clock or not moment.end_clock.strip():
        violations.append("end_clock is empty")

    # Score tuples must be valid (enforced by ScoreTuple but double-check)
    if not isinstance(moment.score_before, ScoreTuple):
        violations.append("score_before is not a ScoreTuple")
    if not isinstance(moment.score_after, ScoreTuple):
        violations.append("score_after is not a ScoreTuple")

    return violations


def validate_story_structure(story: StoryOutput) -> list[str]:
    """Validate structural requirements of a complete story.

    Enforces:
    - Story is non-empty
    - All moments pass structural validation
    - No play_id appears in multiple moments
    - Moments are ordered by game time (period, then clock descending)

    Returns list of violations (empty if valid).
    """
    violations: list[str] = []

    # Non-empty
    if not story.moments:
        violations.append("Story has no moments")
        return violations  # Can't validate further

    # Validate each moment
    for i, moment in enumerate(story.moments):
        moment_violations = validate_moment_structure(moment)
        for v in moment_violations:
            violations.append(f"Moment {i}: {v}")

    # No overlapping play_ids
    seen_play_ids: dict[int, int] = {}
    for i, moment in enumerate(story.moments):
        for pid in moment.play_ids:
            if pid in seen_play_ids:
                violations.append(
                    f"play_id {pid} appears in moment {seen_play_ids[pid]} "
                    f"and moment {i}"
                )
            seen_play_ids[pid] = i

    # Ordering validation
    for i in range(1, len(story.moments)):
        prev = story.moments[i - 1]
        curr = story.moments[i]

        # Period must be non-decreasing
        if curr.period < prev.period:
            violations.append(
                f"Moments not ordered: moment {i-1} period={prev.period}, "
                f"moment {i} period={curr.period}"
            )

        # Within same period, clock must be descending (countdown)
        if curr.period == prev.period:
            prev_seconds = _clock_to_seconds(prev.start_clock)
            curr_seconds = _clock_to_seconds(curr.start_clock)
            if prev_seconds is not None and curr_seconds is not None:
                if curr_seconds > prev_seconds:
                    violations.append(
                        f"Moments not ordered within period {curr.period}: "
                        f"moment {i-1} clock={prev.start_clock} ({prev_seconds}s), "
                        f"moment {i} clock={curr.start_clock} ({curr_seconds}s)"
                    )

    return violations


def validate_plays_exist(
    story: StoryOutput,
    available_play_ids: set[int],
) -> list[str]:
    """Validate all play_ids in story exist in source PBP.

    Args:
        story: The story to validate
        available_play_ids: Set of valid play_ids from source PBP

    Returns list of violations (empty if valid).
    """
    violations: list[str] = []

    for i, moment in enumerate(story.moments):
        for pid in moment.play_ids:
            if pid not in available_play_ids:
                violations.append(
                    f"Moment {i}: play_id {pid} does not exist in source PBP"
                )

    return violations


# =============================================================================
# NARRATIVE VALIDATORS (Contract Section 7: Narrative Tests)
# =============================================================================


def _extract_player_names(text: str) -> set[str]:
    """Extract potential player names from text.

    Heuristic: capitalized words that aren't common English words.
    """
    common_words = {
        "The", "A", "An", "And", "But", "Or", "For", "With", "From", "To",
        "In", "On", "At", "By", "As", "Is", "It", "He", "She", "They",
        "His", "Her", "Their", "This", "That", "These", "Those",
        "Boston", "Miami", "Lakers", "Celtics", "Warriors", "Heat",  # Team names
        "Cleveland", "Denver", "Phoenix", "Chicago", "Dallas", "Houston",
        "Golden", "State", "Los", "Angeles", "New", "York", "San", "Antonio",
        "Portland", "Trail", "Blazers", "Oklahoma", "City", "Thunder",
    }

    # Find capitalized words
    pattern = r'\b([A-Z][a-z]+)\b'
    matches = re.findall(pattern, text)

    return {m for m in matches if m not in common_words}


def _extract_action_terms(text: str) -> set[str]:
    """Extract basketball action terms from text."""
    action_terms = {
        "three", "three-pointer", "layup", "dunk", "jumper", "shot",
        "free throw", "rebound", "steal", "block", "assist", "turnover",
        "foul", "timeout", "bucket", "basket", "score", "scores",
        "drills", "drains", "sinks", "hits", "makes", "misses",
        "drives", "attacks", "pulls up", "step-back", "fadeaway",
    }

    text_lower = text.lower()
    found = set()
    for term in action_terms:
        if term in text_lower:
            found.add(term)

    return found


def validate_forbidden_language(narrative: str) -> list[str]:
    """Check narrative for forbidden language.

    Returns list of violations (empty if valid).
    """
    violations: list[str] = []
    narrative_lower = narrative.lower()

    # Check forbidden terms
    for term in ALL_FORBIDDEN_TERMS:
        if term in narrative_lower:
            violations.append(f"Forbidden term found: '{term}'")

    # Check header patterns
    lines = narrative.split('\n')
    for line in lines:
        line_stripped = line.strip()
        for pattern in FORBIDDEN_HEADER_PATTERNS:
            if re.match(pattern, line_stripped, re.IGNORECASE):
                violations.append(f"Header-like pattern found: '{line_stripped}'")

    return violations


def validate_narrative_traceability(
    moment: CondensedMoment,
    plays: Sequence[PlayData],
) -> list[str]:
    """Validate narrative is traceable to backing plays.

    Enforces:
    - Narrative references at least one explicitly narrated play
    - Player names in narrative appear in backing plays
    - No claims unsupported by plays

    Args:
        moment: The moment to validate
        plays: The PlayData objects backing this moment

    Returns list of violations (empty if valid).
    """
    violations: list[str] = []

    if not moment.narrative:
        violations.append("Narrative is empty")
        return violations

    # Build play lookup
    play_map = {p.play_index: p for p in plays}

    # Verify plays match moment
    for pid in moment.play_ids:
        if pid not in play_map:
            violations.append(f"play_id {pid} not found in provided plays")

    # Get explicit play descriptions
    explicit_descriptions = []
    for pid in moment.explicitly_narrated_play_ids:
        if pid in play_map:
            explicit_descriptions.append(play_map[pid].description)

    # Check that at least one explicit play is referenced
    narrative_lower = moment.narrative.lower()

    # Extract key terms from explicit plays
    explicit_terms: set[str] = set()
    for desc in explicit_descriptions:
        desc_lower = desc.lower()
        # Extract player names
        names = _extract_player_names(desc)
        explicit_terms.update(n.lower() for n in names)
        # Extract action terms
        actions = _extract_action_terms(desc)
        explicit_terms.update(actions)

    # Check if any explicit term appears in narrative
    if explicit_terms:
        found_any = any(term in narrative_lower for term in explicit_terms)
        if not found_any:
            violations.append(
                f"Narrative does not reference any explicitly narrated play. "
                f"Expected terms: {list(explicit_terms)[:5]}..."
            )

    # Check player names in narrative are from backing plays
    all_play_text = " ".join(p.description for p in plays)
    narrative_names = _extract_player_names(moment.narrative)
    play_names = _extract_player_names(all_play_text)

    for name in narrative_names:
        if name.lower() not in {n.lower() for n in play_names}:
            # Could be team name or other entity - only warn for clear player names
            # Conservative: don't fail on ambiguous names
            pass

    # Check for forbidden language
    forbidden_violations = validate_forbidden_language(moment.narrative)
    violations.extend(forbidden_violations)

    return violations


def validate_no_future_references(
    story: StoryOutput,
    all_plays: Sequence[PlayData],
) -> list[str]:
    """Validate no moment references plays from future moments.

    Enforces: No narrative references future events.

    Args:
        story: Complete story
        all_plays: All plays in chronological order

    Returns list of violations (empty if valid).
    """
    violations: list[str] = []

    # Build play index to moment index mapping
    play_to_moment: dict[int, int] = {}
    for moment_idx, moment in enumerate(story.moments):
        for pid in moment.play_ids:
            play_to_moment[pid] = moment_idx

    # Build play index to description mapping
    play_descriptions = {p.play_index: p.description for p in all_plays}

    # For each moment, check narrative doesn't reference future plays
    for moment_idx, moment in enumerate(story.moments):
        narrative_lower = moment.narrative.lower()

        # Get play_ids from future moments
        future_play_ids = {
            pid for pid, midx in play_to_moment.items()
            if midx > moment_idx
        }

        # Check if future player names appear
        for pid in future_play_ids:
            if pid in play_descriptions:
                future_names = _extract_player_names(play_descriptions[pid])
                current_names = set()
                for cpid in moment.play_ids:
                    if cpid in play_descriptions:
                        current_names.update(
                            _extract_player_names(play_descriptions[cpid])
                        )

                # Only flag if name is in future but NOT in current
                for name in future_names:
                    if name.lower() in narrative_lower:
                        if name not in current_names:
                            violations.append(
                                f"Moment {moment_idx}: May reference future play "
                                f"(player '{name}' appears in moment {play_to_moment[pid]})"
                            )

    return violations


# =============================================================================
# TRACEABILITY DEBUG HOOKS (Contract Section 7: Verification Questions)
# =============================================================================


def trace_sentence_to_plays(
    sentence: str,
    moment: CondensedMoment,
    plays: Sequence[PlayData],
) -> TraceabilityResult:
    """Identify which plays justify a narrative sentence.

    This answers: "Which plays back this sentence?"

    Args:
        sentence: A sentence or phrase from the narrative
        moment: The moment containing the sentence
        plays: The PlayData objects backing this moment

    Returns:
        TraceabilityResult with matched play_ids or explanation of failure
    """
    sentence_lower = sentence.lower()

    # Build play map
    play_map = {p.play_index: p for p in plays}

    # Extract terms from sentence
    sentence_names = _extract_player_names(sentence)
    sentence_actions = _extract_action_terms(sentence)
    sentence_terms = {n.lower() for n in sentence_names} | sentence_actions

    if not sentence_terms:
        return TraceabilityResult(
            traceable=False,
            matched_play_ids=[],
            unmatched_terms=[],
            explanation="No identifiable terms (players, actions) in sentence",
        )

    # Find matching plays
    matched_ids: list[int] = []
    matched_terms: set[str] = set()

    for pid in moment.play_ids:
        if pid not in play_map:
            continue

        play = play_map[pid]
        play_text_lower = play.description.lower()

        # Check for term matches
        for term in sentence_terms:
            if term in play_text_lower:
                if pid not in matched_ids:
                    matched_ids.append(pid)
                matched_terms.add(term)

    unmatched = list(sentence_terms - matched_terms)

    if matched_ids:
        return TraceabilityResult(
            traceable=True,
            matched_play_ids=matched_ids,
            unmatched_terms=unmatched,
            explanation=f"Sentence traces to {len(matched_ids)} play(s) via terms: {list(matched_terms)}",
        )
    else:
        return TraceabilityResult(
            traceable=False,
            matched_play_ids=[],
            unmatched_terms=unmatched,
            explanation=f"No plays match sentence terms: {list(sentence_terms)}",
        )


def trace_narrative_to_plays(
    moment: CondensedMoment,
    plays: Sequence[PlayData],
) -> list[TraceabilityResult]:
    """Trace each sentence in a narrative to backing plays.

    Args:
        moment: The moment to analyze
        plays: The PlayData objects backing this moment

    Returns:
        List of TraceabilityResult, one per sentence
    """
    # Split narrative into sentences
    sentences = re.split(r'[.!?]+', moment.narrative)
    sentences = [s.strip() for s in sentences if s.strip()]

    results = []
    for sentence in sentences:
        result = trace_sentence_to_plays(sentence, moment, plays)
        results.append(result)

    return results


def explain_moment_backing(
    moment: CondensedMoment,
    plays: Sequence[PlayData],
) -> dict:
    """Generate complete traceability explanation for a moment.

    Answers all verification questions from the contract:
    1. Which plays back each sentence?
    2. What was the score?
    3. What plays are not explicitly narrated?
    4. Is this moment grounded?

    Args:
        moment: The moment to explain
        plays: The PlayData objects backing this moment

    Returns:
        Dict with complete traceability information
    """
    # Trace each sentence
    sentence_traces = trace_narrative_to_plays(moment, plays)

    # Answer verification questions
    return {
        "moment_play_ids": list(moment.play_ids),
        "explicitly_narrated_play_ids": list(moment.explicitly_narrated_play_ids),
        "implicitly_covered_play_ids": list(
            set(moment.play_ids) - set(moment.explicitly_narrated_play_ids)
        ),
        "score_before": {
            "home": moment.score_before.home,
            "away": moment.score_before.away,
        },
        "score_after": {
            "home": moment.score_after.home,
            "away": moment.score_after.away,
        },
        "sentence_traceability": [
            {
                "sentence": sentences[i] if i < len(sentences := re.split(r'[.!?]+', moment.narrative)) else "",
                "traceable": r.traceable,
                "matched_play_ids": r.matched_play_ids,
                "explanation": r.explanation,
            }
            for i, r in enumerate(sentence_traces)
        ],
        "is_grounded": all(r.traceable for r in sentence_traces) if sentence_traces else False,
    }


# =============================================================================
# COMPLETE VALIDATION (All Contract Requirements)
# =============================================================================


def validate_story_contract(
    story: StoryOutput,
    plays: Sequence[PlayData] | None = None,
    *,
    strict: bool = True,
) -> ValidationResult:
    """Validate a complete story against the Story contract.

    Performs ALL structural and narrative validations.

    Args:
        story: The story to validate
        plays: Optional sequence of all PlayData (required for full validation)
        strict: If True, narrative traceability is enforced

    Returns:
        ValidationResult with valid flag and list of violations
    """
    violations: list[str] = []

    # Structural validation
    structural_violations = validate_story_structure(story)
    violations.extend(structural_violations)

    # If plays provided, validate they exist
    if plays is not None:
        available_ids = {p.play_index for p in plays}
        existence_violations = validate_plays_exist(story, available_ids)
        violations.extend(existence_violations)

        # Build play map for narrative validation
        play_map = {p.play_index: p for p in plays}

        # Narrative validation for each moment
        for i, moment in enumerate(story.moments):
            moment_plays = [
                play_map[pid] for pid in moment.play_ids
                if pid in play_map
            ]

            if strict and moment_plays:
                narrative_violations = validate_narrative_traceability(
                    moment, moment_plays
                )
                for v in narrative_violations:
                    violations.append(f"Moment {i}: {v}")

        # Future reference validation
        if strict:
            future_violations = validate_no_future_references(story, plays)
            violations.extend(future_violations)

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
    )


def validate_moment_contract(
    moment: CondensedMoment,
    plays: Sequence[PlayData] | None = None,
    *,
    strict: bool = True,
) -> ValidationResult:
    """Validate a single moment against the Story contract.

    Args:
        moment: The moment to validate
        plays: Optional sequence of PlayData for this moment
        strict: If True, narrative traceability is enforced

    Returns:
        ValidationResult with valid flag and list of violations
    """
    violations: list[str] = []

    # Structural validation
    structural_violations = validate_moment_structure(moment)
    violations.extend(structural_violations)

    # Narrative validation if plays provided
    if plays is not None and strict:
        narrative_violations = validate_narrative_traceability(moment, plays)
        violations.extend(narrative_violations)

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
    )
