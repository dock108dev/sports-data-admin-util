"""Moment data types and enums.

This module defines the core data structures for the moment system:
- MomentType: Enum of narrative moment types
- PlayerContribution: Player stats within a moment
- MomentReason: Explanation of why a moment exists
- RunInfo: Scoring run metadata
- Moment: The main moment dataclass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..lead_ladder import LeadState


class MomentType(str, Enum):
    """Types of narrative moments based on Lead Ladder crossings."""

    # Lead Ladder crossing types (primary)
    LEAD_BUILD = "LEAD_BUILD"  # Lead tier increased
    CUT = "CUT"  # Lead tier decreased (opponent cutting in)
    TIE = "TIE"  # Game returned to even
    FLIP = "FLIP"  # Leader changed

    # Special context types
    CLOSING_CONTROL = "CLOSING_CONTROL"  # Late-game lock-in (dagger)
    HIGH_IMPACT = "HIGH_IMPACT"  # Non-scoring event changing control
    NEUTRAL = "NEUTRAL"  # Normal flow, no tier changes

    # PHASE 1.3: Run-based moment type
    MOMENTUM_SHIFT = "MOMENTUM_SHIFT"  # Significant scoring run that caused tier change
    
    # Recap moment types (contextual summaries at key boundaries)
    HALFTIME_RECAP = "HALFTIME_RECAP"  # Halftime summary
    PERIOD_RECAP = "PERIOD_RECAP"  # End of period summary (NHL, baseball)
    GAME_RECAP = "GAME_RECAP"  # Final game summary
    OVERTIME_RECAP = "OVERTIME_RECAP"  # Overtime period summary


@dataclass
class PlayerContribution:
    """Player stats within a moment."""

    name: str
    stats: dict[str, int] = field(default_factory=dict)
    summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stats": self.stats,
            "summary": self.summary,
        }


@dataclass
class MomentReason:
    """Explains WHY a moment exists.

    Every moment must have a reason. If you can't populate this,
    the moment should not exist.
    """

    trigger: str  # "tier_cross" | "flip" | "tie" | "closing_lock" | "high_impact" | "opener"
    control_shift: str | None  # "home" | "away" | None
    narrative_delta: str  # "tension ↑" | "control gained" | "pressure relieved" | etc.

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "control_shift": self.control_shift,
            "narrative_delta": self.narrative_delta,
        }


@dataclass
class RunInfo:
    """Information about a scoring run within a moment.

    Runs do NOT create moments by themselves. They are metadata
    attached to moments when a run contributed to a tier crossing.

    A run is a sequence of unanswered scoring by one team.
    Runs are ONLY promoted to moment metadata if they:
    - Caused a tier crossing (LEAD_BUILD or CUT)
    - Caused a lead flip (FLIP)

    Runs that didn't move control become key_play_ids instead.
    """

    team: str  # "home" or "away"
    points: int
    unanswered: bool  # True if opponent scored 0 during run
    play_ids: list[int] = field(default_factory=list)  # Indices of scoring plays in run
    start_idx: int = 0  # Timeline index where run started
    end_idx: int = 0  # Timeline index where run ended


@dataclass
class RecapContext:
    """Contextual summary data for recap moments at key game boundaries.
    
    Priority order (most to least important):
    1. momentum_summary: Who finished strong and gained control
    2. key_runs: Significant scoring runs in the period
    3. largest_lead: Biggest lead and which team had it
    4. lead_changes: Number of times the lead changed hands
    5. running_score: Current game score
    6. top_performers: Key players in the period
    7. period_score: Scoring in just this period
    """
    
    # Priority 1: Momentum and control (most important)
    momentum_summary: str = ""  # "Lakers finished strong" or "Back-and-forth battle"
    who_has_control: str | None = None  # "home", "away", or None (tied/unclear)
    
    # Priority 2: Key runs
    key_runs: list[dict[str, Any]] = field(default_factory=list)  # [{team, points, description}]
    
    # Priority 3: Largest lead
    largest_lead: int = 0
    largest_lead_team: str | None = None  # "home" or "away"
    
    # Priority 4: Lead changes
    lead_changes_count: int = 0
    
    # Priority 5: Running score
    running_score: tuple[int, int] = (0, 0)  # (home, away)
    
    # Priority 6: Top performers
    top_performers: list[dict[str, Any]] = field(default_factory=list)  # [{name, team, stats}]
    
    # Priority 7: Period score
    period_score: tuple[int, int] = (0, 0)  # (home, away) scoring in this period only
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "momentum_summary": self.momentum_summary,
            "who_has_control": self.who_has_control,
            "key_runs": self.key_runs,
            "largest_lead": self.largest_lead,
            "largest_lead_team": self.largest_lead_team,
            "lead_changes_count": self.lead_changes_count,
            "running_score": self.running_score,
            "top_performers": self.top_performers,
            "period_score": self.period_score,
        }


@dataclass
class MomentContext:
    """Lightweight narrative context for AI enrichment.
    
    This provides memory and awareness so AI can write coherent,
    non-repetitive recaps. These are SIGNALS, not rules.
    
    Added in Prompt 2 (Phase 1-3): Context-Aware Moment Plumbing
    """
    
    # Phase awareness
    game_phase: str = "middle"  # "opening" | "middle" | "closing"
    phase_progress: float = 0.5  # 0.0 to 1.0 (percentage through game)
    is_overtime: bool = False
    is_closing_window: bool = False
    
    # Narrative continuity
    previous_moment_type: str | None = None  # Type of previous moment
    previous_narrative_delta: str | None = None  # What the last moment established
    is_continuation: bool = False  # Is this extending previous narrative?
    parent_moment_id: str | None = None  # If split from another moment
    
    # Volatility context
    recent_flip_tie_count: int = 0  # FLIPs/TIEs in recent moments
    volatility_phase: str = "stable"  # "stable" | "volatile" | "back_and_forth"
    
    # Control context
    controlling_team: str | None = None  # "home" | "away" | None
    control_duration: int = 0  # Consecutive moments with same control
    tier_stability: str = "stable"  # "stable" | "oscillating" | "shifting"
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "game_phase": self.game_phase,
            "phase_progress": round(self.phase_progress, 3),
            "is_overtime": self.is_overtime,
            "is_closing_window": self.is_closing_window,
            "previous_moment_type": self.previous_moment_type,
            "previous_narrative_delta": self.previous_narrative_delta,
            "is_continuation": self.is_continuation,
            "parent_moment_id": self.parent_moment_id,
            "recent_flip_tie_count": self.recent_flip_tie_count,
            "volatility_phase": self.volatility_phase,
            "controlling_team": self.controlling_team,
            "control_duration": self.control_duration,
            "tier_stability": self.tier_stability,
        }


@dataclass
class Moment:
    """A contiguous segment of plays forming a narrative unit.

    Every play in the timeline belongs to exactly one Moment.
    Moments are always chronologically ordered by start_play.
    """

    id: str
    type: MomentType
    start_play: int
    end_play: int
    play_count: int

    # Score tracking
    score_before: tuple[int, int] = (0, 0)  # (home, away) at start
    score_after: tuple[int, int] = (0, 0)  # (home, away) at end
    score_start: str = ""  # Format "away–home"
    score_end: str = ""  # Format "away–home"

    # Lead Ladder state
    ladder_tier_before: int = 0
    ladder_tier_after: int = 0
    team_in_control: str | None = None  # "home", "away", or None

    # Context (RESOLVED DURING RESOLUTION PASS)
    teams: list[str] = field(default_factory=list)
    primary_team: str | None = None  # "home" or "away"
    players: list[PlayerContribution] = field(default_factory=list)
    key_play_ids: list[int] = field(default_factory=list)
    clock: str = ""

    # WHY THIS MOMENT EXISTS
    reason: MomentReason | None = None

    # Metadata
    is_notable: bool = False
    is_period_start: bool = False  # Flag for period boundaries
    is_recap: bool = False  # Flag for recap moments (zero-width contextual summaries)
    note: str | None = None
    run_info: RunInfo | None = None  # If a run contributed to this moment
    bucket: str = ""  # "early", "mid", "late" (derived from clock)

    # PHASE 2.1: Importance scoring
    importance_score: float = 0.0
    importance_factors: dict[str, Any] = field(default_factory=dict)

    # PHASE 3.1: Chapter moments
    is_chapter: bool = False
    chapter_info: dict[str, Any] = field(default_factory=dict)

    # PHASE 4: Player & Box Score Integration
    moment_boxscore: Any = None
    narrative_summary: Any = None
    
    # Recap context (for HALFTIME_RECAP, PERIOD_RECAP, GAME_RECAP, OVERTIME_RECAP)
    recap_context: RecapContext | None = None

    # AI-generated content
    headline: str = ""  # max 60 chars
    summary: str = ""  # max 150 chars
    
    # PROMPT 2: Context-aware plumbing (Phase 1-3)
    # Game phase state at the time this moment occurred
    phase_state: Any = None  # GamePhaseState from game_structure.py
    
    # Narrative context for AI enrichment
    narrative_context: MomentContext | None = None

    @property
    def display_weight(self) -> str:
        """How prominent to render this moment: high, medium, low."""
        if self.type in (MomentType.FLIP, MomentType.TIE, MomentType.HIGH_IMPACT):
            return "high"
        if self.type in (MomentType.CLOSING_CONTROL, MomentType.LEAD_BUILD):
            return "medium"
        if self.type in (MomentType.CUT,):
            return "medium"
        return "low"

    @property
    def display_icon(self) -> str:
        """Suggested icon for this moment type."""
        icons = {
            MomentType.FLIP: "swap",
            MomentType.TIE: "equals",
            MomentType.LEAD_BUILD: "trending-up",
            MomentType.CUT: "trending-down",
            MomentType.CLOSING_CONTROL: "lock",
            MomentType.HIGH_IMPACT: "zap",
            MomentType.NEUTRAL: "minus",
            MomentType.HALFTIME_RECAP: "pause-circle",
            MomentType.PERIOD_RECAP: "clock",
            MomentType.GAME_RECAP: "flag",
            MomentType.OVERTIME_RECAP: "clock",
        }
        return icons.get(self.type, "circle")

    @property
    def display_color_hint(self) -> str:
        """Color intent: tension, positive, negative, neutral, recap."""
        if self.type in (MomentType.FLIP, MomentType.TIE):
            return "tension"
        if self.type == MomentType.CLOSING_CONTROL:
            return "positive"
        if self.type == MomentType.HIGH_IMPACT:
            return "highlight"
        if self.type in (MomentType.HALFTIME_RECAP, MomentType.PERIOD_RECAP, 
                         MomentType.GAME_RECAP, MomentType.OVERTIME_RECAP):
            return "recap"  # Frontend can style with 10-15% more border
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses."""
        # Build score context with team identification
        score_context = {
            "current": {
                "home": self.score_after[0],
                "away": self.score_after[1],
                "formatted": self.score_end,
            },
            "start": {
                "home": self.score_before[0],
                "away": self.score_before[1],
                "formatted": self.score_start,
            },
            "margin": abs(self.score_after[0] - self.score_after[1]),
            "leader": self.team_in_control,
        }
        
        # Filter players to only those with meaningful contributions
        key_players = [
            p.to_dict() for p in self.players
            if p.stats and sum(p.stats.values()) > 0
        ][:3]  # Top 3 only
        
        result = {
            "id": self.id,
            "type": self.type.value,
            "start_play": self.start_play,
            "end_play": self.end_play,
            "play_count": self.play_count,
            "teams": self.teams,
            "primary_team": self.primary_team,
            "players": [p.to_dict() for p in self.players],
            "key_players": key_players,  # NEW: Filtered top contributors
            "score_start": self.score_start,
            "score_end": self.score_end,
            "score_context": score_context,  # NEW: Structured score info
            "clock": self.clock,
            "is_notable": self.is_notable,
            "is_period_start": self.is_period_start,
            "is_recap": self.is_recap,
            "note": self.note,
            "ladder_tier_before": self.ladder_tier_before,
            "ladder_tier_after": self.ladder_tier_after,
            "team_in_control": self.team_in_control,
            "key_play_ids": self.key_play_ids,
            "headline": self.headline,
            "summary": self.summary,
            "display_weight": self.display_weight,
            "display_icon": self.display_icon,
            "display_color_hint": self.display_color_hint,
        }
        if self.reason:
            result["reason"] = self.reason.to_dict()
        if self.run_info:
            result["run_info"] = {
                "team": self.run_info.team,
                "points": self.run_info.points,
                "unanswered": self.run_info.unanswered,
                "play_ids": self.run_info.play_ids,
            }
        result["importance_score"] = round(self.importance_score, 2)
        if self.importance_factors:
            result["importance_factors"] = self.importance_factors

        result["is_chapter"] = self.is_chapter
        if self.is_chapter and self.chapter_info:
            result["chapter_info"] = self.chapter_info

        if self.moment_boxscore:
            result["moment_boxscore"] = self.moment_boxscore.to_dict()
        if self.narrative_summary:
            result["narrative_summary"] = self.narrative_summary.to_dict()
            result["deterministic_summary"] = self.narrative_summary.text
        
        if self.recap_context:
            result["recap_context"] = self.recap_context.to_dict()
        
        # PROMPT 2: Include phase state and narrative context
        if self.phase_state is not None:
            result["phase_state"] = self.phase_state.to_dict() if hasattr(self.phase_state, 'to_dict') else self.phase_state
        
        if self.narrative_context is not None:
            result["narrative_context"] = self.narrative_context.to_dict()

        return result
