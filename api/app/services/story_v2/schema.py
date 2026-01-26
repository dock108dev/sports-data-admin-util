"""
Story V2 Schema Definitions.

This module defines the canonical data structures for Story V2 output.
All definitions derive exclusively from docs/story_v2_contract.md.

A story is an ordered list of condensed moments.
A condensed moment is a small set of Play-by-Play (PBP) plays
with at least one explicitly narrated play.

These schemas enforce contract compliance. They contain no behavior,
no generation logic, and no optional fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


class SchemaValidationError(Exception):
    """Raised when data violates the Story V2 contract."""

    pass


@dataclass(frozen=True)
class ScoreTuple:
    """Score state as (home, away) tuple.

    Immutable representation of game score at a point in time.
    """

    home: int
    away: int

    def __post_init__(self) -> None:
        if not isinstance(self.home, int):
            raise SchemaValidationError(
                f"score.home must be int, got {type(self.home).__name__}"
            )
        if not isinstance(self.away, int):
            raise SchemaValidationError(
                f"score.away must be int, got {type(self.away).__name__}"
            )
        if self.home < 0:
            raise SchemaValidationError(
                f"score.home must be non-negative, got {self.home}"
            )
        if self.away < 0:
            raise SchemaValidationError(
                f"score.away must be non-negative, got {self.away}"
            )


@dataclass(frozen=True)
class CondensedMoment:
    """A condensed moment: the atomic unit of Story V2.

    A condensed moment is a small set of PBP plays with at least one
    explicitly narrated play. It is the smallest unit that supports
    both narrative coherence and full play traceability.

    All fields are required. No optional fields are permitted.
    Extensions require contract amendment.

    CONTRACT GUARANTEES:
    - play_ids: Non-empty list of unique play identifiers
    - explicitly_narrated_play_ids: Non-empty strict subset of play_ids
    - start_clock: Valid game clock at first play
    - end_clock: Valid game clock at last play
    - period: Valid period number (positive integer)
    - score_before: Score state at moment start
    - score_after: Score state at moment end
    - narrative: Non-empty text describing at least one explicitly narrated play
    """

    play_ids: tuple[int, ...]
    explicitly_narrated_play_ids: tuple[int, ...]
    start_clock: str
    end_clock: str
    period: int
    score_before: ScoreTuple
    score_after: ScoreTuple
    narrative: str

    def __post_init__(self) -> None:
        _validate_moment_fields(self)


@dataclass(frozen=True)
class StoryV2Output:
    """Story V2 output: an ordered list of condensed moments.

    This is the complete output structure for Story V2.
    It contains no metadata, no summaries, no headers, and no
    game-level narrative. Only the ordered sequence of moments.

    CONTRACT GUARANTEES:
    - moments: Non-empty ordered list of CondensedMoment objects
    - Moments are ordered by (period, start_clock) descending clock
    - No play_id appears in multiple moments
    """

    moments: tuple[CondensedMoment, ...]

    def __post_init__(self) -> None:
        _validate_story_structure(self)


def _validate_moment_fields(moment: CondensedMoment) -> None:
    """Validate all fields of a CondensedMoment.

    Raises SchemaValidationError on any contract violation.
    """
    # play_ids: must be non-empty tuple of integers
    if not isinstance(moment.play_ids, tuple):
        raise SchemaValidationError(
            f"play_ids must be tuple, got {type(moment.play_ids).__name__}"
        )
    if len(moment.play_ids) == 0:
        raise SchemaValidationError("play_ids must be non-empty")
    for pid in moment.play_ids:
        if not isinstance(pid, int):
            raise SchemaValidationError(
                f"play_ids elements must be int, got {type(pid).__name__}"
            )

    # explicitly_narrated_play_ids: must be non-empty tuple of integers
    if not isinstance(moment.explicitly_narrated_play_ids, tuple):
        raise SchemaValidationError(
            f"explicitly_narrated_play_ids must be tuple, "
            f"got {type(moment.explicitly_narrated_play_ids).__name__}"
        )
    if len(moment.explicitly_narrated_play_ids) == 0:
        raise SchemaValidationError("explicitly_narrated_play_ids must be non-empty")
    for pid in moment.explicitly_narrated_play_ids:
        if not isinstance(pid, int):
            raise SchemaValidationError(
                f"explicitly_narrated_play_ids elements must be int, "
                f"got {type(pid).__name__}"
            )

    # explicitly_narrated_play_ids must be strict subset of play_ids
    play_ids_set = set(moment.play_ids)
    narrated_set = set(moment.explicitly_narrated_play_ids)
    if not narrated_set.issubset(play_ids_set):
        extra = narrated_set - play_ids_set
        raise SchemaValidationError(
            f"explicitly_narrated_play_ids must be subset of play_ids. "
            f"Found {extra} not in play_ids."
        )

    # start_clock: must be non-empty string
    if not isinstance(moment.start_clock, str):
        raise SchemaValidationError(
            f"start_clock must be str, got {type(moment.start_clock).__name__}"
        )
    if len(moment.start_clock.strip()) == 0:
        raise SchemaValidationError("start_clock must be non-empty")

    # end_clock: must be non-empty string
    if not isinstance(moment.end_clock, str):
        raise SchemaValidationError(
            f"end_clock must be str, got {type(moment.end_clock).__name__}"
        )
    if len(moment.end_clock.strip()) == 0:
        raise SchemaValidationError("end_clock must be non-empty")

    # period: must be positive integer
    if not isinstance(moment.period, int):
        raise SchemaValidationError(
            f"period must be int, got {type(moment.period).__name__}"
        )
    if moment.period < 1:
        raise SchemaValidationError(f"period must be >= 1, got {moment.period}")

    # score_before: validated by ScoreTuple.__post_init__
    if not isinstance(moment.score_before, ScoreTuple):
        raise SchemaValidationError(
            f"score_before must be ScoreTuple, "
            f"got {type(moment.score_before).__name__}"
        )

    # score_after: validated by ScoreTuple.__post_init__
    if not isinstance(moment.score_after, ScoreTuple):
        raise SchemaValidationError(
            f"score_after must be ScoreTuple, "
            f"got {type(moment.score_after).__name__}"
        )

    # narrative: must be non-empty string
    if not isinstance(moment.narrative, str):
        raise SchemaValidationError(
            f"narrative must be str, got {type(moment.narrative).__name__}"
        )
    if len(moment.narrative.strip()) == 0:
        raise SchemaValidationError("narrative must be non-empty")


def _validate_story_structure(story: StoryV2Output) -> None:
    """Validate the structure of a StoryV2Output.

    Raises SchemaValidationError on any contract violation.
    """
    # moments: must be non-empty tuple
    if not isinstance(story.moments, tuple):
        raise SchemaValidationError(
            f"moments must be tuple, got {type(story.moments).__name__}"
        )
    if len(story.moments) == 0:
        raise SchemaValidationError("moments must be non-empty")

    # Each moment must be a valid CondensedMoment
    for i, moment in enumerate(story.moments):
        if not isinstance(moment, CondensedMoment):
            raise SchemaValidationError(
                f"moments[{i}] must be CondensedMoment, "
                f"got {type(moment).__name__}"
            )

    # Moments must be ordered by (period, start_clock descending)
    # Clock descending means higher clock values come first within a period
    # (e.g., 12:00 before 11:30 before 0:00)
    for i in range(1, len(story.moments)):
        prev = story.moments[i - 1]
        curr = story.moments[i]

        if curr.period < prev.period:
            raise SchemaValidationError(
                f"moments are not ordered by period: "
                f"moment[{i - 1}].period={prev.period}, "
                f"moment[{i}].period={curr.period}"
            )

        if curr.period == prev.period:
            # Within same period, clock must be descending (countdown)
            prev_seconds = _clock_to_seconds(prev.start_clock)
            curr_seconds = _clock_to_seconds(curr.start_clock)
            if prev_seconds is not None and curr_seconds is not None:
                if curr_seconds > prev_seconds:
                    raise SchemaValidationError(
                        f"moments are not ordered by clock within period {curr.period}: "
                        f"moment[{i - 1}].start_clock={prev.start_clock}, "
                        f"moment[{i}].start_clock={curr.start_clock}"
                    )

    # No play_id may appear in multiple moments
    seen_play_ids: dict[int, int] = {}
    for i, moment in enumerate(story.moments):
        for pid in moment.play_ids:
            if pid in seen_play_ids:
                raise SchemaValidationError(
                    f"play_id {pid} appears in multiple moments: "
                    f"moment[{seen_play_ids[pid]}] and moment[{i}]"
                )
            seen_play_ids[pid] = i


def _clock_to_seconds(clock: str) -> int | None:
    """Parse game clock to seconds remaining.

    Returns None if clock cannot be parsed.
    Does not raise; used only for ordering validation.
    """
    if not clock:
        return None
    try:
        parts = clock.replace(".", ":").split(":")
        if len(parts) >= 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        return int(float(parts[0]))
    except (ValueError, IndexError):
        return None


def validate_moment(moment: CondensedMoment) -> None:
    """Validate a single CondensedMoment.

    Raises SchemaValidationError if the moment violates the contract.
    This function is idempotent; CondensedMoment validates on construction.
    """
    if not isinstance(moment, CondensedMoment):
        raise SchemaValidationError(
            f"Expected CondensedMoment, got {type(moment).__name__}"
        )
    _validate_moment_fields(moment)


def validate_story(story: StoryV2Output) -> None:
    """Validate a complete StoryV2Output.

    Raises SchemaValidationError if the story violates the contract.
    This function is idempotent; StoryV2Output validates on construction.
    """
    if not isinstance(story, StoryV2Output):
        raise SchemaValidationError(
            f"Expected StoryV2Output, got {type(story).__name__}"
        )
    _validate_story_structure(story)


def moment_from_dict(data: dict) -> CondensedMoment:
    """Construct a CondensedMoment from a dictionary.

    Raises SchemaValidationError if data is malformed or violates contract.
    """
    required_keys = {
        "play_ids",
        "explicitly_narrated_play_ids",
        "start_clock",
        "end_clock",
        "period",
        "score_before",
        "score_after",
        "narrative",
    }

    if not isinstance(data, dict):
        raise SchemaValidationError(f"Expected dict, got {type(data).__name__}")

    missing = required_keys - set(data.keys())
    if missing:
        raise SchemaValidationError(f"Missing required fields: {missing}")

    extra = set(data.keys()) - required_keys
    if extra:
        raise SchemaValidationError(f"Unexpected fields (forbidden): {extra}")

    score_before_data = data["score_before"]
    score_after_data = data["score_after"]

    if isinstance(score_before_data, dict):
        score_before = ScoreTuple(
            home=score_before_data.get("home", 0),
            away=score_before_data.get("away", 0),
        )
    elif isinstance(score_before_data, (list, tuple)) and len(score_before_data) == 2:
        score_before = ScoreTuple(home=score_before_data[0], away=score_before_data[1])
    else:
        raise SchemaValidationError(
            f"score_before must be dict or 2-tuple, got {type(score_before_data).__name__}"
        )

    if isinstance(score_after_data, dict):
        score_after = ScoreTuple(
            home=score_after_data.get("home", 0),
            away=score_after_data.get("away", 0),
        )
    elif isinstance(score_after_data, (list, tuple)) and len(score_after_data) == 2:
        score_after = ScoreTuple(home=score_after_data[0], away=score_after_data[1])
    else:
        raise SchemaValidationError(
            f"score_after must be dict or 2-tuple, got {type(score_after_data).__name__}"
        )

    return CondensedMoment(
        play_ids=tuple(data["play_ids"]),
        explicitly_narrated_play_ids=tuple(data["explicitly_narrated_play_ids"]),
        start_clock=data["start_clock"],
        end_clock=data["end_clock"],
        period=data["period"],
        score_before=score_before,
        score_after=score_after,
        narrative=data["narrative"],
    )


def story_from_dict(data: dict) -> StoryV2Output:
    """Construct a StoryV2Output from a dictionary.

    Raises SchemaValidationError if data is malformed or violates contract.
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(f"Expected dict, got {type(data).__name__}")

    if "moments" not in data:
        raise SchemaValidationError("Missing required field: moments")

    extra = set(data.keys()) - {"moments"}
    if extra:
        raise SchemaValidationError(f"Unexpected fields (forbidden): {extra}")

    moments_data = data["moments"]
    if not isinstance(moments_data, (list, tuple)):
        raise SchemaValidationError(
            f"moments must be list or tuple, got {type(moments_data).__name__}"
        )

    moments = tuple(moment_from_dict(m) for m in moments_data)
    return StoryV2Output(moments=moments)
