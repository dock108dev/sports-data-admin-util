"""Stage 3: Quality scoring for AI-generated narratives.

Computes a composite quality score (0-100) from heuristic signals:
1. Repetition ratio — penalizes repeated n-grams across blocks
2. Vocabulary diversity — type-token ratio of unique words
3. Readability grade — sentence/word length approximation
4. Cliché count — flags overused sports writing phrases
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CLICHE_PHRASES: list[str] = [
    "at the end of the day",
    "gave it their all",
    "left it all on the court",
    "left it all on the field",
    "left it all on the ice",
    "when it mattered most",
    "stepped up big",
    "came up big",
    "put the team on his back",
    "proved why",
    "showed why",
    "rose to the occasion",
    "in crunch time",
    "down the stretch",
    "went on a tear",
    "caught fire",
    "couldn't miss",
    "took over",
    "put on a show",
    "made a statement",
    "sent a message",
    "the rest is history",
    "a tale of two halves",
    "a game of runs",
    "wire to wire",
    "never looked back",
    "flipped the script",
    "sealed the deal",
    "iced the game",
    "slammed the door",
    "weathered the storm",
    "turned the tide",
]

# Weights for composite score (must sum to 1.0)
WEIGHT_REPETITION = 0.25
WEIGHT_VOCABULARY = 0.25
WEIGHT_READABILITY = 0.25
WEIGHT_CLICHE = 0.25


@dataclass
class QualityScoreResult:
    """Result of quality scoring for a set of blocks."""

    composite_score: float
    repetition_score: float
    vocabulary_score: float
    readability_score: float
    cliche_score: float
    cliche_count: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite_score": round(self.composite_score, 1),
            "repetition_score": round(self.repetition_score, 1),
            "vocabulary_score": round(self.vocabulary_score, 1),
            "readability_score": round(self.readability_score, 1),
            "cliche_score": round(self.cliche_score, 1),
            "cliche_count": self.cliche_count,
            "details": self.details,
        }


def _compute_repetition_score(narratives: list[str]) -> tuple[float, dict[str, Any]]:
    """Score 0-100 based on n-gram repetition across blocks.

    Lower repetition = higher score.
    Checks bigrams and trigrams across all narratives combined.
    """
    if not narratives:
        return 100.0, {"bigram_repeat_ratio": 0, "trigram_repeat_ratio": 0}

    all_words: list[str] = []
    for text in narratives:
        words = re.findall(r"\b[a-z]+\b", text.lower())
        all_words.extend(words)

    if len(all_words) < 4:
        return 100.0, {"bigram_repeat_ratio": 0, "trigram_repeat_ratio": 0}

    bigrams = [f"{all_words[i]} {all_words[i + 1]}" for i in range(len(all_words) - 1)]
    trigrams = [
        f"{all_words[i]} {all_words[i + 1]} {all_words[i + 2]}" for i in range(len(all_words) - 2)
    ]

    bigram_counts = Counter(bigrams)
    trigram_counts = Counter(trigrams)

    repeated_bigrams = sum(c - 1 for c in bigram_counts.values() if c > 1)
    repeated_trigrams = sum(c - 1 for c in trigram_counts.values() if c > 1)

    bigram_ratio = repeated_bigrams / len(bigrams) if bigrams else 0
    trigram_ratio = repeated_trigrams / len(trigrams) if trigrams else 0

    combined_ratio = (bigram_ratio * 0.4) + (trigram_ratio * 0.6)
    score = max(0, 100 - (combined_ratio * 500))

    return score, {
        "bigram_repeat_ratio": round(bigram_ratio, 3),
        "trigram_repeat_ratio": round(trigram_ratio, 3),
    }


def _compute_vocabulary_score(narratives: list[str]) -> tuple[float, dict[str, Any]]:
    """Score 0-100 based on vocabulary diversity (type-token ratio).

    Higher diversity = higher score.
    """
    if not narratives:
        return 100.0, {"type_token_ratio": 1.0, "unique_words": 0, "total_words": 0}

    all_words: list[str] = []
    for text in narratives:
        words = re.findall(r"\b[a-z]+\b", text.lower())
        all_words.extend(words)

    total = len(all_words)
    if total == 0:
        return 100.0, {"type_token_ratio": 1.0, "unique_words": 0, "total_words": 0}

    unique = len(set(all_words))
    ttr = unique / total

    # TTR naturally decreases with text length; normalize via log-corrected TTR
    # Corrected TTR = unique / log2(total) for fairer comparison across lengths
    corrected_ttr = unique / math.log2(total) if total > 1 else 1.0
    # Normalize: typical sports text corrected TTR is 3-15
    score = min(100, max(0, (corrected_ttr - 2) / 12 * 100))

    return score, {
        "type_token_ratio": round(ttr, 3),
        "corrected_ttr": round(corrected_ttr, 1),
        "unique_words": unique,
        "total_words": total,
    }


def _compute_readability_score(narratives: list[str]) -> tuple[float, dict[str, Any]]:
    """Score 0-100 based on readability (Automated Readability Index).

    Target: grade level 8-12 for sports writing. Too simple or too complex
    both reduce the score.
    """
    if not narratives:
        return 100.0, {"avg_sentence_len": 0, "avg_word_len": 0, "ari": 0}

    combined = " ".join(narratives)
    sentences = [s.strip() for s in re.split(r"[.!?]+", combined) if s.strip()]
    words = combined.split()
    chars = sum(len(w) for w in words)

    num_sentences = max(len(sentences), 1)
    num_words = max(len(words), 1)

    avg_sentence_len = num_words / num_sentences
    avg_word_len = chars / num_words

    # Automated Readability Index
    ari = 4.71 * avg_word_len + 0.5 * avg_sentence_len - 21.43

    # Ideal range: grade 8-12
    if 8 <= ari <= 12:
        score = 100.0
    elif ari < 8:
        score = max(0, 100 - (8 - ari) * 15)
    else:
        score = max(0, 100 - (ari - 12) * 15)

    return score, {
        "avg_sentence_len": round(avg_sentence_len, 1),
        "avg_word_len": round(avg_word_len, 1),
        "ari": round(ari, 1),
    }


def _compute_cliche_score(narratives: list[str]) -> tuple[float, int, dict[str, Any]]:
    """Score 0-100 based on cliché usage. Fewer clichés = higher score.

    Returns (score, cliche_count, details).
    """
    if not narratives:
        return 100.0, 0, {"cliches_found": []}

    combined = " ".join(narratives).lower()
    found: list[str] = []

    for phrase in CLICHE_PHRASES:
        count = combined.count(phrase)
        for _ in range(count):
            found.append(phrase)

    cliche_count = len(found)
    # Each cliché reduces score by 15 points
    score = max(0, 100 - cliche_count * 15)

    return score, cliche_count, {"cliches_found": found[:10]}


def compute_quality_score(
    blocks: list[dict[str, Any]],
) -> QualityScoreResult:
    """Compute composite quality score (0-100) for narrative blocks.

    Combines four heuristic subscores:
    - Repetition (25%): penalizes repeated n-grams
    - Vocabulary diversity (25%): rewards varied word choice
    - Readability (25%): targets grade 8-12 reading level
    - Cliché count (25%): penalizes overused phrases
    """
    narratives = [block.get("narrative", "") for block in blocks if block.get("narrative")]

    rep_score, rep_details = _compute_repetition_score(narratives)
    vocab_score, vocab_details = _compute_vocabulary_score(narratives)
    read_score, read_details = _compute_readability_score(narratives)
    cliche_score, cliche_count, cliche_details = _compute_cliche_score(narratives)

    composite = (
        rep_score * WEIGHT_REPETITION
        + vocab_score * WEIGHT_VOCABULARY
        + read_score * WEIGHT_READABILITY
        + cliche_score * WEIGHT_CLICHE
    )

    result = QualityScoreResult(
        composite_score=composite,
        repetition_score=rep_score,
        vocabulary_score=vocab_score,
        readability_score=read_score,
        cliche_score=cliche_score,
        cliche_count=cliche_count,
        details={
            "repetition": rep_details,
            "vocabulary": vocab_details,
            "readability": read_details,
            "cliche": cliche_details,
        },
    )

    logger.info(
        "quality_scoring_complete",
        extra={
            "composite_score": round(composite, 1),
            "repetition_score": round(rep_score, 1),
            "vocabulary_score": round(vocab_score, 1),
            "readability_score": round(read_score, 1),
            "cliche_score": round(cliche_score, 1),
            "cliche_count": cliche_count,
        },
    )

    return result
