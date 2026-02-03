"""Embedded tweet selection for collapsed game flow.

EMBEDDED TWEET CONTRACT (Phase 4)
=================================
Embedded tweets are the ONLY social elements allowed in the collapsed game flow.
They act as reaction beats, not narrative drivers.

Key principles:
1. OPTIONAL: Story must read correctly with zero embedded tweets
2. LIMITED: Max 5 per game, max 1 per block
3. DETERMINISTIC: Selection is reproducible given same inputs
4. NON-STRUCTURAL: Tweets never create/split blocks

Embedded tweets may enhance pacing but must NEVER:
- Add length to the story
- Compromise the 20-60 second read invariant
- Drive narrative decisions
- Couple to specific plays or moments

Related modules:
- block_types.py: Block structures
- social_events.py: Social post processing
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, Sequence

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Selection limits (Task 4.1)
MIN_EMBEDDED_TWEETS = 0  # Embedded tweets are optional
MAX_EMBEDDED_TWEETS = 5  # Hard cap per game
PREFERRED_MIN_EMBEDDED = 2  # Prefer at least 2 if available
PREFERRED_MAX_EMBEDDED = 5  # Prefer up to 5

# Cap enforcement (Task 4.2)
MAX_TWEETS_PER_BLOCK = 1  # Hard cap: 1 tweet per block


class TweetPosition(str, Enum):
    """Position category for distribution preference."""

    EARLY = "EARLY"  # Opening context (first third)
    MID = "MID"  # Momentum/reaction (middle third)
    LATE = "LATE"  # Resolution/outcome (final third)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class ScoredTweet:
    """A tweet with its computed score and metadata.

    This is the internal representation used during selection.
    The score determines priority when enforcing caps.
    """

    tweet_id: str | int
    posted_at: datetime
    text: str
    author: str
    phase: str  # From Phase 3 classification
    score: float  # Computed by scorer
    position: TweetPosition  # Computed from game position
    has_media: bool = False
    media_type: str | None = None

    # Optional metadata for scoring
    engagement: int = 0
    is_verified: bool = False
    is_team_account: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "tweet_id": self.tweet_id,
            "posted_at": self.posted_at.isoformat(),
            "text": self.text,
            "author": self.author,
            "phase": self.phase,
            "score": self.score,
            "position": self.position.value,
            "has_media": self.has_media,
            "media_type": self.media_type,
        }


@dataclass
class EmbeddedTweetSelection:
    """Result of the embedded tweet selection process.

    Contains selected tweets and metadata about the selection.
    """

    tweets: list[ScoredTweet]
    total_candidates: int
    selection_method: str
    distribution: dict[str, int]  # Position -> count

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "tweets": [t.to_dict() for t in self.tweets],
            "total_candidates": self.total_candidates,
            "selection_method": self.selection_method,
            "distribution": self.distribution,
            "selected_count": len(self.tweets),
        }


@dataclass
class BlockTweetAssignment:
    """Assignment of embedded tweets to narrative blocks.

    This is the result after cap enforcement.
    """

    block_index: int
    tweet: ScoredTweet | None  # None if no tweet assigned

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "block_index": self.block_index,
            "tweet": self.tweet.to_dict() if self.tweet else None,
        }


# =============================================================================
# SCORER PROTOCOL (Pluggable)
# =============================================================================


class TweetScorer(Protocol):
    """Protocol for tweet scoring implementations.

    Scoring must be:
    - Deterministic given the same inputs
    - Independent of play/moment/narrative data
    - Replaceable without changing selection logic
    """

    def score(self, tweet: dict[str, Any]) -> float:
        """Compute a score for a tweet.

        Args:
            tweet: Tweet data dict with fields like text, author, engagement

        Returns:
            Score as float (higher = more likely to be selected)
        """
        ...


class DefaultTweetScorer:
    """Default tweet scorer using simple heuristics.

    This is a placeholder implementation that can be replaced
    with a more sophisticated scoring model.

    Scoring factors (all configurable):
    - Media presence: +2.0
    - Team account: +1.5
    - Verified account: +0.5
    - Engagement (normalized): +0-2.0
    - Text length (sweet spot): +0-1.0
    """

    def __init__(
        self,
        media_weight: float = 2.0,
        team_account_weight: float = 1.5,
        verified_weight: float = 0.5,
        engagement_weight: float = 2.0,
        length_weight: float = 1.0,
    ):
        self.media_weight = media_weight
        self.team_account_weight = team_account_weight
        self.verified_weight = verified_weight
        self.engagement_weight = engagement_weight
        self.length_weight = length_weight

    def score(self, tweet: dict[str, Any]) -> float:
        """Compute score using weighted heuristics."""
        score = 0.0

        # Media presence (images/videos are engaging)
        if tweet.get("has_media") or tweet.get("media_type"):
            score += self.media_weight

        # Team account (authoritative source)
        if tweet.get("is_team_account"):
            score += self.team_account_weight

        # Verified account (credibility)
        if tweet.get("is_verified"):
            score += self.verified_weight

        # Engagement (normalized to 0-1 scale, capped at 1000)
        engagement = tweet.get("engagement", 0)
        if engagement > 0:
            normalized = min(engagement / 1000, 1.0)
            score += normalized * self.engagement_weight

        # Text length (prefer medium-length tweets: 50-150 chars)
        text = tweet.get("text", "")
        text_len = len(text) if text else 0
        if 50 <= text_len <= 150:
            score += self.length_weight
        elif 30 <= text_len <= 200:
            score += self.length_weight * 0.5

        return score


# =============================================================================
# POSITION CLASSIFICATION
# =============================================================================


def classify_tweet_position(
    posted_at: datetime,
    game_start: datetime,
    estimated_duration_minutes: int = 150,
) -> TweetPosition:
    """Classify a tweet's position within the game.

    Divides game into thirds for distribution preference:
    - EARLY: First third of game
    - MID: Middle third
    - LATE: Final third

    Args:
        posted_at: When the tweet was posted
        game_start: Game start time
        estimated_duration_minutes: Estimated game length

    Returns:
        TweetPosition enum value
    """
    elapsed = (posted_at - game_start).total_seconds()
    duration_seconds = estimated_duration_minutes * 60

    if elapsed < 0:
        # Pregame tweets count as EARLY
        return TweetPosition.EARLY

    ratio = elapsed / duration_seconds if duration_seconds > 0 else 0

    if ratio < 0.33:
        return TweetPosition.EARLY
    elif ratio < 0.67:
        return TweetPosition.MID
    else:
        return TweetPosition.LATE


# =============================================================================
# TASK 4.1: EMBEDDED TWEET SELECTION
# =============================================================================


def select_embedded_tweets(
    tweets: Sequence[dict[str, Any]],
    game_start: datetime,
    estimated_duration_minutes: int = 150,
    scorer: TweetScorer | None = None,
    max_tweets: int = MAX_EMBEDDED_TWEETS,
) -> EmbeddedTweetSelection:
    """Select high-signal tweets for embedded display.

    Task 4.1: Select 2-5 embedded tweets maximum.

    Selection algorithm:
    1. Score all tweets using the scorer
    2. Classify position (EARLY/MID/LATE)
    3. Sort by score descending
    4. Select top tweets with distribution preference

    Distribution preference:
    - Try to include tweets from each position (EARLY, MID, LATE)
    - Fall back to highest scores if distribution isn't possible

    Args:
        tweets: List of tweet dicts to select from
        game_start: Game start time for position classification
        estimated_duration_minutes: Estimated game length
        scorer: Tweet scorer (uses DefaultTweetScorer if None)
        max_tweets: Maximum tweets to select (default 5)

    Returns:
        EmbeddedTweetSelection with selected tweets
    """
    if scorer is None:
        scorer = DefaultTweetScorer()

    # Clamp max_tweets to hard cap
    max_tweets = min(max_tweets, MAX_EMBEDDED_TWEETS)

    # Handle empty input
    if not tweets:
        return EmbeddedTweetSelection(
            tweets=[],
            total_candidates=0,
            selection_method="none",
            distribution={},
        )

    # Score and classify all tweets
    scored_tweets: list[ScoredTweet] = []
    for tweet in tweets:
        # Skip tweets with empty text
        text = tweet.get("text", "")
        if not text or not text.strip():
            continue

        # Parse posted_at
        posted_at = tweet.get("posted_at")
        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif not isinstance(posted_at, datetime):
            continue

        score = scorer.score(tweet)
        position = classify_tweet_position(
            posted_at, game_start, estimated_duration_minutes
        )

        scored_tweet = ScoredTweet(
            tweet_id=tweet.get("id") or tweet.get("tweet_id", ""),
            posted_at=posted_at,
            text=text,
            author=tweet.get("author") or tweet.get("source_handle", ""),
            phase=tweet.get("phase", "unknown"),
            score=score,
            position=position,
            has_media=bool(tweet.get("has_media") or tweet.get("media_type")),
            media_type=tweet.get("media_type"),
            engagement=tweet.get("engagement", 0),
            is_verified=tweet.get("is_verified", False),
            is_team_account=tweet.get("is_team_account", False),
        )
        scored_tweets.append(scored_tweet)

    total_candidates = len(scored_tweets)

    # If fewer than preferred minimum, return all available
    if len(scored_tweets) <= PREFERRED_MIN_EMBEDDED:
        # Sort by time for determinism
        scored_tweets.sort(key=lambda t: t.posted_at)
        distribution = _compute_distribution(scored_tweets)
        return EmbeddedTweetSelection(
            tweets=scored_tweets,
            total_candidates=total_candidates,
            selection_method="all_available",
            distribution=distribution,
        )

    # Select with distribution preference
    selected = _select_with_distribution(scored_tweets, max_tweets)

    # Sort selected by time for deterministic ordering
    selected.sort(key=lambda t: t.posted_at)

    distribution = _compute_distribution(selected)

    return EmbeddedTweetSelection(
        tweets=selected,
        total_candidates=total_candidates,
        selection_method="distributed_score",
        distribution=distribution,
    )


def _select_with_distribution(
    tweets: list[ScoredTweet],
    max_count: int,
) -> list[ScoredTweet]:
    """Select tweets with distribution preference across positions.

    Tries to include at least one tweet from each position (EARLY, MID, LATE)
    if available, then fills remaining slots by score.

    Args:
        tweets: Scored tweets to select from
        max_count: Maximum number to select

    Returns:
        List of selected tweets
    """
    # Group by position
    by_position: dict[TweetPosition, list[ScoredTweet]] = {
        TweetPosition.EARLY: [],
        TweetPosition.MID: [],
        TweetPosition.LATE: [],
    }
    for tweet in tweets:
        by_position[tweet.position].append(tweet)

    # Sort each group by score descending
    for position in by_position:
        by_position[position].sort(key=lambda t: t.score, reverse=True)

    selected: list[ScoredTweet] = []
    used_ids: set[str | int] = set()

    # Phase 1: Pick best from each position (distribution preference)
    for position in [TweetPosition.EARLY, TweetPosition.MID, TweetPosition.LATE]:
        if len(selected) >= max_count:
            break
        if by_position[position]:
            top = by_position[position][0]
            selected.append(top)
            used_ids.add(top.tweet_id)

    # Phase 2: Fill remaining slots with highest scores
    if len(selected) < max_count:
        # Combine remaining tweets from all positions
        remaining = [
            t for t in tweets if t.tweet_id not in used_ids
        ]
        remaining.sort(key=lambda t: t.score, reverse=True)

        for tweet in remaining:
            if len(selected) >= max_count:
                break
            selected.append(tweet)
            used_ids.add(tweet.tweet_id)

    return selected


def _compute_distribution(tweets: list[ScoredTweet]) -> dict[str, int]:
    """Compute position distribution of selected tweets."""
    distribution: dict[str, int] = {
        TweetPosition.EARLY.value: 0,
        TweetPosition.MID.value: 0,
        TweetPosition.LATE.value: 0,
    }
    for tweet in tweets:
        distribution[tweet.position.value] += 1
    return distribution


# =============================================================================
# TASK 4.2: HARD CAP ENFORCEMENT
# =============================================================================


def enforce_embedded_caps(
    selected_tweets: list[ScoredTweet],
    block_count: int,
) -> list[BlockTweetAssignment]:
    """Enforce hard caps on embedded tweets.

    Task 4.2 hard rules:
    - Max 1 embedded tweet per block
    - Max 5 embedded tweets per game
    - Tweets never create/split blocks

    Algorithm:
    1. Limit tweets to min(block_count, MAX_EMBEDDED_TWEETS)
    2. Assign highest-scored tweets to blocks by position affinity
    3. Each block gets at most 1 tweet

    Args:
        selected_tweets: Pre-selected tweets (from select_embedded_tweets)
        block_count: Number of narrative blocks

    Returns:
        List of BlockTweetAssignment (one per block)
    """
    # Initialize assignments (one per block, all None initially)
    assignments: list[BlockTweetAssignment] = [
        BlockTweetAssignment(block_index=i, tweet=None)
        for i in range(block_count)
    ]

    if not selected_tweets or block_count == 0:
        return assignments

    # Enforce hard caps
    max_assignable = min(block_count, MAX_EMBEDDED_TWEETS, len(selected_tweets))

    # Sort tweets by score descending for priority
    sorted_tweets = sorted(selected_tweets, key=lambda t: t.score, reverse=True)

    # Take only top max_assignable tweets
    tweets_to_assign = sorted_tweets[:max_assignable]

    # Assign tweets to blocks based on position affinity
    # EARLY -> first blocks, MID -> middle blocks, LATE -> last blocks
    assigned_blocks: set[int] = set()
    assigned_tweets: set[str | int] = set()

    for tweet in tweets_to_assign:
        if len(assigned_blocks) >= block_count:
            break

        # Find best block for this tweet's position
        target_block = _find_target_block(
            tweet.position,
            block_count,
            assigned_blocks,
        )

        if target_block is not None:
            assignments[target_block] = BlockTweetAssignment(
                block_index=target_block,
                tweet=tweet,
            )
            assigned_blocks.add(target_block)
            assigned_tweets.add(tweet.tweet_id)

    logger.info(
        "embedded_tweets_assigned",
        extra={
            "block_count": block_count,
            "tweets_available": len(selected_tweets),
            "tweets_assigned": len(assigned_blocks),
            "max_assignable": max_assignable,
        },
    )

    return assignments


def _find_target_block(
    position: TweetPosition,
    block_count: int,
    assigned_blocks: set[int],
) -> int | None:
    """Find the best block index for a tweet's position.

    Position mapping:
    - EARLY: Prefer first third of blocks
    - MID: Prefer middle third of blocks
    - LATE: Prefer last third of blocks

    Falls back to any available block if preferred range is full.

    Args:
        position: Tweet position (EARLY/MID/LATE)
        block_count: Total number of blocks
        assigned_blocks: Already assigned block indices

    Returns:
        Best available block index, or None if all assigned
    """
    if block_count == 0:
        return None

    # Calculate preferred ranges
    third = block_count / 3

    if position == TweetPosition.EARLY:
        preferred_start = 0
        preferred_end = max(1, int(third))
    elif position == TweetPosition.MID:
        preferred_start = max(1, int(third))
        preferred_end = min(block_count, int(2 * third) + 1)
    else:  # LATE
        preferred_start = max(0, int(2 * third))
        preferred_end = block_count

    # Try preferred range first
    for i in range(preferred_start, preferred_end):
        if i not in assigned_blocks:
            return i

    # Fall back to any available block
    for i in range(block_count):
        if i not in assigned_blocks:
            return i

    return None


def apply_embedded_tweets_to_blocks(
    blocks: list[dict[str, Any]],
    assignments: list[BlockTweetAssignment],
) -> list[dict[str, Any]]:
    """Apply embedded tweet assignments to block dicts.

    Adds an 'embedded_tweet' field to each block if assigned.
    Does NOT modify block structure (no splitting, no new blocks).

    Args:
        blocks: List of block dicts
        assignments: Tweet assignments from enforce_embedded_caps

    Returns:
        Updated blocks with embedded_tweet fields
    """
    # Create a map of block_index -> tweet
    tweet_map: dict[int, ScoredTweet | None] = {
        a.block_index: a.tweet for a in assignments
    }

    updated_blocks = []
    for block in blocks:
        block_copy = dict(block)
        block_index = block_copy.get("block_index", 0)

        tweet = tweet_map.get(block_index)
        if tweet:
            block_copy["embedded_tweet"] = tweet.to_dict()
        else:
            block_copy["embedded_tweet"] = None

        updated_blocks.append(block_copy)

    return updated_blocks


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def select_and_assign_embedded_tweets(
    tweets: Sequence[dict[str, Any]],
    blocks: list[dict[str, Any]],
    game_start: datetime,
    estimated_duration_minutes: int = 150,
    scorer: TweetScorer | None = None,
) -> tuple[list[dict[str, Any]], EmbeddedTweetSelection]:
    """Complete embedded tweet pipeline: select, cap, and assign.

    Convenience function that combines:
    1. select_embedded_tweets (Task 4.1)
    2. enforce_embedded_caps (Task 4.2)
    3. apply_embedded_tweets_to_blocks

    Args:
        tweets: Available tweets to select from
        blocks: Narrative blocks to assign tweets to
        game_start: Game start time
        estimated_duration_minutes: Estimated game length
        scorer: Optional custom scorer

    Returns:
        Tuple of (updated_blocks, selection_result)
    """
    # Task 4.1: Select embedded tweets
    selection = select_embedded_tweets(
        tweets,
        game_start,
        estimated_duration_minutes,
        scorer,
    )

    # Task 4.2: Enforce caps and assign to blocks
    assignments = enforce_embedded_caps(
        selection.tweets,
        len(blocks),
    )

    # Apply to blocks
    updated_blocks = apply_embedded_tweets_to_blocks(blocks, assignments)

    return updated_blocks, selection
