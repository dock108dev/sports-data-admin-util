"""
Reveal and score detection utilities for social posts and game summaries.

This module provides two primary capabilities:
1. Classification: Detecting if text contains game outcome reveals.
2. Redaction: Removing score-like patterns from text.
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Classification Patterns (from reveal_filter)
# ----------------------------------------------------------------------------

SCORE_PATTERNS = [
    re.compile(r"\b\d{2,3}\s*[-–—]\s*\d{2,3}\b"),
    re.compile(r"\b[WL]\s*\d{2,3}\s*[-–—]\s*\d{2,3}\b", re.I),
    re.compile(r"final\s*:?\s*\d{2,3}\s*[-–—]\s*\d{2,3}", re.I),
]

FINAL_KEYWORDS = [
    re.compile(r"\bfinal\b", re.I),
    re.compile(r"\bfinal score\b", re.I),
    re.compile(r"\bend of (game|regulation)\b", re.I),
    re.compile(r"\bgame over\b", re.I),
    re.compile(r"\bwe win\b", re.I),
    re.compile(r"\bwe lose\b", re.I),
    re.compile(r"\bvictory\b", re.I),
    re.compile(r"\bdefeat\b", re.I),
    re.compile(r"\bwin streak\b", re.I),
    re.compile(r"\blose streak\b", re.I),
]

RECAP_PATTERNS = [
    re.compile(r"\brecap\b", re.I),
    re.compile(r"\bgame recap\b", re.I),
    re.compile(r"\bpost-?game\b", re.I),
    re.compile(r"\bfull (game )?highlights\b", re.I),
    re.compile(r"\bgame summary\b", re.I),
]

SAFE_PATTERNS = [
    re.compile(r"\blineup\b", re.I),
    re.compile(r"\bstarting (five|lineup)\b", re.I),
    re.compile(r"\binjury update\b", re.I),
    re.compile(r"\bstatus update\b", re.I),
    re.compile(r"\bwe'?re underway\b", re.I),
    re.compile(r"\bgame time\b", re.I),
    re.compile(r"\btip-?off\b", re.I),
    re.compile(r"\bwarm-?ups\b", re.I),
]

SCORE_EMOJI_PATTERN = re.compile(r"[🏆✅🎉🚨]")

# ----------------------------------------------------------------------------
# Redaction Patterns (from score_redaction)
# ----------------------------------------------------------------------------

_REDACTION_SCORE_PATTERNS = [
    re.compile(r"\b\d{1,3}\s*[-–—:]\s*\d{1,3}\b"),
    re.compile(r"\b\d{1,3}\s*(?:to|at)\s*\d{1,3}\b", re.IGNORECASE),
]

_WHITESPACE_PATTERN = re.compile(r"\s+")


class RevealCheckResult(NamedTuple):
    reveals_outcome: bool
    reason: str | None = None
    matched_pattern: str | None = None


class RevealClassification(NamedTuple):
    reveal_risk: bool
    reason: str | None = None
    matched_pattern: str | None = None


# ----------------------------------------------------------------------------
# Classification Logic
# ----------------------------------------------------------------------------

def check_for_reveals(text: str) -> RevealCheckResult:
    """Check if text contains definitive game outcome reveals."""
    if not text:
        return RevealCheckResult(False)

    for pattern in SCORE_PATTERNS:
        if pattern.search(text):
            return RevealCheckResult(True, "score", pattern.pattern)

    for pattern in FINAL_KEYWORDS:
        if pattern.search(text):
            return RevealCheckResult(True, "final_keyword", pattern.pattern)

    for pattern in RECAP_PATTERNS:
        if pattern.search(text):
            return RevealCheckResult(True, "recap", pattern.pattern)

    return RevealCheckResult(False)


def classify_reveal_risk(text: str | None) -> RevealClassification:
    """Classify reveal risk conservatively (defaults to risk=True)."""
    if not text:
        return RevealClassification(True, reason="default_no_text")

    reveal_result = check_for_reveals(text)
    if reveal_result.reveals_outcome:
        return RevealClassification(True, reveal_result.reason, reveal_result.matched_pattern)

    if SCORE_EMOJI_PATTERN.search(text):
        return RevealClassification(True, reason="score_emoji", matched_pattern=SCORE_EMOJI_PATTERN.pattern)

    for pattern in SAFE_PATTERNS:
        if pattern.search(text):
            return RevealClassification(False, reason="safe_pattern", matched_pattern=pattern.pattern)

    return RevealClassification(True, reason="default_conservative")


# ----------------------------------------------------------------------------
# Redaction Logic
# ----------------------------------------------------------------------------

def contains_explicit_score(text: str | None) -> bool:
    """Return True if the text contains an explicit score pattern."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in _REDACTION_SCORE_PATTERNS)


def redact_scores(text: str, mask: str = "") -> str:
    """Remove or mask score-like patterns in text."""
    if not text:
        return text
    cleaned = text
    redaction_count = 0
    for pattern in _REDACTION_SCORE_PATTERNS:
        cleaned, count = pattern.subn(mask, cleaned)
        redaction_count += count
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    if redaction_count:
        logger.info(
            "score_redaction_applied",
            extra={
                "redaction_count": redaction_count,
                "original_length": len(text),
                "redacted_length": len(cleaned),
            },
        )
    return cleaned
