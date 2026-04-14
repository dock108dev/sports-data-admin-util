"""Tone detection for Flow narrative generation.

Classifies games into one of 6 tone categories based on game data,
each mapping to distinct prompt adjustments for narrative voice and emphasis.

Tone Categories
===============
- standard: Default balanced tone
- upset_alert: Underdog wins decisively
- blowout: One-sided game with large margin
- pitcher_duel: Low-scoring defensive battle
- comeback: Trailing team overcomes significant deficit
- rivalry: Division rival matchup
- historic: Milestone or record-breaking performance
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from .league_config import get_config


class ToneCategory(str, Enum):
    STANDARD = "standard"
    UPSET_ALERT = "upset_alert"
    BLOWOUT = "blowout"
    PITCHER_DUEL = "pitcher_duel"
    COMEBACK = "comeback"
    RIVALRY = "rivalry"
    HISTORIC = "historic"


# Prompt voice directives per tone category
TONE_DIRECTIVES: dict[str, dict[str, str]] = {
    ToneCategory.STANDARD: {
        "voice": "Balanced and informational with moderate energy.",
        "emphasis": "Give proportional weight to each phase of the game.",
        "pacing": "Steady chronological pacing with natural crescendo toward the finish.",
    },
    ToneCategory.UPSET_ALERT: {
        "voice": "Emphasize the improbability. Use language of surprise — 'stunned', 'upended', 'defied expectations'.",
        "emphasis": "Highlight the moment the upset became real. Name the plays that sealed it.",
        "pacing": "Build tension through the middle blocks, then deliver the shock in RESOLUTION.",
    },
    ToneCategory.BLOWOUT: {
        "voice": "Measured and efficient. Don't manufacture drama where none existed.",
        "emphasis": "Focus on individual performances and milestones rather than game tension. Compress the middle innings/quarters.",
        "pacing": "Front-load the narrative. Once the outcome is decided, shift to individual storylines.",
    },
    ToneCategory.PITCHER_DUEL: {
        "voice": "Slow, deliberate pacing. Emphasize tension and defensive craft.",
        "emphasis": "Detail pitching sequences, defensive gems, and the weight of each run. Every score matters more.",
        "pacing": "Stretch the middle blocks. Let the tension build through inaction — silence is the story.",
    },
    ToneCategory.COMEBACK: {
        "voice": "Crescendo narrative — start subdued, build to peak energy at the turning point.",
        "emphasis": "Name the exact moment the tide turned. Quantify the deficit that was overcome.",
        "pacing": "Compress the early dominance, expand the comeback sequence, land hard on the finish.",
    },
    ToneCategory.RIVALRY: {
        "voice": "Elevated register with historical awareness. Reference the weight of the matchup.",
        "emphasis": "Frame individual battles within the rivalry context. Every play carries extra significance.",
        "pacing": "Steady throughout — rivalry games earn full coverage regardless of score.",
    },
    ToneCategory.HISTORIC: {
        "voice": "Elevated, authoritative register. This is a game people will reference.",
        "emphasis": "Lead with the milestone or record. Contextualize against historical precedent.",
        "pacing": "Front-load the historic achievement, then narrate the game around it.",
    },
}


def detect_tone(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    league_code: str,
) -> ToneCategory:
    """Classify a game into a tone category based on game data.

    Evaluates blocks and game context to determine the narrative tone.
    Categories are checked in priority order — the first match wins.

    Args:
        blocks: List of block dicts with score data
        game_context: Team names and metadata
        league_code: Sport code (NBA, MLB, NHL, NCAAB, NFL)

    Returns:
        The detected ToneCategory for this game
    """
    if not blocks:
        return ToneCategory.STANDARD

    config = get_config(league_code)

    final_block = blocks[-1]
    final_score = final_block.get("score_after", [0, 0])
    final_margin = abs(final_score[0] - final_score[1])

    # Check for historic (from game_context flags)
    if game_context.get("has_milestone") or game_context.get("is_historic"):
        return ToneCategory.HISTORIC

    # Check for comeback: >10pt swing in the final quarter/period
    if _detect_comeback(blocks, config, league_code):
        return ToneCategory.COMEBACK

    # Check for upset: underdog wins by significant margin
    if _detect_upset(final_margin, game_context, config):
        return ToneCategory.UPSET_ALERT

    # Check for blowout
    blowout_threshold = _get_blowout_threshold(league_code)
    if final_margin > blowout_threshold:
        return ToneCategory.BLOWOUT

    # Check for pitcher_duel (baseball-specific low-scoring game)
    if _detect_pitcher_duel(blocks, league_code):
        return ToneCategory.PITCHER_DUEL

    # Check for rivalry
    if game_context.get("is_rivalry") or game_context.get("is_division_rival"):
        return ToneCategory.RIVALRY

    return ToneCategory.STANDARD


def _get_blowout_threshold(league_code: str) -> int:
    """Return the point margin threshold for a blowout classification.

    These are intentionally higher than league_config's blowout_margin
    because tone classification requires a more decisive margin.
    """
    thresholds = {
        "NBA": 20,
        "NCAAB": 20,
        "NFL": 21,
        "MLB": 7,
        "NHL": 4,
    }
    return thresholds.get(league_code, 20)


def _detect_comeback(
    blocks: list[dict[str, Any]],
    config: dict[str, Any],
    league_code: str,
) -> bool:
    """Detect if a game featured a significant comeback.

    A comeback requires:
    1. A swing of >10 points (or sport-equivalent) in the final period
    2. The lead must actually change hands OR the final margin must be
       close (within the close_game_margin threshold)

    A team cutting a 35-point deficit to 21 is not a comeback — it's
    a rally that fell short.
    """
    if len(blocks) < 2:
        return False

    swing_threshold = _get_comeback_swing_threshold(league_code)
    regulation_periods = config.get("regulation_periods", 4)
    close_margin = config.get("close_game_margin", 7)

    # Final margin determines if comeback was successful
    final_block = blocks[-1]
    final_score = final_block.get("score_after", [0, 0])
    final_margin = abs(final_score[0] - final_score[1])

    # Find blocks in the final regulation period or later
    late_blocks = [
        b for b in blocks
        if b.get("period_end", 1) >= regulation_periods
    ]
    if not late_blocks:
        return False

    # Check if the overall late-game arc shows a comeback with lead change
    first_late = late_blocks[0]
    first_score = first_late.get("score_before", [0, 0])
    margin_start = first_score[0] - first_score[1]
    margin_end = final_score[0] - final_score[1]

    total_swing = abs(margin_end - margin_start)
    if total_swing < swing_threshold:
        return False

    # Lead must have changed hands OR final margin must be close
    lead_changed = (margin_start > 0 and margin_end < 0) or (margin_start < 0 and margin_end > 0)
    if lead_changed:
        return True

    # Trailing team closed to within close_game_margin
    if final_margin <= close_margin and total_swing >= swing_threshold:
        return True

    return False


def _get_comeback_swing_threshold(league_code: str) -> int:
    """Return the point swing threshold for comeback classification."""
    thresholds = {
        "NBA": 10,
        "NCAAB": 10,
        "NFL": 14,
        "MLB": 4,
        "NHL": 3,
    }
    return thresholds.get(league_code, 10)


def _detect_upset(
    final_margin: int,
    game_context: dict[str, str],
    config: dict[str, Any],
) -> bool:
    """Detect if the game result is an upset.

    An upset requires:
    - Pre-game favorite/underdog designation in game_context
    - The underdog won by a significant margin (>15 pts or sport-equivalent)
    """
    expected_winner = game_context.get("expected_winner")
    actual_winner = game_context.get("actual_winner")
    upset_margin_str = game_context.get("upset_margin")

    # If explicit upset margin is provided, use it
    if upset_margin_str is not None:
        try:
            return int(upset_margin_str) > 15
        except (ValueError, TypeError):
            pass

    # If we know expected vs actual winner and they differ
    if expected_winner and actual_winner and expected_winner != actual_winner:
        if final_margin > 15:
            return True

    # Check pre-game win probability if available
    pregame_win_prob_str = game_context.get("pregame_win_probability")
    if pregame_win_prob_str is not None:
        try:
            pregame_win_prob = float(pregame_win_prob_str)
            if pregame_win_prob < 0.30 and final_margin > 15:
                return True
        except (ValueError, TypeError):
            pass

    return False


def _detect_pitcher_duel(
    blocks: list[dict[str, Any]],
    league_code: str,
) -> bool:
    """Detect a pitcher's duel (low-scoring, tightly contested game).

    Only applies to MLB. Criteria: combined runs <= 4 and neither team
    scored more than 3 runs.
    """
    if league_code != "MLB":
        return False

    if not blocks:
        return False

    final_block = blocks[-1]
    final_score = final_block.get("score_after", [0, 0])
    combined_runs = final_score[0] + final_score[1]
    max_team_runs = max(final_score[0], final_score[1])

    return combined_runs <= 4 and max_team_runs <= 3


def get_tone_prompt_directives(tone: ToneCategory) -> str:
    """Build prompt text for the detected tone category.

    Returns formatted prompt directives to inject into the game-specific
    prompt layer.
    """
    directives = TONE_DIRECTIVES.get(tone, TONE_DIRECTIVES[ToneCategory.STANDARD])

    lines = [
        f"TONE: {tone.value.upper().replace('_', ' ')}",
        f"- Voice: {directives['voice']}",
        f"- Emphasis: {directives['emphasis']}",
        f"- Pacing: {directives['pacing']}",
    ]
    return "\n".join(lines)
