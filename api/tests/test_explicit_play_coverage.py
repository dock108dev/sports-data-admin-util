"""Tests for explicit play coverage invariant (Task 1.3).

These tests verify:
1. Deterministic sentence generation for PBP plays
2. Missing play injection into narratives
3. Coverage resolution logging
4. Chronological ordering of injected sentences
5. Invariant enforcement (no missing explicit plays)
"""



class TestDeterministicSentenceGeneration:
    """Tests for deterministic sentence generation from PBP data."""

    def test_three_pointer_with_player(self):
        """Three-pointer with player name generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Stephen Curry",
            "description": "Curry makes 3-pt shot from 26 ft",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Curry" in sentence or "Stephen Curry" in sentence
        assert "three" in sentence.lower()
        assert sentence.endswith(".")

    def test_layup_with_player(self):
        """Layup with player name generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "LeBron James",
            "description": "James makes driving layup",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "James" in sentence or "LeBron" in sentence
        assert "layup" in sentence.lower()

    def test_dunk_generates_sentence(self):
        """Dunk play generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Ja Morant",
            "description": "Morant dunks",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Grizzlies", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Morant" in sentence
        assert "dunk" in sentence.lower()

    def test_free_throw_made(self):
        """Made free throw generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Kevin Durant",
            "description": "Durant makes free throw 1 of 2",
            "play_type": "free throw",
        }
        game_context = {"home_team_name": "Suns", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Durant" in sentence
        assert "free throw" in sentence.lower()

    def test_free_throw_missed(self):
        """Missed free throw generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Shaquille O'Neal",
            "description": "O'Neal misses free throw 2 of 2",
            "play_type": "free throw",
        }
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "O'Neal" in sentence
        assert "miss" in sentence.lower() or "free throw" in sentence.lower()

    def test_three_pointer_missed(self):
        """Missed three-pointer generates correct sentence (not 'hit')."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Stephen Curry",
            "description": "Curry misses 3-pt shot from 28 ft",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Curry" in sentence or "Stephen Curry" in sentence
        assert "miss" in sentence.lower()
        assert "hit" not in sentence.lower()

    def test_layup_missed(self):
        """Missed layup generates correct sentence (not 'scored')."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "LeBron James",
            "description": "James misses driving layup",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "James" in sentence or "LeBron" in sentence
        assert "miss" in sentence.lower()
        assert "scored" not in sentence.lower()

    def test_dunk_missed(self):
        """Missed dunk generates correct sentence (not 'finished')."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Ja Morant",
            "description": "Morant misses dunk attempt",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Grizzlies", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Morant" in sentence
        assert "miss" in sentence.lower()
        assert "finished" not in sentence.lower()

    def test_jumper_missed(self):
        """Missed jumper generates correct sentence (not 'hit')."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Kevin Durant",
            "description": "Durant misses 18-foot jumper",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Suns", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Durant" in sentence
        assert "miss" in sentence.lower()
        assert "hit" not in sentence.lower()

    def test_rebound_generates_sentence(self):
        """Rebound generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Dennis Rodman",
            "description": "Rodman defensive rebound",
            "play_type": "rebound",
        }
        game_context = {"home_team_name": "Bulls", "away_team_name": "Jazz"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Rodman" in sentence
        assert "rebound" in sentence.lower()

    def test_steal_generates_sentence(self):
        """Steal generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Chris Paul",
            "description": "Paul steal",
            "play_type": "steal",
        }
        game_context = {"home_team_name": "Suns", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Paul" in sentence
        assert "steal" in sentence.lower()

    def test_turnover_generates_sentence(self):
        """Turnover generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "James Harden",
            "description": "Harden bad pass turnover",
            "play_type": "turnover",
        }
        game_context = {"home_team_name": "Sixers", "away_team_name": "Celtics"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Harden" in sentence
        assert "turnover" in sentence.lower()

    def test_block_generates_sentence(self):
        """Block generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Rudy Gobert",
            "description": "Gobert blocks shot",
            "play_type": "block",
        }
        game_context = {"home_team_name": "Timberwolves", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "Gobert" in sentence
        assert "block" in sentence.lower()

    def test_timeout_generates_sentence(self):
        """Timeout generates correct sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "description": "Lakers timeout",
            "team_abbreviation": "LAL",
            "play_type": "timeout",
        }
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "timeout" in sentence.lower()

    def test_no_player_name_uses_team(self):
        """When no player name, uses team name."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "description": "3-pt shot made",
            "team_abbreviation": "GSW",
            "play_type": "shot",
        }
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert "three" in sentence.lower()
        assert sentence.endswith(".")

    def test_sentence_is_grammatically_complete(self):
        """Generated sentences are grammatically complete."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        plays = [
            {"player_name": "Curry", "description": "Curry makes 3-pt shot"},
            {"player_name": "James", "description": "James dunks"},
            {"player_name": "Durant", "description": "Durant makes free throw"},
        ]
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        for play in plays:
            sentence = _generate_deterministic_sentence(play, game_context)
            # Sentence should end with period
            assert sentence.endswith(".")
            # Sentence should start with capital
            assert sentence[0].isupper()
            # Sentence should not be empty
            assert len(sentence) > 5


class TestMissingPlayInjection:
    """Tests for injecting missing explicit plays into narratives."""

    def test_inject_single_missing_play(self):
        """Single missing play is injected correctly."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
        )

        narrative = "The Lakers started the quarter strong."
        missing_play_indices = [5]
        moment_plays = [
            {"play_index": 5, "player_name": "LeBron James", "description": "James makes layup"}
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        updated, injections = _inject_missing_explicit_plays(
            narrative, missing_play_indices, moment_plays, game_context
        )

        assert len(injections) == 1
        assert "James" in updated or "LeBron" in updated
        assert injections[0]["play_index"] == 5

    def test_inject_multiple_missing_plays(self):
        """Multiple missing plays are all injected."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
        )

        narrative = "The game continued."
        missing_play_indices = [1, 3]
        moment_plays = [
            {"play_index": 1, "player_name": "Curry", "description": "Curry makes 3-pt shot"},
            {"play_index": 2, "player_name": "Durant", "description": "Durant rebound"},
            {"play_index": 3, "player_name": "Thompson", "description": "Thompson dunks"},
        ]
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        updated, injections = _inject_missing_explicit_plays(
            narrative, missing_play_indices, moment_plays, game_context
        )

        assert len(injections) == 2
        assert "Curry" in updated
        assert "Thompson" in updated

    def test_inject_preserves_chronological_order(self):
        """Injected sentences preserve play order."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
        )

        narrative = ""
        missing_play_indices = [3, 1]  # Out of order
        moment_plays = [
            {"play_index": 1, "player_name": "First Player", "description": "First makes shot"},
            {"play_index": 3, "player_name": "Third Player", "description": "Third makes layup"},
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}

        updated, injections = _inject_missing_explicit_plays(
            narrative, missing_play_indices, moment_plays, game_context
        )

        # Injections should be in chronological order (by play_index)
        assert injections[0]["play_index"] == 1
        assert injections[1]["play_index"] == 3

        # First player should appear before Third player in narrative
        first_pos = updated.find("First")
        third_pos = updated.find("Third")
        assert first_pos < third_pos

    def test_inject_appends_to_existing_narrative(self):
        """Injections are appended to existing narrative."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
        )

        narrative = "The Celtics controlled the tempo"  # No period
        missing_play_indices = [1]
        moment_plays = [
            {"play_index": 1, "player_name": "Tatum", "description": "Tatum scores"}
        ]
        game_context = {"home_team_name": "Celtics", "away_team_name": "Lakers"}

        updated, injections = _inject_missing_explicit_plays(
            narrative, missing_play_indices, moment_plays, game_context
        )

        # Original text should be preserved
        assert "Celtics controlled" in updated
        # Injection should be added
        assert "Tatum" in updated

    def test_inject_empty_narrative(self):
        """Injection works on empty narrative."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
        )

        narrative = ""
        missing_play_indices = [1]
        moment_plays = [
            {"play_index": 1, "player_name": "Mitchell", "description": "Mitchell makes 3-pt"}
        ]
        game_context = {"home_team_name": "Jazz", "away_team_name": "Lakers"}

        updated, injections = _inject_missing_explicit_plays(
            narrative, missing_play_indices, moment_plays, game_context
        )

        assert len(injections) == 1
        assert "Mitchell" in updated

    def test_no_injection_when_no_missing(self):
        """No changes when no plays are missing."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
        )

        narrative = "Mitchell hit a three-pointer."
        missing_play_indices = []
        moment_plays = []
        game_context = {"home_team_name": "Jazz", "away_team_name": "Lakers"}

        updated, injections = _inject_missing_explicit_plays(
            narrative, missing_play_indices, moment_plays, game_context
        )

        assert updated == narrative
        assert len(injections) == 0


class TestCoverageResolution:
    """Tests for coverage resolution enum and logging."""

    def test_coverage_resolution_values(self):
        """CoverageResolution has all expected values."""
        from app.services.pipeline.stages.render_narratives import CoverageResolution

        assert CoverageResolution.INITIAL_PASS.value == "initial_pass"
        assert CoverageResolution.REGENERATION_PASS.value == "regeneration_pass"
        assert CoverageResolution.INJECTION_REQUIRED.value == "injection_required"
        assert CoverageResolution.INJECTION_FAILED.value == "injection_failed"

    def test_log_coverage_resolution_returns_data(self):
        """_log_coverage_resolution returns structured data."""
        from app.services.pipeline.stages.render_narratives import (
            _log_coverage_resolution,
            CoverageResolution,
        )

        log_data = _log_coverage_resolution(
            game_id=123,
            moment_index=5,
            resolution=CoverageResolution.INITIAL_PASS,
            explicit_play_ids=[1, 2, 3],
        )

        assert log_data["game_id"] == 123
        assert log_data["moment_index"] == 5
        assert log_data["resolution"] == "initial_pass"
        assert log_data["explicit_play_count"] == 3

    def test_log_coverage_resolution_with_missing(self):
        """_log_coverage_resolution includes missing play info."""
        from app.services.pipeline.stages.render_narratives import (
            _log_coverage_resolution,
            CoverageResolution,
        )

        log_data = _log_coverage_resolution(
            game_id=123,
            moment_index=5,
            resolution=CoverageResolution.REGENERATION_PASS,
            explicit_play_ids=[1, 2, 3],
            missing_after_initial=[2],
        )

        assert log_data["missing_after_initial"] == [2]
        assert log_data["missing_after_initial_count"] == 1

    def test_log_coverage_resolution_with_injections(self):
        """_log_coverage_resolution includes injection details."""
        from app.services.pipeline.stages.render_narratives import (
            _log_coverage_resolution,
            CoverageResolution,
        )

        injections = [
            {"play_index": 2, "injected_sentence": "Player scored."}
        ]

        log_data = _log_coverage_resolution(
            game_id=123,
            moment_index=5,
            resolution=CoverageResolution.INJECTION_REQUIRED,
            explicit_play_ids=[1, 2],
            missing_after_initial=[2],
            missing_after_regen=[2],
            injections=injections,
        )

        assert log_data["injections"] == injections
        assert log_data["injection_count"] == 1


class TestInvariantEnforcement:
    """Tests verifying the invariant is enforced."""

    def test_coverage_check_finds_missing_plays(self):
        """_check_explicit_play_coverage correctly identifies missing plays."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        narrative = "The Lakers played well."
        moment = {"explicitly_narrated_play_ids": [1, 2]}
        moment_plays = [
            {"play_index": 1, "player_name": "LeBron James", "description": "James scores"},
            {"play_index": 2, "player_name": "Anthony Davis", "description": "Davis dunks"},
        ]

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)

        # Neither player is mentioned
        assert 1 in missing
        assert 2 in missing

    def test_coverage_check_passes_when_covered(self):
        """_check_explicit_play_coverage passes when all plays covered."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        narrative = "James scored and then Davis dunked to extend the lead."
        moment = {"explicitly_narrated_play_ids": [1, 2]}
        moment_plays = [
            {"play_index": 1, "player_name": "LeBron James", "description": "James scores"},
            {"play_index": 2, "player_name": "Anthony Davis", "description": "Davis dunks"},
        ]

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)

        assert missing == []

    def test_injection_guarantees_coverage(self):
        """After injection, all explicit plays are covered."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
            _check_explicit_play_coverage,
        )

        narrative = "The game continued."
        moment = {"explicitly_narrated_play_ids": [1, 2]}
        moment_plays = [
            {"play_index": 1, "player_name": "Curry", "description": "Curry makes 3-pt"},
            {"play_index": 2, "player_name": "Thompson", "description": "Thompson layup"},
        ]
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        # Initial check should find missing
        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert len(missing) == 2

        # After injection
        updated, _ = _inject_missing_explicit_plays(
            narrative, missing, moment_plays, game_context
        )

        # Check again - should pass
        still_missing = _check_explicit_play_coverage(updated, moment, moment_plays)
        assert still_missing == []


class TestSentenceQuality:
    """Tests for quality of deterministic sentences."""

    def test_no_subjective_adjectives(self):
        """Deterministic sentences contain no subjective adjectives."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        plays = [
            {"player_name": "Curry", "description": "Curry makes incredible 3-pt shot"},
            {"player_name": "James", "description": "James makes huge dunk"},
            {"player_name": "Durant", "description": "Durant amazing layup"},
        ]
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        forbidden_words = ["incredible", "huge", "amazing", "spectacular", "dominant"]

        for play in plays:
            sentence = _generate_deterministic_sentence(play, game_context)
            for word in forbidden_words:
                assert word not in sentence.lower()

    def test_no_speculation(self):
        """Deterministic sentences contain no speculation."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {"player_name": "Mitchell", "description": "Mitchell layup"}
        game_context = {"home_team_name": "Jazz", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        speculation_phrases = ["wanted to", "tried to", "needed to", "felt"]
        for phrase in speculation_phrases:
            assert phrase not in sentence.lower()

    def test_neutral_factual_language(self):
        """Deterministic sentences use neutral factual language."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {"player_name": "Thompson", "description": "Thompson makes 3-pt shot"}
        game_context = {"home_team_name": "Warriors", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        # Should be simple factual statement
        assert "Thompson" in sentence
        assert "three" in sentence.lower()
        # No crowd/atmosphere
        assert "crowd" not in sentence.lower()
        assert "energy" not in sentence.lower()


class TestEdgeCases:
    """Tests for edge cases in explicit play coverage."""

    def test_empty_explicit_play_list(self):
        """No error when no explicit plays exist."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        narrative = "Play continued."
        moment = {"explicitly_narrated_play_ids": []}
        moment_plays = [{"play_index": 1, "description": "Some play"}]

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert missing == []

    def test_missing_player_name_fallback(self):
        """Injection works when player name is missing."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "description": "Team scores on layup",
            "team_abbreviation": "LAL",
        }
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        sentence = _generate_deterministic_sentence(play, game_context)

        assert sentence.endswith(".")
        assert len(sentence) > 5

    def test_injection_with_empty_description(self):
        """Injection handles plays with empty descriptions."""
        from app.services.pipeline.stages.render_narratives import (
            _generate_deterministic_sentence,
        )

        play = {
            "player_name": "Mitchell",
            "description": "",
        }
        game_context = {"home_team_name": "Jazz", "away_team_name": "Lakers"}

        sentence = _generate_deterministic_sentence(play, game_context)

        # Should still produce something
        assert sentence.endswith(".")

    def test_multiple_injections_each_get_own_sentence(self):
        """Each missing play gets its own injected sentence."""
        from app.services.pipeline.stages.render_narratives import (
            _inject_missing_explicit_plays,
        )

        narrative = ""
        missing_play_indices = [1, 2, 3]
        moment_plays = [
            {"play_index": 1, "player_name": "Player1", "description": "Player1 scores"},
            {"play_index": 2, "player_name": "Player2", "description": "Player2 scores"},
            {"play_index": 3, "player_name": "Player3", "description": "Player3 scores"},
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}

        updated, injections = _inject_missing_explicit_plays(
            narrative, missing_play_indices, moment_plays, game_context
        )

        # Should have 3 separate injections
        assert len(injections) == 3
        # Each player should appear
        assert "Player1" in updated
        assert "Player2" in updated
        assert "Player3" in updated
