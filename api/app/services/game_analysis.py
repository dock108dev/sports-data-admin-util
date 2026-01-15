"""
Game analysis: segments, highlights, and scoring run detection.

This module analyzes timeline events to identify narrative segments
(runs, swings, blowouts) and highlights (lead changes, scoring runs).

AI Integration (Optional):
    Segments can be enriched with AI-generated labels and tone.
    This is OPTIONAL and cached. The core segment detection logic
    remains purely deterministic.

Extracted from timeline_generator.py for maintainability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from .ai_client import enrich_segment, is_ai_available

logger = logging.getLogger(__name__)

# Analysis thresholds (could be configurable per sport)
NBA_OPENING_WINDOW_SECONDS = 6 * 60
NBA_OPENING_EVENT_LIMIT = 4
NBA_RUN_POINTS_THRESHOLD = 8
NBA_SWING_MARGIN_THRESHOLD = 10
NBA_CLOSE_MARGIN_THRESHOLD = 5
NBA_CLOSE_WINDOW_SECONDS = 5 * 60
NBA_BLOWOUT_MARGIN_THRESHOLD = 20
NBA_GARBAGE_MARGIN_THRESHOLD = 18
NBA_GARBAGE_WINDOW_SECONDS = 5 * 60


@dataclass(frozen=True)
class ScoringEvent:
    """A single scoring event extracted from the timeline."""

    timeline_index: int
    timestamp: str
    quarter: int | None
    game_clock: str | None
    home_score: int
    away_score: int
    home_delta: int
    away_delta: int
    scoring_team_id: int | None
    points: int
    lead_team_id: int | None
    margin: int
    signed_margin: int


def _parse_clock_to_seconds(clock: str | None) -> int | None:
    """Parse game clock (MM:SS) to seconds remaining."""
    if not clock:
        return None
    parts = clock.split(":")
    if len(parts) != 2:
        return None
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
    except ValueError:
        return None
    if minutes < 0 or seconds < 0 or seconds >= 60:
        return None
    return minutes * 60 + seconds


def _score_delta(
    previous: tuple[int, int] | None, current: tuple[int, int]
) -> tuple[int, int]:
    """Calculate score change between two score states."""
    if previous is None:
        return current[0], current[1]
    return current[0] - previous[0], current[1] - previous[1]


def _lead_team_id(
    home_score: int, away_score: int, home_team_id: int, away_team_id: int
) -> int | None:
    """Determine which team is leading."""
    if home_score > away_score:
        return home_team_id
    if away_score > home_score:
        return away_team_id
    return None


def _scoring_team_id(
    home_delta: int,
    away_delta: int,
    home_team_id: int,
    away_team_id: int,
) -> tuple[int | None, int]:
    """Determine which team scored and how many points."""
    if home_delta > 0 and away_delta == 0:
        return home_team_id, home_delta
    if away_delta > 0 and home_delta == 0:
        return away_team_id, away_delta
    if home_delta > 0 or away_delta > 0:
        return None, home_delta + away_delta
    return None, 0


def extract_scoring_events(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> list[ScoringEvent]:
    """
    Extract scoring events from the timeline.

    Returns a list of ScoringEvent objects representing score changes.
    """
    home_team_id = summary["teams"]["home"]["id"]
    away_team_id = summary["teams"]["away"]["id"]
    scoring_events: list[ScoringEvent] = []
    previous_score: tuple[int, int] | None = None

    for index, event in enumerate(timeline):
        if event.get("event_type") != "pbp":
            continue
        home_score = event.get("home_score")
        away_score = event.get("away_score")
        if home_score is None or away_score is None:
            continue
        current_score = (home_score, away_score)
        home_delta, away_delta = _score_delta(previous_score, current_score)
        if home_delta == 0 and away_delta == 0:
            previous_score = current_score
            continue
        scoring_team, points = _scoring_team_id(
            home_delta, away_delta, home_team_id, away_team_id
        )
        lead_team = _lead_team_id(home_score, away_score, home_team_id, away_team_id)
        margin = abs(home_score - away_score)
        signed_margin = home_score - away_score
        scoring_events.append(
            ScoringEvent(
                timeline_index=index,
                timestamp=event["synthetic_timestamp"],
                quarter=event.get("quarter"),
                game_clock=event.get("game_clock"),
                home_score=home_score,
                away_score=away_score,
                home_delta=home_delta,
                away_delta=away_delta,
                scoring_team_id=scoring_team,
                points=points,
                lead_team_id=lead_team,
                margin=margin,
                signed_margin=signed_margin,
            )
        )
        previous_score = current_score
    return scoring_events


def _segment_for_event_index(
    segments: list[dict[str, Any]], event_index: int
) -> str | None:
    """Find which segment an event belongs to."""
    for segment in segments:
        key_event_ids = segment["key_event_ids"]
        if not key_event_ids:
            continue
        if key_event_ids[0] <= event_index <= key_event_ids[-1]:
            return segment["segment_id"]
    return None


def _build_segment(
    events: Sequence[ScoringEvent], segment_type: str, segment_number: int
) -> dict[str, Any]:
    """Build a segment dictionary from scoring events."""
    start_event = events[0]
    end_event = events[-1]
    teams_involved = sorted(
        {event.scoring_team_id for event in events if event.scoring_team_id is not None}
    )
    return {
        "segment_id": f"segment_{segment_number}",
        "start_timestamp": start_event.timestamp,
        "end_timestamp": end_event.timestamp,
        "segment_type": segment_type,
        "teams_involved": teams_involved,
        "score_start": {"home": start_event.home_score, "away": start_event.away_score},
        "score_end": {"home": end_event.home_score, "away": end_event.away_score},
        "score_delta": {
            "home": end_event.home_score - start_event.home_score,
            "away": end_event.away_score - start_event.away_score,
        },
        "key_event_ids": [event.timeline_index for event in events],
    }


def _build_run_highlights(
    scoring_events: Sequence[ScoringEvent],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect and build scoring run highlights."""
    highlights: list[dict[str, Any]] = []
    run_team_id: int | None = None
    run_points = 0
    run_start_index = 0

    for index, event in enumerate(scoring_events):
        if event.scoring_team_id is None:
            continue
        if run_team_id is None or event.scoring_team_id != run_team_id:
            if run_team_id is not None and run_points >= NBA_RUN_POINTS_THRESHOLD:
                end_event = scoring_events[index - 1]
                start_event = scoring_events[run_start_index]
                highlights.append(
                    {
                        "highlight_type": "scoring_run",
                        "start_timestamp": start_event.timestamp,
                        "end_timestamp": end_event.timestamp,
                        "teams_involved": [run_team_id],
                        "score_context": {
                            "points": run_points,
                            "start_score": {
                                "home": start_event.home_score,
                                "away": start_event.away_score,
                            },
                            "end_score": {
                                "home": end_event.home_score,
                                "away": end_event.away_score,
                            },
                            "team_id": run_team_id,
                        },
                        "related_segment_id": _segment_for_event_index(
                            segments, start_event.timeline_index
                        ),
                    }
                )
            run_team_id = event.scoring_team_id
            run_points = event.points
            run_start_index = index
        else:
            run_points += event.points

    if run_team_id is not None and run_points >= NBA_RUN_POINTS_THRESHOLD:
        end_event = scoring_events[-1]
        start_event = scoring_events[run_start_index]
        highlights.append(
            {
                "highlight_type": "scoring_run",
                "start_timestamp": start_event.timestamp,
                "end_timestamp": end_event.timestamp,
                "teams_involved": [run_team_id],
                "score_context": {
                    "points": run_points,
                    "start_score": {
                        "home": start_event.home_score,
                        "away": start_event.away_score,
                    },
                    "end_score": {
                        "home": end_event.home_score,
                        "away": end_event.away_score,
                    },
                    "team_id": run_team_id,
                },
                "related_segment_id": _segment_for_event_index(
                    segments, start_event.timeline_index
                ),
            }
        )

    return highlights


def _build_lead_change_highlights(
    scoring_events: Sequence[ScoringEvent],
    segments: list[dict[str, Any]],
    teams_involved: list[int],
) -> list[dict[str, Any]]:
    """Detect and build lead change highlights."""
    highlights: list[dict[str, Any]] = []
    previous_lead_team: int | None = None
    for event in scoring_events:
        if (
            event.lead_team_id is not None
            and previous_lead_team is not None
            and event.lead_team_id != previous_lead_team
        ):
            highlights.append(
                {
                    "highlight_type": "lead_change",
                    "start_timestamp": event.timestamp,
                    "end_timestamp": event.timestamp,
                    "teams_involved": teams_involved,
                    "score_context": {
                        "score": {"home": event.home_score, "away": event.away_score},
                        "lead_team_id": event.lead_team_id,
                    },
                    "related_segment_id": _segment_for_event_index(
                        segments, event.timeline_index
                    ),
                }
            )
        if event.lead_team_id is not None:
            previous_lead_team = event.lead_team_id
    return highlights


def _build_quarter_shift_highlights(
    scoring_events: Sequence[ScoringEvent],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect momentum shifts between quarters."""
    first_per_quarter: dict[int, ScoringEvent] = {}
    last_per_quarter: dict[int, ScoringEvent] = {}
    for event in scoring_events:
        if event.quarter is None:
            continue
        first_per_quarter.setdefault(event.quarter, event)
        last_per_quarter[event.quarter] = event

    highlights: list[dict[str, Any]] = []
    quarters = sorted(first_per_quarter)
    for quarter in quarters:
        next_quarter = quarter + 1
        if next_quarter not in first_per_quarter or quarter not in last_per_quarter:
            continue
        start_event = last_per_quarter[quarter]
        end_event = first_per_quarter[next_quarter]
        margin_change = abs(end_event.signed_margin - start_event.signed_margin)
        lead_changed = start_event.lead_team_id != end_event.lead_team_id
        if margin_change >= NBA_SWING_MARGIN_THRESHOLD or lead_changed:
            highlights.append(
                {
                    "highlight_type": "quarter_shift",
                    "start_timestamp": start_event.timestamp,
                    "end_timestamp": end_event.timestamp,
                    "teams_involved": [
                        tid
                        for tid in (start_event.lead_team_id, end_event.lead_team_id)
                        if tid
                    ],
                    "score_context": {
                        "start_score": {
                            "home": start_event.home_score,
                            "away": start_event.away_score,
                        },
                        "end_score": {
                            "home": end_event.home_score,
                            "away": end_event.away_score,
                        },
                        "margin_change": margin_change,
                    },
                    "related_segment_id": _segment_for_event_index(
                        segments, start_event.timeline_index
                    ),
                }
            )
    return highlights


def _build_game_deciding_highlight(
    scoring_events: Sequence[ScoringEvent],
    segments: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any] | None:
    """Identify the game-deciding stretch."""
    home_score = summary["final_score"]["home"]
    away_score = summary["final_score"]["away"]
    if home_score is None or away_score is None:
        return None
    winner_id = (
        summary["teams"]["home"]["id"]
        if home_score > away_score
        else summary["teams"]["away"]["id"]
    )
    deciding_start_index: int | None = None
    previous_lead: int | None = None
    for index, event in enumerate(scoring_events):
        if event.lead_team_id is not None and event.lead_team_id != previous_lead:
            if event.lead_team_id == winner_id:
                deciding_start_index = index
            previous_lead = event.lead_team_id

    if deciding_start_index is None:
        for index, event in enumerate(scoring_events):
            if event.quarter == 4:
                deciding_start_index = index
                break
    if deciding_start_index is None:
        deciding_start_index = 0

    start_event = scoring_events[deciding_start_index]
    end_event = scoring_events[-1]
    return {
        "highlight_type": "game_deciding_stretch",
        "start_timestamp": start_event.timestamp,
        "end_timestamp": end_event.timestamp,
        "teams_involved": [winner_id],
        "score_context": {
            "start_score": {
                "home": start_event.home_score,
                "away": start_event.away_score,
            },
            "end_score": {"home": end_event.home_score, "away": end_event.away_score},
            "final_margin": abs(home_score - away_score),
        },
        "related_segment_id": _segment_for_event_index(
            segments, start_event.timeline_index
        ),
    }


def build_nba_game_analysis(
    timeline: Sequence[dict[str, Any]], summary: dict[str, Any]
) -> dict[str, Any]:
    """
    Analyze a timeline to produce segments and highlights.

    Segments: chunks of the game with consistent character (run, swing, etc.)
    Highlights: notable moments (lead changes, scoring runs, deciding stretch)

    Args:
        timeline: List of timeline events (PBP and social)
        summary: Game summary with team info and final scores

    Returns:
        dict with "segments" and "highlights" lists
    """
    scoring_events = extract_scoring_events(timeline, summary)
    if not scoring_events:
        return {"segments": [], "highlights": []}

    home_team_id = summary["teams"]["home"]["id"]
    away_team_id = summary["teams"]["away"]["id"]

    segments: list[dict[str, Any]] = []
    run_team_id: int | None = None
    run_points = 0
    current_segment_start = 0
    current_segment_type: str | None = None
    opening_active = True
    previous_lead_team: int | None = None

    for index, event in enumerate(scoring_events):
        if event.scoring_team_id is None:
            run_team_id = None
            run_points = 0
        elif run_team_id is None or event.scoring_team_id != run_team_id:
            run_team_id = event.scoring_team_id
            run_points = event.points
        else:
            run_points += event.points

        clock_remaining = _parse_clock_to_seconds(event.game_clock)
        opening_window = NBA_OPENING_WINDOW_SECONDS
        clock_ok = clock_remaining is None or clock_remaining >= opening_window
        is_opening = (
            opening_active
            and event.quarter == 1
            and index < NBA_OPENING_EVENT_LIMIT
            and clock_ok
        )
        if not is_opening:
            opening_active = False

        is_garbage_time = (
            event.quarter == 4
            and clock_remaining is not None
            and clock_remaining <= NBA_GARBAGE_WINDOW_SECONDS
            and event.margin >= NBA_GARBAGE_MARGIN_THRESHOLD
        )
        is_blowout = event.margin >= NBA_BLOWOUT_MARGIN_THRESHOLD
        is_close = (
            event.quarter == 4
            and clock_remaining is not None
            and clock_remaining <= NBA_CLOSE_WINDOW_SECONDS
            and event.margin <= NBA_CLOSE_MARGIN_THRESHOLD
        )
        lead_changed = (
            previous_lead_team is not None
            and event.lead_team_id is not None
            and event.lead_team_id != previous_lead_team
        )
        if event.lead_team_id is not None:
            previous_lead_team = event.lead_team_id

        if is_opening:
            segment_type = "opening"
        elif is_garbage_time:
            segment_type = "garbage_time"
        elif is_blowout:
            segment_type = "blowout"
        elif lead_changed:
            segment_type = "swing"
        elif run_points >= NBA_RUN_POINTS_THRESHOLD:
            segment_type = "run"
        elif is_close:
            segment_type = "close"
        else:
            segment_type = "steady"

        if current_segment_type is None:
            current_segment_type = segment_type
        elif segment_type != current_segment_type:
            segment_events = scoring_events[current_segment_start:index]
            segments.append(
                _build_segment(segment_events, current_segment_type, len(segments) + 1)
            )
            current_segment_start = index
            current_segment_type = segment_type

    segment_events = scoring_events[current_segment_start:]
    if segment_events:
        segments.append(
            _build_segment(
                segment_events, current_segment_type or "steady", len(segments) + 1
            )
        )

    highlights: list[dict[str, Any]] = []

    highlights.extend(_build_run_highlights(scoring_events, segments))
    highlights.extend(
        _build_lead_change_highlights(
            scoring_events, segments, [home_team_id, away_team_id]
        )
    )
    highlights.extend(_build_quarter_shift_highlights(scoring_events, segments))
    highlights.append(
        _build_game_deciding_highlight(scoring_events, segments, summary)
    )

    return {
        "segments": segments,
        "highlights": [highlight for highlight in highlights if highlight],
    }


async def enrich_segments_with_ai(
    segments: list[dict[str, Any]],
    game_id: int,
    sport: str = "NBA",
) -> list[dict[str, Any]]:
    """
    Enrich segments with AI-generated labels and tone.
    
    This is OPTIONAL and adds human-readable descriptions.
    The core structure (type, boundaries, scores) is unchanged.
    
    AI outputs are cached per (game_id, segment_id).
    """
    if not is_ai_available():
        logger.debug(
            "segment_enrichment_skipped",
            extra={"reason": "ai_unavailable"},
        )
        return segments
    
    enriched_segments = []
    for segment in segments:
        try:
            # Extract phase info from timestamps or segment data
            segment_id = segment.get("segment_id", "unknown")
            segment_type = segment.get("segment_type", "steady")
            
            # Infer start/end phases from key_event_ids or use generic
            start_phase = "early"
            end_phase = "mid"
            play_count = len(segment.get("key_event_ids", []))
            
            # Call AI enrichment (cached)
            enrichment = await enrich_segment(
                game_id=game_id,
                segment_id=segment_id,
                segment_type=segment_type,
                start_phase=start_phase,
                end_phase=end_phase,
                play_count=play_count,
                sport=sport,
            )
            
            # Add AI labels without changing structure
            enriched = {**segment}
            enriched["ai_label"] = enrichment.get("label")
            enriched["ai_tone"] = enrichment.get("tone")
            enriched_segments.append(enriched)
            
        except Exception as e:
            logger.warning(
                "segment_enrichment_failed segment_id=%s error=%s",
                segment.get("segment_id"),
                str(e),
            )
            enriched_segments.append(segment)
    
    logger.info(
        "segments_enriched",
        extra={"count": len(enriched_segments), "game_id": game_id},
    )
    return enriched_segments


async def build_nba_game_analysis_async(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    game_id: int,
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Analyze a timeline with optional AI enrichment.
    
    Same as build_nba_game_analysis but with async AI enrichment
    of segment labels. The core analysis (segment detection, highlights)
    remains deterministic.
    """
    # Run deterministic analysis first
    analysis = build_nba_game_analysis(timeline, summary)
    
    # Optionally enrich segments with AI
    if analysis["segments"] and is_ai_available():
        analysis["segments"] = await enrich_segments_with_ai(
            segments=analysis["segments"],
            game_id=game_id,
            sport=sport,
        )
    
    return analysis
