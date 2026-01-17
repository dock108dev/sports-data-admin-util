"""
Summary generation for game timelines.

=============================================================================
DESIGN PHILOSOPHY (2026-01 Refactor)
=============================================================================

Summary generation is a TWO-LAYER system:

1. STRUCTURE (deterministic, from Moments):
   - Flow classification
   - Phase presence
   - Social distribution
   - Attention points (where to focus)

2. COPY (AI or fallback):
   - headline: One-line game description
   - subhead: Brief supporting context

AI CANNOT AFFECT STRUCTURE. It only writes copy based on
structured Moment data. This separation ensures:
- Deterministic behavior when AI fails
- No AI influence on importance or ordering
- Consistent results across regenerations

Related modules:
- moments.py: Lead Ladder-based partitioning
- ai_client.py: AI copy generation (headline/subhead only)

See docs/SUMMARY_GENERATION.md for the contract.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .. import db_models
from .ai_client import (
    GameSummaryInput,
    generate_fallback_headline,
    generate_headline,
    is_ai_available,
)
from .moments import Moment, MomentType

logger = logging.getLogger(__name__)


# =============================================================================
# FLOW CLASSIFICATION (Deterministic)
# =============================================================================

def classify_game_flow(score_diff: int) -> str:
    """
    Classify game flow based on final score difference.
    
    This is DETERMINISTIC - same input always gives same output.
    """
    if score_diff <= 5:
        return "close"
    elif score_diff <= 12:
        return "competitive"
    elif score_diff <= 20:
        return "comfortable"
    else:
        return "blowout"


# =============================================================================
# ATTENTION POINTS (Deterministic from Moments)
# =============================================================================

def generate_attention_points(
    moments: list[Moment],
    social_by_phase: dict[str, int],
    flow: str,
    has_overtime: bool,
) -> list[str]:
    """
    Generate attention points from Moments.
    
    These are DETERMINISTIC - derived purely from Moment structure.
    AI has no influence on what attention points are generated.
    
    Returns list of short phrases indicating where to focus.
    """
    points: list[str] = []
    
    # Get moment type counts
    type_counts: dict[MomentType, int] = {}
    for m in moments:
        type_counts[m.type] = type_counts.get(m.type, 0) + 1
    
    # Opening
    points.append("Opening minutes set the pace")
    
    # Mid-game based on moment types
    if type_counts.get(MomentType.FLIP, 0) > 0:
        points.append("Lead changes hands at least once")
    elif type_counts.get(MomentType.LEAD_BUILD, 0) >= 2:
        points.append("One team builds a lead early")
    elif type_counts.get(MomentType.CUT, 0) >= 2:
        points.append("Comeback attempt in the middle")
    
    # Late game based on flow
    if flow == "close":
        if has_overtime:
            points.append("Overtime decides it")
        else:
            points.append("Final minutes are where it tightens")
    elif flow == "competitive":
        points.append("Fourth quarter still has stakes")
    elif type_counts.get(MomentType.CLOSING_CONTROL, 0) > 0:
        points.append("A late run seals it")
    else:
        points.append("Outcome becomes clear late")
    
    # Social clustering
    postgame_count = social_by_phase.get("postgame", 0)
    ingame_count = sum(
        social_by_phase.get(p, 0)
        for p in ["q1", "q2", "q3", "q4"] + [f"ot{i}" for i in range(1, 5)]
    )
    
    if ingame_count > 0:
        points.append("In-game reactions mark key moments")
    if postgame_count > 3:
        points.append("Postgame reactions capture the aftermath")
    
    return points[:5]  # Limit to 5


# =============================================================================
# SUMMARY FROM GAME MODEL
# =============================================================================

def build_nba_summary(game: db_models.SportsGame) -> dict[str, Any]:
    """
    Extract basic game metadata from database model.
    
    INTERNAL ONLY: This provides team IDs, names, and scores
    for use by other summary functions.
    """
    home_name = game.home_team.name if game.home_team else "Home"
    away_name = game.away_team.name if game.away_team else "Away"
    home_score = game.home_score
    away_score = game.away_score

    flow = "unknown"
    if home_score is not None and away_score is not None:
        flow = classify_game_flow(abs(home_score - away_score))

    return {
        "teams": {
            "home": {"id": game.home_team_id, "name": home_name},
            "away": {"id": game.away_team_id, "name": away_name},
        },
        "final_score": {"home": home_score, "away": away_score},
        "flow": flow,
    }


# =============================================================================
# MAIN SUMMARY BUILDER (Synchronous, deterministic)
# =============================================================================

def build_summary_from_timeline(
    timeline: Sequence[dict[str, Any]],
    game_analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Build summary metadata from timeline (DETERMINISTIC).
    
    This function extracts structural information from the timeline
    and Moments. It does NOT call AI. All output is deterministic.
    
    For AI-generated copy (headline/subhead), use build_summary_from_timeline_async().
    """
    # Extract basic info
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

    # Compute flow classification (DETERMINISTIC)
    flow = "unknown"
    if final_home_score is not None and final_away_score is not None:
        flow = classify_game_flow(abs(final_home_score - final_away_score))

    # Analyze phases and social distribution
    phases_present = sorted(
        set(e.get("phase") for e in timeline if e.get("phase"))
    )
    has_overtime = any(p.startswith("ot") for p in phases_present)

    social_by_phase: dict[str, int] = {}
    for event in social_events:
        phase = event.get("phase", "unknown")
        social_by_phase[phase] = social_by_phase.get(phase, 0) + 1

    # Get moments from game_analysis
    moments_data = game_analysis.get("moments", [])
    moments = []
    for m in moments_data:
        # Convert dict to minimal Moment-like object for attention points
        # We only need the type field
        m_type_str = m.get("type", "NEUTRAL")
        try:
            m_type = MomentType(m_type_str)
        except ValueError:
            m_type = MomentType.NEUTRAL
        
        # Create a simple object with type attribute
        class SimpleMoment:
            def __init__(self, t: MomentType) -> None:
                self.type = t
        moments.append(SimpleMoment(m_type))

    # Generate attention points (DETERMINISTIC from Moments)
    attention_points = generate_attention_points(
        moments, social_by_phase, flow, has_overtime
    )

    # Generate fallback headline/subhead (DETERMINISTIC)
    moment_types = [m.get("type", "NEUTRAL") for m in moments_data]
    notable_count = sum(1 for m in moments_data if m.get("is_notable"))
    
    fallback_input = GameSummaryInput(
        home_team=home_name,
        away_team=away_name,
        final_score_home=final_home_score or 0,
        final_score_away=final_away_score or 0,
        flow=flow,
        has_overtime=has_overtime,
        moment_types=moment_types,
        notable_count=notable_count,
    )
    fallback = generate_fallback_headline(fallback_input)

    return {
        # Metadata
        "teams": {
            "home": {"id": home_team_id, "name": home_name},
            "away": {"id": away_team_id, "name": away_name},
        },
        "final_score": {"home": final_home_score, "away": final_away_score},
        "flow": flow,
        "phases_in_timeline": phases_present,
        "social_counts": {
            "total": len(social_events),
            "by_phase": social_by_phase,
        },
        # Copy (fallback - can be replaced by AI)
        "headline": fallback.headline,
        "subhead": fallback.subhead,
        # Structure (DETERMINISTIC from Moments)
        "attention_points": attention_points,
        "ai_generated": False,
    }


# =============================================================================
# ASYNC SUMMARY BUILDER (With AI copy generation)
# =============================================================================

async def build_summary_from_timeline_async(
    timeline: Sequence[dict[str, Any]],
    game_analysis: dict[str, Any],
    game_id: int,
    timeline_version: str,
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Build summary with AI-generated headline/subhead.
    
    This function:
    1. Builds deterministic structure (same as sync version)
    2. Calls AI ONLY for headline/subhead (copy)
    3. Falls back gracefully if AI unavailable
    
    AI CANNOT AFFECT:
    - attention_points (from Moments)
    - flow classification
    - social distribution
    - anything structural
    
    AI ONLY WRITES:
    - headline
    - subhead
    """
    # Get deterministic base summary
    base_summary = build_summary_from_timeline(timeline, game_analysis)
    
    # If AI unavailable, return base summary
    if not is_ai_available():
        logger.info(
            "summary_using_fallback",
            extra={"game_id": game_id, "reason": "ai_unavailable"},
        )
        return base_summary
    
    # Build structured input for AI
    moments_data = game_analysis.get("moments", [])
    moment_types = [m.get("type", "NEUTRAL") for m in moments_data]
    notable_count = sum(1 for m in moments_data if m.get("is_notable"))
    
    phases_present = base_summary.get("phases_in_timeline", [])
    has_overtime = any(p.startswith("ot") for p in phases_present)
    
    ai_input = GameSummaryInput(
        home_team=base_summary["teams"]["home"]["name"],
        away_team=base_summary["teams"]["away"]["name"],
        final_score_home=base_summary["final_score"]["home"] or 0,
        final_score_away=base_summary["final_score"]["away"] or 0,
        flow=base_summary["flow"],
        has_overtime=has_overtime,
        moment_types=moment_types,
        notable_count=notable_count,
    )
    
    try:
        # Call AI for headline/subhead ONLY
        ai_output = await generate_headline(
            game_id=game_id,
            timeline_version=timeline_version,
            input_data=ai_input,
        )
        
        # Merge AI copy with deterministic structure
        result = {**base_summary}
        result["headline"] = ai_output.headline
        result["subhead"] = ai_output.subhead
        result["ai_generated"] = True
        
        logger.info(
            "summary_using_ai",
            extra={
                "game_id": game_id,
                "headline_len": len(ai_output.headline),
            },
        )
        return result
        
    except Exception as e:
        logger.warning(
            "summary_ai_fallback",
            extra={"game_id": game_id, "error": str(e)},
        )
        return base_summary
