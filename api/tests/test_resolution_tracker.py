"""Tests for resolution_tracker module."""


class TestResolutionAttempt:
    """Tests for ResolutionAttempt dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        from app.services.resolution_tracker import ResolutionAttempt

        attempt = ResolutionAttempt(
            entity_type="team",
            source_identifier="LAL",
        )

        assert attempt.status == "pending"
        assert attempt.source_context is None
        assert attempt.resolved_id is None
        assert attempt.method is None

    def test_all_fields(self):
        """All fields can be set."""
        from app.services.resolution_tracker import ResolutionAttempt

        attempt = ResolutionAttempt(
            entity_type="team",
            source_identifier="LAL",
            source_context={"game_id": 123},
            resolved_id=456,
            resolved_name="Los Angeles Lakers",
            status="success",
            method="exact_match",
            confidence=1.0,
            failure_reason=None,
            candidates=None,
            play_index=10,
        )

        assert attempt.entity_type == "team"
        assert attempt.source_identifier == "LAL"
        assert attempt.resolved_id == 456
        assert attempt.confidence == 1.0


class TestResolutionSummary:
    """Tests for ResolutionSummary dataclass."""

    def test_default_values(self):
        """Default values are initialized."""
        from app.services.resolution_tracker import ResolutionSummary

        summary = ResolutionSummary(game_id=123)

        assert summary.teams_total == 0
        assert summary.players_total == 0
        assert summary.team_resolutions == []
        assert summary.unresolved_teams == []

    def test_to_dict_empty(self):
        """to_dict works with empty summary."""
        from app.services.resolution_tracker import ResolutionSummary

        summary = ResolutionSummary(game_id=123)
        result = summary.to_dict()

        assert result["game_id"] == 123
        assert result["teams"]["total"] == 0
        assert result["teams"]["resolution_rate"] == 0
        assert result["players"]["total"] == 0
        assert result["players"]["resolution_rate"] == 0

    def test_to_dict_with_data(self):
        """to_dict includes resolution rates."""
        from app.services.resolution_tracker import ResolutionSummary

        summary = ResolutionSummary(
            game_id=123,
            teams_total=4,
            teams_resolved=3,
            teams_failed=1,
            players_total=10,
            players_resolved=8,
            players_failed=2,
        )
        result = summary.to_dict()

        assert result["teams"]["resolution_rate"] == 75.0
        assert result["players"]["resolution_rate"] == 80.0

    def test_to_dict_includes_issues(self):
        """to_dict includes issue lists."""
        from app.services.resolution_tracker import ResolutionSummary

        summary = ResolutionSummary(
            game_id=123,
            unresolved_teams=[{"source": "XYZ", "reason": "Unknown"}],
            ambiguous_teams=[{"source": "LA", "candidates": ["LAL", "LAC"]}],
        )
        result = summary.to_dict()

        assert len(result["issues"]["unresolved_teams"]) == 1
        assert len(result["issues"]["ambiguous_teams"]) == 1


class TestResolutionTracker:
    """Tests for ResolutionTracker class."""

    def test_init(self):
        """Tracker initializes correctly."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123, pipeline_run_id=456)

        assert tracker.game_id == 123
        assert tracker.pipeline_run_id == 456
        assert tracker.attempts == []

    def test_track_team_success(self):
        """Track successful team resolution."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team(
            source_abbrev="LAL",
            resolved_id=1,
            resolved_name="Los Angeles Lakers",
            method="exact_match",
            play_index=5,
        )

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].entity_type == "team"
        assert tracker.attempts[0].status == "success"
        assert tracker.attempts[0].resolved_id == 1

    def test_track_team_partial(self):
        """Track partial team resolution (no ID)."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team(
            source_abbrev="LAL",
            resolved_id=None,
            resolved_name="Lakers",
            method="fuzzy",
        )

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].status == "partial"

    def test_track_team_deduplicates(self):
        """Same team tracked multiple times increments count."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team("LAL", resolved_id=1, play_index=1)
        tracker.track_team("LAL", resolved_id=1, play_index=10)
        tracker.track_team("lal", resolved_id=1, play_index=20)  # Case insensitive

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].source_context["occurrence_count"] == 3
        assert tracker.attempts[0].source_context["last_play_index"] == 20

    def test_track_team_failure(self):
        """Track failed team resolution."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team_failure(
            source_abbrev="XYZ",
            reason="Unknown abbreviation",
            play_index=5,
        )

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].status == "failed"
        assert tracker.attempts[0].failure_reason == "Unknown abbreviation"

    def test_track_team_ambiguous(self):
        """Track ambiguous team resolution with candidates."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team_failure(
            source_abbrev="LA",
            reason="Multiple matches",
            candidates=[
                {"id": 1, "name": "Lakers"},
                {"id": 2, "name": "Clippers"},
            ],
        )

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].status == "ambiguous"
        assert len(tracker.attempts[0].candidates) == 2

    def test_track_player_success(self):
        """Track successful player resolution."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player(
            source_name="LeBron James",
            resolved_name="LeBron James",
            method="passthrough",
            play_index=10,
        )

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].entity_type == "player"
        assert tracker.attempts[0].status == "success"

    def test_track_player_skips_empty(self):
        """Empty player name is skipped."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player(source_name="", play_index=10)
        tracker.track_player(source_name=None, play_index=10)

        assert len(tracker.attempts) == 0

    def test_track_player_deduplicates(self):
        """Same player tracked multiple times increments count."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player("LeBron James", play_index=1)
        tracker.track_player("LeBron James", play_index=5)
        tracker.track_player("lebron james", play_index=10)  # Case insensitive

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].source_context["occurrence_count"] == 3

    def test_track_player_failure(self):
        """Track failed player resolution."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player_failure(
            source_name="Unknown Player",
            reason="Not in roster",
            play_index=5,
        )

        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].status == "failed"
        assert tracker.attempts[0].failure_reason == "Not in roster"

    def test_track_player_failure_skips_empty(self):
        """Empty player failure is skipped."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player_failure("", reason="Test")

        assert len(tracker.attempts) == 0

    def test_track_player_failure_deduplicates(self):
        """Same player failure not tracked twice."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player_failure("Unknown", reason="Not found")
        tracker.track_player_failure("Unknown", reason="Not found again")

        assert len(tracker.attempts) == 1

    def test_get_summary_empty(self):
        """Summary for empty tracker."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        summary = tracker.get_summary()

        assert summary.game_id == 123
        assert summary.teams_total == 0
        assert summary.players_total == 0

    def test_get_summary_teams(self):
        """Summary counts teams correctly."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team("LAL", resolved_id=1)
        tracker.track_team("BOS", resolved_id=2)
        tracker.track_team_failure("XYZ", reason="Unknown")
        tracker.track_team_failure(
            "LA",
            reason="Multiple",
            candidates=[{"id": 1}, {"id": 2}],
        )

        summary = tracker.get_summary()

        assert summary.teams_total == 4
        assert summary.teams_resolved == 2
        assert summary.teams_failed == 1
        assert summary.teams_ambiguous == 1
        assert len(summary.unresolved_teams) == 1
        assert len(summary.ambiguous_teams) == 1

    def test_get_summary_players(self):
        """Summary counts players correctly."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player("LeBron James")
        tracker.track_player("Anthony Davis")
        tracker.track_player_failure("Unknown", reason="Not found")

        summary = tracker.get_summary()

        assert summary.players_total == 3
        assert summary.players_resolved == 2
        assert summary.players_failed == 1
        assert len(summary.unresolved_players) == 1

    def test_get_summary_team_resolutions_details(self):
        """Summary includes team resolution details."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team(
            "LAL",
            resolved_id=1,
            resolved_name="Los Angeles Lakers",
            method="game_context",
        )

        summary = tracker.get_summary()

        assert len(summary.team_resolutions) == 1
        res = summary.team_resolutions[0]
        assert res["source"] == "LAL"
        assert res["resolved_id"] == 1
        assert res["resolved_name"] == "Los Angeles Lakers"
        assert res["method"] == "game_context"

    def test_get_summary_player_resolutions_details(self):
        """Summary includes player resolution details."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_player(
            "L. James",
            resolved_name="LeBron James",
            method="normalized",
        )

        summary = tracker.get_summary()

        assert len(summary.player_resolutions) == 1
        res = summary.player_resolutions[0]
        assert res["source"] == "L. James"
        assert res["resolved_name"] == "LeBron James"
        assert res["method"] == "normalized"

    def test_mixed_resolutions(self):
        """Tracker handles mixed team and player resolutions."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123, pipeline_run_id=456)

        # Track some teams
        tracker.track_team("LAL", resolved_id=1)
        tracker.track_team("BOS", resolved_id=2)

        # Track some players
        tracker.track_player("LeBron James")
        tracker.track_player("Jayson Tatum")
        tracker.track_player("LeBron James")  # Duplicate

        summary = tracker.get_summary()

        assert summary.pipeline_run_id == 456
        assert summary.teams_total == 2
        assert summary.players_total == 2  # Deduplicated

    def test_failure_after_success_increments(self):
        """Tracking same team after success just increments."""
        from app.services.resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(game_id=123)
        tracker.track_team("LAL", resolved_id=1, play_index=1)
        tracker.track_team_failure("LAL", reason="Weird", play_index=5)

        # Should only have 1 attempt, not 2
        assert len(tracker.attempts) == 1
        assert tracker.attempts[0].status == "success"
        assert tracker.attempts[0].source_context["occurrence_count"] == 2
