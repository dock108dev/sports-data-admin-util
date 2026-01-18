"""
Score Normalization for Moments.

Handles normalization of scores in game timelines to ensure score continuity
is structurally reliable for moment detection.

PHASE 1.4: Score normalization ensures that:
1. Missing scores are carried forward from the previous valid score
2. Quarter boundary resets are handled correctly
3. All normalization decisions are recorded for auditability
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass
class ScoreNormalization:
    """Record of a score normalization decision for traceability."""
    index: int
    original_home: int | None
    original_away: int | None
    normalized_home: int
    normalized_away: int
    reason: str  # e.g., "missing_score_carry_forward", "quarter_boundary", "game_start"


@dataclass
class NormalizedTimeline:
    """Result of score normalization with full traceability."""
    events: list[dict[str, Any]]
    normalizations: list[ScoreNormalization]
    
    def had_corrections(self) -> bool:
        """Returns True if any scores were corrected."""
        return len(self.normalizations) > 0


def normalize_scores(events: Sequence[dict[str, Any]]) -> NormalizedTimeline:
    """
    Normalize scores in the timeline by carrying forward the most recent valid score.
    
    PHASE 1.4: This ensures score continuity is structurally reliable.
    
    Rules:
    1. At game start (no prior events), default to (0, 0)
    2. For any event with missing score (None), carry forward the previous valid score
    3. For quarter boundaries, preserve the last valid score from previous quarter
    4. Never silently drop score information
    
    All normalization decisions are recorded for auditability.
    
    Args:
        events: Original timeline events
        
    Returns:
        NormalizedTimeline with events (potentially modified) and normalization records
    """
    normalizations: list[ScoreNormalization] = []
    normalized_events: list[dict[str, Any]] = []
    
    # Track the last valid score
    last_valid_home: int = 0
    last_valid_away: int = 0
    has_seen_valid_score = False
    
    for i, event in enumerate(events):
        # Create a shallow copy to avoid modifying the original
        normalized_event = dict(event)
        
        # Only process PBP events for score normalization
        if event.get("event_type") != "pbp":
            normalized_events.append(normalized_event)
            continue
        
        original_home = event.get("home_score")
        original_away = event.get("away_score")
        
        # Determine the normalized scores
        needs_normalization = False
        reason = ""
        
        if original_home is None or original_away is None:
            # Missing score - carry forward
            needs_normalization = True
            if has_seen_valid_score:
                reason = "missing_score_carry_forward"
            else:
                reason = "game_start_default"
            normalized_home = last_valid_home
            normalized_away = last_valid_away
        elif original_home == 0 and original_away == 0 and has_seen_valid_score:
            # Potential score reset - check if it's a real reset or data issue
            # Real resets happen at quarter boundaries with specific markers
            description = (event.get("description") or "").lower()
            is_quarter_marker = any(m in description for m in [
                "start of", "end of", "beginning of", "start period", "end period"
            ])
            
            if is_quarter_marker:
                # This is a quarter marker with reset score - carry forward
                needs_normalization = True
                reason = "quarter_boundary_carry_forward"
                normalized_home = last_valid_home
                normalized_away = last_valid_away
            else:
                # Check if this is actually a data anomaly (0-0 after significant scoring)
                total_points = last_valid_home + last_valid_away
                if total_points > 10:  # Significant scoring happened, this is likely bad data
                    needs_normalization = True
                    reason = "apparent_reset_carry_forward"
                    normalized_home = last_valid_home
                    normalized_away = last_valid_away
                else:
                    # Early game, could be legitimate (e.g., replay correction)
                    normalized_home = original_home
                    normalized_away = original_away
        else:
            # Valid score - use as-is and update tracking
            normalized_home = original_home
            normalized_away = original_away
            last_valid_home = normalized_home
            last_valid_away = normalized_away
            has_seen_valid_score = True
        
        # Record normalization if applied
        if needs_normalization:
            normalizations.append(ScoreNormalization(
                index=i,
                original_home=original_home,
                original_away=original_away,
                normalized_home=normalized_home,
                normalized_away=normalized_away,
                reason=reason,
            ))
            normalized_event["home_score"] = normalized_home
            normalized_event["away_score"] = normalized_away
            normalized_event["_score_normalized"] = True
            normalized_event["_normalization_reason"] = reason
        
        normalized_events.append(normalized_event)
    
    return NormalizedTimeline(events=normalized_events, normalizations=normalizations)
