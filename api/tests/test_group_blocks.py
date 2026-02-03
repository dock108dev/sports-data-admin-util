"""Tests for GROUP_BLOCKS stage."""

from __future__ import annotations


from app.services.pipeline.stages.block_types import (
    MIN_BLOCKS,
    MAX_BLOCKS,
    SemanticRole,
)
from app.services.pipeline.stages.group_blocks import (
    calculate_block_count,
    _count_lead_changes,
    _find_lead_change_indices,
    _find_scoring_runs,
    _find_period_boundaries,
    _find_split_points,
    _assign_roles,
    _create_blocks,
    _detect_blowout,
    _find_garbage_time_start,
    _compress_blowout_blocks,
    BLOWOUT_MARGIN_THRESHOLD,
)


class TestCalculateBlockCount:
    """Tests for block count calculation."""

    def test_minimum_blocks(self) -> None:
        """Short games with few lead changes produce minimum blocks."""
        moments: list[dict] = []
        lead_changes = 0
        total_plays = 100

        count = calculate_block_count(moments, lead_changes, total_plays)
        assert count == MIN_BLOCKS

    def test_moderate_lead_changes(self) -> None:
        """3+ lead changes adds one block."""
        moments: list[dict] = []
        lead_changes = 3
        total_plays = 100

        count = calculate_block_count(moments, lead_changes, total_plays)
        assert count == MIN_BLOCKS + 1

    def test_many_lead_changes(self) -> None:
        """6+ lead changes adds two blocks."""
        moments: list[dict] = []
        lead_changes = 6
        total_plays = 100

        count = calculate_block_count(moments, lead_changes, total_plays)
        assert count == MIN_BLOCKS + 2

    def test_long_game(self) -> None:
        """Long games (400+ plays) add one block."""
        moments: list[dict] = []
        lead_changes = 0
        total_plays = 500

        count = calculate_block_count(moments, lead_changes, total_plays)
        assert count == MIN_BLOCKS + 1

    def test_maximum_blocks(self) -> None:
        """Block count is capped at maximum."""
        moments: list[dict] = []
        lead_changes = 10
        total_plays = 600

        count = calculate_block_count(moments, lead_changes, total_plays)
        assert count == MAX_BLOCKS

    def test_block_count_always_in_range(self) -> None:
        """Block count always in [4, 7]."""
        for lead_changes in range(0, 15):
            for total_plays in [50, 200, 400, 600]:
                count = calculate_block_count([], lead_changes, total_plays)
                assert MIN_BLOCKS <= count <= MAX_BLOCKS


class TestCountLeadChanges:
    """Tests for lead change counting."""

    def test_no_lead_changes(self) -> None:
        """No lead changes when one team always leads."""
        moments = [
            {"score_after": [10, 5]},
            {"score_after": [20, 10]},
            {"score_after": [30, 15]},
        ]
        assert _count_lead_changes(moments) == 0

    def test_single_lead_change(self) -> None:
        """Detect single lead change."""
        moments = [
            {"score_after": [10, 5]},  # Home leads
            {"score_after": [12, 15]},  # Away takes lead
            {"score_after": [15, 20]},  # Away still leads
        ]
        assert _count_lead_changes(moments) == 1

    def test_multiple_lead_changes(self) -> None:
        """Detect multiple lead changes."""
        moments = [
            {"score_after": [10, 5]},  # Home leads
            {"score_after": [12, 15]},  # Away leads
            {"score_after": [20, 18]},  # Home leads again
            {"score_after": [22, 25]},  # Away leads again
        ]
        assert _count_lead_changes(moments) == 3

    def test_tie_not_counted_as_lead_change(self) -> None:
        """Tie scores don't count as lead changes."""
        moments = [
            {"score_after": [10, 5]},  # Home leads
            {"score_after": [10, 10]},  # Tie
            {"score_after": [15, 10]},  # Home leads (not a lead change from tie)
        ]
        assert _count_lead_changes(moments) == 0


class TestFindLeadChangeIndices:
    """Tests for finding lead change moment indices."""

    def test_no_lead_changes(self) -> None:
        """Empty list when no lead changes."""
        moments = [
            {"score_before": [0, 0], "score_after": [10, 5]},
            {"score_before": [10, 5], "score_after": [20, 10]},
        ]
        assert _find_lead_change_indices(moments) == []

    def test_find_lead_change_index(self) -> None:
        """Find index of moment containing lead change."""
        moments = [
            {"score_before": [0, 0], "score_after": [10, 5]},  # Home leads
            {"score_before": [10, 5], "score_after": [12, 15]},  # Lead change here
            {"score_before": [12, 15], "score_after": [15, 20]},
        ]
        indices = _find_lead_change_indices(moments)
        assert 1 in indices


class TestFindScoringRuns:
    """Tests for detecting scoring runs."""

    def test_no_scoring_runs(self) -> None:
        """No runs when scoring is alternating."""
        moments = [
            {"score_before": [0, 0], "score_after": [2, 0]},
            {"score_before": [2, 0], "score_after": [2, 2]},
            {"score_before": [2, 2], "score_after": [4, 2]},
        ]
        runs = _find_scoring_runs(moments, min_run_size=5)
        assert runs == []

    def test_detect_scoring_run(self) -> None:
        """Detect significant scoring run."""
        moments = [
            {"score_before": [0, 0], "score_after": [3, 0]},
            {"score_before": [3, 0], "score_after": [6, 0]},
            {"score_before": [6, 0], "score_after": [10, 0]},  # 10-0 run
        ]
        runs = _find_scoring_runs(moments, min_run_size=8)
        assert len(runs) == 1
        assert runs[0][2] == 10  # Run size


class TestFindPeriodBoundaries:
    """Tests for detecting period boundaries."""

    def test_no_period_changes(self) -> None:
        """No boundaries in single-period data."""
        moments = [
            {"period": 1},
            {"period": 1},
            {"period": 1},
        ]
        assert _find_period_boundaries(moments) == []

    def test_find_period_boundary(self) -> None:
        """Find index where period changes."""
        moments = [
            {"period": 1},
            {"period": 1},
            {"period": 2},  # Boundary at index 2
            {"period": 2},
        ]
        boundaries = _find_period_boundaries(moments)
        assert boundaries == [2]

    def test_multiple_period_boundaries(self) -> None:
        """Find multiple period boundaries."""
        moments = [
            {"period": 1},
            {"period": 2},  # Boundary at index 1
            {"period": 3},  # Boundary at index 2
            {"period": 4},  # Boundary at index 3
        ]
        boundaries = _find_period_boundaries(moments)
        assert boundaries == [1, 2, 3]


class TestAssignRoles:
    """Tests for semantic role assignment."""

    def test_first_block_is_setup(self) -> None:
        """First block is always SETUP."""
        from app.services.pipeline.stages.block_types import NarrativeBlock

        blocks = [
            NarrativeBlock(0, SemanticRole.RESPONSE, [], 1, 1, (0, 0), (10, 8), [], []),
            NarrativeBlock(1, SemanticRole.RESPONSE, [], 1, 1, (10, 8), (20, 18), [], []),
            NarrativeBlock(2, SemanticRole.RESPONSE, [], 1, 1, (20, 18), (30, 28), [], []),
            NarrativeBlock(3, SemanticRole.RESPONSE, [], 1, 1, (30, 28), (40, 38), [], []),
        ]
        _assign_roles(blocks)
        assert blocks[0].role == SemanticRole.SETUP

    def test_last_block_is_resolution(self) -> None:
        """Last block is always RESOLUTION."""
        from app.services.pipeline.stages.block_types import NarrativeBlock

        blocks = [
            NarrativeBlock(0, SemanticRole.RESPONSE, [], 1, 1, (0, 0), (10, 8), [], []),
            NarrativeBlock(1, SemanticRole.RESPONSE, [], 1, 1, (10, 8), (20, 18), [], []),
            NarrativeBlock(2, SemanticRole.RESPONSE, [], 1, 1, (20, 18), (30, 28), [], []),
            NarrativeBlock(3, SemanticRole.RESPONSE, [], 1, 1, (30, 28), (40, 38), [], []),
        ]
        _assign_roles(blocks)
        assert blocks[-1].role == SemanticRole.RESOLUTION

    def test_no_role_more_than_twice(self) -> None:
        """No role appears more than twice."""
        from app.services.pipeline.stages.block_types import NarrativeBlock

        blocks = [
            NarrativeBlock(i, SemanticRole.RESPONSE, [], 1, 1, (0, 0), (10, 8), [], [])
            for i in range(7)
        ]
        _assign_roles(blocks)

        role_counts: dict[SemanticRole, int] = {}
        for block in blocks:
            role_counts[block.role] = role_counts.get(block.role, 0) + 1

        for count in role_counts.values():
            assert count <= 2


class TestBlockCreation:
    """Tests for block creation from moments."""

    def test_creates_correct_number_of_blocks(self) -> None:
        """Split points create expected number of blocks."""
        moments = [
            {"play_ids": [1], "period": 1, "score_before": [0, 0], "score_after": [2, 0]},
            {"play_ids": [2], "period": 1, "score_before": [2, 0], "score_after": [4, 2]},
            {"play_ids": [3], "period": 1, "score_before": [4, 2], "score_after": [6, 4]},
            {"play_ids": [4], "period": 2, "score_before": [6, 4], "score_after": [8, 6]},
            {"play_ids": [5], "period": 2, "score_before": [8, 6], "score_after": [10, 8]},
        ]
        split_points = [2]  # Creates 2 blocks: [0,1] and [2,3,4]

        blocks = _create_blocks(moments, split_points, [])
        assert len(blocks) == 2

    def test_blocks_cover_all_moments(self) -> None:
        """All moments are covered by blocks."""
        moments = [
            {"play_ids": [i], "period": 1, "score_before": [0, 0], "score_after": [2, 0]}
            for i in range(10)
        ]
        split_points = [3, 7]  # Creates 3 blocks

        blocks = _create_blocks(moments, split_points, [])

        covered_moments: set[int] = set()
        for block in blocks:
            covered_moments.update(block.moment_indices)

        assert covered_moments == set(range(10))

    def test_blocks_have_correct_scores(self) -> None:
        """Blocks have correct score_before and score_after."""
        moments = [
            {"play_ids": [1], "period": 1, "score_before": [0, 0], "score_after": [5, 3]},
            {"play_ids": [2], "period": 1, "score_before": [5, 3], "score_after": [10, 8]},
            {"play_ids": [3], "period": 1, "score_before": [10, 8], "score_after": [15, 12]},
            {"play_ids": [4], "period": 1, "score_before": [15, 12], "score_after": [20, 18]},
        ]
        split_points = [2]  # Block 0: moments 0,1; Block 1: moments 2,3

        blocks = _create_blocks(moments, split_points, [])

        # Block 0
        assert blocks[0].score_before == (0, 0)
        assert blocks[0].score_after == (10, 8)

        # Block 1
        assert blocks[1].score_before == (10, 8)
        assert blocks[1].score_after == (20, 18)


class TestBlockConstraints:
    """Tests for block system constraints."""

    def test_block_count_range(self) -> None:
        """Block count is always in range [4, 7]."""
        # Test various game scenarios
        for num_moments in [4, 10, 20, 50]:
            moments = [
                {
                    "play_ids": [i],
                    "period": 1,
                    "score_before": [0, 0],
                    "score_after": [i * 2, i],
                }
                for i in range(num_moments)
            ]
            lead_changes = num_moments // 5
            total_plays = num_moments * 5

            target_blocks = calculate_block_count(moments, lead_changes, total_plays)
            assert MIN_BLOCKS <= target_blocks <= MAX_BLOCKS

    def test_short_game_produces_minimum_blocks(self) -> None:
        """Even short games produce at least 4 blocks."""
        moments = [
            {"play_ids": [1], "period": 1, "score_before": [0, 0], "score_after": [2, 0]},
            {"play_ids": [2], "period": 1, "score_before": [2, 0], "score_after": [4, 2]},
            {"play_ids": [3], "period": 1, "score_before": [4, 2], "score_after": [6, 4]},
            {"play_ids": [4], "period": 1, "score_before": [6, 4], "score_after": [8, 6]},
        ]

        # With only 4 moments and 0 lead changes, should still get 4 blocks
        target_blocks = calculate_block_count(moments, 0, 20)
        split_points = _find_split_points(moments, target_blocks)

        # Number of blocks = number of split points + 1
        blocks = _create_blocks(moments, split_points, [])
        assert len(blocks) >= MIN_BLOCKS or len(blocks) == len(moments)

    def test_blowout_game_handled(self) -> None:
        """Blowout games (no meaningful lead changes) still produce valid blocks."""
        moments = [
            {"play_ids": [i], "period": 1, "score_before": [i * 3, i], "score_after": [(i + 1) * 3, i + 1]}
            for i in range(20)
        ]

        # No lead changes in a blowout
        lead_changes = 0
        total_plays = 100

        target_blocks = calculate_block_count(moments, lead_changes, total_plays)
        split_points = _find_split_points(moments, target_blocks)
        blocks = _create_blocks(moments, split_points, [])

        assert MIN_BLOCKS <= len(blocks) <= MAX_BLOCKS


class TestBlowoutDetection:
    """Tests for Task 1.5: Blowout detection and handling."""

    def test_detect_blowout_with_sustained_margin(self) -> None:
        """Detects blowout when margin is sustained across periods."""
        moments = [
            {"score_after": [10, 8], "period": 1},   # Close
            {"score_after": [20, 12], "period": 1},  # Gap opening
            {"score_after": [35, 12], "period": 1},  # 23 point margin
            {"score_after": [45, 18], "period": 2},  # Still blowout
            {"score_after": [55, 22], "period": 2},  # Sustained
            {"score_after": [70, 30], "period": 3},  # Period 3
            {"score_after": [85, 40], "period": 3},  # Still sustained
            {"score_after": [100, 50], "period": 4}, # Period 4 - sustained 2+ periods
        ]
        is_blowout, decisive_idx, max_margin = _detect_blowout(moments)
        assert is_blowout is True
        assert decisive_idx is not None
        assert max_margin >= BLOWOUT_MARGIN_THRESHOLD

    def test_no_blowout_in_close_game(self) -> None:
        """No blowout detected in close game."""
        moments = [
            {"score_after": [10, 8], "period": 1},
            {"score_after": [18, 20], "period": 1},
            {"score_after": [28, 26], "period": 2},
            {"score_after": [35, 38], "period": 2},
            {"score_after": [45, 42], "period": 3},
            {"score_after": [52, 55], "period": 3},
            {"score_after": [60, 58], "period": 4},
        ]
        is_blowout, decisive_idx, max_margin = _detect_blowout(moments)
        assert is_blowout is False

    def test_margin_not_sustained_is_not_blowout(self) -> None:
        """Large margin not sustained is not a blowout."""
        moments = [
            {"score_after": [10, 8], "period": 1},
            {"score_after": [30, 8], "period": 1},  # 22 point lead
            {"score_after": [32, 25], "period": 1}, # Lead shrinks
            {"score_after": [35, 32], "period": 2}, # Close again
            {"score_after": [40, 38], "period": 2},
        ]
        is_blowout, decisive_idx, max_margin = _detect_blowout(moments)
        # Had a large margin but wasn't sustained
        assert is_blowout is False


class TestGarbageTimeStart:
    """Tests for Task 1.5: Garbage time detection."""

    def test_finds_garbage_time_start(self) -> None:
        """Finds garbage time when margin and period conditions met."""
        moments = [
            {"score_after": [10, 8], "period": 1},
            {"score_after": [30, 12], "period": 2},  # Large margin but period 2
            {"score_after": [50, 20], "period": 3},  # 30 point margin, period 3 - garbage time
            {"score_after": [60, 25], "period": 3},
        ]
        idx = _find_garbage_time_start(moments)
        assert idx == 2  # Third moment where period >= 3 and margin >= 25

    def test_no_garbage_time_early_periods(self) -> None:
        """No garbage time in early periods even with large margin."""
        moments = [
            {"score_after": [10, 8], "period": 1},
            {"score_after": [40, 10], "period": 2},  # 30 point margin but period 2
        ]
        idx = _find_garbage_time_start(moments)
        assert idx is None

    def test_no_garbage_time_close_game(self) -> None:
        """No garbage time in close game."""
        moments = [
            {"score_after": [25, 22], "period": 3},
            {"score_after": [30, 28], "period": 4},
        ]
        idx = _find_garbage_time_start(moments)
        assert idx is None


class TestBlowoutCompression:
    """Tests for Task 1.5: Blowout block compression."""

    def test_compression_produces_fewer_blocks(self) -> None:
        """Blowout compression produces fewer blocks than normal."""
        moments = [
            {"play_ids": [i], "period": (i // 5) + 1, "score_before": [0, 0], "score_after": [i * 5, i]}
            for i in range(20)
        ]
        decisive_idx = 5  # Blowout became decisive at moment 5
        garbage_idx = 15  # Garbage time at moment 15

        split_points = _compress_blowout_blocks(moments, decisive_idx, garbage_idx)
        num_blocks = len(split_points) + 1

        # Should be compressed to fewer blocks
        assert num_blocks <= 5

    def test_compression_produces_min_blocks(self) -> None:
        """Blowout compression still produces at least MIN_BLOCKS."""
        moments = [
            {"play_ids": [i], "period": 1, "score_before": [0, 0], "score_after": [i * 3, i]}
            for i in range(10)
        ]
        decisive_idx = 3
        garbage_idx = None  # No garbage time

        split_points = _compress_blowout_blocks(moments, decisive_idx, garbage_idx)
        num_blocks = len(split_points) + 1

        assert num_blocks >= MIN_BLOCKS
