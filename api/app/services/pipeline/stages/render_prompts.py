"""Prompt building functions for RENDER_BLOCKS stage.

Contains prompt templates and builders for OpenAI calls.
"""

from __future__ import annotations

from typing import Any

from .render_validation import FORBIDDEN_WORDS
from .render_helpers import detect_overtime_info
from .game_stats_helpers import compute_lead_context


# Game-level flow pass prompt - intentionally tight and low-token
GAME_FLOW_PASS_PROMPT = """You are given the full Game Flow for a single game as a sequence of blocks.

Each block is already correct and final in structure, timing, and scoring.
Your job is to lightly rewrite the narrative text so the blocks flow naturally
as a single game recap, while keeping each block as its own paragraph.

Rules:
- Preserve block order and boundaries
- Do not add or remove events
- Do not change scores, players, or periods
- Each block should be 2-4 sentences in one paragraph
- Improve flow, reduce repetition, and acknowledge the passage of time across blocks
- No hype, no speculation, no raw play-by-play
- CRITICAL: If the game goes to overtime/OT/shootout, the narrative MUST mention this transition
  (e.g., "the game headed to overtime", "forcing an extra period", "sending it to OT")

If a block already flows well, make minimal changes.

Return JSON: {"blocks": [{"i": block_index, "n": "revised narrative"}]}"""


def _format_lead_line(
    score_before: list[int],
    score_after: list[int],
    home_team: str,
    away_team: str,
) -> str | None:
    """Format a lead/margin context line for a block prompt.

    Returns a string like "Lead: Hawks extend the lead to 8" or None
    if there was no scoring change in the block.
    """
    ctx = compute_lead_context(score_before, score_after, home_team, away_team)
    desc = ctx.get("margin_description")
    if not desc:
        return None

    lead_after = ctx["lead_after"]
    lead_before = ctx["lead_before"]

    # Determine which team drove the scoring change
    if lead_after > lead_before:
        actor = home_team
    else:
        actor = away_team

    return f"Lead: {actor} {desc}"


def _format_contributors_line(
    mini_box: dict[str, Any] | None,
    league_code: str,
) -> str | None:
    """Format a contributors line from block mini_box data.

    Reads blockStars and matches to player delta stats.
    NBA/NCAAB: "Contributors: Young +6 pts, Tatum +5 pts"
    NHL: "Contributors: Pastrnak +1g/+1a, Marchand +1g"

    Returns None if mini_box is None, empty, or has no block stars.
    """
    if not mini_box:
        return None

    block_stars = mini_box.get("blockStars", [])
    if not block_stars:
        return None

    # Build lookup from last name -> player dict
    all_players: dict[str, dict[str, Any]] = {}
    for side in ("home", "away"):
        team_data = mini_box.get(side, {})
        for player in team_data.get("players", []):
            name = player.get("name", "")
            last_name = name.split()[-1] if " " in name else name
            all_players[last_name] = player

    parts: list[str] = []
    for star in block_stars:
        player = all_players.get(star)
        if not player:
            continue

        if league_code == "NHL":
            g = player.get("deltaGoals", 0)
            a = player.get("deltaAssists", 0)
            stat_parts = []
            if g:
                stat_parts.append(f"+{g}g")
            if a:
                stat_parts.append(f"+{a}a")
            if stat_parts:
                parts.append(f"{star} {'/'.join(stat_parts)}")
        else:  # NBA / NCAAB
            delta_pts = player.get("deltaPts", 0)
            if delta_pts:
                parts.append(f"{star} +{delta_pts} pts")

    if not parts:
        return None

    return f"Contributors: {', '.join(parts)}"


def build_game_flow_pass_prompt(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
) -> str:
    """Build prompt for game-level flow pass.

    This is a single call that receives all blocks and smooths transitions
    while preserving facts, scores, and structure.

    Args:
        blocks: List of block dicts with narratives already generated
        game_context: Team names and context

    Returns:
        Prompt string for the flow pass
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")
    league_code = game_context.get("sport", "NBA")

    prompt_parts = [
        GAME_FLOW_PASS_PROMPT,
        "",
        f"Game: {away_team} at {home_team}",
        "",
        "BLOCKS:",
    ]

    for block in blocks:
        block_idx = block["block_index"]
        role = block.get("role", "")
        period_start = block.get("period_start", 1)
        period_end = block.get("period_end", period_start)
        score_before = block.get("score_before", [0, 0])
        score_after = block.get("score_after", [0, 0])
        narrative = block.get("narrative", "")

        # Detect overtime info
        ot_info = detect_overtime_info(block, league_code)

        # Period label (sport-aware)
        period_label = _build_period_label(league_code, period_start, period_end)

        prompt_parts.append(f"\nBlock {block_idx} ({role}, {period_label}):")
        prompt_parts.append(
            f"Score: {away_team} {score_before[1]}-{score_before[0]} {home_team} "
            f"-> {away_team} {score_after[1]}-{score_after[0]} {home_team}"
        )

        # Add OT flag if this block enters overtime
        if ot_info["enters_overtime"]:
            prompt_parts.append(f"*** MUST MENTION: Game goes to {ot_info['ot_label']} ***")

        prompt_parts.append(f"Current narrative: {narrative}")

    return "\n".join(prompt_parts)


def build_block_prompt(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    pbp_events: list[dict[str, Any]],
) -> str:
    """Build the prompt for generating block narratives.

    Args:
        blocks: List of block dicts (without narratives)
        game_context: Team names and other context
        pbp_events: PBP events for play descriptions

    Returns:
        Prompt string for OpenAI
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")
    league_code = game_context.get("sport", "NBA")

    # Check if any block involves overtime
    has_any_overtime = any(
        detect_overtime_info(block, league_code)["has_overtime"]
        for block in blocks
    )

    # Build play lookup
    play_lookup: dict[int, dict[str, Any]] = {
        e["play_index"]: e for e in pbp_events if "play_index" in e
    }

    prompt_parts = [
        "Generate broadcast-quality narrative blocks for a game recap.",
        "",
        f"Teams: {away_team} (away) vs {home_team} (home)",
        "",
        "NARRATIVE STRUCTURE:",
        "- Write 2-4 sentences per block (~50-80 words)",
        "- Each block describes a STRETCH of play, not isolated events",
        "- Connect plays with cause-and-effect",
        "- Vary sentence openings",
        "- Focus on the key plays provided - EVERY key play must be referenced",
        "",
        "CONNECTING PHRASES TO USE:",
        "- 'building on that', 'in response', 'shortly after'",
        "- 'over the next several possessions', 'as the quarter progressed'",
        "- 'trading baskets', 'the teams exchanged leads'",
        "",
        "ROLE-SPECIFIC GUIDANCE:",
        "- SETUP: Opening tone, early pace, how the game began",
        "- MOMENTUM_SHIFT: What triggered the change, how it unfolded over several plays",
        "- RESPONSE: How the trailing team fought back, the adjustment they made",
        "- DECISION_POINT: The pivotal stretch that determined the outcome",
        "- RESOLUTION: How the game concluded, the final sequence",
        "",
        "PLAYER NAMES (CRITICAL):",
        "- Use FULL NAME on first mention (e.g., 'Donovan Mitchell', 'Brandon Miller')",
        "- NEVER use initials like 'D. Mitchell' or 'B. Miller' - always spell out first names",
        "- After first mention, use LAST NAME only (e.g., 'Mitchell', 'Miller')",
        "- Common names are fine abbreviated after first mention (Williams, Smith, Jones)",
        "",
        "TEAM ATTRIBUTION (CRITICAL):",
        "- On FIRST mention of each player, tie them to their team naturally:",
        f"  * \"{home_team}'s [Player Name]\" or \"{away_team}'s [Player Name]\" (possessive)",
        f"  * \"[Player Name] for {home_team}\" or \"[Player Name] for {away_team}\" (scoring context)",
        "- After first mention, just use last name without team",
        "- Do NOT use parenthetical abbreviations like '(CHA)' or '(NOP)'",
        "",
        "STYLE REQUIREMENTS:",
        "- Use broadcast tone, not stat-feed prose",
        "- NO stat-listing patterns like 'X had Y points' or 'X finished with Y'",
        "- NO subjective adjectives (incredible, amazing, unbelievable, insane)",
        "- Describe ACTIONS, not statistics",
        "- Keep individual sentences concise (under 30 words each)",
        "",
        "CONTEXTUAL DATA USAGE:",
        "- [Lead:] lines describe how the lead/deficit changed during this block",
        "  Weave naturally: 'extending the lead to 8' or 'pulling within 3'",
        "- [Contributors:] lines show who drove the scoring in this block",
        "  Integrate naturally: mention these players' actions, not their stat lines",
        "- Do NOT quote these lines verbatim - use them as narrative fuel",
        "",
        "FORBIDDEN WORDS (do not use):",
        ", ".join(FORBIDDEN_WORDS),
        "",
    ]

    # Add overtime-specific guidance if game went to OT
    if has_any_overtime:
        prompt_parts.extend([
            "OVERTIME/EXTRA PERIOD REQUIREMENTS (CRITICAL):",
            "- When a block TRANSITIONS into overtime, you MUST explicitly mention it",
            "- Use phrases like 'the game headed to overtime', 'forcing an extra period',",
            "  'sending the game to OT', 'requiring overtime to decide'",
            "- For NHL shootouts, mention 'heading to a shootout' or 'the shootout'",
            "- This is MANDATORY - do NOT skip mentioning overtime when it occurs",
            "",
        ])

    prompt_parts.extend([
        "Return JSON: {\"blocks\": [{\"i\": block_index, \"n\": \"narrative\"}]}",
        "",
        "BLOCKS:",
    ])

    for block in blocks:
        block_idx = block["block_index"]
        role = block["role"]
        score_before = block["score_before"]
        score_after = block["score_after"]
        key_play_ids = block["key_play_ids"]
        period_start = block.get("period_start", 1)
        period_end = block.get("period_end", period_start)

        # Detect overtime info for this block
        ot_info = detect_overtime_info(block, league_code)

        # Build period label
        period_label = _build_period_label(league_code, period_start, period_end)

        # Get key play descriptions
        key_plays_desc = []
        for pid in key_play_ids:
            play = play_lookup.get(pid, {})
            desc = play.get("description", "")
            if desc:
                key_plays_desc.append(f"- {desc}")

        prompt_parts.append(f"\nBlock {block_idx} ({role}, {period_label}):")
        prompt_parts.append(
            f"Score: {away_team} {score_before[1]}-{score_before[0]} {home_team} "
            f"-> {away_team} {score_after[1]}-{score_after[0]} {home_team}"
        )

        # Add explicit overtime flag when block enters/contains OT
        if ot_info["enters_overtime"]:
            prompt_parts.append(f"*** ENTERS {ot_info['ot_label'].upper()} - MUST mention going to {ot_info['ot_label']} ***")
        elif ot_info["has_overtime"] and not ot_info["enters_overtime"]:
            prompt_parts.append(f"(In {ot_info['ot_label']})")

        # Lead/margin context
        lead_line = _format_lead_line(score_before, score_after, home_team, away_team)
        if lead_line:
            prompt_parts.append(lead_line)

        # Block star contributors
        mini_box = block.get("mini_box")
        contributors_line = _format_contributors_line(mini_box, league_code)
        if contributors_line:
            prompt_parts.append(contributors_line)

        if key_plays_desc:
            prompt_parts.append("Key plays:")
            prompt_parts.extend(key_plays_desc[:3])

    return "\n".join(prompt_parts)


def _build_period_label(league_code: str, period_start: int, period_end: int) -> str:
    """Build sport-appropriate period label.

    Args:
        league_code: Sport code (NBA, NHL, NCAAB)
        period_start: Starting period number
        period_end: Ending period number

    Returns:
        Period label string (e.g., "Q1", "P2-P3", "H1", "OT")
    """
    if league_code == "NHL":
        if period_start == period_end:
            if period_start <= 3:
                return f"P{period_start}"
            elif period_start == 4:
                return "OT"
            elif period_start == 5:
                return "SO"
            else:
                return f"OT{period_start - 4}"
        else:
            return f"P{period_start}-P{period_end}"
    elif league_code == "NCAAB":
        if period_start == period_end:
            if period_start <= 2:
                return f"H{period_start}"
            else:
                return f"OT{period_start - 2}"
        else:
            return f"H{period_start}-H{period_end}"
    else:  # NBA
        if period_start == period_end:
            if period_start <= 4:
                return f"Q{period_start}"
            else:
                return f"OT{period_start - 4}"
        else:
            return f"Q{period_start}-Q{period_end}"
