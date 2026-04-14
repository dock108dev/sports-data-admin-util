"""Stage 4: Decision engine and template fallback for Flow content.

Decision thresholds:
- Score >= 70: PUBLISH
- Score 40-69: REGENERATE (max 2 retries with error context)
- Score < 40: FALLBACK to deterministic template

Template fallback produces valid, boring-but-correct summaries
from structured game data without any LLM call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

PUBLISH_THRESHOLD = 70
REGENERATE_THRESHOLD = 40
MAX_RETRIES = 2


class ContentDecision(str, Enum):
    PUBLISH = "PUBLISH"
    REGENERATE = "REGENERATE"
    FALLBACK = "FALLBACK"


@dataclass
class DecisionResult:
    """Result of the content decision engine."""

    decision: ContentDecision
    quality_score: float
    factual_passed: bool
    structural_passed: bool
    retry_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "quality_score": round(self.quality_score, 1),
            "factual_passed": self.factual_passed,
            "structural_passed": self.structural_passed,
            "retry_count": self.retry_count,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def make_decision(
    quality_score: float,
    factual_passed: bool,
    structural_passed: bool,
    retry_count: int = 0,
) -> ContentDecision:
    """Determine whether to publish, regenerate, or fall back.

    Factual or structural failures force regeneration or fallback
    regardless of quality score.
    """
    if not structural_passed:
        if retry_count >= MAX_RETRIES:
            return ContentDecision.FALLBACK
        return ContentDecision.REGENERATE

    if not factual_passed:
        if retry_count >= MAX_RETRIES:
            return ContentDecision.FALLBACK
        return ContentDecision.REGENERATE

    if quality_score >= PUBLISH_THRESHOLD:
        return ContentDecision.PUBLISH

    if quality_score >= REGENERATE_THRESHOLD:
        if retry_count >= MAX_RETRIES:
            return ContentDecision.FALLBACK
        return ContentDecision.REGENERATE

    return ContentDecision.FALLBACK


def run_decision_engine(
    quality_score: float,
    factual_passed: bool,
    structural_passed: bool,
    retry_count: int = 0,
    all_errors: list[str] | None = None,
    all_warnings: list[str] | None = None,
) -> DecisionResult:
    """Run the decision engine and return a full result."""
    decision = make_decision(quality_score, factual_passed, structural_passed, retry_count)

    result = DecisionResult(
        decision=decision,
        quality_score=quality_score,
        factual_passed=factual_passed,
        structural_passed=structural_passed,
        retry_count=retry_count,
        errors=all_errors or [],
        warnings=all_warnings or [],
    )

    logger.info(
        "content_decision_made",
        extra={
            "decision": decision.value,
            "quality_score": round(quality_score, 1),
            "factual_passed": factual_passed,
            "structural_passed": structural_passed,
            "retry_count": retry_count,
        },
    )

    return result


# ============================================================================
# Template fallback: sport-specific deterministic summaries
# ============================================================================

SPORT_TEMPLATES: dict[str, str] = {
    "NBA": (
        "The {winner} defeated the {loser} {winner_score}-{loser_score}. "
        "{top_performer} led the way for {winner_name}. "
        "The game was decided in the {decisive_period}."
    ),
    "NCAAB": (
        "{winner} topped {loser} {winner_score}-{loser_score}. "
        "{top_performer} paced the {winner_name} attack. "
        "The outcome was settled in the {decisive_period}."
    ),
    "NHL": (
        "The {winner} skated past the {loser} {winner_score}-{loser_score}. "
        "{top_performer} made the difference for {winner_name}. "
        "The game was decided in the {decisive_period}."
    ),
    "MLB": (
        "The {winner} beat the {loser} {winner_score}-{loser_score}. "
        "{top_performer} drove the {winner_name} offense. "
        "The game turned in the {decisive_period}."
    ),
}

DEFAULT_TEMPLATE = (
    "The {winner} defeated the {loser} {winner_score}-{loser_score}. "
    "{top_performer} led the way for {winner_name}."
)


def _find_top_performer(blocks: list[dict[str, Any]], sport: str) -> str:
    """Find the top performer from mini_box data across all blocks."""
    best_name = "The team"
    best_value = -1

    stat_key_map: dict[str, str] = {
        "NBA": "pts",
        "NCAAB": "pts",
        "NHL": "goals",
        "MLB": "rbi",
    }
    stat_key = stat_key_map.get(sport, "pts")

    for block in blocks:
        mini_box = block.get("mini_box")
        if not mini_box:
            continue
        for side in ("home", "away"):
            team_data = mini_box.get(side, {})
            for player in team_data.get("players", []):
                val = player.get(stat_key, 0)
                if val > best_value:
                    best_value = val
                    best_name = player.get("name", "The team")

    return best_name


def _determine_decisive_period(blocks: list[dict[str, Any]], sport: str) -> str:
    """Determine which period was most decisive based on score swings."""
    period_labels: dict[str, dict[int, str]] = {
        "NBA": {1: "first quarter", 2: "second quarter", 3: "third quarter", 4: "fourth quarter"},
        "NCAAB": {1: "first half", 2: "second half"},
        "NHL": {1: "first period", 2: "second period", 3: "third period"},
        "MLB": {1: "early innings", 2: "middle innings", 3: "late innings"},
    }
    labels = period_labels.get(sport, {})

    max_swing = 0
    decisive_period = 4

    for block in blocks:
        score_before = block.get("score_before", [0, 0])
        score_after = block.get("score_after", [0, 0])
        swing = abs((score_after[0] - score_before[0]) - (score_after[1] - score_before[1]))
        if swing >= max_swing:
            max_swing = swing
            decisive_period = block.get("period_end", block.get("period_start", 1))

    return labels.get(decisive_period, "late stages")


def generate_template_fallback(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    sport: str,
) -> list[dict[str, Any]]:
    """Generate deterministic template-based content for all blocks.

    Produces valid, boring-but-correct summaries from structured game data.
    No LLM call needed. Returns blocks with replaced narratives.
    """
    if not blocks:
        return blocks

    last_block = blocks[-1]
    score_after = last_block.get("score_after", [0, 0])
    home_score, away_score = score_after[0], score_after[1]

    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")

    if home_score >= away_score:
        winner, loser = home_team, away_team
        winner_score, loser_score = home_score, away_score
    else:
        winner, loser = away_team, home_team
        winner_score, loser_score = away_score, home_score

    top_performer = _find_top_performer(blocks, sport)
    decisive_period = _determine_decisive_period(blocks, sport)

    template = SPORT_TEMPLATES.get(sport, DEFAULT_TEMPLATE)

    summary = template.format(
        winner=winner,
        loser=loser,
        winner_score=winner_score,
        loser_score=loser_score,
        winner_name=winner,
        top_performer=top_performer,
        decisive_period=decisive_period,
    )

    # Distribute the summary across blocks with role-appropriate content
    fallback_blocks = []
    for i, block in enumerate(blocks):
        new_block = dict(block)
        if i == 0:
            new_block["narrative"] = summary
        elif i == len(blocks) - 1:
            new_block["narrative"] = f"Final score: {winner} {winner_score}, {loser} {loser_score}."
        else:
            score_b = block.get("score_before", [0, 0])
            score_a = block.get("score_after", [0, 0])
            new_block["narrative"] = (
                f"{home_team} {score_b[0]}-{score_b[1]} {away_team} "
                f"became {home_team} {score_a[0]}-{score_a[1]} {away_team}."
            )
        fallback_blocks.append(new_block)

    logger.info(
        "template_fallback_generated",
        extra={
            "sport": sport,
            "block_count": len(fallback_blocks),
            "winner": winner,
            "final_score": f"{winner_score}-{loser_score}",
        },
    )

    return fallback_blocks
