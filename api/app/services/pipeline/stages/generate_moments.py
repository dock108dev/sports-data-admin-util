"""GENERATE_MOMENTS Stage Implementation.

This stage segments normalized PBP data into condensed moments using
deterministic, rule-based boundary detection, and selects which plays
must be explicitly narrated.

STORY CONTRACT ALIGNMENT
========================
This implementation adheres to the Story contract:
- Moments are derived DIRECTLY from PBP data
- No signals, momentum, or narrative abstractions
- No LLM/OpenAI calls
- Ordering is by play_index (canonical)
- Output contains NO narrative text

SEGMENTATION RULES
==================
Boundaries occur at:
1. After any scoring play (score changes from previous play)
2. At period boundaries (quarter/half changes)
3. After timeout plays
4. After hard maximum plays (5) to ensure small moments

These rules are:
- Deterministic (same input always produces same output)
- Explainable from PBP facts alone
- Conservative (prefer more, smaller moments)

EXPLICIT NARRATION SELECTION
============================
Each moment must identify at least one play for explicit narration.
Selection rules (in priority order):
1. Scoring plays: Any play where score changed from previous play
2. Notable plays: Plays with notable play_types (blocks, steals, etc.)
3. Fallback: Last play in the moment

This ensures narrative traceability: every moment has a concrete
answer to "which play backs this moment?"

GUARANTEES
==========
1. Full play coverage: Every play appears in exactly one moment
2. No overlap: No play_id appears in more than one moment
3. Correct ordering: Moments ordered by first play's play_index
4. Non-empty: Every moment has at least 1 play_id
5. Narration coverage: Every moment has at least 1 explicitly_narrated_play_id
6. Narration subset: explicitly_narrated_play_ids is a subset of play_ids
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import StageInput, StageOutput

logger = logging.getLogger(__name__)

# Maximum plays per moment before forcing a boundary
MAX_PLAYS_PER_MOMENT = 5

# Play types that indicate stoppages (timeouts, reviews, etc.)
STOPPAGE_PLAY_TYPES = frozenset([
    "timeout",
    "full_timeout",
    "official_timeout",
    "tv_timeout",
    "20_second_timeout",
    "review",
    "instant_replay",
    "delay_of_game",
    "ejection",
])

# Play types that are notable and should be narrated (non-scoring)
# These are plays that typically warrant explicit mention in game narrative
NOTABLE_PLAY_TYPES = frozenset([
    # Defensive plays
    "block",
    "blocked_shot",
    "steal",
    # Turnovers
    "turnover",
    "offensive_foul",
    # Rebounds (contested action)
    "offensive_rebound",
    "defensive_rebound",
    # Fast breaks / assists
    "assist",
    "fast_break",
    # Fouls
    "foul",
    "personal_foul",
    "shooting_foul",
    "technical_foul",
    "flagrant_foul",
    # Other notable events
    "jump_ball",
    "jumpball",
    "violation",
])


def _is_scoring_play(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
) -> bool:
    """Detect if the current play resulted in a score change.

    A scoring play is detected when either home_score or away_score
    differs from the previous play's scores.

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)

    Returns:
        True if score changed, False otherwise
    """
    if previous_event is None:
        # First play: scoring if scores are non-zero
        home = current_event.get("home_score") or 0
        away = current_event.get("away_score") or 0
        return home > 0 or away > 0

    prev_home = previous_event.get("home_score") or 0
    prev_away = previous_event.get("away_score") or 0
    curr_home = current_event.get("home_score") or 0
    curr_away = current_event.get("away_score") or 0

    return curr_home != prev_home or curr_away != prev_away


def _is_period_boundary(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
) -> bool:
    """Detect if this play starts a new period.

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)

    Returns:
        True if period changed, False otherwise
    """
    if previous_event is None:
        return False

    prev_quarter = previous_event.get("quarter") or 1
    curr_quarter = current_event.get("quarter") or 1

    return curr_quarter != prev_quarter


def _is_stoppage_play(event: dict[str, Any]) -> bool:
    """Detect if this play is a stoppage (timeout, review, etc.).

    Args:
        event: The normalized PBP event

    Returns:
        True if this is a stoppage play, False otherwise
    """
    play_type = (event.get("play_type") or "").lower().replace(" ", "_")
    description = (event.get("description") or "").lower()

    # Check explicit play_type
    if play_type in STOPPAGE_PLAY_TYPES:
        return True

    # Check description for timeout indicators
    if "timeout" in description:
        return True

    return False


def _should_start_new_moment(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    current_moment_size: int,
) -> bool:
    """Determine if we should start a new moment before this play.

    BOUNDARY RULES (in priority order):
    1. Period boundary: Always start new moment at period change
    2. Hard maximum: Start new moment if current would exceed MAX_PLAYS_PER_MOMENT
    3. After scoring: Previous play was a scoring play
    4. After stoppage: Previous play was a timeout/review

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)
        current_moment_size: Number of plays in current moment

    Returns:
        True if a new moment should start, False otherwise
    """
    # First play always starts first moment
    if previous_event is None:
        return True

    # Rule 1: Period boundary - always start new moment
    if _is_period_boundary(current_event, previous_event):
        return True

    # Rule 2: Hard maximum exceeded
    if current_moment_size >= MAX_PLAYS_PER_MOMENT:
        return True

    # Rule 3: Previous play was a scoring play
    if _is_scoring_play(previous_event, None):
        # We need the play before previous to check if previous was scoring
        # This is handled by tracking in the main loop
        pass

    # Rule 4: Previous play was a stoppage
    if _is_stoppage_play(previous_event):
        return True

    return False


def _get_score_before_moment(
    events: list[dict[str, Any]],
    moment_start_index: int,
) -> tuple[int, int]:
    """Get the score state BEFORE the first play of a moment.

    The score_before is the score after the play immediately preceding
    the first play of this moment. For the first moment, it's [0, 0].

    Args:
        events: All normalized PBP events
        moment_start_index: Index of first play in this moment

    Returns:
        Tuple of (home_score, away_score) before the moment
    """
    if moment_start_index == 0:
        return (0, 0)

    prev_event = events[moment_start_index - 1]
    home = prev_event.get("home_score") or 0
    away = prev_event.get("away_score") or 0
    return (home, away)


def _get_score_after_moment(last_event: dict[str, Any]) -> tuple[int, int]:
    """Get the score state AFTER the last play of a moment.

    Args:
        last_event: The last PBP event in the moment

    Returns:
        Tuple of (home_score, away_score) after the moment
    """
    home = last_event.get("home_score") or 0
    away = last_event.get("away_score") or 0
    return (home, away)


def _is_notable_play(event: dict[str, Any]) -> bool:
    """Check if a play has a notable play_type.

    Args:
        event: The normalized PBP event

    Returns:
        True if the play_type is in NOTABLE_PLAY_TYPES
    """
    play_type = (event.get("play_type") or "").lower().replace(" ", "_")
    return play_type in NOTABLE_PLAY_TYPES


def _select_explicitly_narrated_plays(
    moment_plays: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> list[int]:
    """Select which plays in a moment must be explicitly narrated.

    SELECTION RULES (deterministic, based on PBP facts only):

    1. SCORING PLAYS: Any play where score differs from the previous play.
       These are the most concrete, verifiable events.

    2. NOTABLE PLAYS: If no scoring plays, select plays with notable
       play_types (blocks, steals, turnovers, etc.).

    3. FALLBACK: If no scoring or notable plays, select the last play.
       Every moment must have at least one narrated play.

    Args:
        moment_plays: List of PBP events in this moment
        all_events: All PBP events (for score comparison)
        moment_start_idx: Index of first play in all_events

    Returns:
        List of play_index values that must be explicitly narrated.
        Guaranteed to be non-empty and a subset of moment play_ids.
    """
    narrated_ids: list[int] = []

    # RULE 1: Identify scoring plays
    for i, play in enumerate(moment_plays):
        # Get the previous event (could be from previous moment or this moment)
        global_idx = moment_start_idx + i
        if global_idx == 0:
            # First play of game - scoring if scores > 0
            home = play.get("home_score") or 0
            away = play.get("away_score") or 0
            if home > 0 or away > 0:
                narrated_ids.append(play["play_index"])
        else:
            prev_event = all_events[global_idx - 1]
            if _is_scoring_play(play, prev_event):
                narrated_ids.append(play["play_index"])

    # If we found scoring plays, return them
    if narrated_ids:
        return narrated_ids

    # RULE 2: Look for notable plays (blocks, steals, etc.)
    for play in moment_plays:
        if _is_notable_play(play):
            narrated_ids.append(play["play_index"])

    # If we found notable plays, return them
    if narrated_ids:
        return narrated_ids

    # RULE 3: Fallback - select the last play
    # This ensures every moment has at least one narrated play
    narrated_ids.append(moment_plays[-1]["play_index"])

    return narrated_ids


def _segment_plays_into_moments(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Segment PBP events into condensed moments.

    ALGORITHM:
    1. Iterate through events in play_index order (already sorted)
    2. Accumulate plays into current moment
    3. Check boundary conditions after each play
    4. When boundary detected, finalize current moment and start new one

    BOUNDARY CONDITIONS (checked AFTER adding play to moment):
    - Scoring play: End moment after the scoring play
    - Stoppage play: End moment after the stoppage
    - Hard maximum: End moment when size reaches MAX_PLAYS_PER_MOMENT
    - Period change: End moment, next play starts new moment

    Args:
        events: Normalized PBP events, ordered by play_index

    Returns:
        List of moment dicts with required fields

    Raises:
        ValueError: If any guarantee is violated
    """
    if not events:
        return []

    moments: list[dict[str, Any]] = []
    current_moment_plays: list[dict[str, Any]] = []
    current_moment_start_idx = 0

    # Track all play_ids for coverage verification
    all_play_ids: set[int] = set()
    assigned_play_ids: set[int] = set()

    for i, event in enumerate(events):
        play_index = event.get("play_index")
        if play_index is None:
            raise ValueError(f"Event at position {i} missing play_index")

        all_play_ids.add(play_index)

        # Check if we should start a new moment BEFORE this play
        previous_event = events[i - 1] if i > 0 else None

        # Period boundary check - start new moment
        if previous_event and _is_period_boundary(event, previous_event):
            if current_moment_plays:
                moments.append(
                    _finalize_moment(events, current_moment_plays, current_moment_start_idx)
                )
                for p in current_moment_plays:
                    assigned_play_ids.add(p["play_index"])
                current_moment_plays = []
            current_moment_start_idx = i

        # Add current play to moment
        current_moment_plays.append(event)

        # Check boundary conditions AFTER adding play
        should_end_moment = False

        # Scoring play ends moment
        if _is_scoring_play(event, previous_event):
            should_end_moment = True

        # Stoppage play ends moment
        if _is_stoppage_play(event):
            should_end_moment = True

        # Hard maximum reached
        if len(current_moment_plays) >= MAX_PLAYS_PER_MOMENT:
            should_end_moment = True

        # Last play always ends moment
        if i == len(events) - 1:
            should_end_moment = True

        if should_end_moment and current_moment_plays:
            moments.append(
                _finalize_moment(events, current_moment_plays, current_moment_start_idx)
            )
            for p in current_moment_plays:
                assigned_play_ids.add(p["play_index"])
            current_moment_plays = []
            current_moment_start_idx = i + 1

    # VERIFICATION: Full coverage
    if all_play_ids != assigned_play_ids:
        missing = all_play_ids - assigned_play_ids
        extra = assigned_play_ids - all_play_ids
        raise ValueError(
            f"Play coverage violation. Missing: {missing}, Extra: {extra}"
        )

    # VERIFICATION: No overlap (handled by set operations above)
    # VERIFICATION: Non-empty moments and narration
    for idx, moment in enumerate(moments):
        if not moment["play_ids"]:
            raise ValueError(f"Moment {idx} has no play_ids")

        # VERIFICATION: Non-empty explicitly_narrated_play_ids
        if not moment.get("explicitly_narrated_play_ids"):
            raise ValueError(f"Moment {idx} has no explicitly_narrated_play_ids")

        # VERIFICATION: Narrated plays are subset of play_ids
        play_ids_set = set(moment["play_ids"])
        narrated_set = set(moment["explicitly_narrated_play_ids"])
        if not narrated_set.issubset(play_ids_set):
            invalid = narrated_set - play_ids_set
            raise ValueError(
                f"Moment {idx} has narrated play_ids not in play_ids: {invalid}"
            )

    # VERIFICATION: Correct ordering
    prev_first_play = -1
    for idx, moment in enumerate(moments):
        first_play = moment["play_ids"][0]
        if first_play <= prev_first_play:
            raise ValueError(
                f"Moment ordering violation at index {idx}: "
                f"first_play {first_play} <= previous {prev_first_play}"
            )
        prev_first_play = first_play

    return moments


def _finalize_moment(
    all_events: list[dict[str, Any]],
    moment_plays: list[dict[str, Any]],
    moment_start_idx: int,
) -> dict[str, Any]:
    """Finalize a moment with all required metadata.

    Args:
        all_events: All PBP events (for score_before lookup)
        moment_plays: Plays in this moment
        moment_start_idx: Index of first play in all_events

    Returns:
        Moment dict matching required output shape
    """
    first_play = moment_plays[0]
    last_play = moment_plays[-1]

    # Extract play_ids in order
    play_ids = [p["play_index"] for p in moment_plays]

    # Select plays that must be explicitly narrated
    explicitly_narrated_play_ids = _select_explicitly_narrated_plays(
        moment_plays, all_events, moment_start_idx
    )

    # Period from first play
    period = first_play.get("quarter") or 1

    # Clock values (may be null)
    start_clock = first_play.get("game_clock")
    end_clock = last_play.get("game_clock")

    # Score states
    score_before = list(_get_score_before_moment(all_events, moment_start_idx))
    score_after = list(_get_score_after_moment(last_play))

    return {
        "play_ids": play_ids,
        "explicitly_narrated_play_ids": explicitly_narrated_play_ids,
        "period": period,
        "start_clock": start_clock,
        "end_clock": end_clock,
        "score_before": score_before,
        "score_after": score_after,
    }


async def execute_generate_moments(stage_input: StageInput) -> StageOutput:
    """Execute the GENERATE_MOMENTS stage.

    Reads normalized PBP from previous stage output and segments
    plays into condensed moments using deterministic rules.

    NO NARRATIVE TEXT IS GENERATED.
    NO LLM/OPENAI CALLS ARE MADE.

    Args:
        stage_input: Input containing previous_output with pbp_events

    Returns:
        StageOutput with moments list

    Raises:
        ValueError: If input is invalid or guarantees are violated
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting GENERATE_MOMENTS for game {game_id}")

    # Get normalized PBP from previous stage output
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("GENERATE_MOMENTS requires previous stage output")

    pbp_events = previous_output.get("pbp_events")
    if not pbp_events:
        raise ValueError("No pbp_events in previous stage output")

    output.add_log(f"Processing {len(pbp_events)} PBP events")

    # Verify events are ordered by play_index
    prev_index = -1
    for i, event in enumerate(pbp_events):
        play_index = event.get("play_index")
        if play_index is None:
            raise ValueError(f"Event at position {i} missing play_index")
        if play_index <= prev_index:
            raise ValueError(
                f"Events not ordered by play_index at position {i}: "
                f"{play_index} <= {prev_index}"
            )
        prev_index = play_index

    output.add_log("Verified play_index ordering")

    # Segment plays into moments
    moments = _segment_plays_into_moments(pbp_events)

    output.add_log(f"Segmented into {len(moments)} moments")

    # Log moment size distribution for reviewability
    sizes = [len(m["play_ids"]) for m in moments]
    if sizes:
        avg_size = sum(sizes) / len(sizes)
        min_size = min(sizes)
        max_size = max(sizes)
        output.add_log(
            f"Moment sizes: min={min_size}, max={max_size}, avg={avg_size:.1f}"
        )

    # Count scoring moments for verification
    scoring_moments = sum(
        1 for m in moments if m["score_before"] != m["score_after"]
    )
    output.add_log(f"Scoring moments: {scoring_moments}")

    # Log explicitly narrated play statistics
    narrated_counts = [len(m["explicitly_narrated_play_ids"]) for m in moments]
    total_narrated = sum(narrated_counts)
    total_plays = sum(sizes)
    narration_pct = (total_narrated / total_plays * 100) if total_plays > 0 else 0
    output.add_log(
        f"Narrated plays: {total_narrated}/{total_plays} ({narration_pct:.1f}%)"
    )
    output.add_log(
        f"Narrated per moment: min={min(narrated_counts)}, max={max(narrated_counts)}, "
        f"avg={sum(narrated_counts)/len(narrated_counts):.1f}"
    )

    # Output matches required shape exactly:
    # {
    #   "moments": [
    #     {
    #       "play_ids": [...],
    #       "explicitly_narrated_play_ids": [...],
    #       "period": int,
    #       "start_clock": str|null,
    #       "end_clock": str|null,
    #       "score_before": [int, int],
    #       "score_after": [int, int]
    #     }
    #   ]
    # }
    output.data = {"moments": moments}

    output.add_log("GENERATE_MOMENTS completed successfully")

    return output
