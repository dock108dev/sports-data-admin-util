"""Prompt construction for OpenAI narrative generation.

This module builds prompts for the OpenAI API to generate moment narratives.
"""

from __future__ import annotations

from typing import Any

from .game_stats_helpers import (
    compute_running_player_stats,
    compute_lead_context,
    format_player_stat_hint,
)


def build_batch_prompt(
    moments_batch: list[tuple[int, dict[str, Any], list[dict[str, Any]]]],
    game_context: dict[str, str],
    is_retry: bool = False,
    all_pbp_events: list[dict[str, Any]] | None = None,
) -> str:
    """Build an OpenAI prompt for a batch of moments.

    Generates multi-sentence narratives (2-4 sentences) that describe
    the full sequence of gameplay within each moment.

    Args:
        moments_batch: List of (moment_index, moment, moment_plays) tuples
        game_context: Team names and sport info
        is_retry: Whether this is a retry after validation failure
        all_pbp_events: Full PBP event list for computing running stats

    Returns:
        Prompt string for OpenAI to generate all narratives in the batch
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")
    player_names = game_context.get("player_names", {})

    # Build player name reference for the prompt (abbrev -> full name)
    name_mappings = []
    for abbrev, full in player_names.items():
        if ". " in abbrev:  # Only abbreviated forms like "D. Mitchell"
            name_mappings.append(f"{abbrev}={full}")

    # Limit to avoid bloating prompt
    name_ref = ", ".join(name_mappings[:40]) if name_mappings else ""

    # Build compact moments data with contextual stats
    moments_lines = []
    for moment_index, moment, moment_plays in moments_batch:
        period = moment.get("period", 1)
        clock = moment.get("start_clock", "")
        score_before = moment.get("score_before", [0, 0])
        score_after = moment.get("score_after", [0, 0])
        explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))

        # Compute lead context for this moment
        lead_ctx = compute_lead_context(score_before, score_after, home_team, away_team)

        # Compute running player stats if PBP events are available
        player_hints = []
        if all_pbp_events and moment_plays:
            first_play_idx = min(
                (p.get("play_index", 0) for p in moment_plays), default=0
            )
            running_stats = compute_running_player_stats(
                all_pbp_events, first_play_idx - 1
            )
            # Get hints for players in this moment
            moment_players = {p.get("player_name") for p in moment_plays if p.get("player_name")}
            for player in moment_players:
                if player in running_stats:
                    hint = format_player_stat_hint(player, running_stats[player])
                    if hint:
                        player_hints.append(hint)

        # Compact play format: just the essentials
        plays_compact = []
        for play in moment_plays:
            play_index = play.get("play_index")
            is_explicit = play_index in explicitly_narrated
            star = "*" if is_explicit else ""
            desc = play.get("description", "")
            if len(desc) > 100:
                desc = desc[:97] + "..."
            plays_compact.append(f"{star}{desc}")

        plays_str = "; ".join(plays_compact)
        score_change = ""
        if score_after != score_before:
            score_change = f" → {away_team} {score_after[0]}-{score_after[1]} {home_team}"

        # Build context line with lead info and player stats
        context_parts = []
        if lead_ctx.get("margin_description"):
            context_parts.append(f"Lead: {lead_ctx['margin_description']}")
        if player_hints:
            context_parts.append(f"Stats: {'; '.join(player_hints[:3])}")

        context_line = f" [{', '.join(context_parts)}]" if context_parts else ""

        moments_lines.append(
            f"[{moment_index}] Q{period} {clock} ({away_team} {score_before[0]}-{score_before[1]} {home_team}{score_change}){context_line}: {plays_str}"
        )

    moments_block = "\n".join(moments_lines)

    # Build prompt with player name rule
    name_rule = "- FULL NAME on first mention (e.g., \"Donovan Mitchell\"), LAST NAME only after. NEVER use initials like \"D. Mitchell\"."
    if name_ref:
        name_rule += f"\n  Names: {name_ref}"

    # Retry prompt is more explicit about requirements
    if is_retry:
        retry_warning = "\n\nIMPORTANT: Previous response failed validation. Ensure:\n- Each narrative is 2-4 sentences\n- All *starred plays are mentioned\n- No subjective adjectives (huge, dominant, electric)\n- No speculation about intent or psychology\n"
    else:
        retry_warning = ""

    # Style guidance for retry prompts
    if is_retry:
        style_emphasis = """
STYLE (must sound natural when read aloud):
- Vary sentence length (mix short and longer sentences)
- Don't start multiple sentences the same way
- Lead with actions, not statistics
- Avoid templated patterns like "X scored, then Y answered" repeated"""
    else:
        style_emphasis = ""

    prompt = f"""Write broadcast-style recaps for each moment. {away_team} vs {home_team}.
{retry_warning}
You are a sports broadcaster summarizing game action. DO NOT transcribe each play - instead, tell the STORY of what happened.

WHAT TO WRITE:
- Focus on OUTCOMES: who scored, the margin, scoring runs
- Use the [Lead: ...] context to describe how the score changed: "pushed the lead to 8" or "trimmed the deficit to 3"
- Use the [Stats: ...] context for player milestones: "his third three of the half" or "already at 12 points"
- Mention *starred plays by player name, but don't describe every play in sequence
- Write like you're giving a 10-second recap between commercials

STYLE:
- 2-3 SHORT punchy sentences, not long compound sentences
- Lead with the result, not the sequence of events
- Skip routine plays (rebounds, inbounds) unless they led to something
{name_rule}
{style_emphasis}

GOOD EXAMPLES:
"Miami opened with a quick 5-0 run, Adebayo draining a three on the first possession. Chicago answered through Smith, who finished with a dunk to cut it to one."

"The Bulls went on a 7-0 run to take their first lead. Vučević's jumper capped the spurt, putting Chicago up 12-10."

"Back-to-back turnovers led to easy Miami points. Larsson converted at the line to extend the lead to four."

BAD (too play-by-play):
"Adebayo won the tip and Powell got the ball. Adebayo then made a three-pointer from 26 feet. Smith made a jump shot. Wiggins made a layup assisted by Jakučionis."

FORBIDDEN: dominant, electric, huge, massive, incredible, clutch, momentum, turning point, crowd erupted, wanted to, felt

{moments_block}

JSON: {{"items":[{{"i":0,"n":"recap"}},...]}}"""

    return prompt


def build_moment_prompt(
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    game_context: dict[str, str],
    moment_index: int,
    is_retry: bool = False,
) -> str:
    """Build the OpenAI prompt for a single moment.

    Generates broadcast-style recaps that summarize the action.

    Args:
        moment: The moment data
        moment_plays: PBP events for the moment
        game_context: Team names and sport info
        moment_index: Index of this moment
        is_retry: Whether this is a retry after validation failure

    Returns:
        Prompt string for OpenAI
    """
    home_team = game_context.get("home_team_name", "Home")
    away_team = game_context.get("away_team_name", "Away")
    player_names = game_context.get("player_names", {})

    period = moment.get("period", 1)
    clock = moment.get("start_clock", "")
    score_before = moment.get("score_before", [0, 0])
    score_after = moment.get("score_after", [0, 0])
    explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))

    # Compute scoring context
    away_pts = score_after[0] - score_before[0]
    home_pts = score_after[1] - score_before[1]
    lead_after = score_after[1] - score_after[0]  # positive = home leads

    # Build play descriptions
    plays_desc = []
    for play in moment_plays:
        play_index = play.get("play_index")
        is_explicit = play_index in explicitly_narrated
        marker = "*" if is_explicit else ""
        desc = play.get("description", "No description")
        plays_desc.append(f"  {marker}{desc}")

    plays_block = "\n".join(plays_desc)

    # Player name mappings
    name_mappings = []
    for abbrev, full in player_names.items():
        if ". " in abbrev:
            name_mappings.append(f"{abbrev}={full}")
    name_ref = ", ".join(name_mappings[:30]) if name_mappings else ""

    name_rule = "Use FULL NAME on first mention, LAST NAME only after."
    if name_ref:
        name_rule += f" Names: {name_ref}"

    if is_retry:
        retry_note = "\n\nPREVIOUS RESPONSE FAILED. Mention all *starred plays by player name.\n"
    else:
        retry_note = ""

    # Build margin context
    if lead_after > 0:
        margin_ctx = f"{home_team} leads by {lead_after}"
    elif lead_after < 0:
        margin_ctx = f"{away_team} leads by {abs(lead_after)}"
    else:
        margin_ctx = "Game tied"

    prompt = f"""Write a broadcast-style recap (2-3 sentences). {away_team} vs {home_team}.
{retry_note}
Q{period} at {clock}
Score: {away_team} {score_before[0]}-{score_before[1]} {home_team} → {away_team} {score_after[0]}-{score_after[1]} {home_team}
Scoring: {away_team} +{away_pts}, {home_team} +{home_pts}. {margin_ctx}.

Plays:
{plays_block}

Write like a broadcaster giving a quick recap:
- Focus on the outcome and margin, not every play
- Mention *starred players naturally
- {name_rule}
- 2-3 SHORT sentences

FORBIDDEN: dominant, electric, huge, momentum, turning point, wanted to, felt

Respond with ONLY the recap text."""

    return prompt
