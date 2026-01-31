"""Prompt construction for OpenAI narrative generation.

This module builds prompts for the OpenAI API to generate moment narratives.
"""

from __future__ import annotations

from typing import Any


def build_batch_prompt(
    moments_batch: list[tuple[int, dict[str, Any], list[dict[str, Any]]]],
    game_context: dict[str, str],
    is_retry: bool = False,
) -> str:
    """Build an OpenAI prompt for a batch of moments.

    Generates multi-sentence narratives (2-4 sentences) that describe
    the full sequence of gameplay within each moment.

    Args:
        moments_batch: List of (moment_index, moment, moment_plays) tuples
        game_context: Team names and sport info
        is_retry: Whether this is a retry after validation failure

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

    # Build compact moments data
    moments_lines = []
    for moment_index, moment, moment_plays in moments_batch:
        period = moment.get("period", 1)
        clock = moment.get("start_clock", "")
        score_before = moment.get("score_before", [0, 0])
        score_after = moment.get("score_after", [0, 0])
        explicitly_narrated = set(moment.get("explicitly_narrated_play_ids", []))

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
        moments_lines.append(
            f"[{moment_index}] Q{period} {clock} ({away_team} {score_before[0]}-{score_before[1]} {home_team}{score_change}): {plays_str}"
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

    prompt = f"""Write 2-4 sentence narratives for each moment. {away_team} vs {home_team}.
{retry_warning}
Each narrative should:
- Describe the SEQUENCE of actions across the moment (not just one play)
- Reference ALL *starred plays (these MUST appear in the narrative)
- Use plain factual language like a neutral broadcast recap
- Follow chronological order
- Sound natural when read aloud (like a broadcast recap, not a stat sheet)

REQUIRED format:
{name_rule}
- Vary sentence length naturally (mix short and compound sentences)
- Vary sentence openers (don't start every sentence the same way)
- Lead with actions, not statistics
- Allowed: scoring runs, unanswered points, responses
{style_emphasis}
FORBIDDEN (will fail validation):
- Subjective adjectives: dominant, electric, huge, massive, incredible, clutch
- Speculation: wanted to, tried to, felt, seemed to
- Crowd/atmosphere: crowd erupted, fans, energy
- Metaphors: took over, caught fire, in the zone
- Summary language: momentum, turning point, crucial, pivotal
- Metric-first sentences: "Mitchell scored 12 points" (say action first)

GOOD: "The Suns opened with back-to-back baskets before the Lakers answered with a three. Mitchell converted in transition. The lead grew to five."

BAD: "The Suns scored. The Lakers scored. The Suns scored again." (repetitive structure)
BAD: "Mitchell scored 12 points in the quarter." (metric-first)

{moments_block}

JSON: {{"items":[{{"i":0,"n":"2-4 sentence narrative"}},...]}}"""

    return prompt


def build_moment_prompt(
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
    game_context: dict[str, str],
    moment_index: int,
    is_retry: bool = False,
) -> str:
    """Build the OpenAI prompt for a single moment.

    Generates multi-sentence narratives (2-4 sentences) that describe
    the full sequence of gameplay within the moment.

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

    # Build play descriptions
    plays_desc = []
    for play in moment_plays:
        play_index = play.get("play_index")
        is_explicit = play_index in explicitly_narrated
        marker = "[MUST REFERENCE]" if is_explicit else ""
        desc = play.get("description", "No description")
        plays_desc.append(f"  {marker} {desc}")

    plays_block = "\n".join(plays_desc)

    # Player name mappings
    name_mappings = []
    for abbrev, full in player_names.items():
        if ". " in abbrev:
            name_mappings.append(f"{abbrev}={full}")
    name_ref = ", ".join(name_mappings[:30]) if name_mappings else ""

    name_rule = "Use FULL NAME on first mention, LAST NAME only after. NEVER use initials."
    if name_ref:
        name_rule += f" Names: {name_ref}"

    if is_retry:
        retry_note = "\n\nPREVIOUS RESPONSE FAILED VALIDATION. Requirements:\n- 2-4 sentences\n- All [MUST REFERENCE] plays mentioned\n- No subjective adjectives\n"
    else:
        retry_note = ""

    prompt = f"""Write a 2-4 sentence narrative for this moment. {away_team} vs {home_team}.
{retry_note}
Context: Q{period} at {clock}
Score: {away_team} {score_before[0]} - {home_team} {score_before[1]} → {away_team} {score_after[0]} - {home_team} {score_after[1]}

Plays:
{plays_block}

Rules:
- Describe the SEQUENCE of actions (not just one play)
- ALL [MUST REFERENCE] plays MUST appear in the narrative
- {name_rule}
- Plain factual language, neutral broadcast style
- Vary sentence length and structure

FORBIDDEN: momentum, turning point, dominant, electric, wanted to, felt, crowd erupted

Respond with ONLY the narrative text (2-4 sentences, no JSON)."""

    return prompt
