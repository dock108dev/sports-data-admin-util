"""
Grounded highlight generation for game timelines.

Highlights are labeled windows of play, backed by specific events, with contextual meaning.
Each highlight answers: What happened, When, Who was involved, Why it mattered.

This module provides:
- GroundedHighlight data model with play references
- Highlight generation from timeline events
- Deduplication and variety enforcement
- Contextual enrichment (players, game phase, momentum)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

logger = logging.getLogger(__name__)


class HighlightType(str, Enum):
    """Enumeration of highlight types for stable API contract."""
    SCORING_RUN = "SCORING_RUN"
    LEAD_CHANGE = "LEAD_CHANGE"
    MOMENTUM_SHIFT = "MOMENTUM_SHIFT"
    STAR_TAKEOVER = "STAR_TAKEOVER"
    GAME_DECIDING_STRETCH = "GAME_DECIDING_STRETCH"
    COMEBACK = "COMEBACK"
    BLOWOUT_START = "BLOWOUT_START"


class GamePhase(str, Enum):
    """Game phase for contextual labeling."""
    EARLY = "early"  # Q1 or first ~25% of game
    MID = "mid"      # Q2-Q3 or middle 50%
    LATE = "late"    # Q4 or last 25%
    CLOSING = "closing"  # Final 5 minutes


@dataclass
class GroundedHighlight:
    """
    A highlight grounded in real play-by-play events.
    
    Every highlight is traceable to specific plays in the timeline,
    providing navigation primitives for consumers.
    """
    highlight_id: str
    highlight_type: HighlightType
    title: str
    description: str
    
    # Play grounding - join keys to timeline
    start_play_id: str  # play_index as string for API consistency
    end_play_id: str
    key_play_ids: list[str] = field(default_factory=list)  # 1-3 most important
    
    # Context
    involved_teams: list[str] = field(default_factory=list)  # Team abbreviations
    involved_players: list[str] = field(default_factory=list)  # Player names
    score_change: str = ""  # "92–96 → 98–96"
    game_clock_range: str = ""  # "Q4 7:42–5:58"
    game_phase: GamePhase = GamePhase.MID
    
    # Metadata
    importance_score: float = 0.5  # 0-1, for sorting
    segment_id: str | None = None  # Internal reference, not displayed
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to API-friendly dict."""
        return {
            "highlight_id": self.highlight_id,
            "type": self.highlight_type.value,
            "title": self.title,
            "description": self.description,
            "start_play_id": self.start_play_id,
            "end_play_id": self.end_play_id,
            "key_play_ids": self.key_play_ids,
            "involved_teams": self.involved_teams,
            "involved_players": self.involved_players,
            "score_change": self.score_change,
            "game_clock_range": self.game_clock_range,
            "game_phase": self.game_phase.value,
            "importance_score": self.importance_score,
        }


def _generate_highlight_id() -> str:
    """Generate a unique highlight ID."""
    return f"hl_{uuid.uuid4().hex[:8]}"


def _determine_game_phase(quarter: int | None, game_clock: str | None, total_quarters: int = 4) -> GamePhase:
    """Determine game phase from quarter and clock."""
    if quarter is None:
        return GamePhase.MID
    
    if quarter == 1:
        return GamePhase.EARLY
    elif quarter == 2:
        return GamePhase.MID
    elif quarter == 3:
        return GamePhase.MID
    elif quarter >= total_quarters:
        # Check if in closing stretch (last 5 minutes)
        if game_clock:
            try:
                parts = game_clock.replace(".", ":").split(":")
                minutes = int(parts[0]) if parts else 12
                if minutes <= 5:
                    return GamePhase.CLOSING
            except (ValueError, IndexError):
                pass
        return GamePhase.LATE
    
    return GamePhase.MID


def _format_score_change(start_home: int, start_away: int, end_home: int, end_away: int) -> str:
    """Format score change as 'away-home → away-home'."""
    return f"{start_away}–{start_home} → {end_away}–{end_home}"


def _format_clock_range(start_quarter: int | None, start_clock: str | None, 
                         end_quarter: int | None, end_clock: str | None) -> str:
    """Format game clock range as 'Q4 7:42–5:58'."""
    if start_quarter is None or end_quarter is None:
        return ""
    
    start_q = f"Q{start_quarter}" if start_quarter <= 4 else f"OT{start_quarter - 4}"
    end_q = f"Q{end_quarter}" if end_quarter <= 4 else f"OT{end_quarter - 4}"
    
    start_c = start_clock or "12:00"
    end_c = end_clock or "0:00"
    
    if start_quarter == end_quarter:
        return f"{start_q} {start_c}–{end_c}"
    else:
        return f"{start_q} {start_c} – {end_q} {end_c}"


def _extract_players_from_plays(
    plays: Sequence[dict[str, Any]], 
    start_idx: int, 
    end_idx: int,
    team_id: int | None = None
) -> list[str]:
    """
    Extract player names from play descriptions within a range.
    
    This is a heuristic - looks for common patterns like "J. Tatum makes..."
    """
    players: set[str] = set()
    
    for i, play in enumerate(plays):
        if play.get("play_index", i) < start_idx or play.get("play_index", i) > end_idx:
            continue
        
        description = play.get("description", "")
        if not description:
            continue
        
        # Look for player name patterns (e.g., "J. Tatum", "LeBron James")
        # This is a simple heuristic - could be improved with NER
        words = description.split()
        for j, word in enumerate(words):
            # Pattern: Initial. LastName (e.g., "J. Tatum")
            if len(word) == 2 and word[1] == "." and j + 1 < len(words):
                next_word = words[j + 1]
                if next_word[0].isupper() and len(next_word) > 2:
                    players.add(f"{word} {next_word}")
    
    return list(players)[:3]  # Limit to top 3


def build_grounded_highlights(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    raw_highlights: Sequence[dict[str, Any]],
) -> list[GroundedHighlight]:
    """
    Transform raw highlight detections into grounded, contextual highlights.
    
    Args:
        timeline: Full timeline events (PBP + social)
        summary: Game summary with team info
        raw_highlights: Raw highlight detections from game_analysis
        
    Returns:
        List of GroundedHighlight objects, deduplicated and sorted by importance
    """
    # Extract team info
    home_team = summary.get("teams", {}).get("home", {})
    away_team = summary.get("teams", {}).get("away", {})
    home_abbr = home_team.get("abbreviation", home_team.get("name", "HOME")[:3].upper())
    away_abbr = away_team.get("abbreviation", away_team.get("name", "AWAY")[:3].upper())
    home_name = home_team.get("name", "Home")
    away_name = away_team.get("name", "Away")
    
    # Filter timeline to just PBP events
    pbp_events = [e for e in timeline if e.get("event_type") == "pbp"]
    
    grounded: list[GroundedHighlight] = []
    
    for raw in raw_highlights:
        if not isinstance(raw, dict):
            continue
            
        highlight_type_str = raw.get("highlight_type", "unknown")
        
        # Map to HighlightType enum
        try:
            if highlight_type_str == "scoring_run":
                hl_type = HighlightType.SCORING_RUN
            elif highlight_type_str == "lead_change":
                hl_type = HighlightType.LEAD_CHANGE
            elif highlight_type_str == "quarter_shift":
                hl_type = HighlightType.MOMENTUM_SHIFT
            elif highlight_type_str == "game_deciding_stretch":
                hl_type = HighlightType.GAME_DECIDING_STRETCH
            else:
                continue  # Skip unknown types
        except ValueError:
            continue
        
        # Extract score context
        score_ctx = raw.get("score_context", {})
        start_score = score_ctx.get("start_score", {})
        end_score = score_ctx.get("end_score", {})
        
        # Find corresponding play indices from timeline
        start_ts = raw.get("start_timestamp")
        end_ts = raw.get("end_timestamp")
        
        start_play_idx = 0
        end_play_idx = len(pbp_events) - 1
        start_quarter = None
        end_quarter = None
        start_clock = None
        end_clock = None
        
        # Match timestamps to play indices
        for i, event in enumerate(pbp_events):
            event_ts = event.get("synthetic_timestamp")
            if event_ts == start_ts:
                start_play_idx = event.get("play_index", i)
                start_quarter = event.get("quarter")
                start_clock = event.get("game_clock")
            if event_ts == end_ts:
                end_play_idx = event.get("play_index", i)
                end_quarter = event.get("quarter")
                end_clock = event.get("game_clock")
        
        # Determine game phase
        phase = _determine_game_phase(end_quarter, end_clock)
        
        # Format score change
        score_change = _format_score_change(
            start_score.get("home", 0), start_score.get("away", 0),
            end_score.get("home", 0), end_score.get("away", 0)
        )
        
        # Format clock range
        clock_range = _format_clock_range(start_quarter, start_clock, end_quarter, end_clock)
        
        # Determine involved teams
        teams_involved = raw.get("teams_involved", [])
        team_abbrs = []
        for tid in teams_involved:
            if tid == home_team.get("id"):
                team_abbrs.append(home_abbr)
            elif tid == away_team.get("id"):
                team_abbrs.append(away_abbr)
        if not team_abbrs:
            team_abbrs = [home_abbr, away_abbr]
        
        # Extract players from plays
        players = _extract_players_from_plays(
            pbp_events, start_play_idx, end_play_idx,
            teams_involved[0] if teams_involved else None
        )
        
        # Find key plays (scoring plays within the window)
        key_play_ids = []
        for event in pbp_events:
            idx = event.get("play_index", 0)
            if start_play_idx <= idx <= end_play_idx:
                play_type = event.get("play_type", "")
                if play_type and "score" in play_type.lower() or event.get("home_score") != event.get("away_score"):
                    key_play_ids.append(str(idx))
                    if len(key_play_ids) >= 3:
                        break
        
        # Generate title and description based on type
        title, description = _generate_title_description(
            hl_type, score_ctx, phase, team_abbrs, home_name, away_name
        )
        
        # Calculate importance score
        importance = _calculate_importance(hl_type, phase, score_ctx, end_score)
        
        grounded.append(GroundedHighlight(
            highlight_id=_generate_highlight_id(),
            highlight_type=hl_type,
            title=title,
            description=description,
            start_play_id=str(start_play_idx),
            end_play_id=str(end_play_idx),
            key_play_ids=key_play_ids,
            involved_teams=team_abbrs,
            involved_players=players,
            score_change=score_change,
            game_clock_range=clock_range,
            game_phase=phase,
            importance_score=importance,
            segment_id=raw.get("related_segment_id"),
        ))
    
    # Deduplicate and enforce variety
    grounded = _deduplicate_highlights(grounded)
    
    # Sort by importance (descending)
    grounded.sort(key=lambda h: h.importance_score, reverse=True)
    
    return grounded


def _generate_title_description(
    hl_type: HighlightType,
    score_ctx: dict[str, Any],
    phase: GamePhase,
    team_abbrs: list[str],
    home_name: str,
    away_name: str,
) -> tuple[str, str]:
    """Generate human-readable title and description for a highlight."""
    
    team = team_abbrs[0] if team_abbrs else "Team"
    
    phase_label = {
        GamePhase.EARLY: "early",
        GamePhase.MID: "midway through the game",
        GamePhase.LATE: "late",
        GamePhase.CLOSING: "in the closing stretch",
    }.get(phase, "")
    
    if hl_type == HighlightType.SCORING_RUN:
        points = score_ctx.get("points", 0)
        title = f"{team} goes on a {points}-0 run"
        description = f"{team} seized momentum with a dominant stretch {phase_label}."
        
    elif hl_type == HighlightType.LEAD_CHANGE:
        lead_team_id = score_ctx.get("lead_team_id")
        new_leader = team_abbrs[0] if team_abbrs else "the opponent"
        title = f"Lead swings to {new_leader}"
        description = f"A critical lead change shifted the game's complexion {phase_label}."
        
    elif hl_type == HighlightType.MOMENTUM_SHIFT:
        margin_change = score_ctx.get("margin_change", 0)
        title = f"Momentum shifts with {margin_change}-point swing"
        description = f"A major momentum shift altered the trajectory of the game."
        
    elif hl_type == HighlightType.GAME_DECIDING_STRETCH:
        final_margin = score_ctx.get("final_margin", 0)
        winner = team_abbrs[0] if len(team_abbrs) > 0 else "Winner"
        title = f"{winner} seals it in the final stretch"
        description = f"The game was decided in the closing moments with a {final_margin}-point final margin."
        
    else:
        title = hl_type.value.replace("_", " ").title()
        description = "A significant moment in the game."
    
    return title, description


def _calculate_importance(
    hl_type: HighlightType,
    phase: GamePhase,
    score_ctx: dict[str, Any],
    end_score: dict[str, Any],
) -> float:
    """
    Calculate importance score (0-1) for highlight ranking.
    
    Factors:
    - Type (game-deciding > lead change > run)
    - Phase (closing > late > early > mid)
    - Score context (close games more important)
    """
    base_scores = {
        HighlightType.GAME_DECIDING_STRETCH: 0.9,
        HighlightType.COMEBACK: 0.85,
        HighlightType.LEAD_CHANGE: 0.7,
        HighlightType.MOMENTUM_SHIFT: 0.65,
        HighlightType.SCORING_RUN: 0.6,
        HighlightType.STAR_TAKEOVER: 0.75,
        HighlightType.BLOWOUT_START: 0.5,
    }
    
    phase_multipliers = {
        GamePhase.CLOSING: 1.2,
        GamePhase.LATE: 1.1,
        GamePhase.EARLY: 0.9,
        GamePhase.MID: 1.0,
    }
    
    score = base_scores.get(hl_type, 0.5)
    score *= phase_multipliers.get(phase, 1.0)
    
    # Boost for close games
    margin = abs(end_score.get("home", 0) - end_score.get("away", 0))
    if margin <= 5:
        score *= 1.15
    elif margin <= 10:
        score *= 1.05
    
    return min(1.0, score)


def _deduplicate_highlights(highlights: list[GroundedHighlight]) -> list[GroundedHighlight]:
    """
    Deduplicate and enforce variety in highlights.
    
    Rules:
    - Merge consecutive lead changes within 2 minutes
    - Limit each type to max 3 instances
    - Prefer higher importance when deduplicating
    """
    if not highlights:
        return []
    
    # Sort by start_play_id for consecutive merging
    highlights.sort(key=lambda h: int(h.start_play_id))
    
    # Merge consecutive lead changes
    merged: list[GroundedHighlight] = []
    prev: GroundedHighlight | None = None
    
    for h in highlights:
        if prev is None:
            prev = h
            continue
        
        # Check if consecutive lead changes that should be merged
        if (prev.highlight_type == HighlightType.LEAD_CHANGE and 
            h.highlight_type == HighlightType.LEAD_CHANGE):
            # Check if they're close (within ~30 play indices)
            if abs(int(h.start_play_id) - int(prev.end_play_id)) < 30:
                # Merge: extend prev to include h
                prev = GroundedHighlight(
                    highlight_id=prev.highlight_id,
                    highlight_type=HighlightType.LEAD_CHANGE,
                    title="Back-and-forth lead battle",
                    description="Multiple lead changes in a tightly contested stretch.",
                    start_play_id=prev.start_play_id,
                    end_play_id=h.end_play_id,
                    key_play_ids=prev.key_play_ids + h.key_play_ids,
                    involved_teams=list(set(prev.involved_teams + h.involved_teams)),
                    involved_players=list(set(prev.involved_players + h.involved_players)),
                    score_change=f"{prev.score_change.split('→')[0].strip()} → {h.score_change.split('→')[-1].strip()}",
                    game_clock_range=f"{prev.game_clock_range.split('–')[0]}–{h.game_clock_range.split('–')[-1]}",
                    game_phase=h.game_phase,  # Use later phase
                    importance_score=max(prev.importance_score, h.importance_score) * 1.1,  # Boost merged
                    segment_id=prev.segment_id,
                )
                continue
        
        merged.append(prev)
        prev = h
    
    if prev:
        merged.append(prev)
    
    # Enforce type variety (max 3 per type)
    type_counts: dict[HighlightType, int] = {}
    final: list[GroundedHighlight] = []
    
    # Sort by importance first
    merged.sort(key=lambda h: h.importance_score, reverse=True)
    
    for h in merged:
        count = type_counts.get(h.highlight_type, 0)
        if count < 3:
            final.append(h)
            type_counts[h.highlight_type] = count + 1
    
    return final
