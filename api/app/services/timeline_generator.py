"""Timeline artifact generation for finalized games."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import db_models
from ..db import AsyncSession
from ..utils.datetime_utils import now_utc
from .timeline_validation import validate_and_log, TimelineValidationError

logger = logging.getLogger(__name__)

NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_PREGAME_REAL_SECONDS = 10 * 60
NBA_OVERTIME_PADDING_SECONDS = 30 * 60
DEFAULT_TIMELINE_VERSION = "v1"

# Social post time windows (configurable)
# These define how far before/after the game we include social posts
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60   # 2 hours before game start
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60  # 2 hours after game end
NBA_OPENING_WINDOW_SECONDS = 6 * 60
NBA_OPENING_EVENT_LIMIT = 4
NBA_RUN_POINTS_THRESHOLD = 8
NBA_SWING_MARGIN_THRESHOLD = 10
NBA_CLOSE_MARGIN_THRESHOLD = 5
NBA_CLOSE_WINDOW_SECONDS = 5 * 60
NBA_BLOWOUT_MARGIN_THRESHOLD = 20
NBA_GARBAGE_MARGIN_THRESHOLD = 18
NBA_GARBAGE_WINDOW_SECONDS = 5 * 60

# Canonical phase ordering - this is the source of truth for timeline order
PHASE_ORDER: dict[str, int] = {
    "pregame": 0,
    "q1": 1,
    "q2": 2,
    "halftime": 3,
    "q3": 4,
    "q4": 5,
    "ot1": 6,
    "ot2": 7,
    "ot3": 8,
    "ot4": 9,
    "postgame": 99,
}


def _phase_sort_order(phase: str | None) -> int:
    """Return canonical sort order for a phase. Unknown phases sort late."""
    if phase is None:
        return 50
    return PHASE_ORDER.get(phase, 50)


@dataclass(frozen=True)
class TimelineArtifactPayload:
    game_id: int
    sport: str
    timeline_version: str
    generated_at: datetime
    timeline: list[dict[str, Any]]
    summary: dict[str, Any]
    game_analysis: dict[str, Any]


class TimelineGenerationError(Exception):
    """Raised when timeline generation fails due to invalid input."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class _ScoringEvent:
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


def _progress_from_index(index: int, total: int) -> float:
    if total <= 1:
        return 0.5
    return index / (total - 1)


def _score_delta(previous: tuple[int, int] | None, current: tuple[int, int]) -> tuple[int, int]:
    if previous is None:
        return current[0], current[1]
    return current[0] - previous[0], current[1] - previous[1]


def _lead_team_id(home_score: int, away_score: int, home_team_id: int, away_team_id: int) -> int | None:
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
    if home_delta > 0 and away_delta == 0:
        return home_team_id, home_delta
    if away_delta > 0 and home_delta == 0:
        return away_team_id, away_delta
    if home_delta > 0 or away_delta > 0:
        return None, home_delta + away_delta
    return None, 0


def _extract_scoring_events(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> list[_ScoringEvent]:
    home_team_id = summary["teams"]["home"]["id"]
    away_team_id = summary["teams"]["away"]["id"]
    scoring_events: list[_ScoringEvent] = []
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
        scoring_team, points = _scoring_team_id(home_delta, away_delta, home_team_id, away_team_id)
        lead_team = _lead_team_id(home_score, away_score, home_team_id, away_team_id)
        margin = abs(home_score - away_score)
        signed_margin = home_score - away_score
        scoring_events.append(
            _ScoringEvent(
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


def _segment_for_event_index(segments: list[dict[str, Any]], event_index: int) -> str | None:
    for segment in segments:
        key_event_ids = segment["key_event_ids"]
        if not key_event_ids:
            continue
        if key_event_ids[0] <= event_index <= key_event_ids[-1]:
            return segment["segment_id"]
    return None


def build_nba_game_analysis(timeline: Sequence[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    scoring_events = _extract_scoring_events(timeline, summary)
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
        is_opening = (
            opening_active
            and event.quarter == 1
            and index < NBA_OPENING_EVENT_LIMIT
            and (clock_remaining is None or clock_remaining >= NBA_OPENING_WINDOW_SECONDS)
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
            segments.append(_build_segment(segment_events, current_segment_type, len(segments) + 1))
            current_segment_start = index
            current_segment_type = segment_type

    segment_events = scoring_events[current_segment_start:]
    if segment_events:
        segments.append(_build_segment(segment_events, current_segment_type or "steady", len(segments) + 1))

    highlights: list[dict[str, Any]] = []

    highlights.extend(_build_run_highlights(scoring_events, segments))
    highlights.extend(_build_lead_change_highlights(scoring_events, segments, [home_team_id, away_team_id]))
    highlights.extend(_build_quarter_shift_highlights(scoring_events, segments))
    highlights.append(_build_game_deciding_highlight(scoring_events, segments, summary))

    return {"segments": segments, "highlights": [highlight for highlight in highlights if highlight]}


def _build_segment(events: Sequence[_ScoringEvent], segment_type: str, segment_number: int) -> dict[str, Any]:
    start_event = events[0]
    end_event = events[-1]
    teams_involved = sorted({event.scoring_team_id for event in events if event.scoring_team_id is not None})
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
    scoring_events: Sequence[_ScoringEvent],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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
                            "start_score": {"home": start_event.home_score, "away": start_event.away_score},
                            "end_score": {"home": end_event.home_score, "away": end_event.away_score},
                            "team_id": run_team_id,
                        },
                        "related_segment_id": _segment_for_event_index(segments, start_event.timeline_index),
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
                    "start_score": {"home": start_event.home_score, "away": start_event.away_score},
                    "end_score": {"home": end_event.home_score, "away": end_event.away_score},
                    "team_id": run_team_id,
                },
                "related_segment_id": _segment_for_event_index(segments, start_event.timeline_index),
            }
        )

    return highlights


def _build_lead_change_highlights(
    scoring_events: Sequence[_ScoringEvent],
    segments: list[dict[str, Any]],
    teams_involved: list[int],
) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    previous_lead_team: int | None = None
    for event in scoring_events:
        if event.lead_team_id is not None and previous_lead_team is not None and event.lead_team_id != previous_lead_team:
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
                    "related_segment_id": _segment_for_event_index(segments, event.timeline_index),
                }
            )
        if event.lead_team_id is not None:
            previous_lead_team = event.lead_team_id
    return highlights


def _build_quarter_shift_highlights(
    scoring_events: Sequence[_ScoringEvent],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    first_per_quarter: dict[int, _ScoringEvent] = {}
    last_per_quarter: dict[int, _ScoringEvent] = {}
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
                        team_id
                        for team_id in (start_event.lead_team_id, end_event.lead_team_id)
                        if team_id
                    ],
                    "score_context": {
                        "start_score": {"home": start_event.home_score, "away": start_event.away_score},
                        "end_score": {"home": end_event.home_score, "away": end_event.away_score},
                        "margin_change": margin_change,
                    },
                    "related_segment_id": _segment_for_event_index(segments, start_event.timeline_index),
                }
            )
    return highlights


def _build_game_deciding_highlight(
    scoring_events: Sequence[_ScoringEvent],
    segments: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any] | None:
    home_score = summary["final_score"]["home"]
    away_score = summary["final_score"]["away"]
    if home_score is None or away_score is None:
        return None
    winner_id = summary["teams"]["home"]["id"] if home_score > away_score else summary["teams"]["away"]["id"]
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
            "start_score": {"home": start_event.home_score, "away": start_event.away_score},
            "end_score": {"home": end_event.home_score, "away": end_event.away_score},
            "final_margin": abs(home_score - away_score),
        },
        "related_segment_id": _segment_for_event_index(segments, start_event.timeline_index),
    }


def _nba_phase_for_quarter(quarter: int | None) -> str:
    """
    Map quarter number to narrative phase.
    
    This is the canonical phase assignment for PBP events.
    Phase determines ordering, not timestamp.
    """
    if quarter is None:
        return "pregame"
    if quarter == 1:
        return "q1"
    if quarter == 2:
        return "q2"
    if quarter == 3:
        return "q3"
    if quarter == 4:
        return "q4"
    # Overtime periods: q5 -> ot1, q6 -> ot2, etc.
    ot_number = quarter - 4
    return f"ot{ot_number}"


def _nba_block_for_quarter(quarter: int | None) -> str:
    """Alias for backwards compatibility with timeline_block field."""
    return _nba_phase_for_quarter(quarter)


def _nba_quarter_start(game_start: datetime, quarter: int) -> datetime:
    halftime_offset = NBA_HALFTIME_REAL_SECONDS if quarter >= 3 else 0
    return game_start + timedelta(seconds=(quarter - 1) * NBA_QUARTER_REAL_SECONDS + halftime_offset)


def _nba_regulation_end(game_start: datetime) -> datetime:
    return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS)


def _nba_game_end(game_start: datetime, plays: Sequence[db_models.SportsGamePlay]) -> datetime:
    has_overtime = any((play.quarter or 0) > 4 for play in plays)
    end_time = _nba_regulation_end(game_start)
    if has_overtime:
        end_time += timedelta(seconds=NBA_OVERTIME_PADDING_SECONDS)
    return end_time


def _build_pbp_events(
    plays: Sequence[db_models.SportsGamePlay],
    game_start: datetime,
) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Build PBP events with phase assignment.
    
    Each event gets:
    - phase: The narrative phase (q1, q2, etc.) - controls ordering
    - intra_phase_order: Sort key within phase (from game clock)
    - synthetic_timestamp: For display/debugging only, NOT for ordering
    """
    grouped: dict[int | None, list[db_models.SportsGamePlay]] = {}
    for play in plays:
        grouped.setdefault(play.quarter, []).append(play)

    events: list[tuple[datetime, dict[str, Any]]] = []
    for quarter, quarter_plays in sorted(grouped.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        sorted_plays = sorted(quarter_plays, key=lambda play: play.play_index)
        phase = _nba_phase_for_quarter(quarter)

        if quarter is None:
            window_start = game_start - timedelta(seconds=NBA_PREGAME_REAL_SECONDS)
            window_seconds = NBA_PREGAME_REAL_SECONDS
        elif quarter <= 4:
            window_start = _nba_quarter_start(game_start, quarter)
            window_seconds = NBA_QUARTER_REAL_SECONDS
        else:
            window_start = _nba_regulation_end(game_start)
            window_seconds = NBA_OVERTIME_PADDING_SECONDS

        for index, play in enumerate(sorted_plays):
            remaining_seconds = _parse_clock_to_seconds(play.game_clock)
            if quarter and quarter <= 4 and remaining_seconds is not None:
                progress = (NBA_QUARTER_GAME_SECONDS - remaining_seconds) / NBA_QUARTER_GAME_SECONDS
            else:
                progress = _progress_from_index(index, len(sorted_plays))

            progress = min(max(progress, 0.0), 1.0)
            event_time = window_start + timedelta(seconds=window_seconds * progress)
            
            # Compute intra-phase order from game clock (inverted: 12:00 -> 0, 0:00 -> 720)
            if remaining_seconds is not None:
                intra_phase_order = NBA_QUARTER_GAME_SECONDS - remaining_seconds
            else:
                intra_phase_order = int(progress * NBA_QUARTER_GAME_SECONDS)
            
            event_payload = {
                "event_type": "pbp",
                "phase": phase,
                "intra_phase_order": intra_phase_order,
                "play_index": play.play_index,
                "quarter": play.quarter,
                "game_clock": play.game_clock,
                "play_type": play.play_type,
                "team_id": play.team_id,
                "player_id": play.player_id,
                "player_name": play.player_name,
                "description": play.description,
                "home_score": play.home_score,
                "away_score": play.away_score,
                "synthetic_timestamp": event_time.isoformat(),
                "timeline_block": phase,  # Kept for backwards compatibility
            }
            events.append((event_time, event_payload))

    return events


def _compute_phase_boundaries(game_start: datetime, has_overtime: bool = False) -> dict[str, tuple[datetime, datetime]]:
    """
    Compute time boundaries for each narrative phase.
    
    Returns dict of phase -> (start_time, end_time).
    These boundaries are used to assign social posts to phases.
    """
    pregame_start = game_start - timedelta(hours=2)
    q1_start = game_start
    q1_end = game_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    q2_end = game_start + timedelta(seconds=2 * NBA_QUARTER_REAL_SECONDS)
    halftime_end = q2_end + timedelta(seconds=NBA_HALFTIME_REAL_SECONDS)
    q3_end = halftime_end + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    q4_end = halftime_end + timedelta(seconds=2 * NBA_QUARTER_REAL_SECONDS)
    
    boundaries = {
        "pregame": (pregame_start, q1_start),
        "q1": (q1_start, q1_end),
        "q2": (q1_end, q2_end),
        "halftime": (q2_end, halftime_end),
        "q3": (halftime_end, q3_end),
        "q4": (q3_end, q4_end),
    }
    
    if has_overtime:
        ot_start = q4_end
        ot_end = q4_end + timedelta(seconds=NBA_OVERTIME_PADDING_SECONDS)
        boundaries["ot1"] = (ot_start, ot_end)
        boundaries["postgame"] = (ot_end, ot_end + timedelta(hours=2))
    else:
        boundaries["postgame"] = (q4_end, q4_end + timedelta(hours=2))
    
    return boundaries


def _assign_social_phase(posted_at: datetime, boundaries: dict[str, tuple[datetime, datetime]]) -> str:
    """
    Assign a social post to a narrative phase based on posting time.
    
    Phase determines ordering. Timestamp is secondary.
    """
    for phase in ["pregame", "q1", "q2", "halftime", "q3", "q4", "ot1", "ot2", "postgame"]:
        if phase not in boundaries:
            continue
        start, end = boundaries[phase]
        if start <= posted_at < end:
            return phase
    
    # Fallback: if before all phases, pregame; if after all, postgame
    earliest_start = min(b[0] for b in boundaries.values())
    if posted_at < earliest_start:
        return "pregame"
    return "postgame"


# Role assignment patterns (compiled once at module load)
_ROLE_PATTERNS = {
    # Pregame patterns
    "context": [
        re.compile(r"\b(starting|lineup|injury|out tonight|questionable|doubtful|inactive)\b", re.I),
        re.compile(r"\b(report|update|status)\b", re.I),
    ],
    "hype": [
        re.compile(r"\b(game\s*day|let'?s\s*go|tip[- ]?off|ready|tonight)\b", re.I),
        re.compile(r"🔥|💪|⬆️|🏀", re.I),
    ],
    # In-game patterns
    "momentum": [
        re.compile(r"\d+-\d+\s*(run|lead|up\s+by)", re.I),
        re.compile(r"\b(run|streak|straight)\b", re.I),
    ],
    "milestone": [
        re.compile(r"\b(triple[- ]?double|double[- ]?double|career[- ]?high)\b", re.I),
        re.compile(r"\b(\d+th|first|record)\b.*\b(of the season|in franchise)\b", re.I),
    ],
    # Postgame patterns
    "result": [
        re.compile(r"\b(final|win|loss|victory|defeat)\b", re.I),
        re.compile(r"\bGG\b", re.I),
        re.compile(r"\d+\s*-\s*\d+\s*(final|$)", re.I),
    ],
    "reflection": [
        re.compile(r"\b(on to the next|tough loss|great win|back at it)\b", re.I),
        re.compile(r"\b(next game|wednesday|tomorrow)\b", re.I),
    ],
    # Universal patterns
    "highlight": [
        # Video/media indicators - typically these have media attachments
        re.compile(r"👀|🎥|📹|watch|replay", re.I),
    ],
    "ambient": [
        re.compile(r"\b(crowd|arena|atmosphere|loud)\b", re.I),
    ],
}


def _assign_social_role(text: str | None, phase: str, has_media: bool = False) -> str:
    """
    Assign a narrative role to a social post.
    
    Roles define WHY a post is in the timeline:
    - hype: Build anticipation (pregame)
    - context: Provide information (pregame, early game)
    - reaction: Respond to action (in-game)
    - momentum: Mark a shift (in-game)
    - milestone: Celebrate achievement (any)
    - highlight: Share video/clip (any)
    - commentary: General observation (in-game)
    - result: Announce outcome (postgame)
    - reflection: Post-game takeaway (postgame)
    - ambient: Atmosphere content (any)
    
    See docs/SOCIAL_EVENT_ROLES.md for the full taxonomy.
    """
    # Default roles by phase
    if phase == "pregame":
        default_role = "hype"
    elif phase == "postgame":
        default_role = "result"
    elif phase == "halftime":
        default_role = "commentary"
    else:
        default_role = "reaction"
    
    # If no text, use media type or ambient
    if not text or not text.strip():
        return "highlight" if has_media else "ambient"
    
    text_lower = text.lower()
    
    # Check for media/highlight first (highest priority)
    if has_media:
        for pattern in _ROLE_PATTERNS.get("highlight", []):
            if pattern.search(text):
                return "highlight"
    
    # Phase-specific refinements
    if phase == "pregame":
        # Check context patterns
        for pattern in _ROLE_PATTERNS.get("context", []):
            if pattern.search(text):
                return "context"
        # Default to hype for pregame
        return "hype"
    
    elif phase == "postgame":
        # Check result patterns
        for pattern in _ROLE_PATTERNS.get("result", []):
            if pattern.search(text):
                return "result"
        # Check reflection patterns
        for pattern in _ROLE_PATTERNS.get("reflection", []):
            if pattern.search(text):
                return "reflection"
        return "result"
    
    else:
        # In-game phases (q1, q2, q3, q4, halftime, ot)
        # Check milestone first (can appear anytime)
        for pattern in _ROLE_PATTERNS.get("milestone", []):
            if pattern.search(text):
                return "milestone"
        
        # Check momentum
        for pattern in _ROLE_PATTERNS.get("momentum", []):
            if pattern.search(text):
                return "momentum"
        
        # Short exclamatory posts are reactions
        if len(text) < 30 and (text.endswith("!") or "!" in text or any(c in text for c in "🔥💪👏🙌")):
            return "reaction"
        
        # Default to commentary for longer in-game posts
        if len(text) > 50:
            return "commentary"
        
        return "reaction"


def _build_social_events(
    posts: Iterable[db_models.GameSocialPost],
    phase_boundaries: dict[str, tuple[datetime, datetime]],
) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Build social events with phase and role assignment.
    
    Each event gets:
    - phase: The narrative phase - controls ordering
    - role: The narrative intent - why it's in the timeline
    - intra_phase_order: Sort key within phase
    - synthetic_timestamp: The actual posted_at time
    
    Events with null or empty text are DROPPED (not included in timeline).
    See docs/SOCIAL_EVENT_ROLES.md for role taxonomy.
    """
    events: list[tuple[datetime, dict[str, Any]]] = []
    dropped_count = 0
    
    for post in posts:
        # Filter: Drop posts with null or empty text
        text = post.tweet_text
        if text is None or text.strip() == "":
            dropped_count += 1
            logger.debug(
                "social_post_dropped_empty_text",
                extra={"post_id": getattr(post, "id", None), "author": post.source_handle},
            )
            continue
        
        event_time = post.posted_at
        phase = _assign_social_phase(event_time, phase_boundaries)
        
        # Assign role based on phase and content
        # TODO: Pass has_media=True if post has video/image attachment
        has_media = False  # Placeholder until media detection is implemented
        role = _assign_social_role(text, phase, has_media)
        
        # Compute intra-phase order as seconds since phase start
        if phase in phase_boundaries:
            phase_start = phase_boundaries[phase][0]
            intra_phase_order = (event_time - phase_start).total_seconds()
        else:
            intra_phase_order = 0
        
        event_payload = {
            "event_type": "tweet",
            "phase": phase,
            "role": role,
            "intra_phase_order": intra_phase_order,
            "author": post.source_handle,
            "handle": post.source_handle,
            "text": text,
            "synthetic_timestamp": event_time.isoformat(),
        }
        events.append((event_time, event_payload))
    
    if dropped_count > 0:
        logger.info(
            "social_posts_filtered",
            extra={"dropped_empty_text": dropped_count, "included": len(events)},
        )
    
    return events


def build_nba_summary(
    game: db_models.SportsGame,
) -> dict[str, Any]:
    """
    Extract basic game metadata for internal use.
    
    INTERNAL ONLY: This function provides team IDs, names, and final scores
    for use by build_summary_from_timeline(). It does NOT generate narrative
    content. All narrative must come from the timeline artifact.
    
    Returns:
        dict with teams (id/name), final_score, and flow classification
    """
    home_name = game.home_team.name if game.home_team else "Home"
    away_name = game.away_team.name if game.away_team else "Away"
    home_score = game.home_score
    away_score = game.away_score

    flow = "unknown"
    if home_score is not None and away_score is not None:
        diff = abs(home_score - away_score)
        if diff <= 5:
            flow = "close"
        elif diff <= 12:
            flow = "competitive"
        elif diff <= 20:
            flow = "comfortable"
        else:
            flow = "blowout"

    return {
        "teams": {
            "home": {"id": game.home_team_id, "name": home_name},
            "away": {"id": game.away_team_id, "name": away_name},
        },
        "final_score": {"home": home_score, "away": away_score},
        "flow": flow,
    }


def _format_score_context(score: dict[str, int], home_name: str, away_name: str) -> str:
    return f"{away_name} {score['away']}, {home_name} {score['home']}"


def _winner_info(summary: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    home_score = summary["final_score"]["home"]
    away_score = summary["final_score"]["away"]
    if home_score is None or away_score is None:
        return None, None, None
    if home_score > away_score:
        return summary["teams"]["home"]["name"], home_score, away_score
    if away_score > home_score:
        return summary["teams"]["away"]["name"], away_score, home_score
    return None, home_score, away_score


def _segment_narrative(
    segment: dict[str, Any],
    home_id: int,
    away_id: int,
    home_name: str,
    away_name: str,
) -> str:
    segment_type = segment["segment_type"]
    teams_involved = segment["teams_involved"]
    start_score = segment["score_start"]
    end_score = segment["score_end"]
    score_delta = segment["score_delta"]
    start_context = _format_score_context(start_score, home_name, away_name)
    end_context = _format_score_context(end_score, home_name, away_name)

    if len(teams_involved) == 1:
        team_id = teams_involved[0]
        if team_id == home_id:
            team_name = home_name
            opponent_name = away_name
            team_delta = score_delta["home"]
            opponent_delta = score_delta["away"]
        elif team_id == away_id:
            team_name = away_name
            opponent_name = home_name
            team_delta = score_delta["away"]
            opponent_delta = score_delta["home"]
        else:
            team_name = "One side"
            opponent_name = "the opponent"
            team_delta = score_delta["home"] + score_delta["away"]
            opponent_delta = 0
        delta_phrase = f"{team_delta}-{opponent_delta}"
    else:
        team_name = "Both teams"
        opponent_name = "each other"
        delta_phrase = f"{score_delta['home']}-{score_delta['away']}"

    if segment_type == "opening":
        return (
            f"The opening stretch set the tone as {team_name} pushed the pace. "
            f"The score moved from {start_context} to {end_context}."
        )
    if segment_type == "run":
        return (
            f"{team_name} went on a run, outscoring {opponent_name} {delta_phrase} "
            f"from {start_context} to {end_context}."
        )
    if segment_type == "swing":
        return (
            f"Momentum swung as the lead changed hands in this stretch. "
            f"The score flipped from {start_context} to {end_context}."
        )
    if segment_type == "close":
        return (
            f"The finish tightened up, keeping the margin within striking distance. "
            f"The score inched from {start_context} to {end_context}."
        )
    if segment_type == "blowout":
        return (
            f"A lopsided burst opened the gap, pushing the score from {start_context} to {end_context}."
        )
    if segment_type == "garbage_time":
        return (
            f"With the outcome largely decided, the closing minutes drifted from {start_context} "
            f"to {end_context}."
        )
    return (
        f"The game stayed steady in this stretch, moving from {start_context} to {end_context}."
    )


def build_summary_from_timeline(
    timeline: Sequence[dict[str, Any]],
    game_analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a READING GUIDE for the timeline, not a traditional recap.
    
    This summary:
    - Sets expectations for what kind of game this was
    - Points out where attention should increase while scrolling
    - Explains how the story unfolds as the timeline progresses
    
    It should feel incomplete without the timeline.
    Its purpose is to guide how the timeline is read, not replace it.
    
    See docs/SUMMARY_GENERATION.md for the contract.
    """
    # Extract basic info from timeline
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
    
    # Compute flow classification
    flow = "unknown"
    if final_home_score is not None and final_away_score is not None:
        diff = abs(final_home_score - final_away_score)
        if diff <= 5:
            flow = "close"
        elif diff <= 12:
            flow = "competitive"
        elif diff <= 20:
            flow = "comfortable"
        else:
            flow = "blowout"
    
    # Determine winner
    winner_name: str | None = None
    loser_name: str | None = None
    if final_home_score is not None and final_away_score is not None:
        if final_home_score > final_away_score:
            winner_name = home_name
            loser_name = away_name
        elif final_away_score > final_home_score:
            winner_name = away_name
            loser_name = home_name
    
    # Analyze phases and social distribution
    phases_present = sorted(set(e.get("phase") for e in timeline if e.get("phase")))
    has_overtime = any(p.startswith("ot") for p in phases_present)
    
    social_by_phase: dict[str, int] = {}
    for event in social_events:
        phase = event.get("phase", "unknown")
        social_by_phase[phase] = social_by_phase.get(phase, 0) + 1
    
    # Analyze highlights for attention points
    highlights = game_analysis.get("highlights", [])
    segments = game_analysis.get("segments", [])
    
    # Find key narrative moments
    scoring_runs = [h for h in highlights if h.get("highlight_type") == "scoring_run"]
    lead_changes = [h for h in highlights if h.get("highlight_type") == "lead_change"]
    deciding_stretch = next(
        (h for h in highlights if h.get("highlight_type") == "game_deciding_stretch"),
        None,
    )
    
    # === BUILD THE READING GUIDE ===
    
    # Overview: 1-2 paragraphs setting expectations
    overview_parts: list[str] = []
    
    # Opening sentence - tone setting
    if flow == "blowout":
        overview_parts.append(
            f"This one gets away early. {winner_name} takes control and never really lets go."
        )
    elif flow == "comfortable":
        overview_parts.append(
            f"A game that looks closer on paper than it felt. {winner_name} stays in command through the middle quarters."
        )
    elif flow == "competitive":
        overview_parts.append(
            f"Back and forth for most of it, with stretches where either team could take over."
        )
    elif flow == "close":
        if has_overtime:
            overview_parts.append(
                "This one needs extra time. The tension builds steadily, especially in the final minutes of regulation."
            )
        else:
            overview_parts.append(
                "Tight throughout. The kind of game where every possession in the fourth starts to matter."
            )
    else:
        overview_parts.append("A game worth scrolling through from start to finish.")
    
    # Second sentence - where to focus
    if scoring_runs:
        run_phases = set()
        for run in scoring_runs[:3]:
            # Infer phase from score context
            if run.get("score_context", {}).get("start_score"):
                run_phases.add("mid-game")
        if run_phases:
            overview_parts.append(
                "Watch for the runs — there are stretches where momentum clearly swings."
            )
    
    # Third sentence - social atmosphere
    total_social = len(social_events)
    if total_social > 0:
        if social_by_phase.get("q4", 0) > 0 or social_by_phase.get("postgame", 0) > 3:
            overview_parts.append(
                "Reactions pick up as it winds down — you'll feel when the energy shifts."
            )
        elif social_by_phase.get("pregame", 0) > 0:
            overview_parts.append(
                "Some pre-game buzz sets the tone before things get going."
            )
    
    overview = " ".join(overview_parts)
    
    # Attention Points: Where to increase focus
    attention_points: list[str] = []
    
    # Opening stretch
    attention_points.append("The first few minutes set the early tempo")
    
    # Mid-game momentum
    if scoring_runs:
        if flow in ["blowout", "comfortable"]:
            attention_points.append(
                "A stretch in the second or third where the gap starts to open"
            )
        else:
            attention_points.append(
                "Mid-game swings where control changes hands"
            )
    
    # Late game
    if flow == "close":
        attention_points.append("The final minutes are where everything tightens")
    elif flow == "competitive":
        attention_points.append("Watch the fourth — there's still something to play for")
    elif deciding_stretch:
        attention_points.append("A decisive run that effectively ends it")
    else:
        attention_points.append("The closing stretch confirms the outcome")
    
    # Social clustering
    postgame_count = social_by_phase.get("postgame", 0)
    ingame_count = sum(
        social_by_phase.get(p, 0) 
        for p in ["q1", "q2", "q3", "q4"] + [f"ot{i}" for i in range(1, 5)]
    )
    
    if ingame_count > 0:
        attention_points.append("In-game reactions mark the moments that landed")
    if postgame_count > 3:
        attention_points.append("Postgame reactions capture the aftermath")
    
    # === RETURN STRUCTURE ===
    return {
        # Metadata (preserved for compatibility)
        "teams": {
            "home": {"id": home_team_id, "name": home_name},
            "away": {"id": away_team_id, "name": away_name},
        },
        "final_score": {"home": final_home_score, "away": final_away_score},
        "flow": flow,
        "phases_in_timeline": phases_present,
        "social_counts": {
            "total": total_social,
            "by_phase": social_by_phase,
        },
        
        # Reading Guide (new primary output)
        "overview": overview,
        "attention_points": attention_points,
        
        # Legacy fields (deprecated but kept for compatibility)
        "overall_summary": overview,  # Alias for overview
        "closing_summary": "",        # Deprecated: reading guides don't "close"
        "segments": [],               # Deprecated: attention_points replaces this
    }


def build_nba_timeline(
    game: db_models.SportsGame,
    plays: Sequence[db_models.SportsGamePlay],
    social_posts: Sequence[db_models.GameSocialPost],
) -> tuple[list[dict[str, Any]], dict[str, Any], datetime]:
    game_start = game.start_time
    game_end = _nba_game_end(game_start, plays)
    has_overtime = any((play.quarter or 0) > 4 for play in plays)

    # Compute phase boundaries for social event assignment
    phase_boundaries = _compute_phase_boundaries(game_start, has_overtime)

    pbp_events = _build_pbp_events(plays, game_start)
    social_events = _build_social_events(social_posts, phase_boundaries)
    timeline = _merge_timeline_events(pbp_events, social_events)
    summary = build_nba_summary(game)
    return timeline, summary, game_end


def _merge_timeline_events(
    pbp_events: Sequence[tuple[datetime, dict[str, Any]]],
    social_events: Sequence[tuple[datetime, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Merge PBP and social events using PHASE-FIRST ordering.
    
    Ordering is determined by:
    1. phase_order (from PHASE_ORDER constant) - PRIMARY
    2. intra_phase_order (clock progress for PBP, seconds for social) - SECONDARY
    3. event_type tiebreaker (pbp before tweet at same position) - TERTIARY
    
    synthetic_timestamp is NOT used for ordering. It is retained for
    display/debugging purposes only.
    
    See docs/TIMELINE_ASSEMBLY.md for the canonical assembly recipe.
    """
    merged = list(pbp_events) + list(social_events)

    def sort_key(item: tuple[datetime, dict[str, Any]]) -> tuple[int, float, int, int]:
        _, payload = item
        
        # Primary: phase order
        phase = payload.get("phase", "unknown")
        phase_order = _phase_sort_order(phase)
        
        # Secondary: intra-phase order
        intra_order = payload.get("intra_phase_order", 0)
        
        # Tertiary: event type (pbp=0, tweet=1) so PBP comes first at ties
        event_type_order = 0 if payload.get("event_type") == "pbp" else 1
        
        # Quaternary: play_index for PBP stability
        play_index = payload.get("play_index", 0)
        
        return (phase_order, intra_order, event_type_order, play_index)

    sorted_events = sorted(merged, key=sort_key)
    
    # Extract payloads, removing internal sort keys from output
    result = []
    for _, payload in sorted_events:
        # Remove intra_phase_order from output (internal use only)
        output = {k: v for k, v in payload.items() if k != "intra_phase_order"}
        result.append(output)
    
    return result


async def generate_timeline_artifact(
    session: AsyncSession,
    game_id: int,
    timeline_version: str = DEFAULT_TIMELINE_VERSION,
    generated_by: str = "api",
    generation_reason: str | None = None,
) -> TimelineArtifactPayload:
    logger.info(
        "timeline_artifact_generation_started",
        extra={"game_id": game_id, "timeline_version": timeline_version},
    )
    try:
        result = await session.execute(
            select(db_models.SportsGame)
            .options(
                selectinload(db_models.SportsGame.league),
                selectinload(db_models.SportsGame.home_team),
                selectinload(db_models.SportsGame.away_team),
            )
            .where(db_models.SportsGame.id == game_id)
        )
        game = result.scalar_one_or_none()
        if not game:
            raise TimelineGenerationError("Game not found", status_code=404)

        if not game.is_final:
            raise TimelineGenerationError("Game is not final", status_code=409)

        league_code = game.league.code if game.league else ""
        if league_code != "NBA":
            raise TimelineGenerationError("Timeline generation only supported for NBA", status_code=422)

        plays_result = await session.execute(
            select(db_models.SportsGamePlay)
            .where(db_models.SportsGamePlay.game_id == game_id)
            .order_by(db_models.SportsGamePlay.play_index)
        )
        plays = plays_result.scalars().all()
        if not plays:
            raise TimelineGenerationError("Missing play-by-play data", status_code=422)

        game_start = game.start_time
        game_end = _nba_game_end(game_start, plays)
        has_overtime = any((play.quarter or 0) > 4 for play in plays)
        
        # Compute phase boundaries for social event assignment
        phase_boundaries = _compute_phase_boundaries(game_start, has_overtime)

        # Expanded social post window: include pregame and postgame
        # Posts are assigned to phases by _assign_social_phase(), not filtered out
        social_window_start = game_start - timedelta(seconds=SOCIAL_PREGAME_WINDOW_SECONDS)
        social_window_end = game_end + timedelta(seconds=SOCIAL_POSTGAME_WINDOW_SECONDS)
        
        posts_result = await session.execute(
            select(db_models.GameSocialPost)
            .where(
                db_models.GameSocialPost.game_id == game_id,
                db_models.GameSocialPost.posted_at >= social_window_start,
                db_models.GameSocialPost.posted_at <= social_window_end,
            )
            .order_by(db_models.GameSocialPost.posted_at)
        )
        posts = posts_result.scalars().all()
        
        logger.info(
            "social_posts_window",
            extra={
                "game_id": game_id,
                "window_start": social_window_start.isoformat(),
                "window_end": social_window_end.isoformat(),
                "posts_found": len(posts),
            },
        )

        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "build_synthetic_timeline"},
        )
        pbp_events = _build_pbp_events(plays, game_start)
        if not pbp_events:
            raise TimelineGenerationError("Missing play-by-play data", status_code=422)
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "build_synthetic_timeline",
                "events": len(pbp_events),
            },
        )

        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "merge_social_events"},
        )
        social_events = _build_social_events(posts, phase_boundaries)
        timeline = _merge_timeline_events(pbp_events, social_events)
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "merge_social_events",
                "timeline_events": len(timeline),
                "social_posts": len(posts),
            },
        )

        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "game_segmentation"},
        )
        # Build basic summary for game_analysis (team IDs, final scores)
        base_summary = build_nba_summary(game)
        game_analysis = build_nba_game_analysis(timeline, base_summary)
        logger.info(
            "timeline_artifact_phase_completed",
            extra={
                "game_id": game_id,
                "phase": "game_segmentation",
                "segments": len(game_analysis.get("segments", [])),
                "highlights": len(game_analysis.get("highlights", [])),
            },
        )

        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "narrative_summary"},
        )
        # Build summary from timeline artifact only (timeline-anchored)
        # This ensures summary reflects what's in the feed, not raw data
        # Pass base_summary for team names (not re-querying, just cached metadata)
        game_analysis_with_summary = {**game_analysis, "summary": base_summary}
        summary_json = build_summary_from_timeline(timeline, game_analysis_with_summary)
        logger.info(
            "timeline_artifact_phase_completed",
            extra={"game_id": game_id, "phase": "narrative_summary"},
        )

        # VALIDATION GATE: Validate timeline before persistence
        # Bad timelines never ship. See docs/TIMELINE_VALIDATION.md
        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "validation"},
        )
        try:
            validation_report = validate_and_log(timeline, summary_json, game_id)
            logger.info(
                "timeline_artifact_phase_completed",
                extra={
                    "game_id": game_id,
                    "phase": "validation",
                    "verdict": validation_report.verdict,
                    "critical_passed": validation_report.critical_passed,
                    "warnings": validation_report.warnings_count,
                },
            )
        except TimelineValidationError as exc:
            logger.error(
                "timeline_artifact_validation_blocked",
                extra={
                    "game_id": game_id,
                    "phase": "validation",
                    "report": exc.report.to_dict(),
                },
            )
            raise TimelineGenerationError(
                f"Timeline validation failed: {exc}",
                status_code=422,
            ) from exc

        logger.info(
            "timeline_artifact_phase_started",
            extra={"game_id": game_id, "phase": "persist_artifact"},
        )
        generated_at = now_utc()
        artifact_result = await session.execute(
            select(db_models.SportsGameTimelineArtifact).where(
                db_models.SportsGameTimelineArtifact.game_id == game_id,
                db_models.SportsGameTimelineArtifact.sport == "NBA",
                db_models.SportsGameTimelineArtifact.timeline_version == timeline_version,
            )
        )
        artifact = artifact_result.scalar_one_or_none()

        if artifact is None:
            artifact = db_models.SportsGameTimelineArtifact(
                game_id=game_id,
                sport="NBA",
                timeline_version=timeline_version,
                generated_at=generated_at,
                timeline_json=timeline,
                game_analysis_json=game_analysis,
                summary_json=summary_json,
                generated_by=generated_by,
                generation_reason=generation_reason,
            )
            session.add(artifact)
        else:
            artifact.generated_at = generated_at
            artifact.timeline_json = timeline
            artifact.game_analysis_json = game_analysis
            artifact.summary_json = summary_json
            artifact.generated_by = generated_by
            artifact.generation_reason = generation_reason

        await session.flush()
        logger.info(
            "timeline_artifact_phase_completed",
            extra={"game_id": game_id, "phase": "persist_artifact"},
        )

        logger.info(
            "timeline_artifact_generated",
            extra={
                "game_id": game_id,
                "timeline_version": timeline_version,
                "timeline_events": len(timeline),
                "social_posts": len(posts),
                "plays": len(plays),
            },
        )

        return TimelineArtifactPayload(
            game_id=game_id,
            sport="NBA",
            timeline_version=timeline_version,
            generated_at=generated_at,
            timeline=timeline,
            summary=summary_json,
            game_analysis=game_analysis,
        )
    except Exception:
        logger.exception(
            "timeline_artifact_generation_failed",
            extra={"game_id": game_id, "timeline_version": timeline_version},
        )
        raise
