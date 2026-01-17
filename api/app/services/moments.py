"""
Moments: Partition game timeline into narrative segments.

A Moment is a contiguous stretch of plays forming a narrative unit.
- NEUTRAL: Normal flow
- RUN: One team scores unanswered (≥8 pts)
- BATTLE: Back-and-forth lead changes
- CLOSING: Final minutes of close game

Highlights are moments where is_notable=True.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

logger = logging.getLogger(__name__)


class MomentType(str, Enum):
    NEUTRAL = "NEUTRAL"
    RUN = "RUN"
    BATTLE = "BATTLE"
    CLOSING = "CLOSING"


# Thresholds
RUN_POINTS_THRESHOLD = 8  # Unanswered points to detect a run
RUN_NOTABLE_THRESHOLD = 8  # Points for run to be notable
BATTLE_LEAD_CHANGES = 2  # Min lead changes for a battle
CLOSING_MINUTES = 5  # Last N minutes of Q4
CLOSING_MARGIN = 10  # Max margin for close game


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
class Moment:
    """A contiguous segment of plays forming a narrative unit."""
    id: str
    type: MomentType
    start_play: int
    end_play: int
    play_count: int
    teams: list[str] = field(default_factory=list)
    players: list[PlayerContribution] = field(default_factory=list)
    score_start: str = ""
    score_end: str = ""
    clock: str = ""
    is_notable: bool = False
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "start_play": self.start_play,
            "end_play": self.end_play,
            "play_count": self.play_count,
            "teams": self.teams,
            "players": [p.to_dict() for p in self.players],
            "score_start": self.score_start,
            "score_end": self.score_end,
            "clock": self.clock,
            "is_notable": self.is_notable,
            "note": self.note,
        }


def _parse_clock_to_seconds(clock: str | None) -> int | None:
    """Parse game clock (MM:SS) to seconds remaining."""
    if not clock:
        return None
    try:
        parts = clock.replace(".", ":").split(":")
        if len(parts) >= 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        return int(float(parts[0]))
    except (ValueError, IndexError):
        return None


def _format_score(home: int | None, away: int | None) -> str:
    """Format score as 'away–home'."""
    if home is None or away is None:
        return ""
    return f"{away}–{home}"


def _detect_runs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect scoring runs in the timeline."""
    runs = []
    current_run_team: int | None = None
    current_run_points = 0
    current_run_start = 0

    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue

        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0

        # Determine which team scored (compare to previous)
        if i > 0:
            prev = events[i - 1]
            prev_home = prev.get("home_score", 0) or 0
            prev_away = prev.get("away_score", 0) or 0
            home_delta = home_score - prev_home
            away_delta = away_score - prev_away

            if home_delta > 0 and away_delta == 0:
                scoring_team = 1  # Home
                points = home_delta
            elif away_delta > 0 and home_delta == 0:
                scoring_team = 2  # Away
                points = away_delta
            else:
                # Both scored or neither - reset run
                if current_run_points >= RUN_POINTS_THRESHOLD:
                    runs.append({
                        "start": current_run_start,
                        "end": i - 1,
                        "points": current_run_points,
                        "team": current_run_team,
                    })
                current_run_team = None
                current_run_points = 0
                continue

            if scoring_team != current_run_team:
                # New team scored - save previous run if significant
                if current_run_points >= RUN_POINTS_THRESHOLD:
                    runs.append({
                        "start": current_run_start,
                        "end": i - 1,
                        "points": current_run_points,
                        "team": current_run_team,
                    })
                current_run_team = scoring_team
                current_run_points = points
                current_run_start = i
            else:
                current_run_points += points

    # Close any open run
    if current_run_points >= RUN_POINTS_THRESHOLD:
        runs.append({
            "start": current_run_start,
            "end": len(events) - 1,
            "points": current_run_points,
            "team": current_run_team,
        })

    return runs


def _detect_closing_stretch(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Detect closing stretch of a close game."""
    q4_events = [
        (i, e) for i, e in enumerate(events)
        if e.get("event_type") == "pbp" and e.get("quarter") == 4
    ]

    if not q4_events:
        return None

    # Find events in last CLOSING_MINUTES
    closing_events = []
    for i, event in q4_events:
        clock = _parse_clock_to_seconds(event.get("game_clock"))
        if clock is not None and clock <= CLOSING_MINUTES * 60:
            home = event.get("home_score", 0) or 0
            away = event.get("away_score", 0) or 0
            margin = abs(home - away)
            if margin <= CLOSING_MARGIN:
                closing_events.append((i, event))

    if len(closing_events) < 3:
        return None

    return {
        "start": closing_events[0][0],
        "end": closing_events[-1][0],
    }


def partition_game(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> list[Moment]:
    """
    Partition a game timeline into moments.

    Every play belongs to exactly one moment.
    Moments are contiguous and chronologically ordered.
    """
    events = list(timeline)
    if not events:
        return []

    # Get PBP-only events for analysis
    pbp_indices = [i for i, e in enumerate(events) if e.get("event_type") == "pbp"]
    if not pbp_indices:
        return []

    # Detect patterns
    runs = _detect_runs(events)
    closing = _detect_closing_stretch(events)

    # Build moments from patterns
    moments: list[Moment] = []
    used_indices: set[int] = set()
    moment_id = 0

    # Add run moments
    for run in runs:
        start_idx = run["start"]
        end_idx = run["end"]
        start_event = events[start_idx]
        end_event = events[end_idx]

        moment_id += 1
        moments.append(Moment(
            id=f"m_{moment_id:03d}",
            type=MomentType.RUN,
            start_play=start_idx,
            end_play=end_idx,
            play_count=end_idx - start_idx + 1,
            teams=["HOME" if run["team"] == 1 else "AWAY"],
            score_start=_format_score(
                start_event.get("home_score"),
                start_event.get("away_score"),
            ),
            score_end=_format_score(
                end_event.get("home_score"),
                end_event.get("away_score"),
            ),
            clock=f"Q{start_event.get('quarter', '?')} {start_event.get('game_clock', '')}–{end_event.get('game_clock', '')}",
            is_notable=run["points"] >= RUN_NOTABLE_THRESHOLD,
            note=f"{run['points']}-0 run",
        ))
        for i in range(start_idx, end_idx + 1):
            used_indices.add(i)

    # Add closing stretch if not overlapping
    if closing:
        start_idx = closing["start"]
        end_idx = closing["end"]
        if not any(i in used_indices for i in range(start_idx, end_idx + 1)):
            start_event = events[start_idx]
            end_event = events[end_idx]

            moment_id += 1
            moments.append(Moment(
                id=f"m_{moment_id:03d}",
                type=MomentType.CLOSING,
                start_play=start_idx,
                end_play=end_idx,
                play_count=end_idx - start_idx + 1,
                score_start=_format_score(
                    start_event.get("home_score"),
                    start_event.get("away_score"),
                ),
                score_end=_format_score(
                    end_event.get("home_score"),
                    end_event.get("away_score"),
                ),
                clock=f"Q4 {start_event.get('game_clock', '')}–{end_event.get('game_clock', '')}",
                is_notable=True,
                note="Closing stretch",
            ))
            for i in range(start_idx, end_idx + 1):
                used_indices.add(i)

    # Fill gaps with NEUTRAL moments
    current_start: int | None = None
    for i in pbp_indices:
        if i in used_indices:
            if current_start is not None:
                # Close neutral stretch
                start_event = events[current_start]
                end_event = events[i - 1]
                moment_id += 1
                moments.append(Moment(
                    id=f"m_{moment_id:03d}",
                    type=MomentType.NEUTRAL,
                    start_play=current_start,
                    end_play=i - 1,
                    play_count=i - current_start,
                    score_start=_format_score(
                        start_event.get("home_score"),
                        start_event.get("away_score"),
                    ),
                    score_end=_format_score(
                        end_event.get("home_score"),
                        end_event.get("away_score"),
                    ),
                    is_notable=False,
                ))
                current_start = None
        else:
            if current_start is None:
                current_start = i

    # Close any trailing neutral
    if current_start is not None:
        last_idx = pbp_indices[-1]
        start_event = events[current_start]
        end_event = events[last_idx]
        moment_id += 1
        moments.append(Moment(
            id=f"m_{moment_id:03d}",
            type=MomentType.NEUTRAL,
            start_play=current_start,
            end_play=last_idx,
            play_count=last_idx - current_start + 1,
            score_start=_format_score(
                start_event.get("home_score"),
                start_event.get("away_score"),
            ),
            score_end=_format_score(
                end_event.get("home_score"),
                end_event.get("away_score"),
            ),
            is_notable=False,
        ))

    # Sort by start_play
    moments.sort(key=lambda m: m.start_play)

    return moments


def get_highlights(moments: list[Moment]) -> list[Moment]:
    """Return moments that are notable (is_notable=True)."""
    return [m for m in moments if m.is_notable]
