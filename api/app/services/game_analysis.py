"""
Game Analysis: Timeline partitioning + AI enrichment into narrative moments.

ARCHITECTURE:
1. partition_game() - Creates moments from timeline (Lead Ladder + merge logic)
2. enrich_game_moments() - Adds AI headlines/summaries (single OpenAI call per game)

OpenAI is a NARRATIVE RENDERER, not a decision engine.
- All structure (boundaries, importance, order) decided BEFORE AI is called
- AI adds energy, momentum, pressure language
- If AI fails, the build fails (no silent fallbacks)

NO LEGACY FALLBACKS. If this system fails, it fails loudly.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Sequence

from .ai_client import (
    GameContext,
    MomentEnrichmentInput,
    enrich_game_moments,
)
from .moments import Moment, partition_game

logger = logging.getLogger(__name__)


# Sport-specific Lead Ladder thresholds
# These define the point margins that represent meaningful lead tiers
SPORT_THRESHOLDS: dict[str, list[int]] = {
    "NBA": [3, 6, 10, 16],      # NBA: 3-pt game, 6-pt (2 poss), 10+ comfortable, 16+ blowout
    "NCAAB": [3, 6, 10, 16],    # College basketball similar to NBA
    "NHL": [1, 2, 3],           # Hockey: 1 goal, 2 goals, 3+ goals
    "NFL": [3, 7, 14, 21],      # Football: FG, TD, 2 TDs, 3 TDs
    "MLB": [1, 2, 4],           # Baseball: 1 run, 2 runs, 4+ runs
}

DEFAULT_THRESHOLDS = [3, 6, 10, 16]  # Default to NBA-style


def get_thresholds_for_sport(sport: str) -> list[int]:
    """Get Lead Ladder thresholds for a sport."""
    return SPORT_THRESHOLDS.get(sport.upper(), DEFAULT_THRESHOLDS)


def _format_time_window(moment: Moment, summary: dict[str, Any]) -> str:
    """
    Format a time window string for AI context.
    
    Examples: "Q1 12:00-11:18", "Q4 2:30-1:45"
    """
    # Clock is already in the moment
    if moment.clock:
        return moment.clock
    return f"Play {moment.start_play}-{moment.end_play}"


def _build_enrichment_inputs(
    moments: list[Moment],
    summary: dict[str, Any],
) -> list[MomentEnrichmentInput]:
    """
    Convert Moment objects to MomentEnrichmentInput for AI.
    
    This prepares the data the AI needs without giving it decision power.
    """
    inputs = []
    for m in moments:
        # Build reason dict
        reason_dict = {}
        if m.reason:
            reason_dict = {
                "trigger": m.reason.trigger,
                "control_shift": m.reason.control_shift,
                "narrative_delta": m.reason.narrative_delta,
            }
        
        # Build run info if present
        run_info = None
        if m.run_info:
            run_info = {
                "team": m.run_info.team,
                "points": m.run_info.points,
                "unanswered": m.run_info.unanswered,
            }
        
        inputs.append(MomentEnrichmentInput(
            id=m.id,
            type=m.type.value,
            score_before=f"{m.score_before[1]}-{m.score_before[0]}",  # away-home format
            score_after=f"{m.score_after[1]}-{m.score_after[0]}",
            time_window=_format_time_window(m, summary),
            reason=reason_dict,
            team_in_control=m.team_in_control,
            run_info=run_info,
            key_plays=[],  # Could expand with actual play descriptions if needed
        ))
    
    return inputs


def _apply_enrichment_to_moments(
    moments: list[Moment],
    enrichment_map: dict[str, tuple[str, str]],
) -> None:
    """
    Apply AI-generated headlines/summaries back to Moment objects.
    
    Modifies moments in place.
    """
    for m in moments:
        if m.id in enrichment_map:
            headline, summary = enrichment_map[m.id]
            m.headline = headline
            m.summary = summary


def build_game_analysis(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Analyze a game timeline into moments (sync, no AI enrichment).

    For AI enrichment, use build_game_analysis_async().
    """
    summary_with_sport = {**summary, "sport": sport}
    
    thresholds = get_thresholds_for_sport(sport)
    moments = partition_game(timeline, summary_with_sport, thresholds=thresholds)

    return {
        "moments": [m.to_dict() for m in moments],
        "game_headline": "",
        "game_subhead": "",
    }


async def build_game_analysis_async(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    game_id: int,
    sport: str = "NBA",
    timeline_version: str | None = None,
) -> dict[str, Any]:
    """
    Analyze a game timeline into moments with AI enrichment.
    
    This is the full pipeline:
    1. partition_game() - Create moments from timeline
    2. enrich_game_moments() - Add AI headlines/summaries (single OpenAI call)
    
    Args:
        timeline: Full timeline events (PBP + social)
        summary: Game summary metadata
        game_id: Database game ID (for caching/logging)
        sport: Sport code (NBA, NHL, NFL, etc.)
        timeline_version: Version string for cache invalidation
        
    Returns:
        {
            "moments": [...],       # Moments with AI headlines/summaries
            "game_headline": "...", # AI-generated game headline
            "game_subhead": "...",  # AI-generated game subhead
        }
        
    Raises:
        AIConfigurationError: If OPENAI_API_KEY is not set
        AIEnrichmentError: If OpenAI call fails
        AIValidationError: If AI output is invalid
    """
    summary_with_sport = {**summary, "sport": sport}
    
    # Step 1: Partition game into moments
    thresholds = get_thresholds_for_sport(sport)
    moments = partition_game(timeline, summary_with_sport, thresholds=thresholds)
    
    if not moments:
        logger.warning("game_analysis_no_moments", extra={"game_id": game_id})
        return {
            "moments": [],
            "game_headline": "",
            "game_subhead": "",
        }
    
    # Generate version if not provided
    version = timeline_version or str(uuid.uuid4())[:8]
    
    # Step 2: Build context for AI
    home_team = summary.get("home_team", {}).get("name", "Home")
    away_team = summary.get("away_team", {}).get("name", "Away")
    
    # Get final score from last moment or summary
    final_home = summary.get("home_team", {}).get("score", 0)
    final_away = summary.get("away_team", {}).get("score", 0)
    
    # If summary doesn't have score, use last moment
    if final_home == 0 and final_away == 0 and moments:
        last_moment = moments[-1]
        final_home = last_moment.score_after[0]
        final_away = last_moment.score_after[1]
    
    game_context = GameContext(
        home_team=home_team,
        away_team=away_team,
        final_score_home=final_home,
        final_score_away=final_away,
        sport=sport.upper(),
    )
    
    # Step 3: Convert moments to AI input format
    enrichment_inputs = _build_enrichment_inputs(moments, summary)
    
    logger.info(
        "game_analysis_calling_ai",
        extra={
            "game_id": game_id,
            "moment_count": len(moments),
            "sport": sport,
        },
    )
    
    # Step 4: Call OpenAI (single call for all moments)
    enrichment = await enrich_game_moments(
        game_id=game_id,
        timeline_version=version,
        game_context=game_context,
        moments=enrichment_inputs,
    )
    
    # Step 5: Apply AI content back to moments
    enrichment_map = {
        m.id: (m.headline, m.summary)
        for m in enrichment.moments
    }
    _apply_enrichment_to_moments(moments, enrichment_map)
    
    logger.info(
        "game_analysis_complete",
        extra={
            "game_id": game_id,
            "moment_count": len(moments),
            "game_headline": enrichment.game_headline[:50] if enrichment.game_headline else "",
        },
    )
    
    return {
        "moments": [m.to_dict() for m in moments],
        "game_headline": enrichment.game_headline,
        "game_subhead": enrichment.game_subhead,
    }
