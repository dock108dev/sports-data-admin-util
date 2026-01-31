"""Play coverage validation and deterministic sentence injection.

This module validates that narratives properly reference explicit plays
and injects deterministic sentences when AI output is insufficient.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .narrative_types import CoverageResolution, FORBIDDEN_PATTERNS
from .style_validation import split_into_sentences, validate_narrative_style

logger = logging.getLogger(__name__)


def count_sentences(text: str) -> int:
    """Count the number of sentences in text.

    Uses simple heuristic: count sentence-ending punctuation.

    Args:
        text: Input text

    Returns:
        Number of sentences
    """
    if not text:
        return 0
    # Count sentence-ending punctuation followed by space or end
    # Handles: . ! ? and their combinations with quotes
    return len(re.findall(r'[.!?]["\']?\s*(?=[A-Z]|$)', text.strip()))


def extract_play_identifiers(play: dict[str, Any]) -> list[str]:
    """Extract identifiable tokens from a play for matching.

    Extracts player names, action verbs, and key nouns that would
    appear in a narrative referencing this play.

    Args:
        play: PBP play data

    Returns:
        List of lowercase identifier tokens
    """
    identifiers = []

    # Player name (if present)
    player_name = play.get("player_name", "")
    if player_name:
        # Add full name and last name
        identifiers.append(player_name.lower())
        parts = player_name.split()
        if len(parts) > 1:
            identifiers.append(parts[-1].lower())  # Last name

    # Description tokens
    description = play.get("description", "")
    if description:
        # Extract key action words
        desc_lower = description.lower()

        # Scoring plays
        if "three" in desc_lower or "3-pt" in desc_lower or "3pt" in desc_lower:
            identifiers.extend(["three", "three-pointer", "3-pointer"])
        if "layup" in desc_lower:
            identifiers.append("layup")
        if "dunk" in desc_lower:
            identifiers.append("dunk")
        if "free throw" in desc_lower:
            identifiers.extend(["free throw", "free-throw", "foul shot"])
        if "jumper" in desc_lower or "jump shot" in desc_lower:
            identifiers.extend(["jumper", "jump shot", "shot"])

        # Non-scoring plays
        if "rebound" in desc_lower:
            identifiers.append("rebound")
        if "turnover" in desc_lower:
            identifiers.append("turnover")
        if "steal" in desc_lower:
            identifiers.append("steal")
        if "block" in desc_lower:
            identifiers.append("block")
        if "foul" in desc_lower:
            identifiers.append("foul")
        if "assist" in desc_lower:
            identifiers.append("assist")

    return identifiers


def check_explicit_play_coverage(
    narrative: str,
    explicit_play_ids: set[int],
    moment_plays: list[dict[str, Any]],
) -> tuple[bool, set[int], set[int]]:
    """Check if narrative covers all explicitly narrated plays.

    A play is considered "covered" if any of its identifiers appear
    in the narrative text.

    Args:
        narrative: The narrative text
        explicit_play_ids: Set of play_index values that must be covered
        moment_plays: All plays in the moment

    Returns:
        Tuple of (all_covered, covered_ids, missing_ids)
    """
    if not explicit_play_ids:
        return True, set(), set()

    narrative_lower = narrative.lower()
    covered_ids: set[int] = set()
    missing_ids: set[int] = set()

    for play in moment_plays:
        play_index = play.get("play_index")
        if play_index not in explicit_play_ids:
            continue

        identifiers = extract_play_identifiers(play)

        # Check if any identifier appears in narrative
        found = any(ident in narrative_lower for ident in identifiers)

        if found:
            covered_ids.add(play_index)
        else:
            missing_ids.add(play_index)

    all_covered = len(missing_ids) == 0
    return all_covered, covered_ids, missing_ids


def generate_deterministic_sentence(
    play: dict[str, Any],
    game_context: dict[str, str],
) -> str:
    """Generate a deterministic sentence describing a play.

    Used when AI fails to reference an explicit play - ensures
    traceability by adding a minimal, factual sentence.

    Args:
        play: The PBP play data
        game_context: Team names for context

    Returns:
        A deterministic sentence describing the play
    """
    # Extract play data
    player_name = play.get("player_name", "")
    description = play.get("description", "")
    team_abbrev = play.get("team_abbreviation", "")

    # Get team names from context
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")

    # Determine which team the player is on
    team_name = ""
    if team_abbrev:
        if team_abbrev.upper() in home_team.upper():
            team_name = home_team
        elif team_abbrev.upper() in away_team.upper():
            team_name = away_team
        else:
            team_name = team_abbrev

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
        if player_name:
            return f"{player_name} hit a jumper."
        return f"{team_name or 'The team'} made a shot."

    # Non-scoring plays
    if "rebound" in desc_lower:
        if "offensive" in desc_lower:
            if player_name:
                return f"{player_name} grabbed an offensive rebound."
            return f"{team_name or 'The team'} secured an offensive rebound."
        if player_name:
            return f"{player_name} pulled down the rebound."
        return f"{team_name or 'The team'} got the rebound."

    if "turnover" in desc_lower:
        if player_name:
            return f"{player_name} committed a turnover."
        return f"{team_name or 'The team'} turned it over."

    if "steal" in desc_lower:
        if player_name:
            return f"{player_name} came up with a steal."
        return f"{team_name or 'The team'} got a steal."

    if "block" in desc_lower:
        if player_name:
            return f"{player_name} blocked the shot."
        return "The shot was blocked."

    if "foul" in desc_lower:
        if player_name:
            return f"{player_name} was called for a foul."
        return "A foul was called."

    # Generic fallback
    if player_name:
        return f"{player_name} was involved in the play."
    if team_name:
        return f"{team_name} made a play."
    return "Play continued."


def inject_missing_explicit_plays(
    narrative: str,
    missing_play_ids: set[int],
    moment_plays: list[dict[str, Any]],
    game_context: dict[str, str],
) -> str:
    """Inject deterministic sentences for missing explicit plays.

    Appends minimal factual sentences to ensure all explicit plays
    are covered in the narrative.

    Args:
        narrative: The original narrative
        missing_play_ids: Play indices not covered by narrative
        moment_plays: All plays in the moment
        game_context: Team names for sentence generation

    Returns:
        Enhanced narrative with injected sentences
    """
    if not missing_play_ids:
        return narrative

    # Build lookup
    play_lookup = {p.get("play_index"): p for p in moment_plays}

    # Generate sentences for missing plays (in play_index order)
    injected_sentences = []
    for play_id in sorted(missing_play_ids):
        play = play_lookup.get(play_id)
        if play:
            sentence = generate_deterministic_sentence(play, game_context)
            injected_sentences.append(sentence)

    if not injected_sentences:
        return narrative

    # Append to narrative
    enhanced = narrative.rstrip()
    if not enhanced.endswith((".", "!", "?")):
        enhanced += "."
    enhanced += " " + " ".join(injected_sentences)

    return enhanced


def log_coverage_resolution(
    moment_index: int,
    resolution: CoverageResolution,
    original_coverage: tuple[bool, set[int], set[int]],
    final_coverage: tuple[bool, set[int], set[int]] | None = None,
) -> None:
    """Log the resolution of explicit play coverage.

    Args:
        moment_index: Index of the moment
        resolution: How coverage was achieved
        original_coverage: Initial (all_covered, covered, missing) tuple
        final_coverage: Final coverage after resolution (if injection used)
    """
    all_covered, covered, missing = original_coverage

    if resolution == CoverageResolution.INITIAL_PASS:
        logger.debug(
            f"Moment {moment_index}: Coverage OK on initial pass "
            f"(covered {len(covered)} explicit plays)"
        )
    elif resolution == CoverageResolution.REGENERATION_PASS:
        logger.info(
            f"Moment {moment_index}: Coverage OK after regeneration "
            f"(covered {len(covered)} explicit plays)"
        )
    elif resolution == CoverageResolution.INJECTION_REQUIRED:
        if final_coverage:
            _, final_covered, final_missing = final_coverage
            logger.warning(
                f"Moment {moment_index}: Required injection for {len(missing)} plays. "
                f"Originally covered: {covered}, injected: {missing}"
            )
        else:
            logger.warning(
                f"Moment {moment_index}: Injection attempted for {len(missing)} plays"
            )


def validate_narrative(
    narrative: str,
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    moment_index: int,
    check_style: bool = True,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Validate a narrative against story contract rules.

    Returns hard errors (fail the moment), soft errors (warnings),
    and style details for analytics.

    Args:
        narrative: The narrative text to validate
        moment: The moment data
        moment_plays: PBP events for the moment
        moment_index: Index for logging
        check_style: Whether to run style validation

    Returns:
        Tuple of (hard_errors, soft_errors, style_details)
    """
    hard_errors: list[str] = []
    soft_errors: list[str] = []
    style_details: list[dict[str, Any]] = []

    # Hard validation: narrative must exist
    if not narrative or not narrative.strip():
        hard_errors.append(f"Moment {moment_index}: Empty narrative")
        return hard_errors, soft_errors, style_details

    # Soft validation: sentence count (2-4 preferred)
    sentences = split_into_sentences(narrative)
    sentence_count = len(sentences)
    if sentence_count < 2:
        soft_errors.append(
            f"Moment {moment_index}: Only {sentence_count} sentence(s), expected 2-4"
        )
    elif sentence_count > 5:
        soft_errors.append(
            f"Moment {moment_index}: {sentence_count} sentences, expected 2-4"
        )

    # Hard validation: forbidden language
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(narrative):
            hard_errors.append(
                f"Moment {moment_index}: Forbidden language detected: {pattern.pattern}"
            )
            break  # One forbidden phrase is enough to fail

    # Soft validation: explicit play coverage
    explicit_ids = set(moment.get("explicitly_narrated_play_ids", []))
    if explicit_ids:
        all_covered, covered, missing = check_explicit_play_coverage(
            narrative, explicit_ids, moment_plays
        )
        if not all_covered:
            soft_errors.append(
                f"Moment {moment_index}: Missing explicit plays: {missing}"
            )

    # Style validation (soft, for tracking)
    if check_style:
        style_warnings, details = validate_narrative_style(narrative, moment_index)
        soft_errors.extend(style_warnings)
        style_details.extend(details)

    return hard_errors, soft_errors, style_details
