"""Three-layer prompt architecture for RENDER_BLOCKS stage.

Layer 1 — System prompt: Stable narrator identity, voice, structural contract
Layer 2 — Game-specific prompt: Variable data (teams, blocks, plays, tone)
Layer 3 — Guardrail postscript: Enforcement reminder for factual grounding

Pure computational helpers are in render_prompt_helpers.py.
Tone detection is in tone_detection.py.
"""

from __future__ import annotations

import re
from typing import Any

from .render_helpers import detect_overtime_info
from .render_prompt_helpers import (
    _build_period_label,
    _detect_big_lead_comeback,
    _detect_close_game,
    _format_contributors_line,
    _format_lead_line,
    detect_game_winning_play,
    detect_sustained_lead,
)
from .render_validation import FORBIDDEN_WORDS
from .tone_detection import ToneCategory, detect_tone, get_tone_prompt_directives

# ---------------------------------------------------------------------------
# Layer 1: System Prompt — stable across all games
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior sports writer producing game recap narratives from structured play-by-play data. Your prose blends the authority of a broadsheet sports section with the energy of a highlight broadcast.

OUTPUT CONTRACT
- Each block is 1-5 sentences (~40-100 words). Vary length by role.
- Return JSON: {"blocks": [{"i": block_index, "n": "narrative"}]}

HARD RULES
- NEVER invent statistics, quotes, or events not present in the provided data.
- NEVER use the phrase "in a game that" in any block.
- Every player name must appear EXACTLY as provided in the data.
- Use FULL NAME on first mention (e.g., "Donovan Mitchell"). NEVER use initials like "D. Mitchell".
- After first mention, use LAST NAME only. Names apply across the entire flow, not per-block.

NARRATIVE STRUCTURE
- Each block describes a STRETCH of play, not isolated events.
- Connect plays with cause-and-effect.
- Vary sentence openings — no two consecutive sentences should start the same way.
- Describe ACTIONS, not statistics. Use broadcast tone, not stat-feed prose.
- NO stat-listing patterns like "X had Y points" or "X finished with Y".
- Keep individual sentences concise (under 30 words each).

ROLE-SPECIFIC GUIDANCE
- SETUP: Establish tone and early shape. May contain zero specific plays. Abstraction encouraged.
  * NEVER foreshadow or spoil the outcome. No "would be", "would prove", "would not recover".
  * Write as if the game is unfolding — the reader doesn't know who wins yet.
- MOMENTUM_SHIFT: Name the trigger, summarize the effect. Describe the run, not each play.
- RESPONSE: Bridge narrative rhythm. Team-level summary preferred. Often abstract.
  * MUST describe an actual scoring response or tactical adjustment.
  * If the score did not change, describe the state of play, not a "response".
- DECISION_POINT: Highest specificity. Name exact plays and players. This block earns detail.
- RESOLUTION: Land the outcome with the defining play. For close games, narrate the final moment. For blowouts, keep it short.

NARRATIVE COMPRESSION
- Collapse consecutive scoring into runs (e.g., "went on a 12-0 run").
- Use team-level descriptions for collective action.
- Describe momentum through state change, not event enumeration.
- Omitting routine scoring detail is acceptable.

CONTEXTUAL DATA USAGE:
- [Lead:] lines: Weave naturally ("extending the lead to 8", "pulling within 3").
- [Peak:] lines: Anchor the high-water mark ("built a 22-point lead before...").
- [Contributors:] lines: Mention these players' actions, not their stat lines.
- Do NOT quote these lines verbatim — use them as narrative fuel."""

# ---------------------------------------------------------------------------
# Layer 1: System Prompt for Flow Pass
# ---------------------------------------------------------------------------

# Backward-compatible alias used by test_render_blocks.py
GAME_FLOW_PASS_PROMPT = FLOW_PASS_SYSTEM_PROMPT = """You are given the full Game Flow for a single game as a sequence of blocks.

Each block is already correct and final in structure, timing, and scoring.
Your job is to rewrite for narrative coherence so the blocks flow naturally
as a single game recap, while keeping each block as its own paragraph.

Rules:
- Preserve block order and boundaries
- Preserve scores, players, and chronology. You may restructure sentences for flow.
- Do not change scores or periods
- Each block should be 1-5 sentences in one paragraph
- Improve flow, reduce repetition, and acknowledge the passage of time across blocks
- No hype, no speculation, no raw play-by-play
- SETUP blocks must NOT foreshadow the outcome. Write as if the game is still unfolding.
- RESPONSE blocks must reflect an actual scoring change. If the score didn't move, describe the state, not a "response."
- Give each half/period proportional narrative weight. Don't compress late-game action into a throwaway line.
- If a trailing team never got within single digits, don't call it a "comeback" — call it a rally that fell short.
- Ensure player names appear in full only on first mention across the entire flow. Use last name thereafter.
- Use full team name only once early. Rotate between short name and pronoun.
- CRITICAL: If the game goes to overtime/OT/shootout, the narrative MUST mention this transition

If a block already flows well, make minimal changes.

Return JSON: {"blocks": [{"i": block_index, "n": "revised narrative"}]}"""


# ---------------------------------------------------------------------------
# Layer 3: Guardrail Postscript — enforcement reminder
# ---------------------------------------------------------------------------

GUARDRAIL_POSTSCRIPT = """FINAL CHECKLIST (you MUST satisfy ALL before responding):
- Every narrative block present in the output JSON
- No statistics, player names, or events that aren't in the provided data
- No season stats, career stats, or historical comparisons unless provided
- No injury speculation or psychological attribution ("wanted to", "felt", "motivated by")
- No foreshadowing in SETUP blocks — write as if the outcome is unknown
- Every block respects the 1-5 sentence range
- Tone matches the tone directive above
- FORBIDDEN WORDS not used: {forbidden}"""


def _build_guardrail_postscript() -> str:
    """Build the guardrail postscript with current forbidden words."""
    return GUARDRAIL_POSTSCRIPT.format(forbidden=", ".join(FORBIDDEN_WORDS))


# ---------------------------------------------------------------------------
# Public API: build_block_prompt (three-layer)
# ---------------------------------------------------------------------------


def build_block_prompt(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    pbp_events: list[dict[str, Any]],
) -> str:
    """Build the three-layer prompt for generating block narratives.

    Layer 1: System prompt (stable narrator identity)
    Layer 2: Game-specific data (teams, blocks, plays, tone)
    Layer 3: Guardrail postscript (enforcement reminder)

    Args:
        blocks: List of block dicts (without narratives)
        game_context: Team names and other context
        pbp_events: PBP events for play descriptions

    Returns:
        Prompt string for OpenAI
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")
    home_abbrev = game_context.get("home_team_abbrev", "")
    away_abbrev = game_context.get("away_team_abbrev", "")
    league_code = game_context.get("sport", "NBA")

    # --- Layer 1: System prompt ---
    prompt_parts = [SYSTEM_PROMPT, ""]

    # --- Layer 2: Game-specific prompt ---
    prompt_parts.extend(_build_game_specific_layer(
        blocks, game_context, pbp_events,
        home_team, away_team, home_abbrev, away_abbrev, league_code,
    ))

    # --- Layer 3: Guardrail postscript ---
    prompt_parts.extend(["", _build_guardrail_postscript()])

    return "\n".join(prompt_parts)


def _build_game_specific_layer(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
    pbp_events: list[dict[str, Any]],
    home_team: str,
    away_team: str,
    home_abbrev: str,
    away_abbrev: str,
    league_code: str,
) -> list[str]:
    """Build Layer 2: game-specific prompt content.

    Includes teams, rosters, tone directives, sport-specific rules,
    game-pattern guidance, and block data.
    """
    # Build abbreviation -> full team name lookup
    abbrev_to_team: dict[str, str] = {}
    if home_abbrev:
        abbrev_to_team[home_abbrev.upper()] = home_team
    if away_abbrev:
        abbrev_to_team[away_abbrev.upper()] = away_team

    # Detect game patterns
    has_any_overtime = any(
        detect_overtime_info(block, league_code)["has_overtime"]
        for block in blocks
    )
    is_close_game, max_margin = _detect_close_game(blocks)
    is_comeback, game_peak_margin, final_margin = _detect_big_lead_comeback(blocks)
    is_sustained, sustained_min_margin, sustained_leader = detect_sustained_lead(blocks)

    # Detect tone
    tone = detect_tone(blocks, game_context, league_code)

    # Build play lookup
    play_lookup: dict[int, dict[str, Any]] = {
        e["play_index"]: e for e in pbp_events if "play_index" in e
    }

    # Build player rosters from PBP
    home_players: set[str] = set()
    away_players: set[str] = set()
    for evt in pbp_events:
        name = evt.get("player_name", "")
        evt_abbrev = (evt.get("team_abbreviation") or "").upper()
        if not name or not evt_abbrev:
            continue
        if home_abbrev and evt_abbrev == home_abbrev.upper():
            home_players.add(name)
        elif away_abbrev and evt_abbrev == away_abbrev.upper():
            away_players.add(name)

    parts: list[str] = [
        f"Teams: {away_team} (away) vs {home_team} (home)",
    ]

    # Rosters
    if home_players or away_players:
        parts.append("")
        parts.append("ROSTERS:")
        if home_players:
            roster = ", ".join(sorted(home_players)[:10])
            parts.append(f"{home_team} (home): {roster}")
        if away_players:
            roster = ", ".join(sorted(away_players)[:10])
            parts.append(f"{away_team} (away): {roster}")

    # Tone directives
    parts.extend(["", get_tone_prompt_directives(tone), ""])

    # Team attribution rules
    parts.extend([
        "TEAM ATTRIBUTION:",
        f"- On first mention: \"{home_team}'s [Player]\" or \"[Player] for {away_team}\"",
        "- After first mention, just use last name without team",
        "- Do NOT use parenthetical abbreviations like '(CHA)' or '(NOP)'",
        "- Full team name once in SETUP. Rotate between short name, nickname, and pronoun.",
        "",
    ])

    # League-specific rules
    parts.extend(_build_league_rules(league_code, home_team, away_team))

    # Game-pattern-specific guidance
    score_unit = "runs" if league_code == "MLB" else "pts"
    if is_close_game:
        parts.extend([
            f"CLOSE GAME (max margin: {max_margin} {score_unit}):",
            f"- Do NOT overstate leads when margin is 1-2 {score_unit}. Emphasize back-and-forth.",
            "- RESOLUTION: Capture the tension of the finish with specificity.",
            "",
        ])

    if is_comeback:
        comeback_gap = game_peak_margin - final_margin
        parts.extend([
            f"BIG LEAD / COMEBACK (peak margin: {game_peak_margin}, final: {final_margin}):",
            f"- A team led by {game_peak_margin} at one point. Do NOT describe this as a 'modest' or 'slim' lead.",
            "- If the lead eroded, narrate the comeback arc — name the swing.",
            "- Use [Peak:] data in blocks to anchor the high-water mark.",
        ])
        if comeback_gap < game_peak_margin // 2:
            parts.append(
                f"- The trailing team never got closer than {final_margin}. Do NOT oversell this as a 'comeback' — "
                f"it was a rally that fell short. Frame it as tightening, not a real threat."
            )
        parts.append("")

    if is_sustained and not is_close_game and not is_comeback:
        leader_name = home_team if sustained_leader == "home" else away_team
        parts.extend([
            f"SUSTAINED LEAD ({leader_name} led by {sustained_min_margin}+ the entire second half):",
            f"- {leader_name} was in firm control. Do NOT frame minor margin changes (1-3 {score_unit}) as 'runs', 'pushes', 'responses', or comeback attempts.",
            "- If the trailing team cut the lead from 10 to 8, that is routine scoring — not a surge, rally, or threat.",
            "- Use language like 'maintained control', 'kept the margin comfortable', 'never seriously threatened'.",
            "- Only narrate an actual run if the margin drops by 6+ points in a single block.",
            "",
        ])

    if has_any_overtime:
        parts.extend([
            "OVERTIME/EXTRA PERIOD REQUIREMENTS (CRITICAL):",
            "- When a block TRANSITIONS into overtime, you MUST explicitly mention it",
            "- Use phrases like 'the game headed to overtime', 'forcing an extra period'",
            "- For NHL shootouts, mention 'heading to a shootout'",
            "- This is MANDATORY — do NOT skip mentioning overtime when it occurs",
            "",
        ])

    # Proportional coverage
    parts.extend([
        "PROPORTIONAL COVERAGE:",
        "- Give each half/period proportional narrative weight.",
        "- Late-game blocks should never feel like afterthoughts.",
        "",
    ])

    # Block data
    parts.extend([
        "BLOCKS:",
    ])

    for block in blocks:
        parts.extend(_format_block_data(
            block, play_lookup, abbrev_to_team,
            home_team, away_team, league_code, pbp_events,
        ))

    return parts


def _build_league_rules(
    league_code: str,
    home_team: str,
    away_team: str,
) -> list[str]:
    """Build league-specific prompt rules."""
    parts: list[str] = []

    if league_code == "MLB":
        parts.extend([
            "CONNECTING PHRASES:",
            "- 'building on that', 'in response', 'shortly after'",
            "- 'over the next several at-bats', 'as the inning progressed'",
            "- 'trading runs', 'the teams exchanged leads'",
            "",
            "BASEBALL-SPECIFIC:",
            "- Use 'innings' not 'quarters' or 'periods'",
            "- Use 'runs' not 'points'",
            "- Late-game = 7th inning onward",
            "- Extra innings (10th+), not 'overtime'",
            "- 'went on a 3-run rally' not 'went on a 12-0 run'",
            "",
            "INNING STRUCTURE (CRITICAL):",
            f"- {away_team} is the AWAY team and bats FIRST (top half).",
            f"- {home_team} is the HOME team and bats SECOND (bottom half).",
            "- NEVER say the home team 'struck first' if the away team scored in the top of the same inning.",
            "",
            "SCORELESS INNINGS:",
            "- If both teams went scoreless, describe it plainly — don't manufacture drama.",
            "- Do NOT use 'momentum shifted' or 'the tide turned' for scoreless innings.",
            "- Only use tension language for scoreless innings if it's a 0-0 game in the late innings (7th+).",
            "",
        ])
    else:
        parts.extend([
            "CONNECTING PHRASES:",
            "- 'building on that', 'in response', 'shortly after'",
            "- 'over the next several possessions', 'as the period progressed'",
            "- 'trading baskets', 'the teams exchanged leads'",
            "",
        ])

    return parts


def _format_block_data(
    block: dict[str, Any],
    play_lookup: dict[int, dict[str, Any]],
    abbrev_to_team: dict[str, str],
    home_team: str,
    away_team: str,
    league_code: str,
    pbp_events: list[dict[str, Any]],
) -> list[str]:
    """Format a single block's data for the prompt."""
    parts: list[str] = []
    block_idx = block["block_index"]
    role = block["role"]
    score_before = block["score_before"]
    score_after = block["score_after"]
    key_play_ids = block["key_play_ids"]
    period_start = block.get("period_start", 1)
    period_end = block.get("period_end", period_start)

    ot_info = detect_overtime_info(block, league_code)
    period_label = _build_period_label(league_code, period_start, period_end)

    # Key play descriptions
    key_plays_desc = []
    for pid in key_play_ids:
        play = play_lookup.get(pid, {})
        desc = play.get("description", "")
        if desc:
            bracket_match = re.match(r"^\[([^\]]+)\]\s*", desc)
            if bracket_match:
                abbrev = bracket_match.group(1).upper()
                team_name = abbrev_to_team.get(abbrev, bracket_match.group(1))
                clean_desc = f"({team_name}) {desc[bracket_match.end():]}"
            else:
                clean_desc = desc
            clean_desc = re.sub(r"\b\d+'(?![a-zA-Z])\s*", "", clean_desc)
            key_plays_desc.append(f"- {clean_desc}")

    parts.append(f"\nBlock {block_idx} ({role}, {period_label}):")
    parts.append(
        f"Score: {away_team} {score_before[1]}-{score_before[0]} {home_team} "
        f"-> {away_team} {score_after[1]}-{score_after[0]} {home_team}"
    )

    # Scoreless block flag (MLB)
    total_runs_scored = abs(score_after[0] - score_before[0]) + abs(score_after[1] - score_before[1])
    if total_runs_scored == 0 and league_code == "MLB":
        parts.append("(No runs scored in this block — describe plainly, no manufactured drama)")

    # Overtime flags
    if ot_info["enters_overtime"]:
        parts.append(f"*** ENTERS {ot_info['ot_label'].upper()} - MUST mention going to {ot_info['ot_label']} ***")
    elif ot_info["has_overtime"] and not ot_info["enters_overtime"]:
        parts.append(f"(In {ot_info['ot_label']})")

    # Decided game flag for RESOLUTION
    if role == "RESOLUTION":
        final_margin = abs(score_after[0] - score_after[1])
        if final_margin >= 15:
            parts.append("(Outcome decided — summarize the final margin, skip garbage time)")
        else:
            gw_hint = detect_game_winning_play(
                block, pbp_events, home_team, away_team, league_code,
            )
            if gw_hint:
                parts.append(f"*** {gw_hint} ***")
                parts.append(
                    "- This play DECIDED the game. Narrate it with specificity — "
                    "do NOT use generic 'held on' framing. Name the player and the moment."
                )

    # Lead context
    lead_line = _format_lead_line(score_before, score_after, home_team, away_team)
    if lead_line:
        parts.append(lead_line)

    # Peak margin context
    block_peak_margin = block.get("peak_margin", 0)
    block_peak_leader = block.get("peak_leader", 0)
    boundary_margin = max(abs(score_before[0] - score_before[1]),
                          abs(score_after[0] - score_after[1]))
    if block_peak_margin >= boundary_margin + 6:
        peak_team = home_team if block_peak_leader == 1 else away_team
        parts.append(
            f"Peak: {peak_team} led by as many as {block_peak_margin} during this stretch"
        )

    # Contributors
    mini_box = block.get("mini_box")
    contributors_line = _format_contributors_line(mini_box, league_code)
    if contributors_line:
        parts.append(contributors_line)

    if key_plays_desc:
        parts.append("Key plays:")
        parts.extend(key_plays_desc[:3])

    return parts


# ---------------------------------------------------------------------------
# Public API: build_game_flow_pass_prompt
# ---------------------------------------------------------------------------


def build_game_flow_pass_prompt(
    blocks: list[dict[str, Any]],
    game_context: dict[str, str],
) -> str:
    """Build prompt for game-level flow pass.

    Uses the flow-pass system prompt plus game-specific block data.

    Args:
        blocks: List of block dicts with narratives already generated
        game_context: Team names and context

    Returns:
        Prompt string for the flow pass
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")
    league_code = game_context.get("sport", "NBA")

    is_close_game, max_margin = _detect_close_game(blocks)
    is_comeback, game_peak_margin, final_margin = _detect_big_lead_comeback(blocks)

    prompt_parts = [
        FLOW_PASS_SYSTEM_PROMPT,
        "",
        f"Game: {away_team} (away) at {home_team} (home)",
    ]

    if league_code == "MLB":
        prompt_parts.append(
            f"\nREMINDER: {away_team} bats first (top of each inning), "
            f"{home_team} bats second (bottom). Do not say the home team "
            f"'struck first' if the away team scored in the top of the inning."
        )

    score_unit = "runs" if league_code == "MLB" else "pts"
    if is_close_game:
        prompt_parts.append(
            f"\nNOTE: Close game (max margin: {max_margin} {score_unit}). Don't overstate leads. Detail the finish."
        )

    if is_comeback:
        prompt_parts.append(
            f"\nNOTE: Comeback game (peak margin: {game_peak_margin}, final: {final_margin}). "
            f"A team led by {game_peak_margin} at one point — narrate the swing."
        )

    prompt_parts.extend([
        "",
        "BLOCKS:",
    ])

    for block in blocks:
        block_idx = block["block_index"]
        role = block.get("role", "")
        period_start = block.get("period_start", 1)
        period_end = block.get("period_end", period_start)
        score_before = block.get("score_before", [0, 0])
        score_after = block.get("score_after", [0, 0])
        narrative = block.get("narrative", "")

        ot_info = detect_overtime_info(block, league_code)
        period_label = _build_period_label(league_code, period_start, period_end)

        prompt_parts.append(f"\nBlock {block_idx} ({role}, {period_label}):")
        prompt_parts.append(
            f"Score: {away_team} {score_before[1]}-{score_before[0]} {home_team} "
            f"-> {away_team} {score_after[1]}-{score_after[0]} {home_team}"
        )

        if ot_info["enters_overtime"]:
            prompt_parts.append(f"*** MUST MENTION: Game goes to {ot_info['ot_label']} ***")

        flow_peak = block.get("peak_margin", 0)
        flow_boundary = max(abs(score_before[0] - score_before[1]),
                            abs(score_after[0] - score_after[1]))
        if flow_peak >= flow_boundary + 6:
            prompt_parts.append(f"(Peak margin in this block: {flow_peak})")

        prompt_parts.append(f"Current narrative: {narrative}")

    return "\n".join(prompt_parts)
