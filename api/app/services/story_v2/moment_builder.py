"""
Story V2 Moment Builder: Deterministic segmentation of PBP into condensed moments.

This module partitions an ordered stream of PBP plays into CondensedMoment objects.
It is pure segmentation logic with no narrative generation.

AUTHORITATIVE INPUTS:
- docs/story_v2_contract.md
- docs/pbp_story_v2_assumptions.md
- story_v2/schema.py

BOUNDARY RULES (applied in order):

1. SCORE_CHANGE
   - Close moment after any play that changes the score
   - Score change detected by comparing current play's score to previous

2. POSSESSION_CHANGE
   - Close moment after turnover events
   - Detected by play_type or description containing possession-change keywords

3. STOPPAGE
   - Close moment after timeout or review events
   - Detected by play_type or description containing stoppage keywords

4. COMPOSITE_SEQUENCE_END
   - Keep foul + free throw sequences together as one moment
   - Close moment after the final free throw or next non-free-throw play

5. MAX_PLAYS_CAP
   - Hard cap at DEFAULT_MAX_PLAYS_PER_MOMENT (5)
   - Extended to COMPOSITE_MAX_PLAYS (7) only for composite sequences
   - Forces moment close regardless of other signals

GUARANTEES:
- Every play_index appears in exactly one moment
- Moments are returned in ascending play_index order
- No gaps in coverage
- No overlap in play_ids between moments

NARRATIVE PLACEHOLDER:
This module sets narrative to a placeholder value.
Actual narrative generation is a separate phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from .schema import (
    CondensedMoment,
    ScoreTuple,
    StoryV2Output,
    SchemaValidationError,
    validate_story,
)


# Configuration constants
DEFAULT_MAX_PLAYS_PER_MOMENT = 5
COMPOSITE_MAX_PLAYS = 7
NARRATIVE_PLACEHOLDER = "[NARRATIVE_PENDING]"


class BoundaryReason(Enum):
    """Concrete reasons why a moment boundary was created."""

    SCORE_CHANGE = "SCORE_CHANGE"
    POSSESSION_CHANGE = "POSSESSION_CHANGE"
    STOPPAGE = "STOPPAGE"
    COMPOSITE_SEQUENCE_END = "COMPOSITE_SEQUENCE_END"
    MAX_PLAYS_CAP = "MAX_PLAYS_CAP"
    END_OF_INPUT = "END_OF_INPUT"


# Event detection keywords (case-insensitive matching against description/play_type)

TURNOVER_KEYWORDS = frozenset([
    "turnover",
    "steal",
    "lost ball",
    "bad pass",
    "out of bounds",
    "offensive foul",
    "traveling",
    "travel",
    "double dribble",
    "kicked ball",
    "giveaway",
])

STOPPAGE_KEYWORDS = frozenset([
    "timeout",
    "time out",
    "review",
    "challenge",
    "delay of game",
    "official timeout",
    "tv timeout",
    "media timeout",
])

FOUL_KEYWORDS = frozenset([
    "foul",
    "personal foul",
    "shooting foul",
    "flagrant",
    "technical",
    "offensive foul",
])

FREE_THROW_KEYWORDS = frozenset([
    "free throw",
    "ft ",
    "foul shot",
])

SCORING_PLAY_TYPES = frozenset([
    "made_shot",
    "made shot",
    "field goal",
    "goal",
    "touchdown",
    "free throw made",
    "ft made",
    "3pt",
    "2pt",
    "dunk",
    "layup",
])


@dataclass
class PlayData:
    """Normalized view of a single PBP play for moment building.

    This is the input contract for the moment builder.
    All fields match pbp_story_v2_assumptions.md expectations.
    """

    play_index: int
    period: int
    game_clock: str
    description: str
    play_type: str | None
    team_id: int | None
    home_score: int
    away_score: int


@dataclass
class MomentDebugInfo:
    """Debug information for a single moment."""

    start_play_index: int
    end_play_index: int
    play_count: int
    boundary_reason: BoundaryReason
    triggering_play_index: int


@dataclass
class BuilderResult:
    """Result of moment building, with optional debug info."""

    moments: list[CondensedMoment]
    debug_info: list[MomentDebugInfo] | None = None


class MomentBuildError(Exception):
    """Raised when moment building fails due to contract violation."""

    pass


def _normalize_text(text: str | None) -> str:
    """Normalize text for keyword matching."""
    if not text:
        return ""
    return text.lower().strip()


def _contains_keyword(text: str | None, keywords: frozenset[str]) -> bool:
    """Check if text contains any keyword."""
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(kw in normalized for kw in keywords)


def _is_turnover(play: PlayData) -> bool:
    """Detect if play is a turnover/possession change event."""
    return (
        _contains_keyword(play.description, TURNOVER_KEYWORDS)
        or _contains_keyword(play.play_type, TURNOVER_KEYWORDS)
    )


def _is_stoppage(play: PlayData) -> bool:
    """Detect if play is a stoppage event (timeout, review, etc.)."""
    return (
        _contains_keyword(play.description, STOPPAGE_KEYWORDS)
        or _contains_keyword(play.play_type, STOPPAGE_KEYWORDS)
    )


def _is_foul(play: PlayData) -> bool:
    """Detect if play is a foul event."""
    return (
        _contains_keyword(play.description, FOUL_KEYWORDS)
        or _contains_keyword(play.play_type, FOUL_KEYWORDS)
    )


def _is_free_throw(play: PlayData) -> bool:
    """Detect if play is a free throw event."""
    return (
        _contains_keyword(play.description, FREE_THROW_KEYWORDS)
        or _contains_keyword(play.play_type, FREE_THROW_KEYWORDS)
    )


def _is_scoring_play(
    play: PlayData,
    prev_home_score: int,
    prev_away_score: int,
) -> bool:
    """Detect if play changed the score."""
    return (
        play.home_score != prev_home_score
        or play.away_score != prev_away_score
    )


def _select_narrated_play(plays: list[PlayData]) -> int:
    """Select which play to mark as explicitly narrated.

    Selection priority:
    1. Last scoring play in the moment
    2. Last play in the moment (if no scoring play)

    Returns the play_index of the selected play.
    """
    if not plays:
        raise MomentBuildError("Cannot select narrated play from empty list")

    # Find scoring plays by detecting score changes
    scoring_plays: list[PlayData] = []
    prev_home = 0
    prev_away = 0

    for i, play in enumerate(plays):
        if i == 0:
            # First play: check if score is non-zero (indicating scoring)
            if play.home_score > 0 or play.away_score > 0:
                scoring_plays.append(play)
        else:
            prev_home = plays[i - 1].home_score
            prev_away = plays[i - 1].away_score
            if _is_scoring_play(play, prev_home, prev_away):
                scoring_plays.append(play)

    if scoring_plays:
        return scoring_plays[-1].play_index

    return plays[-1].play_index


@dataclass
class _MomentBuilder:
    """Internal builder state for constructing moments."""

    plays: list[PlayData] = field(default_factory=list)
    in_composite_sequence: bool = False

    def add_play(self, play: PlayData) -> None:
        """Add a play to the current moment."""
        self.plays.append(play)

    def clear(self) -> None:
        """Clear the current moment state."""
        self.plays = []
        self.in_composite_sequence = False

    @property
    def play_count(self) -> int:
        """Number of plays in current moment."""
        return len(self.plays)

    @property
    def is_empty(self) -> bool:
        """Check if moment is empty."""
        return len(self.plays) == 0


def _should_close_moment(
    builder: _MomentBuilder,
    current_play: PlayData,
    next_play: PlayData | None,
    prev_home_score: int,
    prev_away_score: int,
) -> tuple[bool, BoundaryReason]:
    """Decide if moment should be closed after current play.

    Returns (should_close, reason).
    """
    max_plays = (
        COMPOSITE_MAX_PLAYS if builder.in_composite_sequence
        else DEFAULT_MAX_PLAYS_PER_MOMENT
    )

    # Rule 5: MAX_PLAYS_CAP - always enforce hard cap
    if builder.play_count >= max_plays:
        return True, BoundaryReason.MAX_PLAYS_CAP

    # Rule 4: COMPOSITE_SEQUENCE handling
    if _is_foul(current_play):
        # Start composite sequence - don't close yet
        builder.in_composite_sequence = True
        return False, BoundaryReason.COMPOSITE_SEQUENCE_END

    if builder.in_composite_sequence:
        if _is_free_throw(current_play):
            # Check if next play is also a free throw
            if next_play is not None and _is_free_throw(next_play):
                return False, BoundaryReason.COMPOSITE_SEQUENCE_END
            # This is the last free throw - close after it
            return True, BoundaryReason.COMPOSITE_SEQUENCE_END

        # Non-free-throw play after foul - close composite sequence
        return True, BoundaryReason.COMPOSITE_SEQUENCE_END

    # Rule 1: SCORE_CHANGE - close after scoring plays
    if _is_scoring_play(current_play, prev_home_score, prev_away_score):
        return True, BoundaryReason.SCORE_CHANGE

    # Rule 2: POSSESSION_CHANGE - close after turnovers
    if _is_turnover(current_play):
        return True, BoundaryReason.POSSESSION_CHANGE

    # Rule 3: STOPPAGE - close after timeouts/reviews
    if _is_stoppage(current_play):
        return True, BoundaryReason.STOPPAGE

    return False, BoundaryReason.END_OF_INPUT


def _build_moment(
    plays: list[PlayData],
    boundary_reason: BoundaryReason,
    score_before: tuple[int, int],
) -> tuple[CondensedMoment, MomentDebugInfo]:
    """Build a CondensedMoment from accumulated plays.

    Args:
        plays: List of plays in chronological order
        boundary_reason: Why this moment's boundary was created
        score_before: (home, away) score before first play

    Returns:
        Tuple of (CondensedMoment, MomentDebugInfo)
    """
    if not plays:
        raise MomentBuildError("Cannot build moment from empty play list")

    first_play = plays[0]
    last_play = plays[-1]

    play_ids = tuple(p.play_index for p in plays)
    narrated_play_id = _select_narrated_play(plays)

    # Use first play's clock as start, last play's clock as end
    start_clock = first_play.game_clock or "0:00"
    end_clock = last_play.game_clock or "0:00"

    # Period from first play (all plays in moment should be same period in practice)
    period = first_play.period

    # Score before is provided; score after is from last play
    score_before_tuple = ScoreTuple(home=score_before[0], away=score_before[1])
    score_after_tuple = ScoreTuple(home=last_play.home_score, away=last_play.away_score)

    moment = CondensedMoment(
        play_ids=play_ids,
        explicitly_narrated_play_ids=(narrated_play_id,),
        start_clock=start_clock,
        end_clock=end_clock,
        period=period,
        score_before=score_before_tuple,
        score_after=score_after_tuple,
        narrative=NARRATIVE_PLACEHOLDER,
    )

    debug_info = MomentDebugInfo(
        start_play_index=first_play.play_index,
        end_play_index=last_play.play_index,
        play_count=len(plays),
        boundary_reason=boundary_reason,
        triggering_play_index=last_play.play_index,
    )

    return moment, debug_info


def build_condensed_moments(
    plays: Sequence[PlayData],
    *,
    debug: bool = False,
) -> BuilderResult:
    """Build condensed moments from ordered PBP plays.

    Args:
        plays: Ordered sequence of plays (must be sorted by play_index)
        debug: If True, include debug information in result

    Returns:
        BuilderResult containing moments and optional debug info

    Raises:
        MomentBuildError: If input violates assumptions or coverage fails
    """
    if not plays:
        raise MomentBuildError("Cannot build moments from empty play list")

    # Verify plays are ordered by play_index
    for i in range(1, len(plays)):
        if plays[i].play_index <= plays[i - 1].play_index:
            raise MomentBuildError(
                f"Plays are not ordered by play_index: "
                f"play[{i - 1}].play_index={plays[i - 1].play_index}, "
                f"play[{i}].play_index={plays[i].play_index}"
            )

    moments: list[CondensedMoment] = []
    debug_infos: list[MomentDebugInfo] = []
    builder = _MomentBuilder()

    # Track score before current moment
    score_before: tuple[int, int] = (0, 0)
    prev_home_score = 0
    prev_away_score = 0

    for i, play in enumerate(plays):
        builder.add_play(play)

        # Peek at next play for composite sequence handling
        next_play = plays[i + 1] if i + 1 < len(plays) else None

        should_close, reason = _should_close_moment(
            builder,
            play,
            next_play,
            prev_home_score,
            prev_away_score,
        )

        if should_close:
            moment, debug_info = _build_moment(
                builder.plays,
                reason,
                score_before,
            )
            moments.append(moment)
            debug_infos.append(debug_info)

            # Update score_before for next moment
            score_before = (play.home_score, play.away_score)
            builder.clear()

        # Update previous scores for next iteration
        prev_home_score = play.home_score
        prev_away_score = play.away_score

    # Handle any remaining plays
    if not builder.is_empty:
        moment, debug_info = _build_moment(
            builder.plays,
            BoundaryReason.END_OF_INPUT,
            score_before,
        )
        moments.append(moment)
        debug_infos.append(debug_info)

    # Validate coverage: every play must appear exactly once
    _validate_coverage(plays, moments)

    # Validate against schema
    try:
        story = StoryV2Output(moments=tuple(moments))
        validate_story(story)
    except SchemaValidationError as e:
        raise MomentBuildError(f"Schema validation failed: {e}") from e

    return BuilderResult(
        moments=moments,
        debug_info=debug_infos if debug else None,
    )


def _validate_coverage(
    plays: Sequence[PlayData],
    moments: list[CondensedMoment],
) -> None:
    """Validate that all plays are covered exactly once.

    Raises MomentBuildError on any violation.
    """
    input_play_ids = {p.play_index for p in plays}
    moment_play_ids: set[int] = set()

    for moment in moments:
        for pid in moment.play_ids:
            if pid in moment_play_ids:
                raise MomentBuildError(
                    f"play_index {pid} appears in multiple moments (overlap)"
                )
            moment_play_ids.add(pid)

    missing = input_play_ids - moment_play_ids
    if missing:
        raise MomentBuildError(
            f"Coverage gap: play_indices {missing} not included in any moment"
        )

    extra = moment_play_ids - input_play_ids
    if extra:
        raise MomentBuildError(
            f"Invalid coverage: play_indices {extra} in moments but not in input"
        )


def plays_from_raw(
    raw_plays: Sequence[dict[str, Any]],
    *,
    forward_fill_scores: bool = True,
) -> list[PlayData]:
    """Convert raw PBP dictionaries to PlayData objects.

    Args:
        raw_plays: List of raw play dictionaries from database/API
        forward_fill_scores: If True, forward-fill missing scores

    Returns:
        List of PlayData objects ready for moment building

    Note:
        Per pbp_story_v2_assumptions.md Section 8.5, score forward-fill
        is an upstream normalization concern. This function provides it
        as a convenience but it should be applied before Story V2.
    """
    result: list[PlayData] = []
    last_home_score = 0
    last_away_score = 0

    for raw in raw_plays:
        home_score = raw.get("home_score")
        away_score = raw.get("away_score")

        if forward_fill_scores:
            if home_score is None:
                home_score = last_home_score
            if away_score is None:
                away_score = last_away_score
        else:
            home_score = home_score or 0
            away_score = away_score or 0

        play = PlayData(
            play_index=raw["play_index"],
            period=raw.get("quarter") or raw.get("period") or 1,
            game_clock=raw.get("game_clock") or "0:00",
            description=raw.get("description") or "",
            play_type=raw.get("play_type"),
            team_id=raw.get("team_id"),
            home_score=home_score,
            away_score=away_score,
        )
        result.append(play)

        last_home_score = home_score
        last_away_score = away_score

    return result
