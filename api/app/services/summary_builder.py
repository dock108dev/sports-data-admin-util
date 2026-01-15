"""
Summary generation for game timelines.

This module generates "reading guides" for timelines, not traditional recaps.
Summaries are built exclusively from timeline artifacts.

Related modules:
- timeline_generator.py: Main timeline assembly
- ai_client.py: AI generation for summary text
- game_analysis.py: Segment/highlight extraction

See docs/SUMMARY_GENERATION.md for the contract.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .. import db_models
from .ai_client import generate_summary, is_ai_available

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def build_nba_summary(game: db_models.SportsGame) -> dict[str, Any]:
    """
    Extract basic game metadata for internal use.

    INTERNAL ONLY: This function provides team IDs, names, and final scores
    for use by build_summary_from_timeline(). It does NOT generate narrative
    content. All narrative must come from the timeline artifact.

    Returns:
        dict with teams (id/name), final_score, and flow classification
    """
    home_name = game.home_team.name if game.home_team else "Home"
    away_name = game.away_team.name if game.away_team else "Away"
    home_score = game.home_score
    away_score = game.away_score

    flow = "unknown"
    if home_score is not None and away_score is not None:
        diff = abs(home_score - away_score)
        if diff <= 5:
            flow = "close"
        elif diff <= 12:
            flow = "competitive"
        elif diff <= 20:
            flow = "comfortable"
        else:
            flow = "blowout"

    return {
        "teams": {
            "home": {"id": game.home_team_id, "name": home_name},
            "away": {"id": game.away_team_id, "name": away_name},
        },
        "final_score": {"home": home_score, "away": away_score},
        "flow": flow,
    }


def _format_score_context(
    score: dict[str, int], home_name: str, away_name: str
) -> str:
    return f"{away_name} {score['away']}, {home_name} {score['home']}"


def _winner_info(
    summary: dict[str, Any]
) -> tuple[str | None, int | None, int | None]:
    home_score = summary["final_score"]["home"]
    away_score = summary["final_score"]["away"]
    if home_score is None or away_score is None:
        return None, None, None
    if home_score > away_score:
        return summary["teams"]["home"]["name"], home_score, away_score
    if away_score > home_score:
        return summary["teams"]["away"]["name"], away_score, home_score
    return None, home_score, away_score


def _segment_narrative(
    segment: dict[str, Any],
    home_id: int,
    away_id: int,
    home_name: str,
    away_name: str,
) -> str:
    """Generate narrative text for a game segment."""
    segment_type = segment["segment_type"]
    teams_involved = segment["teams_involved"]
    start_score = segment["score_start"]
    end_score = segment["score_end"]
    score_delta = segment["score_delta"]
    start_context = _format_score_context(start_score, home_name, away_name)
    end_context = _format_score_context(end_score, home_name, away_name)

    if len(teams_involved) == 1:
        team_id = teams_involved[0]
        if team_id == home_id:
            team_name = home_name
            opponent_name = away_name
            team_delta = score_delta["home"]
            opponent_delta = score_delta["away"]
        elif team_id == away_id:
            team_name = away_name
            opponent_name = home_name
            team_delta = score_delta["away"]
            opponent_delta = score_delta["home"]
        else:
            team_name = "One side"
            opponent_name = "the opponent"
            team_delta = score_delta["home"] + score_delta["away"]
            opponent_delta = 0
        delta_phrase = f"{team_delta}-{opponent_delta}"
    else:
        team_name = "Both teams"
        opponent_name = "each other"
        delta_phrase = f"{score_delta['home']}-{score_delta['away']}"

    if segment_type == "opening":
        return (
            f"The opening stretch set the tone as {team_name} pushed the pace. "
            f"The score moved from {start_context} to {end_context}."
        )
    if segment_type == "run":
        return (
            f"{team_name} went on a run, outscoring {opponent_name} {delta_phrase} "
            f"from {start_context} to {end_context}."
        )
    if segment_type == "swing":
        return (
            "Momentum swung as the lead changed hands in this stretch. "
            f"The score flipped from {start_context} to {end_context}."
        )
    if segment_type == "close":
        return (
            "The finish tightened up, keeping the margin within striking distance. "
            f"The score inched from {start_context} to {end_context}."
        )
    if segment_type == "blowout":
        return (
            f"A lopsided burst opened the gap, pushing the score "
            f"from {start_context} to {end_context}."
        )
    if segment_type == "garbage_time":
        return (
            f"With the outcome largely decided, the closing minutes drifted "
            f"from {start_context} to {end_context}."
        )
    return (
        f"The game stayed steady in this stretch, moving "
        f"from {start_context} to {end_context}."
    )


# =============================================================================
# MAIN SUMMARY BUILDERS
# =============================================================================


def build_summary_from_timeline(
    timeline: Sequence[dict[str, Any]],
    game_analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a READING GUIDE for the timeline, not a traditional recap.

    This summary:
    - Sets expectations for what kind of game this was
    - Points out where attention should increase while scrolling
    - Explains how the story unfolds as the timeline progresses

    It should feel incomplete without the timeline.
    Its purpose is to guide how the timeline is read, not replace it.

    See docs/SUMMARY_GENERATION.md for the contract.
    """
    # Extract basic info from timeline
    pbp_events = [e for e in timeline if e.get("event_type") == "pbp"]
    social_events = [e for e in timeline if e.get("event_type") == "tweet"]

    # Find final scores
    final_home_score: int | None = None
    final_away_score: int | None = None

    for event in reversed(pbp_events):
        if event.get("home_score") is not None and final_home_score is None:
            final_home_score = event["home_score"]
        if event.get("away_score") is not None and final_away_score is None:
            final_away_score = event["away_score"]
        if final_home_score is not None and final_away_score is not None:
            break

    # Extract team info from game_analysis
    summary_data = game_analysis.get("summary", {})
    home_name = summary_data.get("teams", {}).get("home", {}).get("name", "Home")
    away_name = summary_data.get("teams", {}).get("away", {}).get("name", "Away")
    home_team_id = summary_data.get("teams", {}).get("home", {}).get("id")
    away_team_id = summary_data.get("teams", {}).get("away", {}).get("id")

    # Compute flow classification
    flow = "unknown"
    if final_home_score is not None and final_away_score is not None:
        diff = abs(final_home_score - final_away_score)
        if diff <= 5:
            flow = "close"
        elif diff <= 12:
            flow = "competitive"
        elif diff <= 20:
            flow = "comfortable"
        else:
            flow = "blowout"

    # Determine winner
    winner_name: str | None = None
    if final_home_score is not None and final_away_score is not None:
        if final_home_score > final_away_score:
            winner_name = home_name
        elif final_away_score > final_home_score:
            winner_name = away_name

    # Analyze phases and social distribution
    phases_present = sorted(
        set(e.get("phase") for e in timeline if e.get("phase"))
    )
    has_overtime = any(p.startswith("ot") for p in phases_present)

    social_by_phase: dict[str, int] = {}
    for event in social_events:
        phase = event.get("phase", "unknown")
        social_by_phase[phase] = social_by_phase.get(phase, 0) + 1

    # Analyze highlights for attention points
    highlights = game_analysis.get("highlights", [])

    # Find key narrative moments
    scoring_runs = [h for h in highlights if h.get("highlight_type") == "scoring_run"]
    deciding_stretch = next(
        (h for h in highlights if h.get("highlight_type") == "game_deciding_stretch"),
        None,
    )

    # === BUILD THE READING GUIDE ===

    # Overview: 1-2 paragraphs setting expectations
    overview_parts: list[str] = []

    # Opening sentence - tone setting
    if flow == "blowout":
        overview_parts.append(
            f"This one gets away early. "
            f"{winner_name} takes control and never really lets go."
        )
    elif flow == "comfortable":
        overview_parts.append(
            f"A game that looks closer on paper than it felt. "
            f"{winner_name} stays in command through the middle quarters."
        )
    elif flow == "competitive":
        overview_parts.append(
            "Back and forth for most of it, with stretches where "
            "either team could take over."
        )
    elif flow == "close":
        if has_overtime:
            overview_parts.append(
                "This one needs extra time. The tension builds steadily, "
                "especially in the final minutes of regulation."
            )
        else:
            overview_parts.append(
                "Tight throughout. The kind of game where every possession "
                "in the fourth starts to matter."
            )
    else:
        overview_parts.append("A game worth scrolling through from start to finish.")

    # Second sentence - where to focus
    if scoring_runs:
        overview_parts.append(
            "Watch for the runs. There are stretches where momentum clearly swings."
        )

    # Third sentence - social atmosphere
    total_social = len(social_events)
    if total_social > 0:
        if social_by_phase.get("q4", 0) > 0 or social_by_phase.get("postgame", 0) > 3:
            overview_parts.append(
                "Reactions pick up as it winds down. You'll feel when the energy shifts."
            )
        elif social_by_phase.get("pregame", 0) > 0:
            overview_parts.append(
                "Some pre-game buzz sets the tone before things get going."
            )

    overview = " ".join(overview_parts)

    # Attention Points: Where to increase focus
    attention_points: list[str] = []

    # Opening stretch
    attention_points.append("The first few minutes set the early tempo")

    # Mid-game momentum
    if scoring_runs:
        if flow in ["blowout", "comfortable"]:
            attention_points.append(
                "A stretch in the second or third where the gap starts to open"
            )
        else:
            attention_points.append("Mid-game swings where control changes hands")

    # Late game
    if flow == "close":
        attention_points.append("The final minutes are where everything tightens")
    elif flow == "competitive":
        attention_points.append(
            "Watch the fourth. There's still something to play for"
        )
    elif deciding_stretch:
        attention_points.append("A decisive run that effectively ends it")
    else:
        attention_points.append("The closing stretch confirms the outcome")

    # Social clustering
    postgame_count = social_by_phase.get("postgame", 0)
    ingame_count = sum(
        social_by_phase.get(p, 0)
        for p in ["q1", "q2", "q3", "q4"] + [f"ot{i}" for i in range(1, 5)]
    )

    if ingame_count > 0:
        attention_points.append("In-game reactions mark the moments that landed")
    if postgame_count > 3:
        attention_points.append("Postgame reactions capture the aftermath")

    # === RETURN STRUCTURE ===
    return {
        # Metadata (preserved for compatibility)
        "teams": {
            "home": {"id": home_team_id, "name": home_name},
            "away": {"id": away_team_id, "name": away_name},
        },
        "final_score": {"home": final_home_score, "away": final_away_score},
        "flow": flow,
        "phases_in_timeline": phases_present,
        "social_counts": {
            "total": total_social,
            "by_phase": social_by_phase,
        },
        # Reading Guide (new primary output)
        "overview": overview,
        "attention_points": attention_points,
        # Legacy fields (deprecated but kept for compatibility)
        "overall_summary": overview,  # Alias for overview
        "closing_summary": "",  # Deprecated: reading guides don't "close"
        "segments": [],  # Deprecated: attention_points replaces this
    }


async def build_summary_from_timeline_async(
    timeline: Sequence[dict[str, Any]],
    game_analysis: dict[str, Any],
    game_id: int,
    timeline_version: str,
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Build a READING GUIDE for the timeline using AI generation.

    This is the primary summary generation function. It:
    1. Extracts facts from the timeline (deterministic)
    2. Uses AI to generate the reading guide text (cached)
    3. Returns metadata + AI-generated overview/attention points

    AI is grounded strictly in timeline + analysis data.
    AI output is cached permanently per (game_id, timeline_version).

    Falls back to template-based summary if AI is unavailable.
    """
    # First, get the template-based summary for metadata
    template_summary = build_summary_from_timeline(timeline, game_analysis)

    # If AI unavailable, return template summary
    if not is_ai_available():
        logger.info(
            "summary_using_template",
            extra={"game_id": game_id, "reason": "ai_unavailable"},
        )
        return template_summary

    # Extract facts for AI prompt
    phases_present = template_summary.get("phases_in_timeline", [])
    social_counts = template_summary.get("social_counts", {}).get("by_phase", {})

    # Build segment summaries from game_analysis with actual context
    segments = game_analysis.get("segments", [])
    segment_summaries = []
    for seg in segments[:6]:  # Limit to 6
        seg_type = seg.get("segment_type", "steady")
        ai_label = seg.get("ai_label", "")
        score_start = seg.get("score_start", {})
        score_end = seg.get("score_end", {})
        
        # Build a descriptive summary
        if ai_label:
            desc = f"{seg_type}: {ai_label}"
        else:
            start_str = f"{score_start.get('away', 0)}-{score_start.get('home', 0)}"
            end_str = f"{score_end.get('away', 0)}-{score_end.get('home', 0)}"
            desc = f"{seg_type} ({start_str} to {end_str})"
        segment_summaries.append(desc)

    # Build highlight summaries with descriptions
    highlights = game_analysis.get("highlights", [])
    highlight_summaries = []
    for h in highlights[:5]:  # Limit to 5
        h_type = h.get("highlight_type", "moment")
        h_desc = h.get("description")
        if h_desc:
            highlight_summaries.append(h_desc[:60])
        else:
            # Build from score context if available
            score_ctx = h.get("score_context", {})
            if score_ctx:
                highlight_summaries.append(
                    f"{h_type} at {score_ctx.get('margin', 0)} pt margin"
                )

    try:
        # Call AI for reading guide generation (cached)
        ai_summary = await generate_summary(
            game_id=game_id,
            timeline_version=timeline_version,
            phases=phases_present,
            segment_summaries=segment_summaries,
            highlights=highlight_summaries,
            social_counts=social_counts,
            sport=sport,
        )

        # Merge AI output with metadata
        result = {**template_summary}
        result["overview"] = ai_summary.get("overview", template_summary["overview"])
        result["attention_points"] = ai_summary.get(
            "attention_points", template_summary["attention_points"]
        )
        result["overall_summary"] = result["overview"]  # Legacy alias
        result["ai_generated"] = True

        logger.info(
            "summary_using_ai",
            extra={
                "game_id": game_id,
                "overview_len": len(result["overview"]),
                "attention_points": len(result["attention_points"]),
            },
        )
        return result

    except Exception as e:
        logger.warning(
            "summary_ai_fallback_to_template",
            extra={"game_id": game_id, "error": str(e)},
        )
        return template_summary
