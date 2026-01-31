"""Sentence style validation for narrative rendering.

This module validates narrative prose quality and detects style violations
such as repetitive patterns, metric-first sentences, and uniform structure.
"""

from __future__ import annotations

import re
from typing import Any

from .narrative_types import StyleViolationType


def split_into_sentences(text: str | None) -> list[str]:
    """Split text into sentences, handling common abbreviations.

    Args:
        text: Input text to split

    Returns:
        List of sentence strings (non-empty)
    """
    if not text or not text.strip():
        return []

    # Handle common abbreviations that shouldn't split
    # Temporarily replace periods in abbreviations
    protected = text
    abbreviations = [
        "vs.", "Mr.", "Mrs.", "Dr.", "Jr.", "Sr.", "No.",
        "St.", "Rd.", "Ave.", "Blvd.", "Mt.", "Ft.",
    ]
    for abbr in abbreviations:
        protected = protected.replace(abbr, abbr.replace(".", "<DOT>"))

    # Split on sentence-ending punctuation
    # Handles: period, exclamation, question mark followed by space or end
    raw_sentences = re.split(r"(?<=[.!?])\s+", protected)

    # Restore abbreviation periods and filter empty
    sentences = []
    for s in raw_sentences:
        restored = s.replace("<DOT>", ".").strip()
        if restored:
            sentences.append(restored)

    return sentences


def get_sentence_opener(sentence: str, word_count: int = 3) -> str:
    """Get the opening words of a sentence for comparison.

    Args:
        sentence: The sentence to analyze
        word_count: Number of opening words to extract

    Returns:
        Lowercase opener string for comparison
    """
    words = sentence.split()[:word_count]
    return " ".join(words).lower()


def check_sentence_length_variance(sentences: list[str]) -> tuple[bool, float]:
    """Check if sentences have sufficient length variance.

    Returns True if there is good variance, False if too uniform.

    Args:
        sentences: List of sentences to analyze

    Returns:
        Tuple of (has_variance, variance_score)
    """
    if len(sentences) <= 1:
        return True, 1.0

    # Calculate word counts
    lengths = [len(s.split()) for s in sentences]
    mean_length = sum(lengths) / len(lengths)

    if mean_length == 0:
        return True, 1.0

    # Calculate coefficient of variation (std dev / mean)
    variance = sum((slen - mean_length) ** 2 for slen in lengths) / len(lengths)
    std_dev = variance ** 0.5
    cv = std_dev / mean_length

    # Check for extremely uniform lengths (all within 15% of mean AND all same length)
    # Only flag if ALL sentences are nearly identical length
    uniform = all(abs(slen - mean_length) / max(mean_length, 1) < 0.15 for slen in lengths)

    # Check if min/max range is very small for 3+ sentences
    length_range = max(lengths) - min(lengths)
    very_narrow_range = length_range <= 2  # 2 or fewer words difference

    # Only fail if extremely uniform AND narrow range AND 3+ sentences
    if uniform and very_narrow_range and len(sentences) >= 3:
        return False, cv

    return True, cv


def check_repeated_openers(sentences: list[str]) -> list[str]:
    """Check for repeated sentence openers.

    Returns list of openers that appear 2+ times.

    Args:
        sentences: List of sentences to analyze

    Returns:
        List of repeated opener strings
    """
    if len(sentences) <= 1:
        return []

    openers = [get_sentence_opener(s) for s in sentences]
    opener_counts: dict[str, int] = {}
    for opener in openers:
        opener_counts[opener] = opener_counts.get(opener, 0) + 1

    # Return openers that appear 2+ times
    return [opener for opener, count in opener_counts.items() if count >= 2]


def check_metric_first_sentences(sentences: list[str]) -> list[str]:
    """Check for sentences that lead with statistics/metrics.

    Returns sentences that start with metrics rather than actions.

    Args:
        sentences: List of sentences to analyze

    Returns:
        List of metric-first sentences
    """
    metric_patterns = [
        # "X scored 12 points" - number after name
        r"^\w+\s+\w*\s*\d+\s+(points?|rebounds?|assists?)",
        # "The team shot 4-of-5" - shooting stats
        r"^\w+\s+\w*\s*shot\s+\d+-",
        # "With 15 points, ..." - metric-first construction
        r"^with\s+\d+\s+(points?|rebounds?|assists?)",
        # "X went 3-for-4" - shooting line
        r"^\w+\s+went\s+\d+-for-\d+",
    ]

    metric_first = []
    for sentence in sentences:
        for pattern in metric_patterns:
            if re.match(pattern, sentence, re.IGNORECASE):
                metric_first.append(sentence)
                break

    return metric_first


def check_template_repetition(sentences: list[str]) -> bool:
    """Check if sentences follow the same template pattern.

    Detects patterns like "X scored on a Y" repeated multiple times.

    Args:
        sentences: List of sentences to analyze

    Returns:
        True if template repetition detected
    """
    if len(sentences) < 3:
        return False

    # Check for common repetitive patterns
    patterns = [
        r"^\w+\s+scored\s+on\s+a",  # "X scored on a layup/dunk/three"
        r"^\w+\s+made\s+a",  # "X made a shot/three/layup"
        r"^\w+\s+hit\s+a",  # "X hit a three/jumper"
        r"^the\s+\w+\s+scored",  # "The Lakers scored..."
        r"^the\s+\w+\s+answered",  # "The Lakers answered..."
    ]

    # Count how many sentences match each pattern
    for pattern in patterns:
        matches = sum(1 for s in sentences if re.match(pattern, s, re.IGNORECASE))
        # If 3+ sentences match the same pattern, it's repetitive
        if matches >= 3:
            return True

    return False


def validate_narrative_style(
    narrative: str, moment_index: int
) -> tuple[list[str], list[dict[str, Any]]]:
    """Validate narrative style and detect violations.

    Style violations are soft warnings (not failures) to track AI prose quality.
    Returns structured details for analytics and debugging.

    Args:
        narrative: The narrative text to validate
        moment_index: Index of the moment (for logging)

    Returns:
        Tuple of (warning_messages, style_details)
    """
    warnings: list[str] = []
    details: list[dict[str, Any]] = []

    if not narrative or not narrative.strip():
        return warnings, details

    sentences = split_into_sentences(narrative)

    # Skip style validation for very short narratives (1-2 sentences)
    if len(sentences) <= 2:
        return warnings, details

    # Check 1: Sentence length variance
    has_variance, variance_score = check_sentence_length_variance(sentences)
    if not has_variance:
        msg = f"Moment {moment_index}: Uniform sentence lengths (cv={variance_score:.2f})"
        warnings.append(msg)
        details.append({
            "moment_index": moment_index,
            "violation_type": StyleViolationType.UNIFORM_LENGTH.value,
            "score": variance_score,
        })

    # Check 2: Repeated openers
    repeated = check_repeated_openers(sentences)
    if repeated:
        msg = f"Moment {moment_index}: Repeated openers: {repeated}"
        warnings.append(msg)
        details.append({
            "moment_index": moment_index,
            "violation_type": StyleViolationType.REPEATED_OPENER.value,
            "openers": repeated,
        })

    # Check 3: Metric-first sentences
    metric_first = check_metric_first_sentences(sentences)
    if len(metric_first) >= 2:  # Only warn if 2+ metric-first sentences
        msg = f"Moment {moment_index}: Metric-first sentences detected"
        warnings.append(msg)
        details.append({
            "moment_index": moment_index,
            "violation_type": StyleViolationType.METRIC_FIRST.value,
            "count": len(metric_first),
        })

    # Check 4: Template repetition
    if check_template_repetition(sentences):
        msg = f"Moment {moment_index}: Template repetition detected"
        warnings.append(msg)
        details.append({
            "moment_index": moment_index,
            "violation_type": StyleViolationType.TEMPLATE_REPETITION.value,
        })

    return warnings, details
