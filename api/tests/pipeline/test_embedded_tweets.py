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
    assign_tweets_to_blocks_by_time,
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


class TestFlowInvariant:
    """Tests ensuring flow read time is not affected by tweets."""

    def test_flow_length_unchanged_with_tweets(self, game_start, sample_tweets, sample_blocks):
        """Flow length (blocks) unchanged regardless of tweet count."""
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


# =============================================================================
# HELPERS for temporal assignment tests
# =============================================================================


def _make_tweet(tweet_id: int, posted_at: datetime, score: float = 1.0) -> ScoredTweet:
    """Build a minimal ScoredTweet for temporal tests."""
    return ScoredTweet(
        tweet_id=tweet_id,
        posted_at=posted_at,
        text=f"Tweet {tweet_id}",
        author="test",
        phase="in_game",
        score=score,
    )


def _assigned_tweet_ids(assignments: list[BlockTweetAssignment]) -> dict[int, int | None]:
    """Return {block_index: display tweet_id or None}."""
    return {a.block_index: a.tweet.tweet_id if a.tweet else None for a in assignments}


# =============================================================================
# NBA TEMPORAL MATCHING (4 quarters + halftime)
#
# NBA real-time layout (from timeline_types):
#   NBA_QUARTER_REAL_SECONDS = 75*60 / 4 = 1125 s ≈ 18 m 45 s
#   NBA_HALFTIME_REAL_SECONDS = 15*60 = 900 s = 15 m
#
#   Q1 starts at: game_start
#   Q2 starts at: game_start + 1125 s  (≈ +18 m 45 s)
#   Q3 starts at: game_start + 2*1125 + 900 s  (= +3150 s ≈ +52 m 30 s)
#   Q4 starts at: game_start + 3*1125 + 900 s  (= +4275 s ≈ +71 m 15 s)
#   OT1 starts at: game_start + 4500 + 900 s   (= +5400 s = +90 m)
# =============================================================================


class TestNBATemporalAssignment:
    """Tests for temporal block assignment with NBA period timing."""

    def test_tweet_per_quarter_maps_to_correct_block(self, game_start):
        """Tweets during each NBA quarter map to the matching block."""
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
            {"block_index": 2, "period_start": 3},
            {"block_index": 3, "period_start": 4},
        ]
        tweets = [
            _make_tweet(10, game_start + timedelta(minutes=5)),    # Q1 window
            _make_tweet(20, game_start + timedelta(minutes=25)),   # Q2 window
            _make_tweet(30, game_start + timedelta(minutes=60)),   # Q3 window
            _make_tweet(40, game_start + timedelta(minutes=75)),   # Q4 window
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] == 10
        assert ids[1] == 20
        assert ids[2] == 30
        assert ids[3] == 40

    def test_tweet_exactly_at_quarter_boundary(self, game_start):
        """Tweet posted exactly when Q2 starts goes to the Q2 block."""
        q2_start_offset = timedelta(seconds=1125)  # NBA Q2 real-time start
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
        ]
        tweets = [_make_tweet(99, game_start + q2_start_offset)]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[1] == 99

    def test_tweet_before_game_start_unassigned(self, game_start):
        """Tweet posted before tip-off matches no block."""
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
        ]
        tweets = [_make_tweet(1, game_start - timedelta(minutes=10))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] is None
        assert ids[1] is None

    def test_multiple_tweets_same_block_highest_score_wins(self, game_start):
        """When multiple tweets match the same block, highest score is display."""
        blocks = [{"block_index": 0, "period_start": 1}]
        tweets = [
            _make_tweet(1, game_start + timedelta(minutes=2), score=3.0),
            _make_tweet(2, game_start + timedelta(minutes=5), score=8.0),
            _make_tweet(3, game_start + timedelta(minutes=10), score=1.0),
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")

        assert assignments[0].tweet is not None
        assert assignments[0].tweet.tweet_id == 2  # highest score
        additional_ids = {t.tweet_id for t in assignments[0].additional_tweets}
        assert additional_ids == {1, 3}

    def test_empty_tweets_returns_all_none_assignments(self, game_start):
        """Empty tweet list produces assignments with all tweet=None."""
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
        ]

        assignments = assign_tweets_to_blocks_by_time([], blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] is None
        assert ids[1] is None

    def test_empty_blocks_returns_empty(self, game_start):
        """Empty block list returns empty assignments."""
        tweets = [_make_tweet(1, game_start + timedelta(minutes=5))]
        assignments = assign_tweets_to_blocks_by_time(tweets, [], game_start, "NBA")

        assert assignments == []

    def test_nba_overtime_period(self, game_start):
        """Tweet during NBA OT maps to the OT block (period 5)."""
        blocks = [
            {"block_index": 0, "period_start": 4},
            {"block_index": 1, "period_start": 5},  # OT1
        ]
        # OT1 starts at game_start + 4500 + 900 = +5400s = +90 min
        tweets = [_make_tweet(77, game_start + timedelta(minutes=92))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] is None
        assert ids[1] == 77


class TestSamePeriodMultipleBlocks:
    """Tests for blocks that share the same period_start value.

    When blocks share the same period_start, the algorithm subdivides the
    period's real-time window evenly so tweets distribute across blocks
    rather than collapsing to the last one.
    """

    def test_two_blocks_same_period_tweet_distributes(self, game_start):
        """Two blocks in period 1 subdivide the window; early tweet goes to block 0.

        blocks 0, 1 share period 1; block 2 is period 3.
        Period 1 starts at game_start, period 3 starts at ~52.5 min.
        Subdivision: block 0 gets [0, 26.25 min), block 1 gets [26.25, 52.5 min).
        Tweet at +5 min falls in block 0's sub-window.
        """
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 1},  # same period
            {"block_index": 2, "period_start": 3},
        ]
        tweets = [_make_tweet(10, game_start + timedelta(minutes=5))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] == 10
        assert ids[1] is None
        assert ids[2] is None

    def test_two_blocks_same_period_late_tweet_goes_to_second(self, game_start):
        """Late tweet in subdivided window goes to the second block.

        Same setup: block 0 gets [0, 26.25 min), block 1 gets [26.25, 52.5 min).
        Tweet at +30 min falls in block 1's sub-window.
        """
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 1},
            {"block_index": 2, "period_start": 3},
        ]
        tweets = [_make_tweet(10, game_start + timedelta(minutes=30))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] is None
        assert ids[1] == 10

    def test_three_blocks_same_period_tweets_distribute(self, game_start):
        """Three blocks in period 1: tweets spread across sub-windows.

        All 3 blocks share period 1. Next period (2) starts at ~18.75 min.
        Subdivision: block 0 [0, 6.25 min), block 1 [6.25, 12.5 min),
        block 2 [12.5, 18.75 min).
        Tweet at +2 min → block 0, tweet at +8 min → block 1.
        """
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 1},
            {"block_index": 2, "period_start": 1},
        ]
        tweets = [
            _make_tweet(1, game_start + timedelta(minutes=2), score=5.0),
            _make_tweet(2, game_start + timedelta(minutes=8), score=3.0),
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] == 1  # tweet at +2 min in first sub-window
        assert ids[1] == 2  # tweet at +8 min in second sub-window
        assert ids[2] is None  # no tweet in third sub-window


# =============================================================================
# NHL TEMPORAL MATCHING (3 periods + intermissions)
#
# NHL real-time layout:
#   NHL_PERIOD_REAL_SECONDS = 90*60 / 3 = 1800 s = 30 m
#   NHL_INTERMISSION_REAL_SECONDS = 18*60 = 1080 s = 18 m
#
#   P1 starts at: game_start
#   P2 starts at: game_start + 1800 + 1080 = +2880 s = +48 m
#   P3 starts at: game_start + 3600 + 2160 = +5760 s = +96 m
#   OT starts at: game_start + 5400 + 600 = +6000 s = +100 m
# =============================================================================


class TestNHLTemporalAssignment:
    """Tests for temporal block assignment with NHL period timing."""

    def test_tweets_map_to_correct_nhl_periods(self, game_start):
        """Tweets during each NHL period map to the matching block."""
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
            {"block_index": 2, "period_start": 3},
        ]
        tweets = [
            _make_tweet(10, game_start + timedelta(minutes=15)),   # P1 (0-48 min)
            _make_tweet(20, game_start + timedelta(minutes=60)),   # P2 (48-96 min)
            _make_tweet(30, game_start + timedelta(minutes=100)),  # P3 (96+ min)
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NHL")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] == 10
        assert ids[1] == 20
        assert ids[2] == 30

    def test_nhl_intermission_tweet_lands_in_preceding_period(self, game_start):
        """Tweet during intermission (after P1 ends, before P2 starts) stays in P1 block.

        P1 real time runs ~30 min, P2 starts at ~48 min.
        A tweet at 35 min is after P1 game time but before P2 start — belongs to P1.
        """
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
        ]
        tweets = [_make_tweet(55, game_start + timedelta(minutes=35))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NHL")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] == 55
        assert ids[1] is None

    def test_nhl_overtime(self, game_start):
        """Tweet during NHL OT maps to the OT block (period 4)."""
        blocks = [
            {"block_index": 0, "period_start": 3},
            {"block_index": 1, "period_start": 4},  # OT
        ]
        # OT starts at game_start + 5400 + 600 = +100 min
        tweets = [_make_tweet(88, game_start + timedelta(minutes=105))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NHL")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] is None
        assert ids[1] == 88

    def test_nhl_timing_differs_from_nba(self, game_start):
        """Same blocks and tweet time yield different assignments for NHL vs NBA.

        A tweet at game_start + 50 min:
        - NBA: Q3 started at ~52.5 min, so tweet is still in Q2 window → block 1
        - NHL: P2 started at 48 min, so tweet is in P2 window → block 1
        Both map to block 1 here, but for different reasons.

        A tweet at game_start + 20 min:
        - NBA: Q2 starts at ~18.75 min, so tweet is in Q2 → block 1
        - NHL: P1 runs until P2 at 48 min, so tweet is still in P1 → block 0
        """
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
        ]
        tweets = [_make_tweet(42, game_start + timedelta(minutes=20))]

        nba_assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        nhl_assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NHL")

        nba_ids = _assigned_tweet_ids(nba_assignments)
        nhl_ids = _assigned_tweet_ids(nhl_assignments)

        # NBA Q2 starts at ~18.75 min → tweet at 20 min is in Q2
        assert nba_ids[1] == 42
        # NHL P2 starts at 48 min → tweet at 20 min is still in P1
        assert nhl_ids[0] == 42


# =============================================================================
# NCAAB TEMPORAL MATCHING (2 halves + halftime)
#
# NCAAB real-time layout:
#   NCAAB_HALF_REAL_SECONDS = 75*60 / 2 = 2250 s = 37 m 30 s
#   NCAAB_HALFTIME_REAL_SECONDS = 20*60 = 1200 s = 20 m
#
#   H1 starts at: game_start
#   H2 starts at: game_start + 2250 + 1200 = +3450 s = +57 m 30 s
#   OT1 starts at: game_start + 4500 + 600 = +5100 s = +85 m
# =============================================================================


class TestNCAABTemporalAssignment:
    """Tests for temporal block assignment with NCAAB period timing."""

    def test_tweets_map_to_correct_ncaab_halves(self, game_start):
        """Tweets during each NCAAB half map to the matching block."""
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
        ]
        tweets = [
            _make_tweet(10, game_start + timedelta(minutes=20)),  # H1 (0-57.5 min)
            _make_tweet(20, game_start + timedelta(minutes=65)),  # H2 (57.5+ min)
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NCAAB")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] == 10
        assert ids[1] == 20

    def test_ncaab_halftime_tweet_stays_in_first_half(self, game_start):
        """Tweet during NCAAB halftime (after H1 game time, before H2 start) stays in H1.

        H1 real time is ~37.5 min, H2 starts at ~57.5 min.
        A tweet at 45 min is in the halftime window — belongs to H1.
        """
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
        ]
        tweets = [_make_tweet(33, game_start + timedelta(minutes=45))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NCAAB")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] == 33
        assert ids[1] is None

    def test_ncaab_overtime(self, game_start):
        """Tweet during NCAAB OT maps to the OT block (period 3)."""
        blocks = [
            {"block_index": 0, "period_start": 2},
            {"block_index": 1, "period_start": 3},  # OT1
        ]
        # OT1 starts at game_start + 4500 + 600 = +85 min
        tweets = [_make_tweet(66, game_start + timedelta(minutes=90))]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NCAAB")
        ids = _assigned_tweet_ids(assignments)

        assert ids[0] is None
        assert ids[1] == 66

    def test_ncaab_longer_halftime_than_nba(self, game_start):
        """NCAAB's 20-min halftime vs NBA's 15-min halftime affects assignment.

        A tweet at game_start + 55 min:
        - NBA: Q3 started at ~52.5 min → tweet is in Q3 window
        - NCAAB: H2 starts at ~57.5 min → tweet is still in H1 window
        """
        blocks = [
            {"block_index": 0, "period_start": 1},
            {"block_index": 1, "period_start": 2},
            {"block_index": 2, "period_start": 3},
        ]
        tweets = [_make_tweet(50, game_start + timedelta(minutes=55))]

        nba_assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")
        ncaab_assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NCAAB")

        nba_ids = _assigned_tweet_ids(nba_assignments)
        ncaab_ids = _assigned_tweet_ids(ncaab_assignments)

        # NBA: Q3 starts at ~52.5 min, so 55 min is in Q3 → block 2
        assert nba_ids[2] == 50
        # NCAAB: H2 starts at ~57.5 min, so 55 min is still in H1 → block 0
        assert ncaab_ids[0] == 50


# =============================================================================
# GLOBAL CAP ENFORCEMENT (MAX_EMBEDDED_TWEETS = 5)
# =============================================================================


class TestGlobalCap:
    """Tests that the MAX_EMBEDDED_TWEETS=5 global cap is enforced.

    When more than 5 blocks have display tweets, only the top 5 by score
    are kept; the rest are demoted to additional_tweets.
    """

    def test_six_display_tweets_capped_to_five(self, game_start):
        """6 blocks with display tweets → only 5 survive, lowest score demoted.

        NBA period starts: Q1=0, Q2=18.75m, Q3=52.5m, Q4=71.25m, OT1=90m, OT2=105m.
        Each tweet is placed in the middle of its period's window.
        """
        blocks = [
            {"block_index": i, "period_start": i + 1}
            for i in range(6)
        ]
        # Timings that land one tweet per NBA period window
        period_midpoints = [5, 25, 55, 75, 95, 110]  # minutes
        tweets = [
            _make_tweet(i + 1, game_start + timedelta(minutes=m), score=float(i + 1))
            for i, m in enumerate(period_midpoints)
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")

        display_count = sum(1 for a in assignments if a.tweet is not None)
        assert display_count == MAX_EMBEDDED_TWEETS  # 5

        # The lowest-scored tweet (score=1.0, tweet_id=1, block 0) should be demoted
        demoted_block = assignments[0]
        assert demoted_block.tweet is None
        assert len(demoted_block.additional_tweets) == 1
        assert demoted_block.additional_tweets[0].tweet_id == 1

    def test_five_display_tweets_within_cap(self, game_start):
        """5 blocks with display tweets → all kept (exactly at the cap).

        NBA period starts: Q1=0, Q2=18.75m, Q3=52.5m, Q4=71.25m, OT1=90m.
        """
        blocks = [
            {"block_index": i, "period_start": i + 1}
            for i in range(5)
        ]
        period_midpoints = [5, 25, 55, 75, 95]  # minutes
        tweets = [
            _make_tweet(i + 1, game_start + timedelta(minutes=m), score=float(i + 1))
            for i, m in enumerate(period_midpoints)
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")

        display_count = sum(1 for a in assignments if a.tweet is not None)
        assert display_count == 5  # all kept

    def test_seven_blocks_two_demoted(self, game_start):
        """7 blocks (max pipeline blocks) with tweets → 2 lowest scores demoted.

        NBA period starts: Q1=0, Q2=18.75m, Q3=52.5m, Q4=71.25m,
        OT1=90m, OT2=105m, OT3=120m.
        """
        blocks = [
            {"block_index": i, "period_start": i + 1}
            for i in range(7)
        ]
        period_midpoints = [5, 25, 55, 75, 95, 110, 125]  # minutes
        tweets = [
            _make_tweet(
                i + 1,
                game_start + timedelta(minutes=m),
                score=float(10 + i),  # scores 10..16
            )
            for i, m in enumerate(period_midpoints)
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")

        display_count = sum(1 for a in assignments if a.tweet is not None)
        assert display_count == MAX_EMBEDDED_TWEETS

        # Blocks 0 and 1 have lowest scores (10, 11) → demoted
        assert assignments[0].tweet is None
        assert assignments[1].tweet is None
        # Blocks 2-6 retain their display tweets
        for i in range(2, 7):
            assert assignments[i].tweet is not None

    def test_demoted_tweet_preserved_in_additional(self, game_start):
        """Demoted display tweet is moved to additional_tweets, not lost."""
        blocks = [
            {"block_index": i, "period_start": i + 1}
            for i in range(6)
        ]
        period_midpoints = [5, 25, 55, 75, 95, 110]
        tweets = [
            _make_tweet(i + 1, game_start + timedelta(minutes=m), score=float(i + 1))
            for i, m in enumerate(period_midpoints)
        ]

        assignments = assign_tweets_to_blocks_by_time(tweets, blocks, game_start, "NBA")

        # Block 0 had tweet_id=1 (lowest score=1.0), now demoted
        demoted = assignments[0]
        assert demoted.tweet is None
        all_additional_ids = {t.tweet_id for t in demoted.additional_tweets}
        assert 1 in all_additional_ids
