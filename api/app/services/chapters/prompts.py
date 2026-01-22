"""
AI Prompt Templates for Chapter-First Storytelling.

This module contains versioned, canonical prompt templates for AI generation.

ISSUE 10: Generate Per-Chapter Summaries Using Prior Context + Current Chapter Only

GUARANTEES:
- Sequential narration (no future knowledge)
- Callbacks only from provided context
- Observational, grounded voice
- No spoilers unless final chapter
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass

# Version tracking for prompt evolution
PROMPT_VERSION = "1.0.0"
TITLE_PROMPT_VERSION = "1.0.0"
COMPACT_STORY_PROMPT_VERSION = "1.0.0"


# ============================================================================
# CHAPTER SUMMARY PROMPT (NBA V1)
# ============================================================================

CHAPTER_SUMMARY_PROMPT_V1 = """You are a sportscaster narrating NBA game highlights as you watch them unfold, one segment at a time.

You are currently watching Chapter {chapter_index} of this game.

## CONTEXT FROM EARLIER CHAPTERS

You have already narrated these earlier segments:

{prior_summaries}

## CURRENT GAME STATE (SO FAR)

Based on what you've seen through the previous chapters:

**Players (Top Performers So Far):**
{player_summary}

**Teams:**
{team_summary}

**Momentum:** {momentum}

**Themes:** {themes}

## THIS CHAPTER (Chapter {chapter_index})

**Period:** {period}
**Time Range:** {time_range}
**Why This Chapter Started:** {reason_codes}

**Plays in This Chapter:**
{plays}

## YOUR TASK

Write a 1-3 sentence summary of THIS CHAPTER ONLY.

**Voice:**
- Sportscaster watching highlights for the first time
- Observational, energetic, grounded
- No box-score listing, no play-by-play regurgitation

**Allowed:**
- Reference earlier chapters naturally ("Collier stayed aggressive after his strong first three quarters...")
- Use "so far" language ("already had 20", "kept pressing")
- Describe what you see in THIS chapter

**NOT Allowed:**
- Future knowledge ("would finish with", "that sealed it", "the dagger")
- Final outcomes ("ended with", "finished the game")
- Predictions ("was on his way to", "would never recover")
- Spoilers about later chapters

{final_chapter_note}

**Output Format:**
Return ONLY a JSON object with this structure:
{{
  "chapter_summary": "1-3 sentence summary of this chapter"
}}

Do not include any other text outside the JSON object.

Note: Chapter titles are generated separately from summaries.
"""

FINAL_CHAPTER_NOTE = """
⚠️ **SPECIAL NOTE: This is the FINAL CHAPTER of the game.**
You may use conclusive language ("sealed it", "finished with") since the game is over.
"""


# ============================================================================
# PROMPT BUILDER
# ============================================================================

@dataclass
class ChapterPromptContext:
    """Context for building chapter summary prompt."""
    
    chapter_index: int
    prior_summaries: list[str]
    player_summary: str
    team_summary: str
    momentum: str
    themes: str
    period: str
    time_range: str
    reason_codes: str
    plays: str
    is_final_chapter: bool = False


def build_chapter_summary_prompt(context: ChapterPromptContext) -> str:
    """Build chapter summary prompt from context.
    
    Args:
        context: Prompt context with all required fields
        
    Returns:
        Formatted prompt string
    """
    # Format prior summaries
    if context.prior_summaries:
        prior_text = "\n".join([
            f"Chapter {i}: {summary}"
            for i, summary in enumerate(context.prior_summaries)
        ])
    else:
        prior_text = "(This is the first chapter - no prior context)"
    
    # Final chapter note
    final_note = FINAL_CHAPTER_NOTE if context.is_final_chapter else ""
    
    # Build prompt
    prompt = CHAPTER_SUMMARY_PROMPT_V1.format(
        chapter_index=context.chapter_index,
        prior_summaries=prior_text,
        player_summary=context.player_summary,
        team_summary=context.team_summary,
        momentum=context.momentum,
        themes=context.themes,
        period=context.period,
        time_range=context.time_range,
        reason_codes=context.reason_codes,
        plays=context.plays,
        final_chapter_note=final_note,
    )
    
    return prompt


def format_player_summary(players: dict[str, Any]) -> str:
    """Format player signals for prompt.
    
    Args:
        players: Player signals from StoryState
        
    Returns:
        Formatted player summary
    """
    if not players:
        return "(No significant player stats yet)"
    
    lines = []
    for name, player in players.items():
        notable = ", ".join(player["notable_actions_so_far"]) if player.get("notable_actions_so_far") else "none"
        lines.append(
            f"- {name}: {player['points_so_far']} pts "
            f"({player['made_fg_so_far']} FG, {player['made_3pt_so_far']} 3PT) | "
            f"Notable: {notable}"
        )
    
    return "\n".join(lines)


def format_team_summary(teams: dict[str, Any]) -> str:
    """Format team signals for prompt.
    
    Args:
        teams: Team signals from StoryState
        
    Returns:
        Formatted team summary
    """
    if not teams:
        return "(No team scores available)"
    
    lines = []
    for name, team in teams.items():
        score = f"{team['score_so_far']} pts" if team.get('score_so_far') is not None else "score unknown"
        lines.append(f"- {name}: {score}")
    
    return "\n".join(lines)


def format_plays_for_prompt(plays: list[Any]) -> str:
    """Format plays for prompt.
    
    Args:
        plays: List of Play objects
        
    Returns:
        Formatted plays string
    """
    if not plays:
        return "(No plays in this chapter)"
    
    lines = []
    for i, play in enumerate(plays, 1):
        desc = play.raw_data.get("description", "")
        clock = play.raw_data.get("game_clock", "")
        lines.append(f"{i}. {desc} ({clock})")
    
    return "\n".join(lines)


# ============================================================================
# SPOILER DETECTION
# ============================================================================

# Banned phrases that indicate future knowledge or finality
BANNED_PHRASES = [
    "finished with",
    "ended with",
    "would finish",
    "would end",
    "sealed it",
    "sealed the game",
    "the dagger",
    "that was the dagger",
    "would never recover",
    "couldn't recover",
    "was over",
    "game over",
    "put it away",
    "put the game away",
    "closed it out",
    "on his way to",
    "was going to",
    "would go on to",
]

# Phrases that are allowed only in final chapter
FINAL_CHAPTER_ONLY_PHRASES = [
    "sealed",
    "finished",
    "ended",
    "final",
    "closed out",
]


def check_for_spoilers(text: str, is_final_chapter: bool = False) -> list[str]:
    """Check text for spoiler phrases.
    
    Args:
        text: Text to check
        is_final_chapter: Whether this is the final chapter
        
    Returns:
        List of found spoiler phrases
    """
    text_lower = text.lower()
    found = []
    
    # Check banned phrases
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            found.append(phrase)
    
    # Check final-chapter-only phrases (if not final)
    if not is_final_chapter:
        for phrase in FINAL_CHAPTER_ONLY_PHRASES:
            if phrase in text_lower:
                # Check if it's used in a finality context
                # Simple heuristic: if followed by "the game", "it", etc.
                if any(finality in text_lower for finality in ["the game", "it out", "the win"]):
                    found.append(f"{phrase} (finality context)")
    
    return found


# ============================================================================
# CHAPTER TITLE PROMPT (NBA V1)
# ============================================================================

CHAPTER_TITLE_PROMPT_V1 = """You are creating a short, punchy title for a chapter of an NBA game story.

## CHAPTER SUMMARY

The chapter has already been summarized as:

"{chapter_summary}"

## CHAPTER METADATA

- Chapter Index: {chapter_index}
- Period: {period}
- Time Range: {time_range}
- Why This Chapter Started: {reason_codes}

{final_chapter_note}

## YOUR TASK

Create a short title (3-8 words) that:

**Must:**
- Reflect the primary story beat from the summary
- Be descriptive, not declarative
- Work as a UI label/bookmark
- Use title case

**Must NOT:**
- Add any new information beyond the summary
- Include numbers, stats, or scores
- Include timestamps or quarter references
- Imply future outcomes or finality (unless final chapter)
- Use hype language ("epic", "insane", "unbelievable")

**Examples of Good Titles:**
- "Utah Pushes the Pace"
- "Minnesota Answers Back"
- "Tension Builds Late"
- "Closing Chaos"

**Examples of Bad Titles:**
- "Utah Goes Up 12" (includes score)
- "George's Dagger Three" (implies finality)
- "Final Minutes" (timestamp)
- "Fourth Quarter Run" (quarter reference)

**Output Format:**
Return ONLY a JSON object:
{{
  "chapter_title": "Your Title Here"
}}

Do not include any other text outside the JSON object.
"""

TITLE_FINAL_CHAPTER_NOTE = """
⚠️ **SPECIAL NOTE: This is the FINAL CHAPTER.**
You may use conclusive language since the game is over.
"""


@dataclass
class TitlePromptContext:
    """Context for building chapter title prompt."""
    
    chapter_index: int
    chapter_summary: str
    period: str
    time_range: str
    reason_codes: str
    is_final_chapter: bool = False


def build_chapter_title_prompt(context: TitlePromptContext) -> str:
    """Build chapter title prompt from context.
    
    Args:
        context: Title prompt context
        
    Returns:
        Formatted prompt string
    """
    final_note = TITLE_FINAL_CHAPTER_NOTE if context.is_final_chapter else ""
    
    prompt = CHAPTER_TITLE_PROMPT_V1.format(
        chapter_summary=context.chapter_summary,
        chapter_index=context.chapter_index,
        period=context.period,
        time_range=context.time_range,
        reason_codes=context.reason_codes,
        final_chapter_note=final_note,
    )
    
    return prompt


# ============================================================================
# TITLE VALIDATION
# ============================================================================

# Banned words in titles (indicate finality or stats)
TITLE_BANNED_WORDS = [
    "dagger",
    "sealed",
    "clinched",
    "final",
    "finished",
    "ended",
    "won",
    "lost",
    "victory",
    "defeat",
]

# Words that are only allowed in final chapter titles
TITLE_FINAL_ONLY_WORDS = [
    "closing",
    "finish",
    "end",
]


def validate_title_length(title: str) -> bool:
    """Validate title length (3-8 words).
    
    Args:
        title: Title to validate
        
    Returns:
        True if valid length
    """
    word_count = len(title.split())
    return 3 <= word_count <= 8


def check_title_for_numbers(title: str) -> bool:
    """Check if title contains numbers.
    
    Args:
        title: Title to check
        
    Returns:
        True if title contains numbers (invalid)
    """
    return any(char.isdigit() for char in title)


def check_title_for_spoilers(title: str, is_final_chapter: bool = False) -> list[str]:
    """Check title for spoiler words.
    
    Args:
        title: Title to check
        is_final_chapter: Whether this is the final chapter
        
    Returns:
        List of found spoiler words
    """
    title_lower = title.lower()
    found = []
    
    # Check banned words
    for word in TITLE_BANNED_WORDS:
        if word in title_lower:
            found.append(word)
    
    # Check final-only words (if not final)
    if not is_final_chapter:
        for word in TITLE_FINAL_ONLY_WORDS:
            if word in title_lower:
                found.append(f"{word} (final-only)")
    
    return found


def validate_title(
    title: str,
    is_final_chapter: bool = False,
    check_numbers: bool = True,
    check_spoilers: bool = True,
) -> dict[str, Any]:
    """Validate title against all rules.
    
    Args:
        title: Title to validate
        is_final_chapter: Whether this is the final chapter
        check_numbers: Whether to check for numbers
        check_spoilers: Whether to check for spoilers
        
    Returns:
        Dict with validation results
    """
    issues = []
    
    # Length check
    if not validate_title_length(title):
        word_count = len(title.split())
        issues.append(f"Invalid length: {word_count} words (must be 3-8)")
    
    # Numbers check
    if check_numbers and check_title_for_numbers(title):
        issues.append("Contains numbers (not allowed)")
    
    # Spoiler check
    if check_spoilers:
        spoilers = check_title_for_spoilers(title, is_final_chapter)
        if spoilers:
            issues.append(f"Contains spoiler words: {', '.join(spoilers)}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


# ============================================================================
# COMPACT STORY PROMPT (NBA V1)
# ============================================================================

COMPACT_STORY_PROMPT_V1 = """You are a sportscaster writing a cohesive game recap for an NBA game.

You have already narrated this game chapter-by-chapter. Now, synthesize those chapters into a single, readable story that captures the full arc of the game.

## CHAPTER SUMMARIES

Here are the chapter summaries you created, in order:

{chapter_summaries}

## YOUR TASK

Write a compact game story (4-12 minutes of reading time) that:

**Must:**
- Use ONLY the information from the chapter summaries above
- Create a cohesive narrative with clear beginning → middle → end
- Use paragraph-based prose (not bullets)
- Tie together themes and momentum with hindsight
- Include smooth transitions between chapters
- Have a clear closing paragraph

**May:**
- Use hindsight framing ("That early push set the tone...")
- Make thematic callbacks across chapters
- Use clear closing language in the final paragraph
- Reframe earlier moments with full context

**Must NOT:**
- Invent events not present in summaries
- Add stats not implied by summaries
- Contradict chapter summaries
- Use play-by-play listing
- Over-hype ("instant classic", "all-time performance") unless summaries imply it

**Voice:**
- Sportscaster recap tone
- Engaging and readable
- Observational, grounded
- Natural flow between sections

**Structure:**
- Opening: Set the scene and tone
- Middle: Progress through the game's narrative arc
- Closing: Conclude with the outcome and key takeaways

**Output Format:**
Return ONLY a JSON object:
{{
  "compact_story": "Your multi-paragraph story here. Use \\n\\n for paragraph breaks."
}}

Do not include any other text outside the JSON object.
"""


@dataclass
class CompactStoryPromptContext:
    """Context for building compact story prompt."""
    
    chapter_summaries: list[str]
    chapter_titles: list[str] | None = None
    sport: str = "NBA"
    teams: list[str] | None = None
    game_metadata: dict[str, Any] | None = None


def build_compact_story_prompt(context: CompactStoryPromptContext) -> str:
    """Build compact story prompt from context.
    
    Args:
        context: Compact story prompt context
        
    Returns:
        Formatted prompt string
    """
    # Format chapter summaries
    if context.chapter_titles and len(context.chapter_titles) == len(context.chapter_summaries):
        # Include titles if available
        summaries_text = "\n\n".join([
            f"Chapter {i}: {title}\n{summary}"
            for i, (title, summary) in enumerate(zip(context.chapter_titles, context.chapter_summaries))
        ])
    else:
        # Just summaries
        summaries_text = "\n\n".join([
            f"Chapter {i}: {summary}"
            for i, summary in enumerate(context.chapter_summaries)
        ])
    
    prompt = COMPACT_STORY_PROMPT_V1.format(
        chapter_summaries=summaries_text,
    )
    
    return prompt


# ============================================================================
# COMPACT STORY VALIDATION
# ============================================================================

def estimate_reading_time(text: str, words_per_minute: int = 200) -> float:
    """Estimate reading time in minutes.
    
    Args:
        text: Text to estimate
        words_per_minute: Average reading speed
        
    Returns:
        Estimated reading time in minutes
    """
    word_count = len(text.split())
    return word_count / words_per_minute


def validate_compact_story_length(text: str, min_minutes: float = 4.0, max_minutes: float = 12.0) -> dict[str, Any]:
    """Validate compact story length.
    
    Args:
        text: Story text
        min_minutes: Minimum reading time
        max_minutes: Maximum reading time
        
    Returns:
        Validation result
    """
    reading_time = estimate_reading_time(text)
    word_count = len(text.split())
    
    issues = []
    if reading_time < min_minutes:
        issues.append(f"Too short: {reading_time:.1f} min (min {min_minutes})")
    elif reading_time > max_minutes:
        issues.append(f"Too long: {reading_time:.1f} min (max {max_minutes})")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "reading_time_minutes": reading_time,
        "word_count": word_count,
    }


def check_for_new_proper_nouns(
    compact_story: str,
    chapter_summaries: list[str],
) -> list[str]:
    """Check if compact story introduces new proper nouns.
    
    This is a simple heuristic to detect potential contradictions.
    
    Args:
        compact_story: Generated compact story
        chapter_summaries: Original chapter summaries
        
    Returns:
        List of potentially new proper nouns
    """
    # Extract capitalized words (simple heuristic for proper nouns)
    import re
    
    # Get proper nouns from summaries
    summary_text = " ".join(chapter_summaries)
    summary_nouns = set(re.findall(r'\b[A-Z][a-z]+\b', summary_text))
    
    # Get proper nouns from compact story
    story_nouns = set(re.findall(r'\b[A-Z][a-z]+\b', compact_story))
    
    # Find new nouns (excluding common words)
    common_words = {"The", "A", "An", "In", "On", "At", "To", "For", "With", "By", "From", "Of"}
    new_nouns = story_nouns - summary_nouns - common_words
    
    return list(new_nouns)

