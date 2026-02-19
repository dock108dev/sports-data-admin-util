"""Embedded tweet selection for collapsed game flow.

EMBEDDED TWEET CONTRACT
=======================
Embedded tweets are the ONLY social elements allowed in the collapsed game flow.
They act as reaction beats, not narrative drivers.

Key principles:
1. OPTIONAL: Flow must read correctly with zero embedded tweets
2. LIMITED: Max 5 per game, max 1 per block
3. DETERMINISTIC: Selection is reproducible given same inputs
4. NON-STRUCTURAL: Tweets never create/split blocks

Embedded tweets may enhance pacing but must NEVER:
- Add length to the flow
- Compromise the 20-60 second read invariant
- Drive narrative decisions
- Couple to specific plays or moments

Related modules:
- block_types.py: Block structures
- social_events.py: Social post processing
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import select

if TYPE_CHECKING:
    from ....db import AsyncSession

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Selection limits
MIN_EMBEDDED_TWEETS = 0  # Embedded tweets are optional
MAX_EMBEDDED_TWEETS = 5  # Hard cap per game
PREFERRED_MIN_EMBEDDED = 2  # Prefer at least 2 if available
PREFERRED_MAX_EMBEDDED = 5  # Prefer up to 5

# Cap enforcement
MAX_TWEETS_PER_BLOCK = 1  # Hard cap: 1 tweet per block


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class ScoredTweet:
    """A tweet with its computed score and metadata.

    This is the internal representation used during selection.
    The score determines priority when enforcing caps.
    """

    tweet_id: int
    posted_at: datetime
    text: str
    author: str
    phase: str
    score: float  # Computed by scorer
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

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "tweets": [t.to_dict() for t in self.tweets],
            "total_candidates": self.total_candidates,
            "selection_method": self.selection_method,
            "selected_count": len(self.tweets),
        }


@dataclass
class BlockTweetAssignment:
    """Assignment of embedded tweets to narrative blocks.

    Each block gets at most one display tweet (highest-scored temporal match)
    plus additional tweets for consuming apps to use as context.
    """

    block_index: int
    tweet: ScoredTweet | None  # Best tweet for display (None if no match)
    additional_tweets: list[ScoredTweet] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "block_index": self.block_index,
            "tweet": self.tweet.to_dict() if self.tweet else None,
            "additional_tweets": [t.to_dict() for t in self.additional_tweets],
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
# TEMPORAL BLOCK MATCHING
# =============================================================================


def _period_real_start(game_start: datetime, period: int, league_code: str) -> datetime:
    """Dispatch to league-specific period start calculator.

    Args:
        game_start: Tip-off / puck-drop time.
        period: 1-based period number.
        league_code: "NBA", "NHL", or "NCAAB".
    """
    from ....services.timeline_phases import nba_quarter_start, ncaab_period_start, nhl_period_start

    if league_code == "NHL":
        return nhl_period_start(game_start, period)
    if league_code == "NCAAB":
        return ncaab_period_start(game_start, period)
    return nba_quarter_start(game_start, period)


def assign_tweets_to_blocks_by_time(
    scored_tweets: list[ScoredTweet],
    blocks: list[dict[str, Any]],
    game_start: datetime,
    league_code: str,
) -> list[BlockTweetAssignment]:
    """Assign tweets to blocks by temporal matching.

    For each block, compute its real-time window from period_start.
    When multiple blocks share the same period_start, the period's
    real-time window is subdivided evenly so tweets distribute across
    all blocks rather than collapsing to the last one.

    Per block: highest-scored tweet becomes the display tweet,
    remaining matches go into additional_tweets.

    After assignment, enforces MAX_EMBEDDED_TWEETS global cap:
    if more than 5 blocks have display tweets, only the top 5 by
    score are kept; the rest are demoted to additional_tweets.
    """
    if not blocks:
        return []

    # 1. Compute block time window starts (ordered by window_start, block_index)
    block_starts: list[tuple[int, datetime]] = []
    for block in blocks:
        idx = block.get("block_index", len(block_starts))
        period = block.get("period_start", 1)
        window_start = _period_real_start(game_start, period, league_code)
        block_starts.append((idx, window_start))
    block_starts.sort(key=lambda x: (x[1], x[0]))

    # 2. Subdivide when blocks share the same window_start
    groups: list[list[tuple[int, datetime]]] = []
    for entry in block_starts:
        if not groups or entry[1] != groups[-1][0][1]:
            groups.append([entry])
        else:
            groups[-1].append(entry)

    max_period = max(block.get("period_start", 1) for block in blocks)
    final_end = _period_real_start(game_start, max_period + 1, league_code)

    subdivided: list[tuple[int, datetime]] = []
    for g_idx, group in enumerate(groups):
        if len(group) == 1:
            subdivided.append(group[0])
            continue
        group_start = group[0][1]
        group_end = groups[g_idx + 1][0][1] if g_idx + 1 < len(groups) else final_end
        span = (group_end - group_start).total_seconds()
        for k, (block_idx, _) in enumerate(group):
            sub_start = group_start + timedelta(seconds=k * span / len(group))
            subdivided.append((block_idx, sub_start))

    subdivided.sort(key=lambda x: (x[1], x[0]))

    # 3. Match each tweet to the last block whose start <= posted_at
    block_tweets: dict[int, list[ScoredTweet]] = {bs[0]: [] for bs in subdivided}
    for tweet in scored_tweets:
        target: int | None = None
        for block_idx, window_start in subdivided:
            if tweet.posted_at >= window_start:
                target = block_idx
            else:
                break
        if target is not None:
            block_tweets[target].append(tweet)

    # 4. Per block, pick highest-scored tweet as display, rest as additional
    assignments = [
        BlockTweetAssignment(block_index=i, tweet=None)
        for i in range(len(blocks))
    ]
    for block_idx, tweets in block_tweets.items():
        if not tweets:
            continue
        ranked = sorted(tweets, key=lambda t: t.score, reverse=True)
        assignments[block_idx] = BlockTweetAssignment(
            block_index=block_idx,
            tweet=ranked[0],
            additional_tweets=ranked[1:],
        )

    # 5. Enforce global cap: at most MAX_EMBEDDED_TWEETS blocks with display tweets
    display_blocks = [
        (a.block_index, a.tweet.score) for a in assignments if a.tweet is not None
    ]
    if len(display_blocks) > MAX_EMBEDDED_TWEETS:
        display_blocks.sort(key=lambda x: x[1], reverse=True)
        demoted_indices = {bi for bi, _ in display_blocks[MAX_EMBEDDED_TWEETS:]}
        for a in assignments:
            if a.block_index in demoted_indices and a.tweet is not None:
                a.additional_tweets.insert(0, a.tweet)
                a.tweet = None

    return assignments


# =============================================================================
# EMBEDDED TWEET SELECTION
# =============================================================================


def select_embedded_tweets(
    tweets: Sequence[dict[str, Any]],
    game_start: datetime,
    scorer: TweetScorer | None = None,
) -> EmbeddedTweetSelection:
    """Score all candidate tweets for embedded display.

    Scores every tweet and returns them sorted by posted_at.
    Actual block assignment is handled by assign_tweets_to_blocks_by_time.

    Args:
        tweets: List of tweet dicts to select from
        game_start: Game start time
        scorer: Tweet scorer (uses DefaultTweetScorer if None)

    Returns:
        EmbeddedTweetSelection with all scored tweets
    """
    if scorer is None:
        scorer = DefaultTweetScorer()

    # Handle empty input
    if not tweets:
        return EmbeddedTweetSelection(
            tweets=[],
            total_candidates=0,
            selection_method="none",
        )

    # Score all tweets
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

        raw_id = tweet.get("id") or tweet.get("tweet_id")
        if raw_id is None:
            continue
        try:
            tweet_id = int(raw_id)
        except (ValueError, TypeError):
            continue

        score = scorer.score(tweet)

        scored_tweet = ScoredTweet(
            tweet_id=tweet_id,
            posted_at=posted_at,
            text=text,
            author=tweet.get("author") or tweet.get("source_handle", ""),
            phase=tweet.get("phase", "unknown"),
            score=score,
            has_media=bool(tweet.get("has_media") or tweet.get("media_type")),
            media_type=tweet.get("media_type"),
            engagement=tweet.get("engagement", 0),
            is_verified=tweet.get("is_verified", False),
            is_team_account=tweet.get("is_team_account", False),
        )
        scored_tweets.append(scored_tweet)

    total_candidates = len(scored_tweets)

    # Sort by time for deterministic ordering
    scored_tweets.sort(key=lambda t: t.posted_at)

    return EmbeddedTweetSelection(
        tweets=scored_tweets,
        total_candidates=total_candidates,
        selection_method="scored",
    )


def apply_embedded_tweets_to_blocks(
    blocks: list[dict[str, Any]],
    assignments: list[BlockTweetAssignment],
) -> list[dict[str, Any]]:
    """Apply embedded tweet assignments to block dicts.

    Sets embedded_social_post_id (display tweet) and
    additional_social_post_ids (extra context) on each block.
    Does NOT modify block structure (no splitting, no new blocks).

    Args:
        blocks: List of block dicts
        assignments: Tweet assignments from assign_tweets_to_blocks_by_time

    Returns:
        Updated blocks with embedded tweet fields
    """
    # Create a map of block_index -> assignment
    assignment_map: dict[int, BlockTweetAssignment] = {
        a.block_index: a for a in assignments
    }

    updated_blocks = []
    for block in blocks:
        block_copy = dict(block)
        block_index = block_copy.get("block_index", 0)

        assignment = assignment_map.get(block_index)
        if assignment and assignment.tweet:
            block_copy["embedded_social_post_id"] = assignment.tweet.tweet_id
            block_copy["additional_social_post_ids"] = [
                t.tweet_id for t in assignment.additional_tweets
            ]
        else:
            block_copy["embedded_social_post_id"] = None
            block_copy["additional_social_post_ids"] = []

        updated_blocks.append(block_copy)

    return updated_blocks


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def select_and_assign_embedded_tweets(
    tweets: Sequence[dict[str, Any]],
    blocks: list[dict[str, Any]],
    game_start: datetime,
    league_code: str = "NBA",
    scorer: TweetScorer | None = None,
) -> tuple[list[dict[str, Any]], EmbeddedTweetSelection]:
    """Complete embedded tweet pipeline: score and assign by temporal match.

    Convenience function that combines:
    1. select_embedded_tweets — score all candidates
    2. assign_tweets_to_blocks_by_time — temporal block matching
    3. apply_embedded_tweets_to_blocks — write IDs onto block dicts

    Args:
        tweets: Available tweets to select from
        blocks: Narrative blocks to assign tweets to
        game_start: Game start time
        league_code: League code for period timing ("NBA", "NHL", "NCAAB")
        scorer: Optional custom scorer

    Returns:
        Tuple of (updated_blocks, selection_result)
    """
    # Score all tweets
    selection = select_embedded_tweets(tweets, game_start, scorer)

    # Assign to blocks by temporal matching
    assignments = assign_tweets_to_blocks_by_time(
        selection.tweets, blocks, game_start, league_code
    )

    # Apply to blocks
    updated_blocks = apply_embedded_tweets_to_blocks(blocks, assignments)

    return updated_blocks, selection


# =============================================================================
# SHARED SSOT: Load + Attach (used by pipeline and backfill)
# =============================================================================


async def load_and_attach_embedded_tweets(
    session: AsyncSession,
    game_id: int,
    blocks: list[dict[str, Any]],
    league_code: str = "NBA",
    scorer: TweetScorer | None = None,
) -> tuple[list[dict[str, Any]], EmbeddedTweetSelection | None]:
    """Load social posts for a game and attach to blocks.

    Single source of truth called from both:
    - validate_blocks._attach_embedded_tweets (pipeline path)
    - backfill_embedded_tweets.backfill_embedded_tweets_for_game (backfill path)

    Args:
        session: Async database session.
        game_id: Game ID to load social posts for.
        blocks: Blocks to attach tweets to.
        league_code: League code for period timing.
        scorer: Optional custom scorer.

    Returns:
        Tuple of (updated blocks, EmbeddedTweetSelection or None).
    """
    from ....db.social import TeamSocialPost
    from ....db.sports import SportsGame

    # Load game for tip_time
    game_result = await session.execute(
        select(SportsGame).where(SportsGame.id == game_id)
    )
    game = game_result.scalar_one_or_none()

    if not game:
        logger.debug("load_and_attach_no_game", extra={"game_id": game_id})
        return blocks, None

    game_start = game.tip_time or game.game_date
    if game_start and game_start.tzinfo is None:
        game_start = game_start.replace(tzinfo=UTC)

    # Load mapped social posts
    social_result = await session.execute(
        select(TeamSocialPost)
        .where(
            TeamSocialPost.game_id == game_id,
            TeamSocialPost.mapping_status == "mapped",
        )
        .order_by(TeamSocialPost.posted_at)
    )
    social_posts = social_result.scalars().all()

    if not social_posts:
        return blocks, None

    # Convert to dict format and filter to in_game only
    tweets: list[dict[str, Any]] = []
    for post in social_posts:
        if not post.tweet_text:
            continue
        tweets.append({
            "id": post.id,
            "posted_at": post.posted_at,
            "text": post.tweet_text,
            "author": post.source_handle or "",
            "phase": post.game_phase or "in_game",
            "has_media": post.has_video or bool(post.image_url),
            "media_type": post.media_type,
            "post_url": post.post_url,
            "is_team_account": bool(post.source_handle),
        })

    tweets = [t for t in tweets if t["phase"] == "in_game"]

    if not tweets:
        return blocks, None

    updated_blocks, selection = select_and_assign_embedded_tweets(
        tweets=tweets,
        blocks=blocks,
        game_start=game_start,
        league_code=league_code,
        scorer=scorer,
    )
    return updated_blocks, selection
