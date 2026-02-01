"""Tests for moment_types stage."""


class TestBoundaryReason:
    """Tests for BoundaryReason enum."""

    def test_hard_boundaries(self):
        """Hard boundaries are correctly identified."""
        from app.services.pipeline.stages.moment_types import BoundaryReason

        assert BoundaryReason.PERIOD_BOUNDARY.is_hard is True
        assert BoundaryReason.LEAD_CHANGE.is_hard is True
        assert BoundaryReason.EXPLICIT_PLAY_OVERFLOW.is_hard is True
        assert BoundaryReason.ABSOLUTE_MAX_PLAYS.is_hard is True

    def test_soft_boundaries(self):
        """Soft boundaries are correctly identified."""
        from app.services.pipeline.stages.moment_types import BoundaryReason

        assert BoundaryReason.SOFT_CAP_REACHED.is_hard is False
        assert BoundaryReason.SCORING_PLAY.is_hard is False
        assert BoundaryReason.POSSESSION_CHANGE.is_hard is False
        assert BoundaryReason.STOPPAGE.is_hard is False
        assert BoundaryReason.SECOND_EXPLICIT_PLAY.is_hard is False

    def test_end_of_input_not_hard(self):
        """END_OF_INPUT is not a hard boundary."""
        from app.services.pipeline.stages.moment_types import BoundaryReason

        assert BoundaryReason.END_OF_INPUT.is_hard is False


class TestBoundaryType:
    """Tests for BoundaryType enum."""

    def test_boundary_types(self):
        """Boundary types are correct."""
        from app.services.pipeline.stages.moment_types import BoundaryType

        assert BoundaryType.HARD == "HARD"
        assert BoundaryType.SOFT == "SOFT"


class TestCompressionMetrics:
    """Tests for CompressionMetrics dataclass."""

    def test_default_values(self):
        """Default values are correct."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics()
        assert metrics.total_moments == 0
        assert metrics.total_plays == 0
        assert metrics.plays_per_moment == []
        assert metrics.explicit_plays_per_moment == []
        assert metrics.boundary_reasons == {}

    def test_pct_moments_under_soft_cap_empty(self):
        """Empty plays_per_moment returns 0%."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics()
        assert metrics.pct_moments_under_soft_cap == 0.0

    def test_pct_moments_under_soft_cap_all_under(self):
        """All moments under soft cap returns 100%."""
        from app.services.pipeline.stages.moment_types import (
            CompressionMetrics,
            SOFT_CAP_PLAYS,
        )

        metrics = CompressionMetrics(
            plays_per_moment=[3, 5, 7, SOFT_CAP_PLAYS]
        )
        assert metrics.pct_moments_under_soft_cap == 100.0

    def test_pct_moments_under_soft_cap_some_over(self):
        """Some moments over soft cap calculated correctly."""
        from app.services.pipeline.stages.moment_types import (
            CompressionMetrics,
            SOFT_CAP_PLAYS,
        )

        metrics = CompressionMetrics(
            plays_per_moment=[5, SOFT_CAP_PLAYS + 1, 3, SOFT_CAP_PLAYS + 2]
        )
        # 2 of 4 are under or equal to soft cap
        assert metrics.pct_moments_under_soft_cap == 50.0

    def test_pct_moments_single_explicit_empty(self):
        """Empty explicit_plays_per_moment returns 0%."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics()
        assert metrics.pct_moments_single_explicit == 0.0

    def test_pct_moments_single_explicit_all_single(self):
        """All moments with <=1 explicit play returns 100%."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics(
            explicit_plays_per_moment=[1, 0, 1, 1]
        )
        assert metrics.pct_moments_single_explicit == 100.0

    def test_pct_moments_single_explicit_some_multi(self):
        """Some moments with >1 explicit play calculated correctly."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics(
            explicit_plays_per_moment=[1, 2, 1, 2]
        )
        # 2 of 4 have <=1 explicit
        assert metrics.pct_moments_single_explicit == 50.0

    def test_median_plays_per_moment_empty(self):
        """Empty plays_per_moment returns 0."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics()
        assert metrics.median_plays_per_moment == 0.0

    def test_median_plays_per_moment_odd(self):
        """Odd count uses middle value."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics(
            plays_per_moment=[1, 3, 5]
        )
        assert metrics.median_plays_per_moment == 3.0

    def test_median_plays_per_moment_even(self):
        """Even count uses average of middle two."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics(
            plays_per_moment=[1, 3, 5, 7]
        )
        assert metrics.median_plays_per_moment == 4.0  # (3+5)/2

    def test_max_plays_observed_empty(self):
        """Empty plays_per_moment returns 0."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics()
        assert metrics.max_plays_observed == 0

    def test_max_plays_observed(self):
        """Max plays observed is correct."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics(
            plays_per_moment=[3, 10, 5, 8]
        )
        assert metrics.max_plays_observed == 10

    def test_to_dict(self):
        """to_dict serializes correctly."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics(
            total_moments=5,
            total_plays=30,
            plays_per_moment=[5, 6, 7, 6, 6],
            explicit_plays_per_moment=[1, 1, 2, 1, 1],
            boundary_reasons={"SCORING_PLAY": 3, "SOFT_CAP_REACHED": 2},
        )
        result = metrics.to_dict()

        assert result["total_moments"] == 5
        assert result["total_plays"] == 30
        assert result["pct_moments_under_soft_cap"] == 100.0
        assert result["pct_moments_single_explicit"] == 80.0
        assert result["median_plays_per_moment"] == 6.0
        assert result["max_plays_observed"] == 7
        assert result["avg_plays_per_moment"] == 6.0
        assert result["boundary_reasons"] == {"SCORING_PLAY": 3, "SOFT_CAP_REACHED": 2}

    def test_to_dict_empty(self):
        """to_dict handles empty metrics."""
        from app.services.pipeline.stages.moment_types import CompressionMetrics

        metrics = CompressionMetrics()
        result = metrics.to_dict()

        assert result["total_moments"] == 0
        assert result["total_plays"] == 0
        assert result["pct_moments_under_soft_cap"] == 0.0
        assert result["pct_moments_single_explicit"] == 0.0
        assert result["median_plays_per_moment"] == 0.0
        assert result["max_plays_observed"] == 0
        assert result["avg_plays_per_moment"] == 0
        assert result["boundary_reasons"] == {}


class TestConstants:
    """Tests for configuration constants."""

    def test_soft_cap_less_than_absolute_max(self):
        """Soft cap is less than absolute max."""
        from app.services.pipeline.stages.moment_types import (
            SOFT_CAP_PLAYS,
            ABSOLUTE_MAX_PLAYS,
        )

        assert SOFT_CAP_PLAYS < ABSOLUTE_MAX_PLAYS

    def test_preferred_less_than_max_explicit(self):
        """Preferred explicit plays is less than or equal to max."""
        from app.services.pipeline.stages.moment_types import (
            MAX_EXPLICIT_PLAYS_PER_MOMENT,
            PREFERRED_EXPLICIT_PLAYS,
        )

        assert PREFERRED_EXPLICIT_PLAYS <= MAX_EXPLICIT_PLAYS_PER_MOMENT

    def test_expected_values(self):
        """Constants have expected values."""
        from app.services.pipeline.stages.moment_types import (
            SOFT_CAP_PLAYS,
            ABSOLUTE_MAX_PLAYS,
            MAX_EXPLICIT_PLAYS_PER_MOMENT,
            PREFERRED_EXPLICIT_PLAYS,
        )

        assert SOFT_CAP_PLAYS == 30
        assert ABSOLUTE_MAX_PLAYS == 50
        assert MAX_EXPLICIT_PLAYS_PER_MOMENT == 5
        assert PREFERRED_EXPLICIT_PLAYS == 3
