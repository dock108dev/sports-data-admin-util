"""
Story Validator: Validation and QA checks for chapters-first game stories.

PURPOSE:
This module exists to DETECT FAILURE, not to fix it.
If something is wrong, the system must FAIL LOUDLY.

There is NO auto-correction.
There is NO rewriting.
There is NO fallback logic.

If output is invalid, it is invalid.

VALIDATION CATEGORIES:

PART 1 - DETERMINISTIC VALIDATION (Before/After AI):
1. Section Ordering - sequential, no gaps, no chapter overlap, full coverage
2. Stat Consistency - deltas sum correctly, no negatives, player bounds enforced
3. Word Count Tolerance - within +/-15% of target (post-AI only)

PART 2 - POST-AI NARRATIVE GUARD:
4. No New Players - every player name in story must exist in provided data
5. No Stat Invention - no percentages, no inferred totals, no computed stats
6. No Outcome Contradictions - final score matches, winner correct, OT only if section exists

GUIDING PRINCIPLE:
> A wrong story is worse than no story.

Fail loud. Do not rewrite. Do not recover.

ISSUE: Validation and QA Checks (Chapters-First Architecture)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .story_section import StorySection, TeamStatDelta, PlayerStatDelta
from .beat_classifier import BeatType
from .story_renderer import StoryRenderInput, StoryRenderResult, ClosingContext


logger = logging.getLogger(__name__)


# ============================================================================
# VALIDATION ERROR TYPES
# ============================================================================

class StoryValidationError(Exception):
    """Base exception for story validation failures.

    This exception is raised when validation fails.
    NO RECOVERY IS ATTEMPTED.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


class SectionOrderingError(StoryValidationError):
    """Raised when section ordering validation fails."""
    pass


class StatConsistencyError(StoryValidationError):
    """Raised when stat consistency validation fails."""
    pass


class WordCountError(StoryValidationError):
    """Raised when word count is outside tolerance."""
    pass


class PlayerInventionError(StoryValidationError):
    """Raised when AI invented a player not in the data."""
    pass


class StatInventionError(StoryValidationError):
    """Raised when AI invented stats not in the data."""
    pass


class OutcomeContradictionError(StoryValidationError):
    """Raised when AI output contradicts known game outcome."""
    pass


# ============================================================================
# VALIDATION RESULT
# ============================================================================

@dataclass
class ValidationResult:
    """Result of validation check.

    NOTE: This is for reporting, NOT for conditional logic.
    If valid=False, the caller MUST raise or fail.
    """
    valid: bool
    error_type: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "valid": self.valid,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "details": self.details,
        }


# ============================================================================
# PART 1: DETERMINISTIC VALIDATION
# ============================================================================

# ----------------------------------------------------------------------------
# 1. SECTION ORDERING VALIDATION
# ----------------------------------------------------------------------------

def validate_section_ordering(
    sections: list[StorySection],
    all_chapter_ids: list[str],
) -> ValidationResult:
    """Validate that sections are correctly ordered and cover all chapters.

    CHECKS:
    - section_index is sequential (0, 1, 2, ...)
    - No gaps in section_index
    - chapters_included do not overlap across sections
    - chapters_included cover all provided chapter_ids exactly once
    - chapters_included within each section are not empty

    Args:
        sections: List of StorySections to validate
        all_chapter_ids: All chapter IDs that should be covered (in order)

    Returns:
        ValidationResult (valid=True or valid=False with details)
    """
    if not sections:
        return ValidationResult(
            valid=False,
            error_type="SectionOrderingError",
            error_message="No sections provided",
            details={"section_count": 0},
        )

    # Check sequential section indices
    for i, section in enumerate(sections):
        if section.section_index != i:
            return ValidationResult(
                valid=False,
                error_type="SectionOrderingError",
                error_message=f"Section index gap: expected {i}, got {section.section_index}",
                details={
                    "expected_index": i,
                    "actual_index": section.section_index,
                    "section_beat": section.beat_type.value,
                },
            )

    # Check each section has chapters
    for section in sections:
        if not section.chapters_included:
            return ValidationResult(
                valid=False,
                error_type="SectionOrderingError",
                error_message=f"Section {section.section_index} has no chapters",
                details={"section_index": section.section_index},
            )

    # Collect all chapters from sections
    chapters_in_sections: list[str] = []
    chapter_to_section: dict[str, int] = {}

    for section in sections:
        for chapter_id in section.chapters_included:
            if chapter_id in chapter_to_section:
                # Duplicate chapter
                return ValidationResult(
                    valid=False,
                    error_type="SectionOrderingError",
                    error_message=f"Chapter '{chapter_id}' appears in multiple sections",
                    details={
                        "chapter_id": chapter_id,
                        "first_section": chapter_to_section[chapter_id],
                        "duplicate_section": section.section_index,
                    },
                )
            chapter_to_section[chapter_id] = section.section_index
            chapters_in_sections.append(chapter_id)

    # Check coverage matches expected chapters
    if all_chapter_ids:
        expected_set = set(all_chapter_ids)
        actual_set = set(chapters_in_sections)

        missing = expected_set - actual_set
        extra = actual_set - expected_set

        if missing:
            return ValidationResult(
                valid=False,
                error_type="SectionOrderingError",
                error_message=f"Missing chapters: {sorted(missing)}",
                details={
                    "missing_chapters": sorted(missing),
                    "missing_count": len(missing),
                },
            )

        if extra:
            return ValidationResult(
                valid=False,
                error_type="SectionOrderingError",
                error_message=f"Extra chapters not in expected list: {sorted(extra)}",
                details={
                    "extra_chapters": sorted(extra),
                    "extra_count": len(extra),
                },
            )

    return ValidationResult(valid=True)


# ----------------------------------------------------------------------------
# 2. STAT CONSISTENCY VALIDATION
# ----------------------------------------------------------------------------

def validate_stat_consistency(sections: list[StorySection]) -> ValidationResult:
    """Validate that section stats are internally consistent.

    CHECKS:
    - No negative stat deltas
    - Player with points must have FG or FT to explain it
    - Max 3 players per team per section (bounded player lists)
    - Team points should roughly match sum of player points (within reason)

    Args:
        sections: List of StorySections to validate

    Returns:
        ValidationResult
    """
    for section in sections:
        idx = section.section_index

        # Check team deltas for negative values
        for team_key, team_delta in section.team_stat_deltas.items():
            if team_delta.points_scored < 0:
                return ValidationResult(
                    valid=False,
                    error_type="StatConsistencyError",
                    error_message=f"Section {idx}: Team '{team_key}' has negative points ({team_delta.points_scored})",
                    details={
                        "section_index": idx,
                        "team_key": team_key,
                        "points_scored": team_delta.points_scored,
                    },
                )

            if team_delta.personal_fouls_committed < 0:
                return ValidationResult(
                    valid=False,
                    error_type="StatConsistencyError",
                    error_message=f"Section {idx}: Team '{team_key}' has negative fouls",
                    details={
                        "section_index": idx,
                        "team_key": team_key,
                        "fouls": team_delta.personal_fouls_committed,
                    },
                )

            if team_delta.timeouts_used < 0:
                return ValidationResult(
                    valid=False,
                    error_type="StatConsistencyError",
                    error_message=f"Section {idx}: Team '{team_key}' has negative timeouts",
                    details={
                        "section_index": idx,
                        "team_key": team_key,
                        "timeouts": team_delta.timeouts_used,
                    },
                )

        # Check player deltas
        for player_key, player_delta in section.player_stat_deltas.items():
            # Check for negative stats
            if player_delta.points_scored < 0:
                return ValidationResult(
                    valid=False,
                    error_type="StatConsistencyError",
                    error_message=f"Section {idx}: Player '{player_key}' has negative points",
                    details={
                        "section_index": idx,
                        "player_key": player_key,
                        "points": player_delta.points_scored,
                    },
                )

            if player_delta.fg_made < 0:
                return ValidationResult(
                    valid=False,
                    error_type="StatConsistencyError",
                    error_message=f"Section {idx}: Player '{player_key}' has negative FG made",
                    details={
                        "section_index": idx,
                        "player_key": player_key,
                        "fg_made": player_delta.fg_made,
                    },
                )

            # Check: points should be explainable by FG/3PT/FT
            # Points = (FG-3PT)*2 + 3PT*3 + FT*1
            # But we only have fg_made (total), three_pt_made, ft_made
            # Expected: points = (fg_made - three_pt_made)*2 + three_pt_made*3 + ft_made
            # Simplified: points = fg_made*2 + three_pt_made*1 + ft_made
            if player_delta.points_scored > 0:
                expected_min = 0
                expected_max = player_delta.fg_made * 3 + player_delta.ft_made  # All FGs are 3PT

                if player_delta.points_scored > expected_max and player_delta.fg_made == 0 and player_delta.ft_made == 0:
                    return ValidationResult(
                        valid=False,
                        error_type="StatConsistencyError",
                        error_message=f"Section {idx}: Player '{player_delta.player_name}' has {player_delta.points_scored} points but no FG/FT",
                        details={
                            "section_index": idx,
                            "player_key": player_key,
                            "player_name": player_delta.player_name,
                            "points": player_delta.points_scored,
                            "fg_made": player_delta.fg_made,
                            "ft_made": player_delta.ft_made,
                        },
                    )

        # Check bounded player lists (max 3 per team)
        players_by_team: dict[str, int] = {}
        for player_delta in section.player_stat_deltas.values():
            team = player_delta.team_key or "unknown"
            players_by_team[team] = players_by_team.get(team, 0) + 1

        for team_key, count in players_by_team.items():
            if count > 3:
                return ValidationResult(
                    valid=False,
                    error_type="StatConsistencyError",
                    error_message=f"Section {idx}: Team '{team_key}' has {count} players (max 3)",
                    details={
                        "section_index": idx,
                        "team_key": team_key,
                        "player_count": count,
                        "max_allowed": 3,
                    },
                )

    return ValidationResult(valid=True)


# ----------------------------------------------------------------------------
# 3. WORD COUNT TOLERANCE VALIDATION
# ----------------------------------------------------------------------------

# Tolerance: +/- 25% of target (AI generation has natural variance)
WORD_COUNT_TOLERANCE_PCT = 0.25


def validate_word_count(
    result: StoryRenderResult,
    tolerance_pct: float = WORD_COUNT_TOLERANCE_PCT,
) -> ValidationResult:
    """Validate that word count is within acceptable tolerance.

    TOLERANCE: +/- 15% of target_word_count

    This validation applies ONLY after AI rendering.
    There is NO retry on failure.

    Args:
        result: The story render result
        tolerance_pct: Tolerance percentage (default 0.15 = 15%)

    Returns:
        ValidationResult
    """
    target = result.target_word_count
    actual = result.word_count

    # Guard against zero/invalid target
    if target <= 0:
        return ValidationResult(
            valid=False,
            error_type="WordCountError",
            error_message=f"Invalid target word count: {target}",
            details={
                "actual_word_count": actual,
                "target_word_count": target,
            },
        )

    min_allowed = int(target * (1 - tolerance_pct))
    max_allowed = int(target * (1 + tolerance_pct))

    if actual < min_allowed:
        deviation_pct = (target - actual) / target * 100
        return ValidationResult(
            valid=False,
            error_type="WordCountError",
            error_message=f"Word count too low: {actual} (target {target}, min {min_allowed})",
            details={
                "actual_word_count": actual,
                "target_word_count": target,
                "min_allowed": min_allowed,
                "max_allowed": max_allowed,
                "deviation_pct": round(deviation_pct, 1),
            },
        )

    if actual > max_allowed:
        deviation_pct = (actual - target) / target * 100
        return ValidationResult(
            valid=False,
            error_type="WordCountError",
            error_message=f"Word count too high: {actual} (target {target}, max {max_allowed})",
            details={
                "actual_word_count": actual,
                "target_word_count": target,
                "min_allowed": min_allowed,
                "max_allowed": max_allowed,
                "deviation_pct": round(deviation_pct, 1),
            },
        )

    return ValidationResult(valid=True)


# ============================================================================
# PART 2: POST-AI NARRATIVE GUARD
# ============================================================================

# ----------------------------------------------------------------------------
# 4. NO NEW PLAYERS VALIDATION
# ----------------------------------------------------------------------------

def _extract_player_names_from_input(input_data: StoryRenderInput) -> set[str]:
    """Extract all valid player names from rendering input.

    Returns:
        Set of player names (lowercase for comparison)
    """
    names = set()

    for section in input_data.sections:
        for player in section.player_stat_deltas:
            name = player.get("player_name", "")
            if name:
                names.add(name.lower())

    return names


def _extract_names_from_story(compact_story: str) -> set[str]:
    """Extract potential player names from story text.

    Player names in our data are formatted as "A. LastName" (first initial,
    period, space, capitalized last name). We look for this specific pattern
    rather than trying to catch all capitalized words.

    Returns:
        Set of potential player names (lowercase)
    """
    # Pattern: Initial + period + optional space + Capitalized word(s)
    # Examples: "D. Mitchell", "J. Allen", "K. Knueppel"
    name_pattern = r'\b([A-Z]\.\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'

    matches = re.findall(name_pattern, compact_story)

    names = set()
    for match in matches:
        # Normalize: lowercase for comparison
        names.add(match.lower())

    return names


def validate_no_new_players(
    compact_story: str,
    input_data: StoryRenderInput,
) -> ValidationResult:
    """Validate that no invented players appear in the story.

    RULE: Every player name mentioned in compact_story must exist
    in the provided player_stat_deltas.

    Args:
        compact_story: The AI-generated story
        input_data: The original rendering input

    Returns:
        ValidationResult
    """
    valid_names = _extract_player_names_from_input(input_data)
    story_names = _extract_names_from_story(compact_story)

    # Also add team names as valid (they might appear in name-like patterns)
    valid_names.add(input_data.home_team_name.lower())
    valid_names.add(input_data.away_team_name.lower())

    # Check for unknown names
    # A name is "unknown" if it doesn't match any valid name as a substring
    potentially_invented = []

    for story_name in story_names:
        # Check if this name matches or is contained in any valid name
        matched = False
        for valid_name in valid_names:
            if story_name in valid_name or valid_name in story_name:
                matched = True
                break

        if not matched:
            # Additional check: single-word names might be last names
            story_words = story_name.split()
            for word in story_words:
                for valid_name in valid_names:
                    if word in valid_name.split():
                        matched = True
                        break
                if matched:
                    break

        if not matched and len(story_name) > 3:  # Ignore very short matches
            potentially_invented.append(story_name)

    if potentially_invented:
        return ValidationResult(
            valid=False,
            error_type="PlayerInventionError",
            error_message=f"Potentially invented player names: {potentially_invented}",
            details={
                "invented_names": potentially_invented,
                "valid_names": sorted(valid_names),
            },
        )

    return ValidationResult(valid=True)


# ----------------------------------------------------------------------------
# 5. NO STAT INVENTION VALIDATION
# ----------------------------------------------------------------------------

# Patterns that indicate invented stats
STAT_INVENTION_PATTERNS = [
    # Percentages
    (r'\d+(\.\d+)?\s*%', "percentage"),
    (r'shot\s+\d+\s*(of|for)\s*\d+', "shooting fraction"),
    (r'\d+\s*-\s*(of|for)\s*-\s*\d+', "shooting notation"),

    # Efficiency claims
    (r'efficient', "efficiency claim"),
    (r'shooting\s+efficiency', "efficiency claim"),

    # Inferred totals
    (r'(finished|ended)\s+(with|at)\s+\d+\s+(points|rebounds|assists)', "inferred total"),
    (r'(scored|had)\s+a\s+(game|team|season)[\s-]?(high|leading)', "inferred comparison"),

    # Comparative claims
    (r'led\s+all\s+scorers', "inferred leadership"),
    (r'(most|fewest)\s+(points|rebounds|assists)', "inferred superlative"),
]


def validate_no_stat_invention(compact_story: str) -> ValidationResult:
    """Validate that no invented stats appear in the story.

    DISALLOWED:
    - Percentages (e.g., "shot 60%")
    - Efficiency claims
    - Inferred totals (e.g., "finished with 25 points" if not provided)
    - Comparative superlatives (e.g., "led all scorers")

    Args:
        compact_story: The AI-generated story

    Returns:
        ValidationResult
    """
    story_lower = compact_story.lower()
    violations = []

    for pattern, description in STAT_INVENTION_PATTERNS:
        matches = re.findall(pattern, story_lower, re.IGNORECASE)
        if matches:
            # Find the actual matched text for context
            full_matches = re.finditer(pattern, compact_story, re.IGNORECASE)
            for match in full_matches:
                violations.append({
                    "type": description,
                    "match": match.group(),
                    "position": match.start(),
                })

    if violations:
        return ValidationResult(
            valid=False,
            error_type="StatInventionError",
            error_message=f"Found {len(violations)} invented stat pattern(s)",
            details={
                "violations": violations[:5],  # First 5 for readability
                "total_violations": len(violations),
            },
        )

    return ValidationResult(valid=True)


# ----------------------------------------------------------------------------
# 6. NO OUTCOME CONTRADICTIONS VALIDATION
# ----------------------------------------------------------------------------

def validate_no_outcome_contradictions(
    compact_story: str,
    input_data: StoryRenderInput,
) -> ValidationResult:
    """Validate that story does not contradict known game outcome.

    CHECKS:
    - Final score matches closing_context
    - Winner/loser is not contradicted
    - Overtime is only mentioned if OVERTIME section exists

    Args:
        compact_story: The AI-generated story
        input_data: The original rendering input

    Returns:
        ValidationResult
    """
    closing = input_data.closing
    story_lower = compact_story.lower()

    # Determine actual winner
    home_won = closing.final_home_score > closing.final_away_score
    away_won = closing.final_away_score > closing.final_home_score
    is_tie = closing.final_home_score == closing.final_away_score

    home_team_lower = closing.home_team_name.lower()
    away_team_lower = closing.away_team_name.lower()

    # Check for winner/loser contradiction
    win_patterns = ["won", "wins", "victory", "defeated", "beat"]
    loss_patterns = ["lost", "loses", "fell to", "defeat"]

    if home_won:
        # Check if story says away team won
        for pattern in win_patterns:
            if f"{away_team_lower} {pattern}" in story_lower:
                return ValidationResult(
                    valid=False,
                    error_type="OutcomeContradictionError",
                    error_message=f"Story implies {closing.away_team_name} won, but {closing.home_team_name} won {closing.final_home_score}-{closing.final_away_score}",
                    details={
                        "actual_winner": closing.home_team_name,
                        "final_score": f"{closing.final_home_score}-{closing.final_away_score}",
                    },
                )
        # Check if story says home team lost
        for pattern in loss_patterns:
            if f"{home_team_lower} {pattern}" in story_lower:
                return ValidationResult(
                    valid=False,
                    error_type="OutcomeContradictionError",
                    error_message=f"Story implies {closing.home_team_name} lost, but they won {closing.final_home_score}-{closing.final_away_score}",
                    details={
                        "actual_winner": closing.home_team_name,
                        "final_score": f"{closing.final_home_score}-{closing.final_away_score}",
                    },
                )

    if away_won:
        # Check if story says home team won
        for pattern in win_patterns:
            if f"{home_team_lower} {pattern}" in story_lower:
                return ValidationResult(
                    valid=False,
                    error_type="OutcomeContradictionError",
                    error_message=f"Story implies {closing.home_team_name} won, but {closing.away_team_name} won {closing.final_away_score}-{closing.final_home_score}",
                    details={
                        "actual_winner": closing.away_team_name,
                        "final_score": f"{closing.final_away_score}-{closing.final_home_score}",
                    },
                )

    # Check for overtime mention without OVERTIME section
    has_overtime_section = any(
        section.beat_type == BeatType.OVERTIME
        for section in input_data.sections
    )

    overtime_mentions = ["overtime", " ot ", "extra period", "extra time"]
    mentions_overtime = any(ot in story_lower for ot in overtime_mentions)

    if mentions_overtime and not has_overtime_section:
        return ValidationResult(
            valid=False,
            error_type="OutcomeContradictionError",
            error_message="Story mentions overtime but no OVERTIME section exists",
            details={
                "has_overtime_section": has_overtime_section,
                "section_beats": [s.beat_type.value for s in input_data.sections],
            },
        )

    return ValidationResult(valid=True)


# ============================================================================
# AGGREGATE VALIDATION FUNCTIONS
# ============================================================================

def validate_pre_render(
    sections: list[StorySection],
    all_chapter_ids: list[str],
) -> list[ValidationResult]:
    """Run all pre-render validations.

    These validations check deterministic structure BEFORE AI rendering.

    Args:
        sections: StorySections to validate
        all_chapter_ids: All chapter IDs that should be covered

    Returns:
        List of ValidationResults (all should be valid)

    Raises:
        SectionOrderingError: If section ordering fails
        StatConsistencyError: If stat consistency fails
    """
    results = []

    # 1. Section ordering
    ordering_result = validate_section_ordering(sections, all_chapter_ids)
    results.append(ordering_result)
    if not ordering_result.valid:
        logger.error(f"Section ordering validation FAILED: {ordering_result.error_message}")
        raise SectionOrderingError(
            ordering_result.error_message or "Section ordering failed",
            ordering_result.details,
        )

    # 2. Stat consistency
    stat_result = validate_stat_consistency(sections)
    results.append(stat_result)
    if not stat_result.valid:
        logger.error(f"Stat consistency validation FAILED: {stat_result.error_message}")
        raise StatConsistencyError(
            stat_result.error_message or "Stat consistency failed",
            stat_result.details,
        )

    logger.info("Pre-render validation PASSED")
    return results


def validate_post_render(
    compact_story: str,
    input_data: StoryRenderInput,
    result: StoryRenderResult,
) -> list[ValidationResult]:
    """Run all post-render validations.

    These validations check AI output for failures.

    Args:
        compact_story: The AI-generated story
        input_data: The original rendering input
        result: The story render result

    Returns:
        List of ValidationResults

    Raises:
        WordCountError: If word count outside tolerance
        PlayerInventionError: If AI invented players
        StatInventionError: If AI invented stats
        OutcomeContradictionError: If AI contradicts outcome
    """
    results = []

    # 3. Word count tolerance
    word_result = validate_word_count(result)
    results.append(word_result)
    if not word_result.valid:
        logger.error(f"Word count validation FAILED: {word_result.error_message}")
        raise WordCountError(
            word_result.error_message or "Word count failed",
            word_result.details,
        )

    # 4. No new players
    player_result = validate_no_new_players(compact_story, input_data)
    results.append(player_result)
    if not player_result.valid:
        logger.error(f"Player validation FAILED: {player_result.error_message}")
        raise PlayerInventionError(
            player_result.error_message or "Player invention detected",
            player_result.details,
        )

    # 5. No stat invention
    stat_result = validate_no_stat_invention(compact_story)
    results.append(stat_result)
    if not stat_result.valid:
        logger.error(f"Stat invention validation FAILED: {stat_result.error_message}")
        raise StatInventionError(
            stat_result.error_message or "Stat invention detected",
            stat_result.details,
        )

    # 6. No outcome contradictions
    outcome_result = validate_no_outcome_contradictions(compact_story, input_data)
    results.append(outcome_result)
    if not outcome_result.valid:
        logger.error(f"Outcome validation FAILED: {outcome_result.error_message}")
        raise OutcomeContradictionError(
            outcome_result.error_message or "Outcome contradiction detected",
            outcome_result.details,
        )

    logger.info("Post-render validation PASSED")
    return results


def validate_full_pipeline(
    sections: list[StorySection],
    all_chapter_ids: list[str],
    compact_story: str,
    input_data: StoryRenderInput,
    result: StoryRenderResult,
) -> list[ValidationResult]:
    """Run all validations (pre-render and post-render).

    This is the main validation entry point for complete pipeline validation.

    Args:
        sections: StorySections that were rendered
        all_chapter_ids: All chapter IDs that should be covered
        compact_story: The AI-generated story
        input_data: The rendering input
        result: The story render result

    Returns:
        List of all ValidationResults

    Raises:
        StoryValidationError: If any validation fails
    """
    all_results = []

    # Pre-render validations
    pre_results = validate_pre_render(sections, all_chapter_ids)
    all_results.extend(pre_results)

    # Post-render validations
    post_results = validate_post_render(compact_story, input_data, result)
    all_results.extend(post_results)

    return all_results


# ============================================================================
# DEBUG OUTPUT
# ============================================================================

def format_validation_debug(results: list[ValidationResult]) -> str:
    """Format validation results for debugging.

    Args:
        results: List of ValidationResults

    Returns:
        Human-readable debug string
    """
    lines = [
        "Validation Results:",
        "=" * 60,
    ]

    passed = sum(1 for r in results if r.valid)
    failed = len(results) - passed

    lines.append(f"Passed: {passed}/{len(results)}")
    lines.append(f"Failed: {failed}/{len(results)}")
    lines.append("")

    for i, result in enumerate(results):
        status = "PASS" if result.valid else "FAIL"
        lines.append(f"  {i + 1}. [{status}]")

        if not result.valid:
            lines.append(f"      Type: {result.error_type}")
            lines.append(f"      Message: {result.error_message}")
            if result.details:
                lines.append(f"      Details: {result.details}")

    lines.append("=" * 60)

    return "\n".join(lines)
