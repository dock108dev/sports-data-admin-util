"""
Summary generation for game timelines.

=============================================================================
DESIGN PHILOSOPHY (2026-01 Refactor)
=============================================================================

Summary generation is purely DETERMINISTIC structure extraction.

AI-generated copy (headline/subhead) now comes from game_analysis.py via
the batch enrichment call. This module DOES NOT call AI.

Outputs:
- flow: Classification based on score difference
- phases_in_timeline: Which periods are present
- social_counts: Social distribution by phase
- attention_points: Where to focus (derived from Moments)

Related modules:
- moments.py: Lead Ladder-based partitioning
- game_analysis.py: AI enrichment (batch call for all moments + game copy)
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .. import db_models
from .moments import MomentType

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
    moments: list[Any],
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
        m_type = m.type if hasattr(m, 'type') else m.get('type')
        if isinstance(m_type, str):
            try:
                m_type = MomentType(m_type)
            except ValueError:
                m_type = MomentType.NEUTRAL
        type_counts[m_type] = type_counts.get(m_type, 0) + 1
    
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
# MAIN SUMMARY BUILDER
# =============================================================================

def build_summary_from_timeline(
    timeline: Sequence[dict[str, Any]],
    game_analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Build summary metadata from timeline (DETERMINISTIC).
    
    This function extracts structural information from the timeline
    and Moments. It does NOT call AI.
    
    AI-generated headline/subhead comes from game_analysis (via batch enrichment).
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

    # Generate attention points (DETERMINISTIC from Moments)
    attention_points = generate_attention_points(
        moments_data, social_by_phase, flow, has_overtime
    )

    # Get headline/subhead from game_analysis (from batch enrichment)
    headline = game_analysis.get("game_headline", "")
    subhead = game_analysis.get("game_subhead", "")

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
        # AI-generated copy (from batch enrichment)
        "headline": headline,
        "subhead": subhead,
        # Structure (DETERMINISTIC from Moments)
        "attention_points": attention_points,
    }


async def build_summary_from_timeline_async(
    timeline: Sequence[dict[str, Any]],
    game_analysis: dict[str, Any],
    game_id: int,
    timeline_version: str,
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Build summary (async version).
    
    Wraps the sync build_summary_from_timeline for use in async contexts.
    """
    return build_summary_from_timeline(timeline, game_analysis)
