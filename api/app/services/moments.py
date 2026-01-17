"""
Game Moments: The single narrative primitive.

A Moment is a contiguous segment of plays that share a narrative character.
Every play belongs to exactly one Moment. Moments are chronological.

Key invariants:
- Full coverage: union of all moment.plays == all plays in game
- Non-overlapping: no play appears in multiple moments
- Chronological: moments ordered by start_play_id

Highlights are simply moments where is_notable=True.
This is a property, not a separate pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

logger = logging.getLogger(__name__)


class MomentType(str, Enum):
    """
    Moment classification. Minimal set, easily extensible.
    
    Adding a new type requires only adding it here.
    No other layers need modification.
    """
    NEUTRAL = "NEUTRAL"   # No special pattern detected
    RUN = "RUN"           # One team scoring unanswered
    BATTLE = "BATTLE"     # Frequent lead changes / ties
    CLOSING = "CLOSING"   # Final minutes of game


@dataclass
class Moment:
    """
    The single narrative unit.
    
    Every play belongs to exactly one Moment.
    Moments are always chronological.
    """
    # Identity
    id: str                           # "m_001"
    type: MomentType                  # What kind of moment
    
    # Play coverage (the core relationship)
    start_play: int                   # First play index
    end_play: int                     # Last play index (inclusive)
    
    # Context (derived, not controlling)
    teams: list[str] = field(default_factory=list)
    players: list[dict[str, Any]] = field(default_factory=list)
    score_start: str = ""             # "12–15"
    score_end: str = ""               # "18–15"
    clock: str = ""                   # "Q2 8:45–6:12"
    
    # Notable flag (this IS highlights - not a separate concept)
    is_notable: bool = False
    note: str | None = None           # "7-0 run" or "3 lead changes"
    
    @property
    def play_count(self) -> int:
        return self.end_play - self.start_play + 1
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "start_play": self.start_play,
            "end_play": self.end_play,
            "play_count": self.play_count,
            "teams": self.teams,
            "players": self.players,
            "score_start": self.score_start,
            "score_end": self.score_end,
            "clock": self.clock,
            "is_notable": self.is_notable,
            "note": self.note,
        }


def partition_game(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> list[Moment]:
    """
    Partition the entire game into moments.
    
    This is the only entry point. It produces a complete,
    chronological list of moments covering all plays.
    
    Args:
        timeline: Full timeline events
        summary: Game summary with team info
        
    Returns:
        List of Moments, ordered chronologically
    """
    plays = [e for e in timeline if e.get("event_type") == "pbp"]
    if not plays:
        return []
    
    plays = sorted(plays, key=lambda e: e.get("play_index", 0))
    
    # Team info
    home = summary.get("teams", {}).get("home", {})
    away = summary.get("teams", {}).get("away", {})
    home_abbr = home.get("abbreviation", "HOME")
    away_abbr = away.get("abbreviation", "AWAY")
    
    # Detect patterns and build moments
    moments = _build_moments(plays, home_abbr, away_abbr)
    
    # Verify invariant: full coverage
    _verify_coverage(moments, len(plays))
    
    return moments


def get_highlights(moments: list[Moment]) -> list[Moment]:
    """
    Get highlights as a filtered view.
    
    Highlights = moments where is_notable=True.
    This is a view, not a transformation.
    """
    return [m for m in moments if m.is_notable]


# --- Internal Implementation ---


def _build_moments(
    plays: list[dict[str, Any]],
    home_abbr: str,
    away_abbr: str,
) -> list[Moment]:
    """Build moments by detecting patterns and filling gaps."""
    if not plays:
        return []
    
    # Detect patterns (runs, battles, closing)
    patterns = _detect_patterns(plays, home_abbr, away_abbr)
    
    # Build moments from patterns, filling gaps with NEUTRAL
    moments: list[Moment] = []
    current = 0
    counter = 0
    
    for pattern in sorted(patterns, key=lambda p: (p["start"], -p["end"])):
        # Skip patterns that overlap with already processed plays
        if pattern["start"] < current:
            continue
        
        # Fill gap before this pattern
        if pattern["start"] > current:
            moments.append(_make_moment(
                plays, current, pattern["start"] - 1,
                MomentType.NEUTRAL, counter, home_abbr, away_abbr
            ))
            counter += 1
        
        # Create moment for pattern
        moments.append(_make_moment(
            plays, pattern["start"], pattern["end"],
            pattern["type"], counter, home_abbr, away_abbr,
            is_notable=pattern.get("notable", False),
            note=pattern.get("note")
        ))
        counter += 1
        current = pattern["end"] + 1
    
    # Fill remaining
    if current < len(plays):
        moments.append(_make_moment(
            plays, current, len(plays) - 1,
            MomentType.NEUTRAL, counter, home_abbr, away_abbr
        ))
    
    return moments


def _detect_patterns(
    plays: list[dict[str, Any]],
    home_abbr: str,
    away_abbr: str,
) -> list[dict[str, Any]]:
    """
    Detect narrative patterns in play sequence.
    
    Returns non-overlapping patterns. Patterns may leave gaps
    (filled by NEUTRAL moments later).
    """
    patterns: list[dict[str, Any]] = []
    used = set()  # Track which play indices are claimed
    
    # 1. Detect runs (one team scoring unanswered)
    i = 0
    while i < len(plays):
        if i in used:
            i += 1
            continue
        run = _detect_run(plays, i, home_abbr, away_abbr)
        if run:
            patterns.append(run)
            for j in range(run["start"], run["end"] + 1):
                used.add(j)
            i = run["end"] + 1
        else:
            i += 1
    
    # 2. Detect battles (lead changes in short span)
    i = 0
    while i < len(plays):
        if i in used:
            i += 1
            continue
        battle = _detect_battle(plays, i)
        if battle:
            patterns.append(battle)
            for j in range(battle["start"], battle["end"] + 1):
                used.add(j)
            i = battle["end"] + 1
        else:
            i += 1
    
    # 3. Detect closing stretch (final 3 minutes of Q4)
    closing = _detect_closing(plays)
    if closing:
        # Only add if not overlapping significantly
        overlap = sum(1 for j in range(closing["start"], closing["end"] + 1) if j in used)
        if overlap < (closing["end"] - closing["start"]) / 2:
            patterns.append(closing)
    
    return patterns


def _detect_run(
    plays: list[dict[str, Any]],
    start: int,
    home_abbr: str,
    away_abbr: str,
    min_points: int = 6,
) -> dict[str, Any] | None:
    """Detect a scoring run (one team scoring unanswered)."""
    if start >= len(plays):
        return None
    
    start_play = plays[start]
    start_home = start_play.get("home_score") or 0
    start_away = start_play.get("away_score") or 0
    
    home_pts = 0
    away_pts = 0
    end = start
    
    for i in range(start, min(start + 40, len(plays))):
        play = plays[i]
        curr_home = play.get("home_score") or 0
        curr_away = play.get("away_score") or 0
        
        new_home = curr_home - start_home
        new_away = curr_away - start_away
        
        # Check if other team scored
        if home_pts > 0 and new_away > away_pts:
            break
        if away_pts > 0 and new_home > home_pts:
            break
        
        home_pts = new_home
        away_pts = new_away
        end = i
    
    # Qualify as run?
    if home_pts >= min_points and away_pts == 0:
        return {
            "type": MomentType.RUN,
            "start": start,
            "end": end,
            "notable": home_pts >= 8,
            "note": f"{home_pts}-0 run" if home_pts >= 8 else None,
            "team": home_abbr,
        }
    if away_pts >= min_points and home_pts == 0:
        return {
            "type": MomentType.RUN,
            "start": start,
            "end": end,
            "notable": away_pts >= 8,
            "note": f"{away_pts}-0 run" if away_pts >= 8 else None,
            "team": away_abbr,
        }
    
    return None


def _detect_battle(
    plays: list[dict[str, Any]],
    start: int,
    min_changes: int = 3,
    max_span: int = 35,
) -> dict[str, Any] | None:
    """Detect a lead battle (multiple lead changes)."""
    if start >= len(plays):
        return None
    
    start_play = plays[start]
    start_home = start_play.get("home_score") or 0
    start_away = start_play.get("away_score") or 0
    
    leader = "tie" if start_home == start_away else ("home" if start_home > start_away else "away")
    changes = 0
    end = start
    
    for i in range(start, min(start + max_span, len(plays))):
        play = plays[i]
        curr_home = play.get("home_score") or 0
        curr_away = play.get("away_score") or 0
        
        new_leader = "tie" if curr_home == curr_away else ("home" if curr_home > curr_away else "away")
        
        if new_leader != "tie" and new_leader != leader and leader != "tie":
            changes += 1
        
        if new_leader != "tie":
            leader = new_leader
        end = i
        
        if changes >= min_changes:
            break
    
    if changes >= min_changes:
        return {
            "type": MomentType.BATTLE,
            "start": start,
            "end": end,
            "notable": changes >= 4,
            "note": f"{changes} lead changes" if changes >= 4 else None,
        }
    
    return None


def _detect_closing(
    plays: list[dict[str, Any]],
    minutes: float = 3.0,
) -> dict[str, Any] | None:
    """Detect closing stretch (final minutes of Q4)."""
    q4 = [(i, p) for i, p in enumerate(plays) if p.get("quarter") == 4]
    if not q4:
        return None
    
    closing_plays = []
    for i, p in q4:
        clock = p.get("game_clock", "")
        if not clock:
            continue
        try:
            parts = clock.replace(".", ":").split(":")
            mins = float(parts[0]) + float(parts[1]) / 60 if len(parts) >= 2 else float(parts[0])
            if mins <= minutes:
                closing_plays.append(i)
        except (ValueError, IndexError):
            continue
    
    if len(closing_plays) >= 10:
        # Check if game was close
        first = plays[closing_plays[0]]
        margin = abs((first.get("home_score") or 0) - (first.get("away_score") or 0))
        is_close = margin <= 10
        
        return {
            "type": MomentType.CLOSING,
            "start": closing_plays[0],
            "end": closing_plays[-1],
            "notable": is_close,
            "note": "Close finish" if is_close else None,
        }
    
    return None


def _make_moment(
    plays: list[dict[str, Any]],
    start: int,
    end: int,
    mtype: MomentType,
    counter: int,
    home_abbr: str,
    away_abbr: str,
    is_notable: bool = False,
    note: str | None = None,
) -> Moment:
    """Create a Moment from a play range."""
    start_play = plays[start]
    end_play = plays[end]
    
    # Get scores (search for valid scores if endpoints are None)
    start_home, start_away = _get_score(plays, start, end, forward=True)
    end_home, end_away = _get_score(plays, start, end, forward=False)
    
    # Clock range
    s_q = start_play.get("quarter", 1)
    e_q = end_play.get("quarter", 1)
    s_c = start_play.get("game_clock", "")
    e_c = end_play.get("game_clock", "")
    
    clock = f"Q{s_q} {s_c}–{e_c}" if s_q == e_q else f"Q{s_q} {s_c} – Q{e_q} {e_c}"
    
    # Extract notable players
    players = _extract_players(plays, start, end)
    
    return Moment(
        id=f"m_{counter:03d}",
        type=mtype,
        start_play=start_play.get("play_index", start),
        end_play=end_play.get("play_index", end),
        teams=[home_abbr, away_abbr],
        players=players,
        score_start=f"{start_away}–{start_home}",
        score_end=f"{end_away}–{end_home}",
        clock=clock,
        is_notable=is_notable,
        note=note,
    )


def _get_score(
    plays: list[dict[str, Any]],
    start: int,
    end: int,
    forward: bool,
) -> tuple[int, int]:
    """Get score from play range, searching for valid scores."""
    rng = range(start, end + 1) if forward else range(end, start - 1, -1)
    for i in rng:
        if plays[i].get("home_score") is not None:
            return plays[i].get("home_score", 0), plays[i].get("away_score", 0)
    return 0, 0


def _extract_players(
    plays: list[dict[str, Any]],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    """Extract players with notable contributions."""
    import re
    
    stats: dict[str, dict[str, int]] = {}
    
    for i in range(start, min(end + 1, len(plays))):
        play = plays[i]
        desc = (play.get("description") or "").lower()
        name = play.get("player_name")
        
        if not name:
            match = re.search(r'([A-Z]\.\s*[A-Z][a-zA-Z]+)', play.get("description", ""))
            if match:
                name = re.sub(r'[(),:;]+$', '', match.group(1)).strip()
        
        if not name or len(name) < 3:
            continue
        
        if name not in stats:
            stats[name] = {"pts": 0, "stl": 0, "blk": 0}
        
        if any(w in desc for w in ["makes", "made", "scores"]):
            pts = 3 if "three" in desc or "3-pt" in desc else (1 if "free throw" in desc else 2)
            stats[name]["pts"] += pts
        if "steal" in desc:
            stats[name]["stl"] += 1
        if "block" in desc:
            stats[name]["blk"] += 1
    
    # Filter to notable
    result = []
    for name, s in stats.items():
        if s["pts"] >= 4 or s["stl"] >= 1 or s["blk"] >= 1:
            parts = []
            if s["pts"]:
                parts.append(f"{s['pts']} pts")
            if s["stl"]:
                parts.append(f"{s['stl']} stl")
            if s["blk"]:
                parts.append(f"{s['blk']} blk")
            result.append({"name": name, "stats": s, "summary": ", ".join(parts)})
    
    result.sort(key=lambda p: p["stats"]["pts"] + 2 * p["stats"]["stl"] + 2 * p["stats"]["blk"], reverse=True)
    return result[:3]


def _verify_coverage(moments: list[Moment], total_plays: int) -> None:
    """Verify that moments cover all plays exactly once."""
    if not moments:
        return
    
    covered = set()
    for m in moments:
        for p in range(m.start_play, m.end_play + 1):
            if p in covered:
                logger.warning(f"Play {p} covered by multiple moments")
            covered.add(p)
    
    expected = set(range(total_plays))
    missing = expected - covered
    if missing:
        logger.warning(f"Plays not covered: {missing}")
