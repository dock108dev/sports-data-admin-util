"""
Chapter Coverage Validator: Enforces coverage guarantees.

This module provides authoritative validation for chapter coverage,
ensuring no gaps, no overlaps, and deterministic output.

PHASE 1 ISSUE 6: Enforce Chapter Coverage Guarantees

GUARANTEES:
- Every play belongs to exactly one chapter
- No gaps, no overlaps
- Chapters are contiguous and ordered
- Output is deterministic for identical input
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .types import Chapter, GameStory, Play


@dataclass
class CoverageValidationResult:
    """Result of chapter coverage validation.

    Attributes:
        passed: Whether validation passed
        play_count: Total number of plays
        chapter_count: Number of chapters
        chapters_fingerprint: Deterministic fingerprint (sha256)
        errors: List of validation errors (empty if passed)
        metrics: Additional metrics
    """

    passed: bool
    play_count: int
    chapter_count: int
    chapters_fingerprint: str
    errors: list[str]
    metrics: dict[str, Any]

    def __str__(self) -> str:
        """Human-readable summary."""
        if self.passed:
            return (
                f"Coverage: PASS (plays={self.play_count}, "
                f"chapters={self.chapter_count}, "
                f"fingerprint={self.chapters_fingerprint[:16]}...)"
            )
        else:
            return f"Coverage: FAIL ({len(self.errors)} errors)\n" + "\n".join(
                f"  - {err}" for err in self.errors
            )


class CoverageValidationError(Exception):
    """Raised when chapter coverage validation fails."""

    def __init__(self, result: CoverageValidationResult):
        self.result = result
        super().__init__(str(result))


def compute_chapters_fingerprint(chapters: list[Chapter]) -> str:
    """Compute deterministic fingerprint for chapters.

    The fingerprint is a stable hash of:
    - Chapter count
    - Each chapter: (play_start_idx, play_end_idx, sorted(reason_codes))

    This enables determinism verification: same input → same fingerprint.

    Args:
        chapters: List of chapters

    Returns:
        SHA256 hex digest (64 characters)
    """
    # Build canonical representation
    canonical = {
        "chapter_count": len(chapters),
        "chapters": [
            {
                "play_start_idx": ch.play_start_idx,
                "play_end_idx": ch.play_end_idx,
                "reason_codes": sorted(ch.reason_codes),  # Normalize order
            }
            for ch in chapters
        ],
    }

    # Serialize deterministically (sorted keys)
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

    # Hash
    fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return fingerprint


def validate_chapter_coverage(
    chapters: list[Chapter],
    plays: list[Play] | None = None,
    base_index: int = 0,
    fail_fast: bool = True,
) -> CoverageValidationResult:
    """Validate chapter coverage guarantees.

    Validates:
    1. Contiguity: Chapters are contiguous (no gaps between chapters)
    2. No gaps: All play indices covered
    3. No overlaps: No play appears in multiple chapters
    4. Play list consistency: Chapter plays[] matches index range
    5. Deterministic fingerprint

    Args:
        chapters: List of chapters to validate
        plays: Optional list of all plays (for stricter validation)
        base_index: Expected start index (default 0)
        fail_fast: If True, raise exception on first error

    Returns:
        CoverageValidationResult

    Raises:
        CoverageValidationError: If fail_fast=True and validation fails
    """
    errors = []
    metrics = {}

    if not chapters:
        errors.append("No chapters provided")
        result = CoverageValidationResult(
            passed=False,
            play_count=0,
            chapter_count=0,
            chapters_fingerprint="",
            errors=errors,
            metrics=metrics,
        )
        if fail_fast:
            raise CoverageValidationError(result)
        return result

    # Compute fingerprint
    fingerprint = compute_chapters_fingerprint(chapters)

    # Sort chapters by start index (should already be sorted)
    sorted_chapters = sorted(chapters, key=lambda ch: ch.play_start_idx)

    # Check if chapters were out of order
    if sorted_chapters != chapters:
        errors.append(
            "Chapters not sorted by play_start_idx. "
            f"Expected order: {[ch.chapter_id for ch in sorted_chapters]}, "
            f"got: {[ch.chapter_id for ch in chapters]}"
        )

    chapters = sorted_chapters  # Use sorted for validation

    # 1. Validate first chapter starts at base_index
    first_chapter = chapters[0]
    if first_chapter.play_start_idx != base_index:
        errors.append(
            f"First chapter {first_chapter.chapter_id} starts at index "
            f"{first_chapter.play_start_idx}, expected {base_index}"
        )

    # 2. Validate contiguity and no overlaps
    covered_indices = set()

    for i, chapter in enumerate(chapters):
        # Validate chapter internal consistency
        expected_play_count = chapter.play_end_idx - chapter.play_start_idx + 1
        actual_play_count = len(chapter.plays)

        if expected_play_count != actual_play_count:
            errors.append(
                f"Chapter {chapter.chapter_id}: play count mismatch. "
                f"Index range {chapter.play_start_idx}-{chapter.play_end_idx} "
                f"implies {expected_play_count} plays, but plays[] has {actual_play_count}"
            )

        # Check for overlaps
        chapter_indices = set(range(chapter.play_start_idx, chapter.play_end_idx + 1))
        overlap = covered_indices & chapter_indices
        if overlap:
            errors.append(
                f"Chapter {chapter.chapter_id}: overlaps with previous chapters. "
                f"Overlapping indices: {sorted(overlap)}"
            )

        covered_indices.update(chapter_indices)

        # Check contiguity with next chapter
        if i < len(chapters) - 1:
            next_chapter = chapters[i + 1]
            expected_next_start = chapter.play_end_idx + 1
            actual_next_start = next_chapter.play_start_idx

            if actual_next_start != expected_next_start:
                if actual_next_start > expected_next_start:
                    # Gap
                    gap_size = actual_next_start - expected_next_start
                    errors.append(
                        f"Gap between {chapter.chapter_id} and {next_chapter.chapter_id}: "
                        f"{chapter.chapter_id} ends at {chapter.play_end_idx}, "
                        f"{next_chapter.chapter_id} starts at {next_chapter.play_start_idx}. "
                        f"Missing {gap_size} play(s): {list(range(expected_next_start, actual_next_start))}"
                    )
                else:
                    # Overlap (already caught above, but add context)
                    errors.append(
                        f"Overlap between {chapter.chapter_id} and {next_chapter.chapter_id}: "
                        f"{chapter.chapter_id} ends at {chapter.play_end_idx}, "
                        f"{next_chapter.chapter_id} starts at {next_chapter.play_start_idx}"
                    )

    # 3. If plays provided, validate against actual play list
    if plays is not None:
        play_indices = {p.index for p in plays}

        # Check all plays are covered
        missing = play_indices - covered_indices
        if missing:
            errors.append(
                f"Missing play coverage: {len(missing)} plays not in any chapter. "
                f"Indices: {sorted(missing)}"
            )

        # Check no extra indices
        extra = covered_indices - play_indices
        if extra:
            errors.append(
                f"Extra indices in chapters: {len(extra)} indices not in play list. "
                f"Indices: {sorted(extra)}"
            )

        # Validate last chapter ends at last play
        last_chapter = chapters[-1]
        last_play_index = max(play_indices) if play_indices else 0
        if last_chapter.play_end_idx != last_play_index:
            errors.append(
                f"Last chapter {last_chapter.chapter_id} ends at index "
                f"{last_chapter.play_end_idx}, but last play is at index {last_play_index}"
            )

        metrics["play_count"] = len(plays)
        metrics["covered_count"] = len(covered_indices)
        metrics["coverage_ratio"] = len(covered_indices) / len(plays) if plays else 0
    else:
        # Estimate play count from chapters
        if chapters:
            estimated_play_count = (
                chapters[-1].play_end_idx - chapters[0].play_start_idx + 1
            )
            metrics["estimated_play_count"] = estimated_play_count

    # 4. Validate play ordering within chapters
    for chapter in chapters:
        for i in range(len(chapter.plays) - 1):
            curr_play = chapter.plays[i]
            next_play = chapter.plays[i + 1]

            if curr_play.index >= next_play.index:
                errors.append(
                    f"Chapter {chapter.chapter_id}: plays not in order. "
                    f"Play at position {i} has index {curr_play.index}, "
                    f"play at position {i + 1} has index {next_play.index}"
                )
                break  # Only report first ordering error per chapter

    # Build result
    play_count = len(plays) if plays else len(covered_indices)

    result = CoverageValidationResult(
        passed=len(errors) == 0,
        play_count=play_count,
        chapter_count=len(chapters),
        chapters_fingerprint=fingerprint,
        errors=errors,
        metrics=metrics,
    )

    if not result.passed and fail_fast:
        raise CoverageValidationError(result)

    return result


def validate_game_story_coverage(
    story: GameStory, fail_fast: bool = True
) -> CoverageValidationResult:
    """Validate coverage for a complete GameStory.

    Convenience wrapper around validate_chapter_coverage.

    Args:
        story: GameStory to validate
        fail_fast: If True, raise exception on first error

    Returns:
        CoverageValidationResult

    Raises:
        CoverageValidationError: If fail_fast=True and validation fails
    """
    # Extract all plays from chapters
    all_plays = []
    for chapter in story.chapters:
        all_plays.extend(chapter.plays)

    return validate_chapter_coverage(
        chapters=story.chapters, plays=all_plays, base_index=0, fail_fast=fail_fast
    )
