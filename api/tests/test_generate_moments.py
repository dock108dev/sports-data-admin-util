"""Tests for generate_moments module."""

import pytest


class TestFinalizeMoment:
    """Tests for _finalize_moment function."""

    def test_basic_moment_structure(self):
        """Moment has all required fields."""
        from app.services.pipeline.stages.generate_moments import _finalize_moment

        events = [
            {
                "play_index": 1,
                "quarter": 1,
                "game_clock": "12:00",
                "away_score": 0,
                "home_score": 0,
                "play_type": "shot",
            },
            {
                "play_index": 2,
                "quarter": 1,
                "game_clock": "11:45",
                "away_score": 2,
                "home_score": 0,
                "play_type": "made_shot",
            },
        ]
        moment_plays = events
        moment_start_idx = 0

        result = _finalize_moment(events, moment_plays, moment_start_idx)

        assert "play_ids" in result
        assert "explicitly_narrated_play_ids" in result
        assert "period" in result
        assert "start_clock" in result
        assert "end_clock" in result
        assert "score_before" in result
        assert "score_after" in result

    def test_play_ids_extracted(self):
        """Play IDs are extracted from plays."""
        from app.services.pipeline.stages.generate_moments import _finalize_moment

        events = [
            {
                "play_index": 5,
                "quarter": 2,
                "game_clock": "8:00",
                "away_score": 30,
                "home_score": 28,
            },
            {
                "play_index": 6,
                "quarter": 2,
                "game_clock": "7:50",
                "away_score": 32,
                "home_score": 28,
            },
            {
                "play_index": 7,
                "quarter": 2,
                "game_clock": "7:40",
                "away_score": 32,
                "home_score": 28,
            },
        ]
        result = _finalize_moment(events, events, 0)

        assert result["play_ids"] == [5, 6, 7]

    def test_period_from_first_play(self):
        """Period comes from first play."""
        from app.services.pipeline.stages.generate_moments import _finalize_moment

        events = [
            {"play_index": 1, "quarter": 3, "game_clock": "12:00", "away_score": 50, "home_score": 48},
        ]
        result = _finalize_moment(events, events, 0)

        assert result["period"] == 3

    def test_clock_values(self):
        """Start and end clock from first/last plays."""
        from app.services.pipeline.stages.generate_moments import _finalize_moment

        events = [
            {"play_index": 1, "quarter": 1, "game_clock": "10:00", "away_score": 0, "home_score": 0},
            {"play_index": 2, "quarter": 1, "game_clock": "9:30", "away_score": 0, "home_score": 0},
            {"play_index": 3, "quarter": 1, "game_clock": "9:15", "away_score": 0, "home_score": 2},
        ]
        result = _finalize_moment(events, events, 0)

        assert result["start_clock"] == "10:00"
        assert result["end_clock"] == "9:15"

    def test_default_period(self):
        """Missing quarter defaults to 1."""
        from app.services.pipeline.stages.generate_moments import _finalize_moment

        events = [{"play_index": 1, "game_clock": "12:00", "away_score": 0, "home_score": 0}]
        result = _finalize_moment(events, events, 0)

        assert result["period"] == 1


class TestSegmentPlaysIntoMoments:
    """Tests for _segment_plays_into_moments function."""

    def test_empty_events(self):
        """Empty events returns empty moments."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        moments, metrics = _segment_plays_into_moments([])

        assert moments == []
        assert metrics.total_plays == 0
        assert metrics.total_moments == 0

    def test_single_event(self):
        """Single event creates single moment."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {
                "play_index": 1,
                "quarter": 1,
                "game_clock": "12:00",
                "away_score": 0,
                "home_score": 0,
                "play_type": "tip_off",
            }
        ]

        moments, metrics = _segment_plays_into_moments(events)

        assert len(moments) == 1
        assert moments[0]["play_ids"] == [1]
        assert metrics.total_plays == 1
        assert metrics.total_moments == 1

    def test_period_boundary_creates_new_moment(self):
        """Period change forces new moment."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": 1, "quarter": 1, "game_clock": "0:01", "away_score": 28, "home_score": 26},
            {"play_index": 2, "quarter": 2, "game_clock": "12:00", "away_score": 28, "home_score": 26},
        ]

        moments, metrics = _segment_plays_into_moments(events)

        # Each period should be its own moment
        assert len(moments) == 2
        assert moments[0]["play_ids"] == [1]
        assert moments[0]["period"] == 1
        assert moments[1]["play_ids"] == [2]
        assert moments[1]["period"] == 2

    def test_all_plays_covered(self):
        """Every play appears in exactly one moment."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": 0, "home_score": 0}
            for i in range(1, 6)
        ]

        moments, _ = _segment_plays_into_moments(events)

        all_play_ids = []
        for m in moments:
            all_play_ids.extend(m["play_ids"])

        assert sorted(all_play_ids) == [1, 2, 3, 4, 5]

    def test_moments_ordered(self):
        """Moments are ordered by first play."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": 0, "home_score": 0}
            for i in range(1, 10)
        ]

        moments, _ = _segment_plays_into_moments(events)

        prev_first = -1
        for m in moments:
            first_play = m["play_ids"][0]
            assert first_play > prev_first
            prev_first = first_play

    def test_missing_play_index_raises(self):
        """Missing play_index raises ValueError."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"quarter": 1, "game_clock": "12:00", "away_score": 0, "home_score": 0}  # No play_index
        ]

        with pytest.raises(ValueError, match="missing play_index"):
            _segment_plays_into_moments(events)

    def test_narrated_plays_subset_of_play_ids(self):
        """Narrated play IDs are subset of play IDs."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": i * 2, "home_score": 0}
            for i in range(1, 5)
        ]

        moments, _ = _segment_plays_into_moments(events)

        for m in moments:
            play_ids = set(m["play_ids"])
            narrated = set(m["explicitly_narrated_play_ids"])
            assert narrated.issubset(play_ids)

    def test_at_least_one_narrated_per_moment(self):
        """Each moment has at least one narrated play."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": 0, "home_score": 0}
            for i in range(1, 8)
        ]

        moments, _ = _segment_plays_into_moments(events)

        for m in moments:
            assert len(m["explicitly_narrated_play_ids"]) >= 1

    def test_max_two_narrated_per_moment(self):
        """No moment has more than 2 narrated plays."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        # Create events with many scoring plays
        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": i * 2, "home_score": i}
            for i in range(1, 15)
        ]

        moments, _ = _segment_plays_into_moments(events)

        for m in moments:
            assert len(m["explicitly_narrated_play_ids"]) <= 2

    def test_metrics_computed(self):
        """Compression metrics are computed."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": 0, "home_score": 0}
            for i in range(1, 20)
        ]

        _, metrics = _segment_plays_into_moments(events)

        assert metrics.total_plays == 19
        assert metrics.total_moments > 0
        assert len(metrics.plays_per_moment) == metrics.total_moments
        assert len(metrics.explicit_plays_per_moment) == metrics.total_moments


class TestExecuteGenerateMoments:
    """Tests for execute_generate_moments function."""

    @pytest.mark.asyncio
    async def test_requires_previous_output(self):
        """Raises if no previous output."""
        from app.services.pipeline.stages.generate_moments import (
            execute_generate_moments,
        )
        from app.services.pipeline.models import StageInput

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output=None,
        )

        with pytest.raises(ValueError, match="requires previous stage output"):
            await execute_generate_moments(stage_input)

    @pytest.mark.asyncio
    async def test_requires_pbp_events(self):
        """Raises if no pbp_events in previous output."""
        from app.services.pipeline.stages.generate_moments import (
            execute_generate_moments,
        )
        from app.services.pipeline.models import StageInput

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"something_else": []},
        )

        with pytest.raises(ValueError, match="No pbp_events"):
            await execute_generate_moments(stage_input)

    @pytest.mark.asyncio
    async def test_validates_event_ordering(self):
        """Raises if events not ordered."""
        from app.services.pipeline.stages.generate_moments import (
            execute_generate_moments,
        )
        from app.services.pipeline.models import StageInput

        # Out of order play_index
        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={
                "pbp_events": [
                    {"play_index": 5, "quarter": 1, "game_clock": "12:00", "away_score": 0, "home_score": 0},
                    {"play_index": 3, "quarter": 1, "game_clock": "11:00", "away_score": 0, "home_score": 0},
                ]
            },
        )

        with pytest.raises(ValueError, match="not ordered"):
            await execute_generate_moments(stage_input)

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Successful execution returns moments."""
        from app.services.pipeline.stages.generate_moments import (
            execute_generate_moments,
        )
        from app.services.pipeline.models import StageInput

        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": i, "home_score": 0}
            for i in range(1, 6)
        ]

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"pbp_events": events},
        )

        result = await execute_generate_moments(stage_input)

        assert "moments" in result.data
        assert "compression_metrics" in result.data
        assert len(result.data["moments"]) > 0

    @pytest.mark.asyncio
    async def test_output_has_compression_metrics(self):
        """Output includes compression metrics."""
        from app.services.pipeline.stages.generate_moments import (
            execute_generate_moments,
        )
        from app.services.pipeline.models import StageInput

        events = [
            {"play_index": i, "quarter": 1, "game_clock": f"{12-i}:00", "away_score": 0, "home_score": 0}
            for i in range(1, 10)
        ]

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"pbp_events": events},
        )

        result = await execute_generate_moments(stage_input)

        metrics = result.data["compression_metrics"]
        assert "total_plays" in metrics
        assert "total_moments" in metrics
        assert "pct_moments_under_soft_cap" in metrics

    @pytest.mark.asyncio
    async def test_logs_added(self):
        """Execution adds log entries."""
        from app.services.pipeline.stages.generate_moments import (
            execute_generate_moments,
        )
        from app.services.pipeline.models import StageInput

        events = [
            {"play_index": 1, "quarter": 1, "game_clock": "12:00", "away_score": 0, "home_score": 0},
        ]

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"pbp_events": events},
        )

        result = await execute_generate_moments(stage_input)

        assert len(result.logs) > 0
        log_messages = [log["message"] for log in result.logs]
        assert any("Starting GENERATE_MOMENTS" in msg for msg in log_messages)
        assert any("completed successfully" in msg for msg in log_messages)
