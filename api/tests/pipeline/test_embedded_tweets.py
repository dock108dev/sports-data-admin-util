"""Tests for Phase 4: Embedded tweet selection and cap enforcement.

Tests the embedded tweet selection (Task 4.1) and hard cap enforcement (Task 4.2)
implemented in embedded_tweets.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.pipeline.stages.embedded_tweets import (
    # Constants
    MAX_EMBEDDED_TWEETS,
    MAX_TWEETS_PER_BLOCK,
    MIN_EMBEDDED_TWEETS,
    TweetPosition,
    ScoredTweet,
    BlockTweetAssignment,
    # Scorer
    DefaultTweetScorer,
    # Functions
    classify_tweet_position,
    select_embedded_tweets,
    enforce_embedded_caps,
    apply_embedded_tweets_to_blocks,
    select_and_assign_embedded_tweets,
)


@pytest.fixture
def game_start() -> datetime:
    """Sample game start time."""
    return datetime(2026, 1, 15, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_tweets(game_start: datetime) -> list[dict]:
    """Sample tweets for testing."""
    return [
        {
            "id": "tweet_1",
            "text": "Game time! Let's go Lakers!",
            "author": "lakers",
            "posted_at": game_start + timedelta(minutes=5),
            "phase": "q1",
            "has_media": False,
            "is_team_account": True,
            "engagement": 500,
        },
        {
            "id": "tweet_2",
            "text": "Huge three pointer by LeBron! This is getting exciting!",
            "author": "espn",
            "posted_at": game_start + timedelta(minutes=45),
            "phase": "q2",
            "has_media": True,
            "is_verified": True,
            "engagement": 1200,
        },
        {
            "id": "tweet_3",
            "text": "Halftime: Lakers lead by 8.",
            "author": "lakers",
            "posted_at": game_start + timedelta(minutes=75),
            "phase": "halftime",
            "is_team_account": True,
            "engagement": 300,
        },
        {
            "id": "tweet_4",
            "text": "Big run in the third quarter!",
            "author": "nbareporter",
            "posted_at": game_start + timedelta(minutes=100),
            "phase": "q3",
            "engagement": 200,
        },
        {
            "id": "tweet_5",
            "text": "Down to the wire! Celtics within 2.",
            "author": "celtics",
            "posted_at": game_start + timedelta(minutes=140),
            "phase": "q4",
            "has_media": True,
            "is_team_account": True,
            "engagement": 800,
        },
        {
            "id": "tweet_6",
            "text": "Final: Lakers 112, Celtics 108. What a game!",
            "author": "nba",
            "posted_at": game_start + timedelta(minutes=155),
            "phase": "postgame",
            "is_verified": True,
            "engagement": 2000,
        },
    ]


@pytest.fixture
def sample_blocks() -> list[dict]:
    """Sample blocks for testing."""
    return [
        {"block_index": 0, "role": "SETUP", "narrative": "Game started..."},
        {"block_index": 1, "role": "MOMENTUM_SHIFT", "narrative": "Lakers took control..."},
        {"block_index": 2, "role": "RESPONSE", "narrative": "Celtics fought back..."},
        {"block_index": 3, "role": "DECISION_POINT", "narrative": "Critical sequence..."},
        {"block_index": 4, "role": "RESOLUTION", "narrative": "Lakers held on..."},
    ]


class TestConstants:
    """Tests for module constants."""

    def test_max_embedded_tweets(self):
        """Max embedded tweets is 5."""
        assert MAX_EMBEDDED_TWEETS == 5

    def test_max_tweets_per_block(self):
        """Max tweets per block is 1."""
        assert MAX_TWEETS_PER_BLOCK == 1

    def test_min_embedded_tweets(self):
        """Min embedded tweets is 0 (optional)."""
        assert MIN_EMBEDDED_TWEETS == 0


class TestTweetPosition:
    """Tests for TweetPosition enum."""

    def test_position_values(self):
        """Position enum has expected values."""
        assert TweetPosition.EARLY.value == "EARLY"
        assert TweetPosition.MID.value == "MID"
        assert TweetPosition.LATE.value == "LATE"


class TestClassifyTweetPosition:
    """Tests for classify_tweet_position function."""

    def test_early_position(self, game_start):
        """Tweet in first third is EARLY."""
        tweet_time = game_start + timedelta(minutes=20)
        position = classify_tweet_position(tweet_time, game_start, 150)
        assert position == TweetPosition.EARLY

    def test_mid_position(self, game_start):
        """Tweet in middle third is MID."""
        tweet_time = game_start + timedelta(minutes=75)
        position = classify_tweet_position(tweet_time, game_start, 150)
        assert position == TweetPosition.MID

    def test_late_position(self, game_start):
        """Tweet in final third is LATE."""
        tweet_time = game_start + timedelta(minutes=120)
        position = classify_tweet_position(tweet_time, game_start, 150)
        assert position == TweetPosition.LATE

    def test_pregame_is_early(self, game_start):
        """Pregame tweets count as EARLY."""
        tweet_time = game_start - timedelta(minutes=30)
        position = classify_tweet_position(tweet_time, game_start, 150)
        assert position == TweetPosition.EARLY


class TestDefaultTweetScorer:
    """Tests for DefaultTweetScorer."""

    def test_media_increases_score(self):
        """Media presence increases score."""
        scorer = DefaultTweetScorer()
        with_media = {"text": "Test", "has_media": True}
        without_media = {"text": "Test", "has_media": False}

        assert scorer.score(with_media) > scorer.score(without_media)

    def test_team_account_increases_score(self):
        """Team account increases score."""
        scorer = DefaultTweetScorer()
        team = {"text": "Test", "is_team_account": True}
        not_team = {"text": "Test", "is_team_account": False}

        assert scorer.score(team) > scorer.score(not_team)

    def test_engagement_increases_score(self):
        """Higher engagement increases score."""
        scorer = DefaultTweetScorer()
        high_engagement = {"text": "Test", "engagement": 1000}
        low_engagement = {"text": "Test", "engagement": 100}

        assert scorer.score(high_engagement) > scorer.score(low_engagement)

    def test_optimal_text_length_increases_score(self):
        """Optimal text length (50-150 chars) increases score."""
        scorer = DefaultTweetScorer()
        optimal = {"text": "A" * 100}  # 100 chars
        too_short = {"text": "A" * 20}  # 20 chars
        too_long = {"text": "A" * 300}  # 300 chars

        assert scorer.score(optimal) > scorer.score(too_short)
        assert scorer.score(optimal) > scorer.score(too_long)


class TestSelectEmbeddedTweets:
    """Tests for select_embedded_tweets function (Task 4.1)."""

    def test_empty_input_returns_empty(self, game_start):
        """Empty input returns empty selection."""
        result = select_embedded_tweets([], game_start)
        assert len(result.tweets) == 0
        assert result.total_candidates == 0

    def test_selects_up_to_max(self, game_start, sample_tweets):
        """Selects at most MAX_EMBEDDED_TWEETS."""
        result = select_embedded_tweets(sample_tweets, game_start)
        assert len(result.tweets) <= MAX_EMBEDDED_TWEETS

    def test_fewer_than_min_selects_all(self, game_start):
        """If fewer than preferred minimum, selects all."""
        single_tweet = [
            {
                "id": "1",
                "text": "Test tweet",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=10),
                "phase": "q1",
            }
        ]
        result = select_embedded_tweets(single_tweet, game_start)
        assert len(result.tweets) == 1
        assert result.selection_method == "all_available"

    def test_distribution_preference(self, game_start, sample_tweets):
        """Selection prefers distribution across positions."""
        result = select_embedded_tweets(sample_tweets, game_start)

        # Should have tweets from different positions
        positions = {t.position for t in result.tweets}
        # With 6 tweets spanning the game, should get variety
        assert len(positions) >= 2

    def test_deterministic_ordering(self, game_start, sample_tweets):
        """Selection is deterministic (same inputs = same outputs)."""
        result1 = select_embedded_tweets(sample_tweets, game_start)
        result2 = select_embedded_tweets(sample_tweets, game_start)

        assert len(result1.tweets) == len(result2.tweets)
        for t1, t2 in zip(result1.tweets, result2.tweets):
            assert t1.tweet_id == t2.tweet_id

    def test_skips_empty_text(self, game_start):
        """Skips tweets with empty text."""
        tweets = [
            {
                "id": "1",
                "text": "",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=10),
            },
            {
                "id": "2",
                "text": "Valid tweet",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=20),
            },
        ]
        result = select_embedded_tweets(tweets, game_start)
        assert len(result.tweets) == 1
        assert result.tweets[0].tweet_id == "2"

    def test_custom_scorer(self, game_start, sample_tweets):
        """Custom scorer is used when provided."""

        class AlwaysZeroScorer:
            def score(self, tweet):
                return 0.0

        result = select_embedded_tweets(
            sample_tweets, game_start, scorer=AlwaysZeroScorer()
        )
        # Should still select tweets (score doesn't prevent selection)
        assert len(result.tweets) > 0


class TestEnforceEmbeddedCaps:
    """Tests for enforce_embedded_caps function (Task 4.2)."""

    def test_max_one_per_block(self, game_start, sample_tweets):
        """Enforces max 1 tweet per block."""
        selection = select_embedded_tweets(sample_tweets, game_start)
        assignments = enforce_embedded_caps(selection.tweets, block_count=3)

        # Each block should have at most 1 tweet
        tweets_per_block = sum(1 for a in assignments if a.tweet is not None)
        assert tweets_per_block <= 3

    def test_max_five_per_game(self, game_start):
        """Enforces max 5 tweets per game even with more blocks."""
        # Create many tweets
        many_tweets = [
            ScoredTweet(
                tweet_id=f"t{i}",
                posted_at=game_start + timedelta(minutes=i * 10),
                text=f"Tweet {i}",
                author="test",
                phase="q1",
                score=float(i),
                position=TweetPosition.MID,
            )
            for i in range(10)
        ]

        # 10 blocks available
        assignments = enforce_embedded_caps(many_tweets, block_count=10)

        # Only 5 should be assigned
        assigned_count = sum(1 for a in assignments if a.tweet is not None)
        assert assigned_count <= MAX_EMBEDDED_TWEETS

    def test_fewer_blocks_than_tweets(self, game_start):
        """With fewer blocks than tweets, limits to block count."""
        tweets = [
            ScoredTweet(
                tweet_id=f"t{i}",
                posted_at=game_start + timedelta(minutes=i * 10),
                text=f"Tweet {i}",
                author="test",
                phase="q1",
                score=float(i),
                position=TweetPosition.MID,
            )
            for i in range(5)
        ]

        # Only 3 blocks
        assignments = enforce_embedded_caps(tweets, block_count=3)

        assigned_count = sum(1 for a in assignments if a.tweet is not None)
        assert assigned_count <= 3

    def test_empty_tweets_returns_empty_assignments(self):
        """Empty tweets returns all-None assignments."""
        assignments = enforce_embedded_caps([], block_count=5)

        assert len(assignments) == 5
        assert all(a.tweet is None for a in assignments)

    def test_zero_blocks_returns_empty(self, game_start):
        """Zero blocks returns empty list."""
        tweets = [
            ScoredTweet(
                tweet_id="1",
                posted_at=game_start,
                text="Test",
                author="test",
                phase="q1",
                score=1.0,
                position=TweetPosition.EARLY,
            )
        ]
        assignments = enforce_embedded_caps(tweets, block_count=0)
        assert len(assignments) == 0

    def test_position_affinity(self, game_start):
        """Tweets are assigned to blocks matching their position."""
        tweets = [
            ScoredTweet(
                tweet_id="early",
                posted_at=game_start + timedelta(minutes=10),
                text="Early tweet",
                author="test",
                phase="q1",
                score=1.0,
                position=TweetPosition.EARLY,
            ),
            ScoredTweet(
                tweet_id="late",
                posted_at=game_start + timedelta(minutes=140),
                text="Late tweet",
                author="test",
                phase="q4",
                score=1.0,
                position=TweetPosition.LATE,
            ),
        ]

        # 5 blocks
        assignments = enforce_embedded_caps(tweets, block_count=5)

        # Find where tweets were assigned
        early_block = next(
            (a.block_index for a in assignments if a.tweet and a.tweet.tweet_id == "early"),
            None,
        )
        late_block = next(
            (a.block_index for a in assignments if a.tweet and a.tweet.tweet_id == "late"),
            None,
        )

        # Early tweet should be in first blocks, late in last
        assert early_block is not None and early_block < 2
        assert late_block is not None and late_block >= 3


class TestApplyEmbeddedTweetsToBlocks:
    """Tests for apply_embedded_tweets_to_blocks function."""

    def test_adds_embedded_tweet_field(self, sample_blocks, game_start):
        """Adds embedded_tweet field to blocks."""
        tweet = ScoredTweet(
            tweet_id="1",
            posted_at=game_start,
            text="Test",
            author="test",
            phase="q1",
            score=1.0,
            position=TweetPosition.EARLY,
        )
        assignments = [
            BlockTweetAssignment(block_index=0, tweet=tweet),
            BlockTweetAssignment(block_index=1, tweet=None),
            BlockTweetAssignment(block_index=2, tweet=None),
            BlockTweetAssignment(block_index=3, tweet=None),
            BlockTweetAssignment(block_index=4, tweet=None),
        ]

        result = apply_embedded_tweets_to_blocks(sample_blocks, assignments)

        assert result[0]["embedded_social_post_id"] is not None
        assert result[0]["embedded_social_post_id"] == "1"
        assert result[1]["embedded_social_post_id"] is None

    def test_does_not_modify_block_structure(self, sample_blocks, game_start):
        """Does not add/remove/split blocks."""
        tweet = ScoredTweet(
            tweet_id="1",
            posted_at=game_start,
            text="Test",
            author="test",
            phase="q1",
            score=1.0,
            position=TweetPosition.EARLY,
        )
        assignments = [
            BlockTweetAssignment(block_index=i, tweet=tweet if i == 0 else None)
            for i in range(len(sample_blocks))
        ]

        result = apply_embedded_tweets_to_blocks(sample_blocks, assignments)

        # Same number of blocks
        assert len(result) == len(sample_blocks)
        # Original fields preserved
        for i, block in enumerate(result):
            assert block["role"] == sample_blocks[i]["role"]
            assert block["narrative"] == sample_blocks[i]["narrative"]


class TestSelectAndAssignEmbeddedTweets:
    """Tests for the convenience function."""

    def test_complete_pipeline(self, game_start, sample_tweets, sample_blocks):
        """Complete pipeline selects, caps, and assigns."""
        updated_blocks, selection = select_and_assign_embedded_tweets(
            sample_tweets, sample_blocks, game_start
        )

        # Blocks updated
        assert len(updated_blocks) == len(sample_blocks)

        # Some blocks have embedded tweets
        embedded_count = sum(
            1 for b in updated_blocks if b.get("embedded_social_post_id") is not None
        )
        assert embedded_count > 0
        assert embedded_count <= MAX_EMBEDDED_TWEETS
        assert embedded_count <= len(sample_blocks)

        # Selection metadata returned
        assert selection.total_candidates > 0

    def test_zero_tweets_preserves_blocks(self, game_start, sample_blocks):
        """Zero tweets still returns valid blocks."""
        updated_blocks, selection = select_and_assign_embedded_tweets(
            [], sample_blocks, game_start
        )

        assert len(updated_blocks) == len(sample_blocks)
        assert all(b.get("embedded_social_post_id") is None for b in updated_blocks)
        assert selection.total_candidates == 0

    def test_zero_blocks_handles_gracefully(self, game_start, sample_tweets):
        """Zero blocks handles gracefully."""
        updated_blocks, selection = select_and_assign_embedded_tweets(
            sample_tweets, [], game_start
        )

        assert len(updated_blocks) == 0
        # Selection still happens
        assert selection.total_candidates > 0


class TestStoryInvariant:
    """Tests ensuring story read time is not affected by tweets."""

    def test_story_length_unchanged_with_tweets(self, game_start, sample_tweets, sample_blocks):
        """Story length (blocks) unchanged regardless of tweet count."""
        # With tweets
        with_tweets, _ = select_and_assign_embedded_tweets(
            sample_tweets, sample_blocks, game_start
        )

        # Without tweets
        without_tweets, _ = select_and_assign_embedded_tweets(
            [], sample_blocks, game_start
        )

        # Same number of blocks
        assert len(with_tweets) == len(without_tweets)

        # Same narratives
        for i in range(len(sample_blocks)):
            assert with_tweets[i]["narrative"] == without_tweets[i]["narrative"]

    def test_varying_tweet_volume_same_block_count(self, game_start, sample_blocks):
        """Varying tweet volume doesn't change block count."""
        # Few tweets
        few_tweets = [
            {
                "id": "1",
                "text": "Test tweet",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=10),
            }
        ]

        # Many tweets
        many_tweets = [
            {
                "id": str(i),
                "text": f"Tweet {i}",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=i * 5),
            }
            for i in range(20)
        ]

        few_result, _ = select_and_assign_embedded_tweets(
            few_tweets, sample_blocks, game_start
        )
        many_result, _ = select_and_assign_embedded_tweets(
            many_tweets, sample_blocks, game_start
        )

        assert len(few_result) == len(many_result) == len(sample_blocks)
