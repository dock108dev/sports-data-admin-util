"""Tests for score_detection stage."""


class TestGetLeadState:
    """Tests for get_lead_state function."""

    def test_home_leading(self):
        """Home team leading returns HOME."""
        from app.services.pipeline.stages.score_detection import get_lead_state

        assert get_lead_state(10, 5) == "HOME"
        assert get_lead_state(1, 0) == "HOME"
        assert get_lead_state(100, 99) == "HOME"

    def test_away_leading(self):
        """Away team leading returns AWAY."""
        from app.services.pipeline.stages.score_detection import get_lead_state

        assert get_lead_state(5, 10) == "AWAY"
        assert get_lead_state(0, 1) == "AWAY"
        assert get_lead_state(99, 100) == "AWAY"

    def test_tied(self):
        """Tied game returns TIE."""
        from app.services.pipeline.stages.score_detection import get_lead_state

        assert get_lead_state(0, 0) == "TIE"
        assert get_lead_state(10, 10) == "TIE"
        assert get_lead_state(50, 50) == "TIE"


class TestIsLeadChange:
    """Tests for is_lead_change function."""

    def test_home_to_away_is_lead_change(self):
        """HOME lead to AWAY lead is a lead change."""
        from app.services.pipeline.stages.score_detection import is_lead_change

        assert is_lead_change(10, 5, 10, 15) is True

    def test_away_to_home_is_lead_change(self):
        """AWAY lead to HOME lead is a lead change."""
        from app.services.pipeline.stages.score_detection import is_lead_change

        assert is_lead_change(5, 10, 15, 10) is True

    def test_tied_to_lead_not_lead_change(self):
        """Going from tied to a lead is NOT a lead change."""
        from app.services.pipeline.stages.score_detection import is_lead_change

        assert is_lead_change(10, 10, 12, 10) is False
        assert is_lead_change(10, 10, 10, 12) is False

    def test_lead_to_tied_not_lead_change(self):
        """Going from a lead to tied is NOT a lead change."""
        from app.services.pipeline.stages.score_detection import is_lead_change

        assert is_lead_change(12, 10, 12, 12) is False
        assert is_lead_change(10, 12, 12, 12) is False

    def test_same_lead_not_lead_change(self):
        """Maintaining the same lead is NOT a lead change."""
        from app.services.pipeline.stages.score_detection import is_lead_change

        assert is_lead_change(10, 5, 15, 8) is False  # Home still leading
        assert is_lead_change(5, 10, 8, 15) is False  # Away still leading

    def test_tied_to_tied_not_lead_change(self):
        """Remaining tied is NOT a lead change."""
        from app.services.pipeline.stages.score_detection import is_lead_change

        assert is_lead_change(10, 10, 10, 10) is False


class TestIsScoringPlay:
    """Tests for is_scoring_play function."""

    def test_first_play_with_score_is_scoring(self):
        """First play with non-zero score is scoring."""
        from app.services.pipeline.stages.score_detection import is_scoring_play

        event = {"home_score": 2, "away_score": 0}
        assert is_scoring_play(event, None) is True

    def test_first_play_no_score_not_scoring(self):
        """First play with zero score is not scoring."""
        from app.services.pipeline.stages.score_detection import is_scoring_play

        event = {"home_score": 0, "away_score": 0}
        assert is_scoring_play(event, None) is False

    def test_home_score_change_is_scoring(self):
        """Home score increase is a scoring play."""
        from app.services.pipeline.stages.score_detection import is_scoring_play

        prev = {"home_score": 10, "away_score": 5}
        curr = {"home_score": 12, "away_score": 5}
        assert is_scoring_play(curr, prev) is True

    def test_away_score_change_is_scoring(self):
        """Away score increase is a scoring play."""
        from app.services.pipeline.stages.score_detection import is_scoring_play

        prev = {"home_score": 10, "away_score": 5}
        curr = {"home_score": 10, "away_score": 8}
        assert is_scoring_play(curr, prev) is True

    def test_no_score_change_not_scoring(self):
        """No score change is not a scoring play."""
        from app.services.pipeline.stages.score_detection import is_scoring_play

        prev = {"home_score": 10, "away_score": 5}
        curr = {"home_score": 10, "away_score": 5}
        assert is_scoring_play(curr, prev) is False

    def test_missing_scores_default_to_zero(self):
        """Missing scores default to zero."""
        from app.services.pipeline.stages.score_detection import is_scoring_play

        prev = {"home_score": 0, "away_score": 0}
        curr = {}  # Missing scores default to 0
        assert is_scoring_play(curr, prev) is False

    def test_partial_missing_scores(self):
        """Partial missing scores work correctly."""
        from app.services.pipeline.stages.score_detection import is_scoring_play

        prev = {"home_score": 2}  # away_score missing, defaults to 0
        curr = {"away_score": 3}  # home_score missing, defaults to 0
        # prev: 2-0, curr: 0-3 -> both changed
        assert is_scoring_play(curr, prev) is True


class TestIsLeadChangePlay:
    """Tests for is_lead_change_play function."""

    def test_first_play_never_lead_change(self):
        """First play cannot be a lead change."""
        from app.services.pipeline.stages.score_detection import is_lead_change_play

        event = {"home_score": 10, "away_score": 5}
        assert is_lead_change_play(event, None) is False

    def test_lead_change_detected(self):
        """Lead change play correctly detected."""
        from app.services.pipeline.stages.score_detection import is_lead_change_play

        prev = {"home_score": 10, "away_score": 5}
        curr = {"home_score": 10, "away_score": 15}
        assert is_lead_change_play(curr, prev) is True

    def test_no_lead_change_detected(self):
        """Non lead-change play correctly detected."""
        from app.services.pipeline.stages.score_detection import is_lead_change_play

        prev = {"home_score": 10, "away_score": 5}
        curr = {"home_score": 12, "away_score": 5}
        assert is_lead_change_play(curr, prev) is False


class TestGetScoreBeforeMoment:
    """Tests for get_score_before_moment function."""

    def test_first_moment_is_zero(self):
        """First moment (index 0) returns [0, 0]."""
        from app.services.pipeline.stages.score_detection import get_score_before_moment

        events = [{"home_score": 2, "away_score": 0}]
        assert get_score_before_moment(events, 0) == (0, 0)

    def test_gets_previous_event_score(self):
        """Returns score from event before moment start."""
        from app.services.pipeline.stages.score_detection import get_score_before_moment

        events = [
            {"home_score": 2, "away_score": 0},
            {"home_score": 2, "away_score": 3},
            {"home_score": 5, "away_score": 3},
        ]
        # Moment starts at index 2, so should get score from index 1
        assert get_score_before_moment(events, 2) == (2, 3)

    def test_missing_scores_default_to_zero(self):
        """Missing scores in previous event default to zero."""
        from app.services.pipeline.stages.score_detection import get_score_before_moment

        events = [
            {},  # No scores
            {"home_score": 5, "away_score": 3},
        ]
        assert get_score_before_moment(events, 1) == (0, 0)


class TestGetScoreAfterMoment:
    """Tests for get_score_after_moment function."""

    def test_gets_last_event_score(self):
        """Returns score from the last event."""
        from app.services.pipeline.stages.score_detection import get_score_after_moment

        event = {"home_score": 10, "away_score": 8}
        assert get_score_after_moment(event) == (10, 8)

    def test_missing_scores_default_to_zero(self):
        """Missing scores default to zero."""
        from app.services.pipeline.stages.score_detection import get_score_after_moment

        assert get_score_after_moment({}) == (0, 0)
        assert get_score_after_moment({"home_score": 5}) == (5, 0)
        assert get_score_after_moment({"away_score": 3}) == (0, 3)
