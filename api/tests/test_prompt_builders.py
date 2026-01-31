"""Tests for prompt_builders module."""


class TestBuildBatchPrompt:
    """Tests for build_batch_prompt function."""

    def test_basic_prompt_structure(self):
        """Prompt contains required elements."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "12:00",
                    "score_before": [0, 0],
                    "score_after": [2, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "Test player makes layup"}],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context)

        assert "Lakers" in result
        assert "Celtics" in result
        assert "Q1" in result
        assert "12:00" in result
        assert "layup" in result

    def test_explicit_plays_starred(self):
        """Explicitly narrated plays are marked with asterisk."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [0, 0],
                    "score_after": [2, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [
                    {"play_index": 1, "description": "Explicit play"},
                    {"play_index": 2, "description": "Non-explicit play"},
                ],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context)

        assert "*Explicit play" in result
        # Non-explicit should not have star prefix
        assert "Non-explicit play" in result

    def test_retry_warning_included(self):
        """Retry prompts include validation warning."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [0, 0],
                    "score_after": [0, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "Test"}],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context, is_retry=True)

        assert "IMPORTANT: Previous response failed validation" in result
        assert "2-4 sentences" in result

    def test_no_retry_warning_by_default(self):
        """Non-retry prompts don't have warning."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [0, 0],
                    "score_after": [0, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "Test"}],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context, is_retry=False)

        assert "Previous response failed validation" not in result

    def test_player_names_included(self):
        """Player name mappings included in prompt."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [0, 0],
                    "score_after": [0, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "Test"}],
            )
        ]
        game_context = {
            "home_team_name": "Lakers",
            "away_team_name": "Celtics",
            "player_names": {
                "D. Mitchell": "Donovan Mitchell",
                "L. James": "LeBron James",
            },
        }

        result = build_batch_prompt(moments_batch, game_context)

        assert "D. Mitchell=Donovan Mitchell" in result
        assert "L. James=LeBron James" in result

    def test_score_change_shown(self):
        """Score changes are indicated in moment line."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 2,
                    "start_clock": "5:00",
                    "score_before": [50, 48],
                    "score_after": [52, 48],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "Scoring play"}],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context)

        # Should show score change arrow
        assert "→ Celtics 52-48 Lakers" in result

    def test_multiple_moments_in_batch(self):
        """Multiple moments are all included."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "12:00",
                    "score_before": [0, 0],
                    "score_after": [2, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "First moment play"}],
            ),
            (
                1,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [2, 0],
                    "score_after": [4, 0],
                    "explicitly_narrated_play_ids": [2],
                },
                [{"play_index": 2, "description": "Second moment play"}],
            ),
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context)

        assert "[0]" in result
        assert "[1]" in result
        assert "First moment play" in result
        assert "Second moment play" in result

    def test_long_description_truncated(self):
        """Long play descriptions are truncated."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        long_desc = "x" * 150

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [0, 0],
                    "score_after": [0, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": long_desc}],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context)

        # Truncated to ~100 chars with ...
        assert "..." in result
        # Full long description should not be present
        assert long_desc not in result

    def test_json_format_specified(self):
        """Output format specifies JSON structure."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [0, 0],
                    "score_after": [0, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "Test"}],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context)

        assert '{"items":[{"i":0,"n":"2-4 sentence narrative"}' in result

    def test_forbidden_words_listed(self):
        """Prompt lists forbidden words."""
        from app.services.pipeline.stages.prompt_builders import build_batch_prompt

        moments_batch = [
            (
                0,
                {
                    "period": 1,
                    "start_clock": "10:00",
                    "score_before": [0, 0],
                    "score_after": [0, 0],
                    "explicitly_narrated_play_ids": [1],
                },
                [{"play_index": 1, "description": "Test"}],
            )
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_batch_prompt(moments_batch, game_context)

        assert "dominant" in result
        assert "electric" in result
        assert "FORBIDDEN" in result


class TestBuildMomentPrompt:
    """Tests for build_moment_prompt function."""

    def test_basic_structure(self):
        """Single moment prompt has required elements."""
        from app.services.pipeline.stages.prompt_builders import build_moment_prompt

        moment = {
            "period": 3,
            "start_clock": "8:00",
            "score_before": [60, 55],
            "score_after": [62, 55],
            "explicitly_narrated_play_ids": [1],
        }
        plays = [{"play_index": 1, "description": "Test player scores"}]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_moment_prompt(moment, plays, game_context, moment_index=0)

        assert "Lakers" in result
        assert "Celtics" in result
        assert "Q3" in result
        assert "8:00" in result

    def test_must_reference_marker(self):
        """Explicit plays are marked MUST REFERENCE."""
        from app.services.pipeline.stages.prompt_builders import build_moment_prompt

        moment = {
            "period": 1,
            "start_clock": "10:00",
            "score_before": [0, 0],
            "score_after": [2, 0],
            "explicitly_narrated_play_ids": [1],
        }
        plays = [
            {"play_index": 1, "description": "Explicit play"},
            {"play_index": 2, "description": "Other play"},
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_moment_prompt(moment, plays, game_context, moment_index=0)

        assert "[MUST REFERENCE]" in result
        assert "[MUST REFERENCE] Explicit play" in result

    def test_retry_note_included(self):
        """Retry prompts include validation note."""
        from app.services.pipeline.stages.prompt_builders import build_moment_prompt

        moment = {
            "period": 1,
            "start_clock": "10:00",
            "score_before": [0, 0],
            "score_after": [0, 0],
            "explicitly_narrated_play_ids": [1],
        }
        plays = [{"play_index": 1, "description": "Test"}]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_moment_prompt(
            moment, plays, game_context, moment_index=0, is_retry=True
        )

        assert "PREVIOUS RESPONSE FAILED VALIDATION" in result

    def test_score_display(self):
        """Scores are displayed correctly."""
        from app.services.pipeline.stages.prompt_builders import build_moment_prompt

        moment = {
            "period": 4,
            "start_clock": "2:00",
            "score_before": [100, 98],
            "score_after": [100, 101],
            "explicitly_narrated_play_ids": [1],
        }
        plays = [{"play_index": 1, "description": "Game winner"}]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_moment_prompt(moment, plays, game_context, moment_index=0)

        assert "Celtics 100 - Lakers 98" in result
        assert "Celtics 100 - Lakers 101" in result

    def test_player_names_in_prompt(self):
        """Player name rules included."""
        from app.services.pipeline.stages.prompt_builders import build_moment_prompt

        moment = {
            "period": 1,
            "start_clock": "10:00",
            "score_before": [0, 0],
            "score_after": [0, 0],
            "explicitly_narrated_play_ids": [1],
        }
        plays = [{"play_index": 1, "description": "Test"}]
        game_context = {
            "home_team_name": "Lakers",
            "away_team_name": "Celtics",
            "player_names": {"D. Mitchell": "Donovan Mitchell"},
        }

        result = build_moment_prompt(moment, plays, game_context, moment_index=0)

        assert "D. Mitchell=Donovan Mitchell" in result

    def test_response_format_instruction(self):
        """Prompt specifies response format."""
        from app.services.pipeline.stages.prompt_builders import build_moment_prompt

        moment = {
            "period": 1,
            "start_clock": "10:00",
            "score_before": [0, 0],
            "score_after": [0, 0],
            "explicitly_narrated_play_ids": [1],
        }
        plays = [{"play_index": 1, "description": "Test"}]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        result = build_moment_prompt(moment, plays, game_context, moment_index=0)

        assert "ONLY the narrative text" in result
        assert "2-4 sentences" in result

    def test_default_values(self):
        """Missing fields use defaults."""
        from app.services.pipeline.stages.prompt_builders import build_moment_prompt

        moment = {"explicitly_narrated_play_ids": [1]}  # Minimal moment
        plays = [{"play_index": 1, "description": "Test"}]
        game_context = {}  # Empty context

        result = build_moment_prompt(moment, plays, game_context, moment_index=0)

        # Should use defaults
        assert "Home" in result
        assert "Away" in result
        assert "Q1" in result  # Default period 1
