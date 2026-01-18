"""Sport-agnostic game structure and phase detection.

This module provides a unified abstraction for game timing across all sports:
- NBA: 4 quarters × 12 min
- NCAAB: 2 halves × 20 min
- NHL: 3 periods × 20 min
- NFL: 4 quarters × 15 min
- Soccer: 2 halves × 45 min

Instead of checking `quarter >= 4`, use `is_final_phase`.
Instead of hardcoded time thresholds, use percentage-based or sport-specific configs.

Usage:
    from app.services.moments.game_structure import (
        GameStructure,
        GamePhaseState,
        get_game_structure,
        compute_game_phase_state,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ...utils.datetime_utils import parse_clock_to_seconds

logger = logging.getLogger(__name__)


class PhaseType(str, Enum):
    """Type of game phase/period structure."""
    
    QUARTER = "quarter"  # NBA, NFL
    HALF = "half"  # NCAA basketball, soccer
    PERIOD = "period"  # NHL


@dataclass(frozen=True)
class GameStructure:
    """Defines the timing structure for a sport.
    
    This is sport-specific but the interface is uniform.
    All late-game logic uses this structure rather than hardcoded values.
    """
    
    sport: str
    phase_type: PhaseType
    num_regulation_phases: int  # 4 quarters, 2 halves, 3 periods
    phase_duration_seconds: int  # Duration of each phase
    ot_phase_duration_seconds: int  # Duration of OT phases
    
    # Late-game thresholds (percentage of total regulation time)
    late_game_progress_threshold: float = 0.85  # Last 15% of game
    closing_window_pct: float = 0.10  # Last 10% for closing checks
    
    # Absolute time thresholds (fallback / override)
    closing_window_seconds: int = 300  # 5 minutes default
    late_game_window_seconds: int = 180  # 3 minutes for suppression
    
    @property
    def total_regulation_seconds(self) -> int:
        """Total regulation time in seconds."""
        return self.num_regulation_phases * self.phase_duration_seconds
    
    @property
    def final_phase_number(self) -> int:
        """The phase number that constitutes the final phase of regulation."""
        return self.num_regulation_phases
    
    def is_overtime_phase(self, phase_number: int) -> bool:
        """Check if a phase number represents overtime."""
        return phase_number > self.num_regulation_phases
    
    def get_phase_start_seconds(self, phase_number: int) -> int:
        """Get the elapsed seconds at the start of a phase."""
        if phase_number <= self.num_regulation_phases:
            return (phase_number - 1) * self.phase_duration_seconds
        else:
            # Overtime
            ot_number = phase_number - self.num_regulation_phases
            return (self.total_regulation_seconds +
                    (ot_number - 1) * self.ot_phase_duration_seconds)
    
    def compute_elapsed_seconds(
        self,
        phase_number: int,
        clock_seconds: int,
    ) -> int:
        """Compute total elapsed seconds from phase and clock."""
        if phase_number <= self.num_regulation_phases:
            elapsed_in_phase = self.phase_duration_seconds - clock_seconds
            return self.get_phase_start_seconds(phase_number) + elapsed_in_phase
        else:
            # Overtime
            elapsed_in_phase = self.ot_phase_duration_seconds - min(
                clock_seconds, self.ot_phase_duration_seconds
            )
            return self.get_phase_start_seconds(phase_number) + elapsed_in_phase
    
    def compute_remaining_seconds(
        self,
        phase_number: int,
        clock_seconds: int,
    ) -> int:
        """Compute remaining regulation seconds (0 for OT, always clock for OT)."""
        if phase_number > self.num_regulation_phases:
            # In OT - return clock as-is
            return clock_seconds
        
        phases_remaining = self.num_regulation_phases - phase_number
        return phases_remaining * self.phase_duration_seconds + clock_seconds


# =============================================================================
# SPORT CONFIGURATIONS
# =============================================================================

# NBA: 4 quarters × 12 minutes, 5 min OT
NBA_STRUCTURE = GameStructure(
    sport="NBA",
    phase_type=PhaseType.QUARTER,
    num_regulation_phases=4,
    phase_duration_seconds=720,  # 12 min
    ot_phase_duration_seconds=300,  # 5 min
    late_game_progress_threshold=0.85,
    closing_window_pct=0.104,  # ~5 min of 48 min
    closing_window_seconds=300,
    late_game_window_seconds=150,  # 2.5 min
)

# NCAAB: 2 halves × 20 minutes, 5 min OT
NCAAB_STRUCTURE = GameStructure(
    sport="NCAAB",
    phase_type=PhaseType.HALF,
    num_regulation_phases=2,
    phase_duration_seconds=1200,  # 20 min
    ot_phase_duration_seconds=300,  # 5 min
    late_game_progress_threshold=0.875,  # Last 5 min of 40 min
    closing_window_pct=0.125,  # 5 min of 40 min
    closing_window_seconds=300,
    late_game_window_seconds=150,
)

# NHL: 3 periods × 20 minutes, 5 min OT (or shootout)
NHL_STRUCTURE = GameStructure(
    sport="NHL",
    phase_type=PhaseType.PERIOD,
    num_regulation_phases=3,
    phase_duration_seconds=1200,  # 20 min
    ot_phase_duration_seconds=300,  # 5 min
    late_game_progress_threshold=0.917,  # Last 5 min of 60 min
    closing_window_pct=0.083,  # 5 min of 60 min
    closing_window_seconds=300,
    late_game_window_seconds=150,
)

# NFL: 4 quarters × 15 minutes, 10/15 min OT
NFL_STRUCTURE = GameStructure(
    sport="NFL",
    phase_type=PhaseType.QUARTER,
    num_regulation_phases=4,
    phase_duration_seconds=900,  # 15 min
    ot_phase_duration_seconds=600,  # 10 min
    late_game_progress_threshold=0.917,  # Last 5 min of 60 min
    closing_window_pct=0.083,  # 5 min of 60 min
    closing_window_seconds=300,
    late_game_window_seconds=120,  # 2 min warning
)

# Default structure (NBA-like for backward compatibility)
DEFAULT_STRUCTURE = NBA_STRUCTURE

# Registry of sport structures
SPORT_STRUCTURES: dict[str, GameStructure] = {
    "NBA": NBA_STRUCTURE,
    "NCAAB": NCAAB_STRUCTURE,
    "NCAA": NCAAB_STRUCTURE,  # Alias
    "NHL": NHL_STRUCTURE,
    "NFL": NFL_STRUCTURE,
}


def get_game_structure(sport: str | None = None) -> GameStructure:
    """Get the game structure for a sport.
    
    Args:
        sport: Sport identifier (NBA, NCAAB, NHL, NFL, etc.)
    
    Returns:
        GameStructure for the sport, or default if unknown
    """
    if sport is None:
        return DEFAULT_STRUCTURE
    
    return SPORT_STRUCTURES.get(sport.upper(), DEFAULT_STRUCTURE)


# =============================================================================
# GAME PHASE STATE
# =============================================================================

@dataclass
class GamePhaseState:
    """Phase-agnostic game state for late-game logic.
    
    This replaces quarter-specific checks with unified phase logic.
    Use `is_final_phase` instead of `quarter >= 4`.
    Use `is_late_game` instead of hardcoded time checks.
    """
    
    # Raw phase info
    phase_number: int  # 1-indexed (quarter, half, or period number)
    phase_type: PhaseType
    clock_seconds: int  # Seconds remaining in current phase
    
    # Computed timing
    elapsed_seconds: int  # Total elapsed regulation seconds
    remaining_seconds: int  # Total remaining regulation seconds
    game_progress: float  # 0.0 to 1.0 (>1.0 in OT)
    
    # Phase classification
    is_overtime: bool = False
    is_final_phase: bool = False  # Final quarter/half/period of regulation
    is_late_game: bool = False  # In late-game window (progress-based)
    is_closing_window: bool = False  # In closing window (time-based)
    
    # For diagnostics
    sport: str = "NBA"
    total_regulation_seconds: int = 2880
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_number": self.phase_number,
            "phase_type": self.phase_type.value,
            "clock_seconds": self.clock_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "remaining_seconds": self.remaining_seconds,
            "game_progress": round(self.game_progress, 4),
            "is_overtime": self.is_overtime,
            "is_final_phase": self.is_final_phase,
            "is_late_game": self.is_late_game,
            "is_closing_window": self.is_closing_window,
            "sport": self.sport,
        }


def compute_game_phase_state(
    event: dict[str, Any],
    sport: str | None = None,
    structure: GameStructure | None = None,
) -> GamePhaseState:
    """Compute the phase-agnostic game state from an event.
    
    This is the main entry point for phase detection.
    Use this instead of checking quarter numbers directly.
    
    Args:
        event: Timeline event with quarter/period and game_clock
        sport: Sport identifier (optional if structure provided)
        structure: Explicit game structure (optional, derived from sport)
    
    Returns:
        GamePhaseState with all phase classifications
    """
    if structure is None:
        structure = get_game_structure(sport)
    
    # Extract phase number (quarter, half, or period)
    phase_number = event.get("quarter", 1) or event.get("period", 1) or 1
    
    # Parse clock
    clock_str = event.get("game_clock", "12:00") or "12:00"
    try:
        clock_seconds = parse_clock_to_seconds(clock_str)
        if clock_seconds is None:
            clock_seconds = structure.phase_duration_seconds // 2
    except (ValueError, TypeError):
        clock_seconds = structure.phase_duration_seconds // 2
    
    # Compute timing
    is_overtime = structure.is_overtime_phase(phase_number)
    
    if is_overtime:
        elapsed_seconds = structure.compute_elapsed_seconds(phase_number, clock_seconds)
        remaining_seconds = clock_seconds  # In OT, only current phase matters
        # Progress > 1.0 in OT
        ot_number = phase_number - structure.num_regulation_phases
        progress_in_ot = ((structure.ot_phase_duration_seconds - clock_seconds) /
                          structure.ot_phase_duration_seconds)
        game_progress = 1.0 + (ot_number - 1) * 0.1 + progress_in_ot * 0.1
    else:
        elapsed_seconds = structure.compute_elapsed_seconds(phase_number, clock_seconds)
        remaining_seconds = structure.compute_remaining_seconds(phase_number, clock_seconds)
        game_progress = elapsed_seconds / structure.total_regulation_seconds
    
    # Phase classification
    is_final_phase = (phase_number >= structure.final_phase_number or
                      is_overtime)
    
    is_late_game = (game_progress >= structure.late_game_progress_threshold or
                    is_overtime)
    
    is_closing_window = (is_final_phase and
                         remaining_seconds <= structure.closing_window_seconds)
    
    return GamePhaseState(
        phase_number=phase_number,
        phase_type=structure.phase_type,
        clock_seconds=clock_seconds,
        elapsed_seconds=elapsed_seconds,
        remaining_seconds=remaining_seconds,
        game_progress=game_progress,
        is_overtime=is_overtime,
        is_final_phase=is_final_phase,
        is_late_game=is_late_game,
        is_closing_window=is_closing_window,
        sport=structure.sport,
        total_regulation_seconds=structure.total_regulation_seconds,
    )


def compute_game_progress(
    event: dict[str, Any],
    sport: str | None = None,
) -> float:
    """Compute game progress (0.0 to 1.0+) from an event.
    
    Replacement for the old sport-specific get_game_progress().
    
    Args:
        event: Timeline event with quarter/period and game_clock
        sport: Sport identifier
    
    Returns:
        Float from 0.0 (game start) to 1.0 (end of regulation), >1.0 in OT
    """
    phase_state = compute_game_phase_state(event, sport)
    return phase_state.game_progress


def is_final_phase(
    event: dict[str, Any],
    sport: str | None = None,
) -> bool:
    """Check if event is in the final phase of regulation or OT.
    
    Replacement for `quarter >= 4` checks.
    Works across all sports:
    - NBA/NFL: Q4 or OT
    - NCAAB: 2nd half or OT
    - NHL: 3rd period or OT
    
    Args:
        event: Timeline event with quarter/period
        sport: Sport identifier
    
    Returns:
        True if in final phase or overtime
    """
    phase_state = compute_game_phase_state(event, sport)
    return phase_state.is_final_phase


def is_late_game(
    event: dict[str, Any],
    sport: str | None = None,
) -> bool:
    """Check if event is in the late-game window.
    
    Uses sport-specific progress thresholds.
    
    Args:
        event: Timeline event
        sport: Sport identifier
    
    Returns:
        True if in late-game window
    """
    phase_state = compute_game_phase_state(event, sport)
    return phase_state.is_late_game


def is_closing_window(
    event: dict[str, Any],
    sport: str | None = None,
) -> bool:
    """Check if event is in the closing window.
    
    Closing window = final phase AND within time threshold.
    
    Args:
        event: Timeline event
        sport: Sport identifier
    
    Returns:
        True if in closing window
    """
    phase_state = compute_game_phase_state(event, sport)
    return phase_state.is_closing_window


def get_phase_label(phase_state: GamePhaseState) -> str:
    """Get a human-readable label for the current phase.
    
    Args:
        phase_state: Computed game phase state
    
    Returns:
        String like "Q4", "2nd Half", "P3", "OT1"
    """
    if phase_state.is_overtime:
        ot_number = phase_state.phase_number - (
            get_game_structure(phase_state.sport).num_regulation_phases
        )
        return f"OT{ot_number}" if ot_number > 1 else "OT"
    
    if phase_state.phase_type == PhaseType.QUARTER:
        return f"Q{phase_state.phase_number}"
    elif phase_state.phase_type == PhaseType.HALF:
        return f"{phase_state.phase_number}H" if phase_state.phase_number == 1 else "2H"
    elif phase_state.phase_type == PhaseType.PERIOD:
        return f"P{phase_state.phase_number}"
    else:
        return f"Phase {phase_state.phase_number}"


# =============================================================================
# GAME PHASE CONTEXT (AUTHORITATIVE GAME-LEVEL PHASE MODEL)
# =============================================================================

# Default phase thresholds (percentage-based)
DEFAULT_EARLY_GAME_THRESHOLD = 0.35  # First 35% = early game
DEFAULT_MID_GAME_THRESHOLD = 0.75  # 35-75% = mid game
DEFAULT_LATE_GAME_THRESHOLD = 0.85  # 85%+ = late game
DEFAULT_CLOSING_THRESHOLD = 0.90  # 90%+ = closing


@dataclass
class PhaseBoundary:
    """A phase boundary in terms of event index and progress."""
    
    event_index: int
    progress: float
    phase_number: int
    clock_seconds: int
    label: str  # "early", "mid", "late", "closing", "overtime"


@dataclass
class GamePhaseContext:
    """Authoritative game-level phase model.
    
    This is the SINGLE SOURCE OF TRUTH for all phase-related logic.
    Computed once per game and passed to all pipeline components.
    
    ALL phase queries should go through this context:
    - Instead of `get_game_progress()`, use `context.get_progress(event_idx)`
    - Instead of `quarter >= 4`, use `context.is_final_phase(event_idx)`
    - Instead of hardcoded checks, use `context.classify_event(event_idx)`
    
    Usage:
        context = build_game_phase_context(events, sport="NBA")
        
        # Classify any event
        phase = context.classify_event(event_idx)
        
        # Check phase properties
        if context.is_late_game(event_idx):
            ...
        
        # Get progress
        progress = context.get_progress(event_idx)
    """
    
    # Sport and structure
    sport: str
    structure: GameStructure
    
    # Game-level stats
    total_events: int
    total_pbp_events: int
    has_overtime: bool
    max_phase_number: int
    
    # Phase thresholds (percentage-based)
    early_game_threshold: float = DEFAULT_EARLY_GAME_THRESHOLD
    mid_game_threshold: float = DEFAULT_MID_GAME_THRESHOLD
    late_game_threshold: float = DEFAULT_LATE_GAME_THRESHOLD
    closing_threshold: float = DEFAULT_CLOSING_THRESHOLD
    
    # Precomputed phase boundaries (event indices where phases change)
    early_to_mid_idx: int | None = None
    mid_to_late_idx: int | None = None
    late_to_closing_idx: int | None = None
    overtime_start_idx: int | None = None
    
    # Cached event states (event_index -> GamePhaseState)
    _event_states: dict[int, GamePhaseState] | None = None
    
    def __post_init__(self) -> None:
        if self._event_states is None:
            object.__setattr__(self, '_event_states', {})
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize for generation_trace."""
        return {
            "sport": self.sport,
            "phase_type": self.structure.phase_type.value,
            "total_events": self.total_events,
            "total_pbp_events": self.total_pbp_events,
            "has_overtime": self.has_overtime,
            "max_phase_number": self.max_phase_number,
            "total_regulation_seconds": self.structure.total_regulation_seconds,
            "thresholds": {
                "early_game": self.early_game_threshold,
                "mid_game": self.mid_game_threshold,
                "late_game": self.late_game_threshold,
                "closing": self.closing_threshold,
            },
            "boundaries": {
                "early_to_mid_idx": self.early_to_mid_idx,
                "mid_to_late_idx": self.mid_to_late_idx,
                "late_to_closing_idx": self.late_to_closing_idx,
                "overtime_start_idx": self.overtime_start_idx,
            },
        }
    
    def get_event_state(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> GamePhaseState:
        """Get cached or compute phase state for an event.
        
        This is the core method - all other methods delegate to this.
        """
        if self._event_states is None:
            object.__setattr__(self, '_event_states', {})
        
        if event_idx in self._event_states:
            return self._event_states[event_idx]
        
        if 0 <= event_idx < len(events):
            state = compute_game_phase_state(
                events[event_idx],
                structure=self.structure,
            )
            self._event_states[event_idx] = state
            return state
        
        # Out of bounds - return default state
        return GamePhaseState(
            phase_number=1,
            phase_type=self.structure.phase_type,
            clock_seconds=self.structure.phase_duration_seconds,
            elapsed_seconds=0,
            remaining_seconds=self.structure.total_regulation_seconds,
            game_progress=0.0,
            sport=self.sport,
            total_regulation_seconds=self.structure.total_regulation_seconds,
        )
    
    def get_progress(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> float:
        """Get game progress (0.0 to 1.0+) for an event."""
        return self.get_event_state(event_idx, events).game_progress
    
    def classify_event(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> str:
        """Classify an event into a game phase.
        
        Returns one of: "early", "mid", "late", "closing", "overtime"
        """
        state = self.get_event_state(event_idx, events)
        
        if state.is_overtime:
            return "overtime"
        
        progress = state.game_progress
        
        if progress <= self.early_game_threshold:
            return "early"
        elif progress <= self.mid_game_threshold:
            return "mid"
        elif progress <= self.closing_threshold:
            return "late"
        else:
            return "closing"
    
    def is_early_game(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> bool:
        """Check if event is in early game."""
        return self.classify_event(event_idx, events) == "early"
    
    def is_mid_game(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> bool:
        """Check if event is in mid game."""
        return self.classify_event(event_idx, events) == "mid"
    
    def is_late_game(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> bool:
        """Check if event is in late game or later."""
        phase = self.classify_event(event_idx, events)
        return phase in ("late", "closing", "overtime")
    
    def is_closing(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> bool:
        """Check if event is in closing phase."""
        phase = self.classify_event(event_idx, events)
        return phase in ("closing", "overtime")
    
    def is_final_phase(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> bool:
        """Check if event is in final phase of regulation or OT."""
        return self.get_event_state(event_idx, events).is_final_phase
    
    def is_overtime(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> bool:
        """Check if event is in overtime."""
        return self.get_event_state(event_idx, events).is_overtime
    
    def get_phase_label(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> str:
        """Get human-readable phase label for an event."""
        state = self.get_event_state(event_idx, events)
        return get_phase_label(state)
    
    def get_diagnostic_snapshot(
        self,
        event_idx: int,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Get full diagnostic info for an event (for generation_trace)."""
        state = self.get_event_state(event_idx, events)
        phase = self.classify_event(event_idx, events)
        
        return {
            "event_idx": event_idx,
            "phase": phase,
            "phase_label": get_phase_label(state),
            "progress": round(state.game_progress, 4),
            "phase_number": state.phase_number,
            "clock_seconds": state.clock_seconds,
            "elapsed_seconds": state.elapsed_seconds,
            "remaining_seconds": state.remaining_seconds,
            "is_early_game": phase == "early",
            "is_mid_game": phase == "mid",
            "is_late_game": phase in ("late", "closing", "overtime"),
            "is_closing": phase in ("closing", "overtime"),
            "is_final_phase": state.is_final_phase,
            "is_overtime": state.is_overtime,
        }


def build_game_phase_context(
    events: list[dict[str, Any]],
    sport: str | None = None,
    structure: GameStructure | None = None,
    early_game_threshold: float = DEFAULT_EARLY_GAME_THRESHOLD,
    mid_game_threshold: float = DEFAULT_MID_GAME_THRESHOLD,
    late_game_threshold: float = DEFAULT_LATE_GAME_THRESHOLD,
    closing_threshold: float = DEFAULT_CLOSING_THRESHOLD,
) -> GamePhaseContext:
    """Build the authoritative game phase context.
    
    This should be called ONCE per game, early in the pipeline.
    The resulting context is then passed to all phase-dependent logic.
    
    Args:
        events: Full timeline events
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
        structure: Explicit game structure (optional)
        early_game_threshold: Progress threshold for early game end
        mid_game_threshold: Progress threshold for mid game end
        late_game_threshold: Progress threshold for late game start
        closing_threshold: Progress threshold for closing start
    
    Returns:
        GamePhaseContext ready for use by all pipeline components
    """
    if structure is None:
        structure = get_game_structure(sport)
    
    # Scan events to compute game-level stats and boundaries
    total_events = len(events)
    pbp_events = [e for e in events if e.get("event_type") == "pbp"]
    total_pbp_events = len(pbp_events)
    
    has_overtime = False
    max_phase_number = 1
    
    early_to_mid_idx: int | None = None
    mid_to_late_idx: int | None = None
    late_to_closing_idx: int | None = None
    overtime_start_idx: int | None = None
    
    prev_phase = "early"
    
    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue
        
        state = compute_game_phase_state(event, structure=structure)
        max_phase_number = max(max_phase_number, state.phase_number)
        
        if state.is_overtime and not has_overtime:
            has_overtime = True
            overtime_start_idx = i
        
        # Determine current phase
        if state.is_overtime:
            current_phase = "overtime"
        elif state.game_progress <= early_game_threshold:
            current_phase = "early"
        elif state.game_progress <= mid_game_threshold:
            current_phase = "mid"
        elif state.game_progress <= closing_threshold:
            current_phase = "late"
        else:
            current_phase = "closing"
        
        # Track phase transitions
        if prev_phase == "early" and current_phase != "early":
            early_to_mid_idx = i
        if prev_phase == "mid" and current_phase in ("late", "closing", "overtime"):
            mid_to_late_idx = i
        if prev_phase == "late" and current_phase in ("closing", "overtime"):
            late_to_closing_idx = i
        
        prev_phase = current_phase
    
    context = GamePhaseContext(
        sport=structure.sport,
        structure=structure,
        total_events=total_events,
        total_pbp_events=total_pbp_events,
        has_overtime=has_overtime,
        max_phase_number=max_phase_number,
        early_game_threshold=early_game_threshold,
        mid_game_threshold=mid_game_threshold,
        late_game_threshold=late_game_threshold,
        closing_threshold=closing_threshold,
        early_to_mid_idx=early_to_mid_idx,
        mid_to_late_idx=mid_to_late_idx,
        late_to_closing_idx=late_to_closing_idx,
        overtime_start_idx=overtime_start_idx,
        _event_states={},
    )
    
    logger.debug(
        "game_phase_context_built",
        extra={
            "sport": structure.sport,
            "total_events": total_events,
            "total_pbp_events": total_pbp_events,
            "has_overtime": has_overtime,
            "max_phase_number": max_phase_number,
            "early_to_mid_idx": early_to_mid_idx,
            "mid_to_late_idx": mid_to_late_idx,
            "late_to_closing_idx": late_to_closing_idx,
            "overtime_start_idx": overtime_start_idx,
        },
    )
    
    return context


# =============================================================================
# LEGACY COMPATIBILITY HELPERS
# =============================================================================
# These functions maintain backward compatibility while delegating to the
# new authoritative context when available.

_current_context: GamePhaseContext | None = None


def set_current_phase_context(context: GamePhaseContext | None) -> None:
    """Set the current game phase context for legacy functions.
    
    This allows legacy functions to use the authoritative context
    without requiring signature changes everywhere.
    """
    global _current_context
    _current_context = context


def get_current_phase_context() -> GamePhaseContext | None:
    """Get the current game phase context."""
    return _current_context


def clear_phase_context() -> None:
    """Clear the current phase context (call after game processing)."""
    global _current_context
    _current_context = None
