"""Tests for play_classification stage."""


class TestIsTurnoverPlay:
    """Tests for is_turnover_play function."""

    def test_turnover_play_type(self):
        """Turnover play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"play_type": "turnover"}
        assert is_turnover_play(event) is True

    def test_steal_play_type(self):
        """Steal play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"play_type": "steal"}
        assert is_turnover_play(event) is True

    def test_traveling_play_type(self):
        """Traveling play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"play_type": "traveling"}
        assert is_turnover_play(event) is True

    def test_play_type_with_spaces(self):
        """Play type with spaces is normalized."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"play_type": "bad pass"}
        assert is_turnover_play(event) is True

    def test_description_turnover_keyword(self):
        """Turnover in description is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"play_type": "other", "description": "Smith turnover"}
        assert is_turnover_play(event) is True

    def test_description_steal_keyword(self):
        """Steal in description is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"play_type": "other", "description": "Jones steal from Smith"}
        assert is_turnover_play(event) is True

    def test_description_lost_ball(self):
        """Lost ball in description is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"description": "lost ball by Smith"}
        assert is_turnover_play(event) is True

    def test_description_bad_pass(self):
        """Bad pass in description is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"description": "bad pass by Jones"}
        assert is_turnover_play(event) is True

    def test_description_traveling(self):
        """Traveling in description is detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"description": "traveling violation"}
        assert is_turnover_play(event) is True

    def test_non_turnover_play(self):
        """Non-turnover play is not detected."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        event = {"play_type": "made_shot", "description": "Smith makes 2-pt shot"}
        assert is_turnover_play(event) is False

    def test_empty_event(self):
        """Empty event is not a turnover."""
        from app.services.pipeline.stages.play_classification import is_turnover_play

        assert is_turnover_play({}) is False


class TestIsPeriodBoundary:
    """Tests for is_period_boundary function."""

    def test_first_play_not_boundary(self):
        """First play (no previous) is not a boundary."""
        from app.services.pipeline.stages.play_classification import is_period_boundary

        event = {"quarter": 1}
        assert is_period_boundary(event, None) is False

    def test_same_period_not_boundary(self):
        """Same period is not a boundary."""
        from app.services.pipeline.stages.play_classification import is_period_boundary

        prev = {"quarter": 1}
        curr = {"quarter": 1}
        assert is_period_boundary(curr, prev) is False

    def test_period_change_is_boundary(self):
        """Period change is a boundary."""
        from app.services.pipeline.stages.play_classification import is_period_boundary

        prev = {"quarter": 1}
        curr = {"quarter": 2}
        assert is_period_boundary(curr, prev) is True

    def test_quarter_three_to_four(self):
        """Q3 to Q4 is a boundary."""
        from app.services.pipeline.stages.play_classification import is_period_boundary

        prev = {"quarter": 3}
        curr = {"quarter": 4}
        assert is_period_boundary(curr, prev) is True

    def test_missing_quarter_defaults_to_one(self):
        """Missing quarter defaults to 1."""
        from app.services.pipeline.stages.play_classification import is_period_boundary

        prev = {}  # defaults to quarter 1
        curr = {"quarter": 2}
        assert is_period_boundary(curr, prev) is True

        prev = {"quarter": 1}
        curr = {}  # defaults to quarter 1
        assert is_period_boundary(curr, prev) is False


class TestIsStoppagePlay:
    """Tests for is_stoppage_play function."""

    def test_timeout_play_type(self):
        """Timeout play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "timeout"}
        assert is_stoppage_play(event) is True

    def test_full_timeout_play_type(self):
        """Full timeout play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "full_timeout"}
        assert is_stoppage_play(event) is True

    def test_official_timeout_play_type(self):
        """Official timeout play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "official_timeout"}
        assert is_stoppage_play(event) is True

    def test_tv_timeout_play_type(self):
        """TV timeout play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "tv_timeout"}
        assert is_stoppage_play(event) is True

    def test_review_play_type(self):
        """Review play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "review"}
        assert is_stoppage_play(event) is True

    def test_instant_replay_play_type(self):
        """Instant replay play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "instant_replay"}
        assert is_stoppage_play(event) is True

    def test_ejection_play_type(self):
        """Ejection play_type is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "ejection"}
        assert is_stoppage_play(event) is True

    def test_description_timeout(self):
        """Timeout in description is detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "other", "description": "Hawks timeout"}
        assert is_stoppage_play(event) is True

    def test_non_stoppage_play(self):
        """Non-stoppage play is not detected."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        event = {"play_type": "made_shot", "description": "Smith makes 3-pt shot"}
        assert is_stoppage_play(event) is False

    def test_empty_event(self):
        """Empty event is not a stoppage."""
        from app.services.pipeline.stages.play_classification import is_stoppage_play

        assert is_stoppage_play({}) is False


class TestIsNotablePlay:
    """Tests for is_notable_play function."""

    def test_block_is_notable(self):
        """Block play_type is notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "block"}) is True
        assert is_notable_play({"play_type": "blocked_shot"}) is True

    def test_steal_is_notable(self):
        """Steal play_type is notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "steal"}) is True

    def test_turnover_is_notable(self):
        """Turnover play_type is notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "turnover"}) is True

    def test_rebound_is_notable(self):
        """Rebound play_types are notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "offensive_rebound"}) is True
        assert is_notable_play({"play_type": "defensive_rebound"}) is True

    def test_assist_is_notable(self):
        """Assist play_type is notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "assist"}) is True

    def test_foul_is_notable(self):
        """Foul play_types are notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "foul"}) is True
        assert is_notable_play({"play_type": "personal_foul"}) is True
        assert is_notable_play({"play_type": "shooting_foul"}) is True
        assert is_notable_play({"play_type": "technical_foul"}) is True
        assert is_notable_play({"play_type": "flagrant_foul"}) is True

    def test_jump_ball_is_notable(self):
        """Jump ball is notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "jump_ball"}) is True
        assert is_notable_play({"play_type": "jumpball"}) is True

    def test_made_shot_not_notable(self):
        """Made shot is not notable (it's scoring, handled separately)."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({"play_type": "made_shot"}) is False

    def test_empty_event(self):
        """Empty event is not notable."""
        from app.services.pipeline.stages.play_classification import is_notable_play

        assert is_notable_play({}) is False


class TestShouldStartNewMoment:
    """Tests for should_start_new_moment function."""

    def test_first_play_starts_moment(self):
        """First play always starts a new moment."""
        from app.services.pipeline.stages.play_classification import (
            should_start_new_moment,
        )

        event = {"quarter": 1}
        assert should_start_new_moment(event, None, 0) is True

    def test_period_boundary_starts_moment(self):
        """Period change starts a new moment."""
        from app.services.pipeline.stages.play_classification import (
            should_start_new_moment,
        )

        prev = {"quarter": 1}
        curr = {"quarter": 2}
        assert should_start_new_moment(curr, prev, 1) is True

    def test_soft_cap_exceeded_starts_moment(self):
        """Soft cap exceeded starts a new moment."""
        from app.services.pipeline.stages.play_classification import (
            should_start_new_moment,
        )

        prev = {"quarter": 1}
        curr = {"quarter": 1}
        # SOFT_CAP_PLAYS is 8, so at 8 we should start new
        assert should_start_new_moment(curr, prev, 8) is True

    def test_after_stoppage_starts_moment(self):
        """Play after stoppage starts a new moment."""
        from app.services.pipeline.stages.play_classification import (
            should_start_new_moment,
        )

        prev = {"quarter": 1, "play_type": "timeout"}
        curr = {"quarter": 1}
        assert should_start_new_moment(curr, prev, 1) is True

    def test_normal_play_continues_moment(self):
        """Normal play in same period continues moment."""
        from app.services.pipeline.stages.play_classification import (
            should_start_new_moment,
        )

        prev = {"quarter": 1, "play_type": "made_shot"}
        curr = {"quarter": 1}
        assert should_start_new_moment(curr, prev, 3) is False

    def test_under_soft_cap_continues(self):
        """Under soft cap continues moment."""
        from app.services.pipeline.stages.play_classification import (
            should_start_new_moment,
        )

        prev = {"quarter": 1}
        curr = {"quarter": 1}
        assert should_start_new_moment(curr, prev, 5) is False
