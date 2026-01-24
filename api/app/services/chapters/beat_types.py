"""
Beat Types and Constants: Locked beat taxonomy for NBA v1.

This module defines the beat type enums, descriptors, and threshold constants
used throughout the beat classification system.

LOCKED BEAT TAXONOMY (NBA v1):
- FAST_START
- MISSED_SHOT_FEST (deprecated as primary, retained for compatibility)
- BACK_AND_FORTH
- EARLY_CONTROL
- RUN
- RESPONSE
- STALL
- CRUNCH_SETUP
- CLOSING_SEQUENCE
- OVERTIME

No new beats. No renaming. No synonyms. No compound beats.
"""

from __future__ import annotations

from enum import Enum


# ============================================================================
# LOCKED BEAT TAXONOMY (NBA v1)
# ============================================================================


class BeatType(str, Enum):
    """Locked beat types for NBA v1.

    These are the ONLY valid beat types. No additions, renaming, or synonyms.

    Note: MISSED_SHOT_FEST is retained in enum for backward compatibility
    but is no longer used as a primary beat (Phase 2.1).
    """

    FAST_START = "FAST_START"
    MISSED_SHOT_FEST = "MISSED_SHOT_FEST"  # Deprecated as primary beat (Phase 2.1)
    BACK_AND_FORTH = "BACK_AND_FORTH"
    EARLY_CONTROL = "EARLY_CONTROL"
    RUN = "RUN"
    RESPONSE = "RESPONSE"
    STALL = "STALL"
    CRUNCH_SETUP = "CRUNCH_SETUP"
    CLOSING_SEQUENCE = "CLOSING_SEQUENCE"
    OVERTIME = "OVERTIME"


class BeatDescriptor(str, Enum):
    """Secondary descriptors that may coexist with any primary beat.

    Descriptors:
    - Do NOT replace primary beats
    - May coexist with any primary beat
    - Are optional (0-N per chapter or section)

    Phase 2.1: MISSED_SHOT_CONTEXT replaces MISSED_SHOT_FEST as primary beat.
    """

    MISSED_SHOT_CONTEXT = "MISSED_SHOT_CONTEXT"


# ============================================================================
# PRIMARY BEATS AND PRIORITY ORDER (Phase 2.1)
# ============================================================================

# Primary beats that can be assigned as the main beat_type
# MISSED_SHOT_FEST is excluded - it's now a descriptor only
PRIMARY_BEATS: set[BeatType] = {
    BeatType.FAST_START,
    BeatType.EARLY_CONTROL,
    BeatType.RUN,
    BeatType.RESPONSE,
    BeatType.BACK_AND_FORTH,
    BeatType.STALL,
    BeatType.CRUNCH_SETUP,
    BeatType.CLOSING_SEQUENCE,
    BeatType.OVERTIME,
}

# Priority order for section beat selection (highest priority first)
# Used when multiple chapters in a section have different beats
BEAT_PRIORITY: list[BeatType] = [
    BeatType.OVERTIME,  # 1. Highest priority
    BeatType.CLOSING_SEQUENCE,  # 2.
    BeatType.CRUNCH_SETUP,  # 3.
    BeatType.RUN,  # 4.
    BeatType.RESPONSE,  # 5.
    BeatType.BACK_AND_FORTH,  # 6.
    BeatType.EARLY_CONTROL,  # 7.
    BeatType.FAST_START,  # 8.
    BeatType.STALL,  # 9. Lowest priority (default)
]


# ============================================================================
# THRESHOLD CONSTANTS
# ============================================================================

# Threshold for MISSED_SHOT_CONTEXT descriptor (points per play)
MISSED_SHOT_PPP_THRESHOLD = 0.35

# Run detection thresholds
RUN_WINDOW_THRESHOLD = 6  # Minimum unanswered points to start a run window
RUN_MARGIN_EXPANSION_THRESHOLD = (
    8  # Margin increase required to qualify without lead change
)

# Back-and-forth detection thresholds (Phase 2.4)
BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD = 2  # Minimum lead changes to qualify
BACK_AND_FORTH_TIES_THRESHOLD = 3  # Minimum ties to qualify

# Early window detection thresholds (Phase 2.5 - Section-level beats)
EARLY_WINDOW_DURATION_SECONDS = 360  # First 6:00 of Q1 (time > 6:00 remaining)
FAST_START_MIN_COMBINED_POINTS = 30  # Combined points >= 30 for FAST_START
FAST_START_MAX_MARGIN = 6  # Margin <= 6 for FAST_START
EARLY_CONTROL_MIN_LEAD = 8  # Lead >= 8 for EARLY_CONTROL
EARLY_CONTROL_MIN_SHARE_PCT = 0.65  # Leading team scores >= 65% of total

# Late-game beat thresholds (Phase 2.6)
CRUNCH_SETUP_TIME_THRESHOLD = 300  # <= 5:00 remaining in Q4
CRUNCH_SETUP_MARGIN_THRESHOLD = 10  # Margin <= 10 for CRUNCH_SETUP
CLOSING_SEQUENCE_TIME_THRESHOLD = 120  # <= 2:00 remaining in Q4
CLOSING_SEQUENCE_MARGIN_THRESHOLD = 8  # Margin <= 8 for CLOSING_SEQUENCE
