"""Stage 2: Factual validation for AI-generated narratives.

Extracts stat claims from generated text and verifies them against
actual game data. Detects training-data bleed (season averages,
injury claims, historical streaks not in context).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Sport-specific stat patterns: (regex, stat_key, sport_codes)
# Each pattern captures player_name (group 1) and stat_value (group 2)
STAT_CLAIM_PATTERNS: list[tuple[str, str, set[str]]] = [
    # Basketball: "Player scored 25 points" / "Player's 25 points"
    (r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b[''`]?s?\s+(\d+)\s+points?", "pts", {"NBA", "NCAAB"}),
    (r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+scored\s+(\d+)", "pts", {"NBA", "NCAAB"}),
    (
        r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+(?:had|added|contributed)\s+(\d+)\s+(?:assists?|dimes?)",
        "ast",
        {"NBA", "NCAAB"},
    ),
    (
        r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+(?:grabbed|pulled down|had)\s+(\d+)\s+rebounds?",
        "reb",
        {"NBA", "NCAAB"},
    ),
    (
        r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+(?:hit|made|drained|knocked down)\s+(\d+)\s+three",
        "3pm",
        {"NBA", "NCAAB"},
    ),
    # Hockey: "Player scored 2 goals" / "Player had 3 assists"
    (r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+scored\s+(\d+)\s+goals?", "goals", {"NHL"}),
    (
        r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+(?:had|added|contributed)\s+(\d+)\s+assists?",
        "assists",
        {"NHL"},
    ),
    (r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+made\s+(\d+)\s+saves?", "saves", {"NHL"}),
    # Baseball: "Player went 3-for-4" / "Player drove in 2 runs"
    (
        r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+(?:drove in|knocked in|plated)\s+(\d+)\s+runs?",
        "rbi",
        {"MLB"},
    ),
    (
        r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+(?:hit|belted|launched|smashed)\s+(\d+)\s+(?:home runs?|homers?)",
        "hr",
        {"MLB"},
    ),
    (r"(\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+went\s+(\d+)-for-\d+", "hits", {"MLB"}),
    # Generic score claims: "led 85-72" / "trailed 45-50"
    (r"(\d+)-(\d+)\s+(?:lead|advantage|deficit|margin)", "_score", set()),
]

# Patterns indicating training-data bleed
TRAINING_DATA_BLEED_PATTERNS: list[tuple[str, str]] = [
    (r"\bseason\s+averag", "season average reference"),
    (r"\baveraging\s+\d+\.?\d*\s+(?:points|rebounds|assists|goals)", "season average stat"),
    (r"\bcareer[\s-]+high", "career stat reference"),
    (r"\bcareer[\s-]+best", "career stat reference"),
    (r"\binjur(?:y|ed|ies)", "injury reference"),
    (r"\bday-to-day\b", "injury status reference"),
    (r"\bquestionable\b", "injury status reference"),
    (r"\bout\s+(?:for|with|due)", "injury status reference"),
    (r"\b(?:winning|losing|hitting)\s+streak", "streak reference"),
    (r"\bconsecutive\s+(?:games?|wins?|losses?)", "streak reference"),
    (
        r"\blast\s+(?:\d+|five|ten|three|four|six|seven|eight|nine)\s+games?",
        "recent games reference",
    ),
    (r"\bthis\s+season\b", "season context reference"),
    (r"\bon\s+the\s+(?:season|year)\b", "season context reference"),
    (r"\bAll-Star\b", "accolade reference"),
    (r"\bMVP\b", "accolade reference"),
    (r"\brookie\s+of\s+the\s+year\b", "accolade reference"),
]


@dataclass
class StatClaim:
    """A stat claim extracted from narrative text."""

    player_name: str
    stat_key: str
    claimed_value: int
    block_index: int
    match_text: str


@dataclass
class FactualValidationResult:
    """Result of factual validation for a set of blocks."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    claims_checked: int = 0
    claims_verified: int = 0
    claims_failed: int = 0
    bleed_detections: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "claims_checked": self.claims_checked,
            "claims_verified": self.claims_verified,
            "claims_failed": self.claims_failed,
            "bleed_detections": self.bleed_detections,
        }


def extract_stat_claims(
    narrative: str,
    block_index: int,
    sport: str,
) -> list[StatClaim]:
    """Extract stat claims from a narrative block.

    Uses sport-specific regex patterns to find statements like
    "Player scored 25 points" and extract the claim.
    """
    claims: list[StatClaim] = []
    if not narrative:
        return claims

    for pattern, stat_key, sport_codes in STAT_CLAIM_PATTERNS:
        if stat_key == "_score":
            continue
        if sport_codes and sport not in sport_codes:
            continue

        for match in re.finditer(pattern, narrative, re.IGNORECASE):
            player_name = match.group(1).strip()
            try:
                value = int(match.group(2))
            except (ValueError, IndexError):
                continue

            claims.append(
                StatClaim(
                    player_name=player_name,
                    stat_key=stat_key,
                    claimed_value=value,
                    block_index=block_index,
                    match_text=match.group(0),
                )
            )

    return claims


def _find_player_stat(
    mini_box: dict[str, Any],
    player_name: str,
    stat_key: str,
) -> int | None:
    """Look up a player's stat value from mini_box data.

    Uses fuzzy last-name matching: "Young" matches "Trae Young".
    """
    if not mini_box:
        return None

    search_last = player_name.split()[-1].lower() if player_name else ""
    search_full = player_name.lower()

    for side in ("home", "away"):
        team_data = mini_box.get(side, {})
        players = team_data.get("players", [])
        for player in players:
            name = player.get("name", "")
            name_lower = name.lower()
            last_name = name.split()[-1].lower() if name else ""

            if (search_full == name_lower or search_last == last_name) and stat_key in player:
                return player[stat_key]

    return None


def verify_stat_claims(
    claims: list[StatClaim],
    blocks: list[dict[str, Any]],
) -> tuple[list[str], list[str], int, int]:
    """Verify extracted stat claims against mini_box data.

    Returns (errors, warnings, verified_count, failed_count).
    """
    errors: list[str] = []
    warnings: list[str] = []
    verified = 0
    failed = 0

    for claim in claims:
        block = blocks[claim.block_index] if claim.block_index < len(blocks) else None
        if not block:
            warnings.append(
                f"Block {claim.block_index}: Cannot verify claim '{claim.match_text}' — block not found"
            )
            continue

        mini_box = block.get("mini_box")
        if not mini_box:
            warnings.append(
                f"Block {claim.block_index}: Cannot verify '{claim.match_text}' — no mini_box data"
            )
            continue

        actual = _find_player_stat(mini_box, claim.player_name, claim.stat_key)

        if actual is None:
            warnings.append(
                f"Block {claim.block_index}: Player '{claim.player_name}' stat '{claim.stat_key}' "
                f"not found in mini_box"
            )
            continue

        if actual != claim.claimed_value:
            errors.append(
                f"Block {claim.block_index}: Factual error — '{claim.player_name}' "
                f"{claim.stat_key} claimed {claim.claimed_value}, actual {actual}"
            )
            failed += 1
        else:
            verified += 1

    return errors, warnings, verified, failed


def detect_training_data_bleed(
    narrative: str,
    block_index: int,
) -> list[str]:
    """Detect claims that likely come from LLM training data, not game context.

    Catches references to season averages, injury status, historical streaks,
    and other information not provided in the structured game data.
    """
    errors: list[str] = []
    if not narrative:
        return errors

    for pattern, description in TRAINING_DATA_BLEED_PATTERNS:
        if re.search(pattern, narrative, re.IGNORECASE):
            errors.append(f"Block {block_index}: Training-data bleed — {description} detected")

    return errors


def validate_entity_allowlist(
    narrative: str,
    block_index: int,
    game_context: dict[str, str],
    blocks: list[dict[str, Any]],
) -> list[str]:
    """Check that player/team names in narrative exist in game data.

    Builds an allowlist from game_context and mini_box data,
    then flags capitalized multi-word names not in the allowlist.
    """
    warnings: list[str] = []
    if not narrative:
        return warnings

    allowed: set[str] = set()

    for key in ("home_team_name", "away_team_name", "home_team_abbrev", "away_team_abbrev"):
        val = game_context.get(key, "")
        if val:
            allowed.add(val.lower())

    player_names = game_context.get("player_names", {})
    if isinstance(player_names, dict):
        for abbrev, full in player_names.items():
            allowed.add(abbrev.lower())
            allowed.add(full.lower())
            parts = full.split()
            if len(parts) >= 2:
                allowed.add(parts[-1].lower())

    for block in blocks:
        mini_box = block.get("mini_box", {})
        for side in ("home", "away"):
            team_data = mini_box.get(side, {}) if mini_box else {}
            team_name = team_data.get("team", "")
            if team_name:
                allowed.add(team_name.lower())
            for player in team_data.get("players", []):
                name = player.get("name", "")
                if name:
                    allowed.add(name.lower())
                    parts = name.split()
                    if len(parts) >= 2:
                        allowed.add(parts[-1].lower())

    # Extract capitalized multi-word sequences that look like proper nouns
    potential_names = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", narrative)

    for name in potential_names:
        if name.lower() not in allowed:
            # Check if last name alone is allowed (common in sports writing)
            last = name.split()[-1].lower()
            if last not in allowed:
                warnings.append(
                    f"Block {block_index}: Unknown entity '{name}' not in game data allowlist"
                )

    return warnings


def run_factual_validation(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    sport: str,
) -> FactualValidationResult:
    """Run full factual validation across all blocks.

    Stage 2 of the content validation pipeline:
    1. Extract stat claims from narratives
    2. Verify claims against mini_box game data
    3. Detect training-data bleed
    4. Check entity allowlist
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []
    total_claims = 0
    total_verified = 0
    total_failed = 0
    total_bleed = 0

    all_claims: list[StatClaim] = []

    for block in blocks:
        block_idx = block.get("block_index", 0)
        narrative = block.get("narrative", "")

        claims = extract_stat_claims(narrative, block_idx, sport)
        all_claims.extend(claims)

        bleed_errors = detect_training_data_bleed(narrative, block_idx)
        all_errors.extend(bleed_errors)
        total_bleed += len(bleed_errors)

        entity_warnings = validate_entity_allowlist(narrative, block_idx, game_context, blocks)
        all_warnings.extend(entity_warnings)

    errors, warnings, verified, failed = verify_stat_claims(all_claims, blocks)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    total_claims = len(all_claims)
    total_verified = verified
    total_failed = failed

    passed = total_failed == 0 and total_bleed == 0

    result = FactualValidationResult(
        passed=passed,
        errors=all_errors,
        warnings=all_warnings,
        claims_checked=total_claims,
        claims_verified=total_verified,
        claims_failed=total_failed,
        bleed_detections=total_bleed,
    )

    logger.info(
        "factual_validation_complete",
        extra={
            "passed": passed,
            "claims_checked": total_claims,
            "claims_verified": total_verified,
            "claims_failed": total_failed,
            "bleed_detections": total_bleed,
        },
    )

    return result
