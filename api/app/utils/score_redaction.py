"""Utilities for detecting and redacting score-like content."""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

_SCORE_PATTERNS = [
    re.compile(r"\b\d{1,3}\s*[-–—:]\s*\d{1,3}\b"),
    re.compile(r"\b\d{1,3}\s*(?:to|at)\s*\d{1,3}\b", re.IGNORECASE),
]

_WHITESPACE_PATTERN = re.compile(r"\s+")


def contains_explicit_score(text: str | None) -> bool:
    """Return True if the text contains an explicit score pattern."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in _SCORE_PATTERNS)


def redact_scores(text: str, mask: str = "") -> str:
    """Remove or mask score-like patterns in text."""
    if not text:
        return text
    cleaned = text
    redaction_count = 0
    for pattern in _SCORE_PATTERNS:
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
