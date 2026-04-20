"""Load and expose the versioned generic-phrase list for the tier-1 grader.

The phrase data lives in generic_phrases.toml (same directory). The Python module
is a thin loader; all phrase additions must go in the TOML, not here.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

_PHRASES_FILE = Path(__file__).parent / "generic_phrases.toml"


def _load() -> tuple[list[str], float, float]:
    """Parse the TOML file and return (phrases, phrase_weight, density_threshold)."""
    with open(_PHRASES_FILE, "rb") as f:
        data = tomllib.load(f)

    config = data.get("config", {})
    weight = float(config.get("phrase_weight", 3.0))
    density_threshold = float(config.get("density_threshold", 2.0))

    phrases: list[str] = []
    phrases_section = data.get("phrases", {})
    for val in phrases_section.values():
        if isinstance(val, list):
            phrases.extend(str(p).lower() for p in val)

    return phrases, weight, density_threshold


# Loaded once at import time; mutations require a process restart.
GENERIC_PHRASES: list[str]
GENERIC_PHRASE_WEIGHT: float
DENSITY_THRESHOLD: float
GENERIC_PHRASES, GENERIC_PHRASE_WEIGHT, DENSITY_THRESHOLD = _load()


def detect_per_block(text: str) -> list[str]:
    """Return every generic phrase found in text (case-insensitive, in order).

    Performs a simple substring scan against all known phrases. The text is
    lowercased once; phrase list is pre-lowercased at import time. This runs
    across sentence boundaries naturally because we match on the full block text.
    """
    lower = text.lower()
    return [p for p in GENERIC_PHRASES if p in lower]


def phrase_density(text: str) -> float:
    """Return matched generic phrases per 100 words of text.

    Returns 0.0 for empty text.
    """
    word_count = len(text.split())
    if word_count == 0:
        return 0.0
    return (len(detect_per_block(text)) / word_count) * 100
