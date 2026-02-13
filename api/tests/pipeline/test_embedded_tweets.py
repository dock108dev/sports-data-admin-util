"""Tests for embedded tweet selection and temporal block assignment."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.pipeline.stages.embedded_tweets import (
    # Constants
    MAX_EMBEDDED_TWEETS,
    MAX_TWEETS_PER_BLOCK,
    MIN_EMBEDDED_TWEETS,
    ScoredTweet,
    BlockTweetAssignment,
    # Scorer
    DefaultTweetScorer,
    # Functions
    select_embedded_tweets,
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
            "id": 1,
            "text": "Game time! Let's go Lakers!",
            "author": "lakers",
            "posted_at": game_start + timedelta(minutes=5),
            "phase": "q1",
            "has_media": False,
            "is_team_account": True,
            "engagement": 500,
        },
        {
            "id": 2,
            "text": "Huge three pointer by LeBron! This is getting exciting!",
            "author": "espn",
            "posted_at": game_start + timedelta(minutes=45),
            "phase": "q2",
            "has_media": True,
            "is_verified": True,
            "engagement": 1200,
        },
        {
            "id": 3,
            "text": "Halftime: Lakers lead by 8.",
            "author": "lakers",
            "posted_at": game_start + timedelta(minutes=75),
            "phase": "halftime",
            "is_team_account": True,
            "engagement": 300,
        },
        {
            "id": 4,
            "text": "Big run in the third quarter!",
            "author": "nbareporter",
            "posted_at": game_start + timedelta(minutes=100),
            "phase": "q3",
            "engagement": 200,
        },
        {
            "id": 5,
            "text": "Down to the wire! Celtics within 2.",
            "author": "celtics",
            "posted_at": game_start + timedelta(minutes=140),
            "phase": "q4",
            "has_media": True,
            "is_team_account": True,
            "engagement": 800,
        },
        {
            "id": 6,
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
    """Tests for select_embedded_tweets function."""

    def test_empty_input_returns_empty(self, game_start):
        """Empty input returns empty selection."""
        result = select_embedded_tweets([], game_start)
        assert len(result.tweets) == 0
        assert result.total_candidates == 0

    def test_scores_all_candidates(self, game_start, sample_tweets):
        """Scores all valid candidates."""
        result = select_embedded_tweets(sample_tweets, game_start)
        # All valid tweets are scored (those with text and posted_at)
        assert result.total_candidates > 0
        assert len(result.tweets) == result.total_candidates

    def test_single_tweet_scored(self, game_start):
        """Single tweet is scored and returned."""
        single_tweet = [
            {
                "id": 1,
                "text": "Test tweet",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=10),
                "phase": "q1",
            }
        ]
        result = select_embedded_tweets(single_tweet, game_start)
        assert len(result.tweets) == 1
        assert result.selection_method == "scored"

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
                "id": 1,
                "text": "",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=10),
            },
            {
                "id": 2,
                "text": "Valid tweet",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=20),
            },
        ]
        result = select_embedded_tweets(tweets, game_start)
        assert len(result.tweets) == 1
        assert result.tweets[0].tweet_id == 2

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


class TestApplyEmbeddedTweetsToBlocks:
    """Tests for apply_embedded_tweets_to_blocks function."""

    def test_adds_embedded_tweet_field(self, sample_blocks, game_start):
        """Adds embedded_tweet field to blocks."""
        tweet = ScoredTweet(
            tweet_id=1,
            posted_at=game_start,
            text="Test",
            author="test",
            phase="q1",
            score=1.0,
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
        assert result[0]["embedded_social_post_id"] == 1
        assert result[1]["embedded_social_post_id"] is None

    def test_does_not_modify_block_structure(self, sample_blocks, game_start):
        """Does not add/remove/split blocks."""
        tweet = ScoredTweet(
            tweet_id=1,
            posted_at=game_start,
            text="Test",
            author="test",
            phase="q1",
            score=1.0,
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
                "id": 1,
                "text": "Test tweet",
                "author": "test",
                "posted_at": game_start + timedelta(minutes=10),
            }
        ]

        # Many tweets
        many_tweets = [
            {
                "id": i,
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
