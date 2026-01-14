"""Timeline artifact generation for finalized games."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import db_models
from ..db import AsyncSession
from ..utils.datetime_utils import now_utc

logger = logging.getLogger(__name__)

NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_PREGAME_REAL_SECONDS = 10 * 60
NBA_OVERTIME_PADDING_SECONDS = 30 * 60
DEFAULT_TIMELINE_VERSION = "v1"
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


def _nba_block_for_quarter(quarter: int | None) -> str:
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
    return "postgame"


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
    grouped: dict[int | None, list[db_models.SportsGamePlay]] = {}
    for play in plays:
        grouped.setdefault(play.quarter, []).append(play)

    events: list[tuple[datetime, dict[str, Any]]] = []
    for quarter, quarter_plays in sorted(grouped.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        sorted_plays = sorted(quarter_plays, key=lambda play: play.play_index)
        block = _nba_block_for_quarter(quarter)

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
            event_payload = {
                "event_type": "pbp",
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
                "timeline_block": block,
            }
            events.append((event_time, event_payload))

    return events


def _build_social_events(posts: Iterable[db_models.GameSocialPost]) -> list[tuple[datetime, dict[str, Any]]]:
    events: list[tuple[datetime, dict[str, Any]]] = []
    for post in posts:
        event_time = post.posted_at
        event_payload = {
            "event_type": "tweet",
            "author": post.source_handle,
            "handle": post.source_handle,
            "text": post.tweet_text,
            "role": None,
            "synthetic_timestamp": event_time.isoformat(),
        }
        events.append((event_time, event_payload))
    return events


def build_nba_summary(
    game: db_models.SportsGame,
) -> dict[str, Any]:
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


def build_nba_summary_json(summary: dict[str, Any], game_analysis: dict[str, Any]) -> dict[str, Any]:
    home_name = summary["teams"]["home"]["name"]
    away_name = summary["teams"]["away"]["name"]
    home_id = summary["teams"]["home"]["id"]
    away_id = summary["teams"]["away"]["id"]

    winner_name, winner_score, loser_score = _winner_info(summary)
    overall_sentences: list[str] = []
    if summary["final_score"]["home"] is not None and summary["final_score"]["away"] is not None:
        overall_sentences.append(
            f"{away_name} at {home_name} finished {summary['final_score']['home']}-"
            f"{summary['final_score']['away']}."
        )
    if summary["flow"] != "unknown":
        overall_sentences.append(f"It was a {summary['flow']} game from start to finish.")

    deciding_highlight = next(
        (
            highlight
            for highlight in game_analysis.get("highlights", [])
            if highlight.get("highlight_type") == "game_deciding_stretch"
        ),
        None,
    )
    if deciding_highlight:
        start_context = _format_score_context(
            deciding_highlight["score_context"]["start_score"], home_name, away_name
        )
        end_context = _format_score_context(
            deciding_highlight["score_context"]["end_score"], home_name, away_name
        )
        overall_sentences.append(
            f"The decisive stretch ran from {start_context} to {end_context}."
        )

    overall_summary = " ".join(overall_sentences[:4])

    segment_narratives: list[dict[str, Any]] = []
    for segment in game_analysis.get("segments", []):
        segment_narratives.append(
            {
                "segment_id": segment["segment_id"],
                "teams_involved": segment["teams_involved"],
                "score_start": segment["score_start"],
                "score_end": segment["score_end"],
                "narrative": _segment_narrative(segment, home_id, away_id, home_name, away_name),
            }
        )

    if deciding_highlight and winner_name:
        start_context = _format_score_context(
            deciding_highlight["score_context"]["start_score"], home_name, away_name
        )
        end_context = _format_score_context(
            deciding_highlight["score_context"]["end_score"], home_name, away_name
        )
        closing_summary = (
            f"From {start_context} to {end_context}, {winner_name} controlled the final push. "
            f"They closed out the {winner_score}-{loser_score} win."
        )
    elif winner_name:
        closing_summary = f"{winner_name} protected the edge late to secure the win."
    else:
        closing_summary = "The final minutes decided the outcome."

    return {
        **summary,
        "overall_summary": overall_summary,
        "segments": segment_narratives,
        "closing_summary": closing_summary,
    }


def build_nba_timeline(
    game: db_models.SportsGame,
    plays: Sequence[db_models.SportsGamePlay],
    social_posts: Sequence[db_models.GameSocialPost],
) -> tuple[list[dict[str, Any]], dict[str, Any], datetime]:
    game_start = game.start_time
    game_end = _nba_game_end(game_start, plays)

    pbp_events = _build_pbp_events(plays, game_start)
    social_events = _build_social_events(social_posts)
    timeline = _merge_timeline_events(pbp_events, social_events)
    summary = build_nba_summary(game)
    return timeline, summary, game_end


def _merge_timeline_events(
    pbp_events: Sequence[tuple[datetime, dict[str, Any]]],
    social_events: Sequence[tuple[datetime, dict[str, Any]]],
) -> list[dict[str, Any]]:
    merged = list(pbp_events) + list(social_events)

    def sort_key(item: tuple[datetime, dict[str, Any]]) -> datetime:
        event_time, _ = item
        return event_time

    return [payload for _, payload in sorted(merged, key=sort_key)]


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

        posts_result = await session.execute(
            select(db_models.GameSocialPost)
            .where(
                db_models.GameSocialPost.game_id == game_id,
                db_models.GameSocialPost.posted_at >= game_start,
                db_models.GameSocialPost.posted_at <= game_end,
            )
            .order_by(db_models.GameSocialPost.posted_at)
        )
        posts = posts_result.scalars().all()

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
        social_events = _build_social_events(posts)
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
        summary = build_nba_summary(game)
        game_analysis = build_nba_game_analysis(timeline, summary)
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
        summary_json = build_nba_summary_json(summary, game_analysis)
        logger.info(
            "timeline_artifact_phase_completed",
            extra={"game_id": game_id, "phase": "narrative_summary"},
        )

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
