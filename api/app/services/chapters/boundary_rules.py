"""
Chapter Boundary Rules for NBA v1.

This module defines the authoritative rules for when chapter boundaries occur.

PHILOSOPHY:
A chapter represents a scene change, not a possession change or every score.
Boundaries separate different stretches of control, tactical resets, and
emotional/structural shifts in the game.

Boundaries must be rare enough to keep chapters meaningful.

ISSUE 0.3: NBA v1 Rules (Intentionally Simple)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class BoundaryReasonCode(str, Enum):
    """Fixed enum of reason codes explaining chapter boundaries.
    
    These codes are diagnostic, not narrative. They explain WHY a boundary
    exists for debugging, tuning, and validation.
    
    Multiple reason codes may exist per chapter (e.g., PERIOD_START + TIMEOUT).
    Reason codes must be deterministic.
    
    NBA v1 Reason Codes (Issue 0.3):
    """
    
    # Hard boundaries (always break)
    PERIOD_START = "PERIOD_START"          # Start of quarter
    PERIOD_END = "PERIOD_END"              # End of quarter
    OVERTIME_START = "OVERTIME_START"      # Start of overtime
    GAME_END = "GAME_END"                  # End of game
    
    # Scene reset boundaries (usually break)
    TIMEOUT = "TIMEOUT"                    # Team timeout or official timeout
    REVIEW = "REVIEW"                      # Instant replay review or challenge
    
    # Momentum boundaries (conditional, minimal v1)
    RUN_START = "RUN_START"                # A scoring run begins
    RUN_END_RESPONSE = "RUN_END_RESPONSE"  # Run ends and opponent responds
    CRUNCH_START = "CRUNCH_START"          # Transition into crunch time


@dataclass
class BoundaryRule:
    """A rule that determines when a chapter boundary occurs.
    
    Rules are evaluated in precedence order. Higher precedence rules
    override lower precedence rules when multiple triggers occur.
    """
    
    name: str
    reason_code: BoundaryReasonCode
    precedence: int  # Higher = evaluated first
    description: str
    
    def evaluate(self, event: dict[str, Any], context: dict[str, Any]) -> bool:
        """Evaluate if this rule triggers a boundary.
        
        Args:
            event: Current PBP event
            context: Game context (previous events, state, etc.)
            
        Returns:
            True if this rule triggers a boundary
        """
        raise NotImplementedError("Subclasses must implement evaluate()")


# ============================================================================
# NBA v1 BOUNDARY RULES
# ============================================================================

class NBABoundaryRules:
    """NBA v1 chapter boundary rules.
    
    RULE CATEGORIES:
    1. Hard Boundaries (Always Break) - Precedence 100+
    2. Scene Reset Boundaries (Usually Break) - Precedence 50-99
    3. Momentum Boundaries (Conditional) - Precedence 1-49
    
    EXPLICIT NON-BOUNDARIES (Never Break):
    - Individual made baskets
    - Free throws
    - Substitutions (unless part of timeout/review)
    - Fouls without a broader scene change
    - Rebounds
    - Missed shots
    - Isolated turnovers
    
    These are structurally excluded to prevent over-segmentation.
    """
    
    # ========================================================================
    # 1. HARD BOUNDARIES (Always Break)
    # ========================================================================
    
    @staticmethod
    def is_period_start(event: dict[str, Any], prev_event: dict[str, Any] | None) -> bool:
        """Start of quarter always creates a boundary.
        
        Rule: If quarter changed from previous event, this is a period start.
        
        Args:
            event: Current event
            prev_event: Previous event (None if first event)
            
        Returns:
            True if this is the start of a new period
        """
        if prev_event is None:
            return True  # First event is always period start
        
        curr_quarter = event.get("quarter")
        prev_quarter = prev_event.get("quarter")
        
        return curr_quarter != prev_quarter and curr_quarter is not None
    
    @staticmethod
    def is_period_end(event: dict[str, Any], next_event: dict[str, Any] | None) -> bool:
        """End of quarter always creates a boundary.
        
        Rule: If next event is in a different quarter, this is a period end.
        
        Note: This is typically handled by the next event's PERIOD_START,
        so we don't create duplicate boundaries.
        
        Args:
            event: Current event
            next_event: Next event (None if last event)
            
        Returns:
            True if this is the end of a period
        """
        if next_event is None:
            return False  # Last event handled by GAME_END
        
        curr_quarter = event.get("quarter")
        next_quarter = next_event.get("quarter")
        
        return curr_quarter != next_quarter and next_quarter is not None
    
    @staticmethod
    def is_overtime_start(event: dict[str, Any], prev_event: dict[str, Any] | None) -> bool:
        """Start of overtime always creates a boundary.
        
        Rule: If quarter > 4 and previous quarter was 4, this is OT start.
        
        Args:
            event: Current event
            prev_event: Previous event
            
        Returns:
            True if this is the start of overtime
        """
        if prev_event is None:
            return False
        
        curr_quarter = event.get("quarter")
        prev_quarter = prev_event.get("quarter")
        
        # OT is quarter 5+ in NBA
        return (curr_quarter is not None and curr_quarter > 4 and
                prev_quarter is not None and prev_quarter == 4)
    
    @staticmethod
    def is_game_end(event: dict[str, Any], next_event: dict[str, Any] | None) -> bool:
        """End of game always creates a boundary.
        
        Rule: Last event in timeline is game end.
        
        Args:
            event: Current event
            next_event: Next event (None if last event)
            
        Returns:
            True if this is the end of the game
        """
        return next_event is None
    
    # ========================================================================
    # 2. SCENE RESET BOUNDARIES (Usually Break)
    # ========================================================================
    
    @staticmethod
    def is_timeout(event: dict[str, Any]) -> bool:
        """Timeout usually creates a boundary.
        
        Rule: Event description contains "timeout" (team or official).
        
        CLARIFICATIONS:
        - Consecutive timeouts collapse into one boundary (handled by deduplication)
        - Timeout immediately following period start is ignored (handled by precedence)
        
        Args:
            event: Current event
            
        Returns:
            True if this is a timeout
        """
        description = (event.get("description") or "").lower()
        play_type = (event.get("play_type") or "").lower()
        
        return "timeout" in description or "timeout" in play_type
    
    @staticmethod
    def is_review(event: dict[str, Any]) -> bool:
        """Instant replay review usually creates a boundary.
        
        Rule: Event description contains "review" or "challenge".
        
        Args:
            event: Current event
            
        Returns:
            True if this is a review/challenge
        """
        description = (event.get("description") or "").lower()
        play_type = (event.get("play_type") or "").lower()
        
        return ("review" in description or "challenge" in description or
                "review" in play_type or "challenge" in play_type)
    
    # ========================================================================
    # 3. MOMENTUM BOUNDARIES (Conditional, Minimal v1)
    # ========================================================================
    
    @staticmethod
    def is_run_start(
        event: dict[str, Any],
        context: dict[str, Any]
    ) -> bool:
        """A scoring run begins (conditional boundary).
        
        NBA v1 RUN DEFINITION (High Level):
        A run is a sequence of unanswered scoring by one team that:
        - Accumulates 6+ points
        - Spans at least 3 scoring plays
        - Occurs without the opponent scoring
        
        This is intentionally simple. Advanced run detection is Phase 1+.
        
        IMPORTANT: Tier crossings and lead changes alone are NOT boundaries.
        Only actual scoring runs create boundaries.
        
        Args:
            event: Current event
            context: Game context with run tracking
            
        Returns:
            True if a significant run is starting
        """
        # Not implemented in NBA v1
        return False
    
    @staticmethod
    def is_run_end_response(
        event: dict[str, Any],
        context: dict[str, Any]
    ) -> bool:
        """Run ends and opponent responds (conditional boundary).
        
        Rule: After a run, if opponent scores to break the run, that's a scene change.
        
        Args:
            event: Current event
            context: Game context with run tracking
            
        Returns:
            True if this is a response to a run
        """
        # Not implemented in NBA v1
        return False
    
    @staticmethod
    def is_crunch_start(
        event: dict[str, Any],
        prev_event: dict[str, Any] | None,
        context: dict[str, Any]
    ) -> bool:
        """Transition into crunch time (conditional boundary).
        
        NBA v1 CRUNCH TIME DEFINITION:
        - Time: Last 5 minutes of 4th quarter or any overtime
        - Score: Margin <= 5 points
        
        Rule: First event that meets both criteria creates a boundary.
        
        Args:
            event: Current event
            prev_event: Previous event
            context: Game context
            
        Returns:
            True if this is the start of crunch time
        """
        quarter = event.get("quarter")
        if quarter is None:
            return False
        
        # Must be Q4 or OT
        if quarter < 4:
            return False
        
        # Check if we just entered crunch time window
        game_clock = event.get("game_clock", "")
        
        # Parse clock (format: "MM:SS" or "M:SS")
        try:
            if ":" in game_clock:
                parts = game_clock.split(":")
                minutes = int(parts[0])
                seconds = int(parts[1])
                total_seconds = minutes * 60 + seconds
                
                # Must be <= 5 minutes (300 seconds)
                if total_seconds > 300:
                    return False
            else:
                return False
        except (ValueError, IndexError):
            return False
        
        # Check score margin
        home_score = event.get("home_score", 0)
        away_score = event.get("away_score", 0)
        margin = abs(home_score - away_score)
        
        # Must be <= 5 point game
        if margin > 5:
            return False
        
        # Check if previous event was NOT in crunch time
        if prev_event is None:
            return True  # First event in crunch window
        
        prev_quarter = prev_event.get("quarter")
        prev_clock = prev_event.get("game_clock", "")
        
        # If previous was different quarter, this is crunch start
        if prev_quarter != quarter:
            return True
        
        # If previous was > 5 minutes, this is crunch start
        try:
            if ":" in prev_clock:
                parts = prev_clock.split(":")
                prev_minutes = int(parts[0])
                prev_seconds = int(parts[1])
                prev_total_seconds = prev_minutes * 60 + prev_seconds
                
                if prev_total_seconds > 300:
                    return True  # Just entered 5-minute window
        except (ValueError, IndexError):
            pass
        
        return False


# ============================================================================
# BOUNDARY PRECEDENCE ORDER
# ============================================================================

BOUNDARY_PRECEDENCE = {
    # Hard boundaries (highest precedence)
    BoundaryReasonCode.PERIOD_START: 100,
    BoundaryReasonCode.OVERTIME_START: 95,
    BoundaryReasonCode.PERIOD_END: 90,
    BoundaryReasonCode.GAME_END: 85,
    
    # Scene reset boundaries (medium precedence)
    BoundaryReasonCode.REVIEW: 60,
    BoundaryReasonCode.TIMEOUT: 50,
    
    # Momentum boundaries (low precedence)
    BoundaryReasonCode.CRUNCH_START: 20,
    BoundaryReasonCode.RUN_START: 15,
    BoundaryReasonCode.RUN_END_RESPONSE: 10,
}


def resolve_boundary_precedence(reason_codes: list[BoundaryReasonCode]) -> list[BoundaryReasonCode]:
    """Resolve precedence when multiple boundary triggers occur.
    
    PRECEDENCE RULES:
    - Period boundary > timeout > run logic
    - Timeout immediately following period start does not create new chapter
    - Multiple triggers are deduplicated by precedence
    
    Args:
        reason_codes: List of triggered reason codes
        
    Returns:
        Deduplicated list of reason codes in precedence order
    """
    if not reason_codes:
        return []
    
    # Sort by precedence (highest first)
    sorted_codes = sorted(
        reason_codes,
        key=lambda code: BOUNDARY_PRECEDENCE.get(code, 0),
        reverse=True
    )
    
    # Deduplication rules
    result = []
    has_period_boundary = False
    
    for code in sorted_codes:
        # Check if this is a period boundary
        if code in (BoundaryReasonCode.PERIOD_START, BoundaryReasonCode.PERIOD_END,
                    BoundaryReasonCode.OVERTIME_START, BoundaryReasonCode.GAME_END):
            has_period_boundary = True
            result.append(code)
        
        # Skip timeout/review if we have a period boundary
        elif code in (BoundaryReasonCode.TIMEOUT, BoundaryReasonCode.REVIEW):
            if not has_period_boundary:
                result.append(code)
        
        # Include momentum boundaries unless overridden
        else:
            result.append(code)
    
    return result


# ============================================================================
# EXPLICIT NON-BOUNDARIES
# ============================================================================

def is_non_boundary_event(event: dict[str, Any]) -> bool:
    """Check if event is explicitly a non-boundary.
    
    These events NEVER create chapter boundaries by themselves.
    This list is critical to prevent regression into over-segmentation.
    
    EXPLICIT NON-BOUNDARIES:
    - Individual made baskets
    - Free throws
    - Substitutions (unless part of timeout/review)
    - Fouls without a broader scene change
    - Rebounds
    - Missed shots
    - Isolated turnovers
    
    Args:
        event: PBP event
        
    Returns:
        True if this event should never create a boundary
    """
    play_type = (event.get("play_type") or "").lower()
    description = (event.get("description") or "").lower()
    
    # Made baskets (unless part of run logic, handled separately)
    if "made" in description or "makes" in description:
        return True
    
    # Free throws
    if "free throw" in description or "free throw" in play_type:
        return True
    
    # Substitutions
    if "substitution" in description or "sub" in play_type:
        return True
    
    # Fouls
    if "foul" in description or "foul" in play_type:
        # Unless it's a technical/flagrant that might trigger review
        if "technical" not in description and "flagrant" not in description:
            return True
    
    # Rebounds
    if "rebound" in description or "rebound" in play_type:
        return True
    
    # Missed shots
    if "missed" in description or "misses" in description:
        return True
    
    # Turnovers
    if "turnover" in description or "turnover" in play_type:
        return True
    
    return False
