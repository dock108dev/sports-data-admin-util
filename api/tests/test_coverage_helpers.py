"""Tests for coverage_helpers stage."""


class TestCountSentences:
    """Tests for count_sentences function."""

    def test_empty_string(self):
        """Empty string returns 0."""
        from app.services.pipeline.stages.coverage_helpers import count_sentences

        assert count_sentences("") == 0

    def test_single_sentence(self):
        """Single sentence returns 1."""
        from app.services.pipeline.stages.coverage_helpers import count_sentences

        assert count_sentences("This is a sentence.") == 1

    def test_multiple_sentences(self):
        """Multiple sentences counted correctly."""
        from app.services.pipeline.stages.coverage_helpers import count_sentences

        assert count_sentences("First sentence. Second sentence.") == 2

    def test_with_exclamation(self):
        """Exclamation marks counted."""
        from app.services.pipeline.stages.coverage_helpers import count_sentences

        assert count_sentences("Wow! That was amazing.") == 2

    def test_with_question(self):
        """Question marks counted."""
        from app.services.pipeline.stages.coverage_helpers import count_sentences

        assert count_sentences("Is that true? Yes it is.") == 2


class TestExtractPlayIdentifiers:
    """Tests for extract_play_identifiers function."""

    def test_player_name(self):
        """Extracts player name."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"player_name": "LeBron James"}
        identifiers = extract_play_identifiers(play)
        assert "lebron james" in identifiers
        assert "james" in identifiers

    def test_three_pointer(self):
        """Extracts three-pointer keywords."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Smith makes 3-pt shot"}
        identifiers = extract_play_identifiers(play)
        assert "three" in identifiers or "3-pointer" in identifiers

    def test_layup(self):
        """Extracts layup keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Jones driving layup makes"}
        identifiers = extract_play_identifiers(play)
        assert "layup" in identifiers

    def test_dunk(self):
        """Extracts dunk keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Brown slam dunk"}
        identifiers = extract_play_identifiers(play)
        assert "dunk" in identifiers

    def test_rebound(self):
        """Extracts rebound keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "defensive rebound by Smith"}
        identifiers = extract_play_identifiers(play)
        assert "rebound" in identifiers

    def test_turnover(self):
        """Extracts turnover keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Smith turnover (bad pass)"}
        identifiers = extract_play_identifiers(play)
        assert "turnover" in identifiers

    def test_steal(self):
        """Extracts steal keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Jones steal"}
        identifiers = extract_play_identifiers(play)
        assert "steal" in identifiers

    def test_block(self):
        """Extracts block keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Brown block"}
        identifiers = extract_play_identifiers(play)
        assert "block" in identifiers

    def test_empty_play(self):
        """Empty play returns empty list."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        identifiers = extract_play_identifiers({})
        assert identifiers == []


class TestCheckExplicitPlayCoverage:
    """Tests for check_explicit_play_coverage function."""

    def test_empty_explicit_ids(self):
        """Empty explicit_ids returns all covered."""
        from app.services.pipeline.stages.coverage_helpers import (
            check_explicit_play_coverage,
        )

        all_covered, covered, missing = check_explicit_play_coverage(
            "Some narrative", set(), []
        )
        assert all_covered is True
        assert covered == set()
        assert missing == set()

    def test_play_covered(self):
        """Play with matching identifier is covered."""
        from app.services.pipeline.stages.coverage_helpers import (
            check_explicit_play_coverage,
        )

        narrative = "Smith hit a three-pointer to extend the lead."
        explicit_ids = {1}
        plays = [{"play_index": 1, "player_name": "Smith", "description": "3-pt shot"}]

        all_covered, covered, missing = check_explicit_play_coverage(
            narrative, explicit_ids, plays
        )
        assert all_covered is True
        assert 1 in covered

    def test_play_missing(self):
        """Play without matching identifier is missing."""
        from app.services.pipeline.stages.coverage_helpers import (
            check_explicit_play_coverage,
        )

        narrative = "The team scored on a fast break."
        explicit_ids = {1}
        plays = [{"play_index": 1, "player_name": "Jones", "description": "layup"}]

        all_covered, covered, missing = check_explicit_play_coverage(
            narrative, explicit_ids, plays
        )
        assert all_covered is False
        assert 1 in missing

    def test_partial_coverage(self):
        """Some plays covered, some missing."""
        from app.services.pipeline.stages.coverage_helpers import (
            check_explicit_play_coverage,
        )

        narrative = "Smith drove to the basket."
        explicit_ids = {1, 2}
        plays = [
            {"play_index": 1, "player_name": "Smith", "description": "layup"},
            {"play_index": 2, "player_name": "Jones", "description": "block"},
        ]

        all_covered, covered, missing = check_explicit_play_coverage(
            narrative, explicit_ids, plays
        )
        assert all_covered is False
        assert 1 in covered
        assert 2 in missing


class TestGenerateDeterministicSentence:
    """Tests for generate_deterministic_sentence function."""

    def test_three_pointer_made(self):
        """Three pointer generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Smith",
            "description": "Smith makes 3-pt shot",
            "team_abbreviation": "LAL",
        }
        context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}
        result = generate_deterministic_sentence(play, context)
        assert "Smith" in result
        assert "three" in result.lower()

    def test_three_pointer_missed(self):
        """Missed three pointer generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Smith",
            "description": "Smith misses 3-pt shot",
            "team_abbreviation": "LAL",
        }
        context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}
        result = generate_deterministic_sentence(play, context)
        assert "Smith" in result
        assert "missed" in result.lower()

    def test_layup_made(self):
        """Layup generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Jones",
            "description": "Jones makes driving layup",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Jones" in result
        assert "layup" in result.lower()

    def test_dunk(self):
        """Dunk generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Brown",
            "description": "Brown slam dunk",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Brown" in result
        assert "dunk" in result.lower()

    def test_rebound(self):
        """Rebound generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Davis",
            "description": "Davis defensive rebound",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Davis" in result
        assert "rebound" in result.lower()

    def test_turnover(self):
        """Turnover generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Williams",
            "description": "Williams turnover (bad pass)",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Williams" in result
        assert "turnover" in result.lower()

    def test_steal(self):
        """Steal generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Johnson",
            "description": "Johnson steal",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Johnson" in result
        assert "steal" in result.lower()

    def test_block(self):
        """Block generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Carter",
            "description": "Carter block",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Carter" in result
        assert "block" in result.lower()

    def test_foul(self):
        """Foul generates correct sentence."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Miller",
            "description": "Miller personal foul",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Miller" in result
        assert "foul" in result.lower()

    def test_generic_fallback(self):
        """Unknown play type gets generic fallback."""
        from app.services.pipeline.stages.coverage_helpers import (
            generate_deterministic_sentence,
        )

        play = {
            "player_name": "Unknown",
            "description": "something happened",
        }
        result = generate_deterministic_sentence(play, {})
        assert "Unknown" in result


class TestInjectMissingExplicitPlays:
    """Tests for inject_missing_explicit_plays function."""

    def test_no_missing(self):
        """No missing plays returns original narrative."""
        from app.services.pipeline.stages.coverage_helpers import (
            inject_missing_explicit_plays,
        )

        narrative = "Smith scored on a layup."
        result, injections = inject_missing_explicit_plays(
            narrative, set(), [], {}
        )
        assert result == narrative
        assert injections == []

    def test_inject_one_play(self):
        """One missing play is injected."""
        from app.services.pipeline.stages.coverage_helpers import (
            inject_missing_explicit_plays,
        )

        narrative = "The game continued."
        missing = {1}
        plays = [{"play_index": 1, "player_name": "Jones", "description": "three-pointer"}]
        context = {}

        result, injections = inject_missing_explicit_plays(
            narrative, missing, plays, context
        )
        assert len(injections) == 1
        assert "Jones" in result

    def test_inject_multiple_plays(self):
        """Multiple missing plays are injected in order."""
        from app.services.pipeline.stages.coverage_helpers import (
            inject_missing_explicit_plays,
        )

        narrative = "Play continued."
        missing = {1, 2}
        plays = [
            {"play_index": 1, "player_name": "Smith", "description": "three-pointer"},
            {"play_index": 2, "player_name": "Jones", "description": "rebound"},
        ]
        context = {}

        result, injections = inject_missing_explicit_plays(
            narrative, missing, plays, context
        )
        assert len(injections) == 2
        assert "Smith" in result
        assert "Jones" in result

    def test_handles_list_input(self):
        """Handles list input for missing_play_ids."""
        from app.services.pipeline.stages.coverage_helpers import (
            inject_missing_explicit_plays,
        )

        narrative = "The game continued."
        missing = [1]
        plays = [{"play_index": 1, "player_name": "Jones", "description": "dunk"}]

        result, injections = inject_missing_explicit_plays(
            narrative, missing, plays, {}
        )
        assert len(injections) == 1


class TestValidateNarrative:
    """Tests for validate_narrative function."""

    def test_empty_narrative_hard_error(self):
        """Empty narrative is a hard error."""
        from app.services.pipeline.stages.coverage_helpers import validate_narrative

        hard, soft, details = validate_narrative("", {}, [], 0)
        assert len(hard) > 0

    def test_valid_narrative_passes(self):
        """Valid narrative passes validation."""
        from app.services.pipeline.stages.coverage_helpers import validate_narrative

        narrative = "Smith scored on a layup. Jones grabbed the rebound."
        moment = {"explicitly_narrated_play_ids": []}
        plays = []

        hard, soft, details = validate_narrative(narrative, moment, plays, 0)
        assert len(hard) == 0

    def test_forbidden_language_hard_error(self):
        """Forbidden language is a hard error."""
        from app.services.pipeline.stages.coverage_helpers import validate_narrative

        narrative = "The momentum shifted as Smith scored."
        moment = {"explicitly_narrated_play_ids": []}

        hard, soft, details = validate_narrative(narrative, moment, [], 0)
        assert len(hard) > 0

    def test_missing_explicit_plays_soft_error(self):
        """Missing explicit plays is a soft error."""
        from app.services.pipeline.stages.coverage_helpers import validate_narrative

        narrative = "The team scored."
        moment = {"explicitly_narrated_play_ids": [1]}
        plays = [{"play_index": 1, "player_name": "Jones", "description": "three"}]

        hard, soft, details = validate_narrative(narrative, moment, plays, 0)
        assert len(soft) > 0

    def test_too_few_sentences_soft_error(self):
        """Too few sentences is a soft error."""
        from app.services.pipeline.stages.coverage_helpers import validate_narrative

        narrative = "One sentence only."  # Less than 2 sentences
        moment = {"explicitly_narrated_play_ids": []}

        hard, soft, details = validate_narrative(narrative, moment, [], 0)
        assert any("sentence" in s.lower() for s in soft)

    def test_too_many_sentences_soft_error(self):
        """Too many sentences is a soft error."""
        from app.services.pipeline.stages.coverage_helpers import validate_narrative

        narrative = "One. Two. Three. Four. Five. Six. Seven."  # More than 5 sentences
        moment = {"explicitly_narrated_play_ids": []}

        hard, soft, details = validate_narrative(narrative, moment, [], 0)
        assert any("sentence" in s.lower() for s in soft)

    def test_style_disabled(self):
        """Style validation can be disabled."""
        from app.services.pipeline.stages.coverage_helpers import validate_narrative

        narrative = "Smith scored. Jones scored."
        moment = {"explicitly_narrated_play_ids": []}

        hard, soft, details = validate_narrative(
            narrative, moment, [], 0, check_style=False
        )
        # With style disabled, fewer soft errors
        assert len(hard) == 0


class TestExtractPlayIdentifiersMore:
    """Additional tests for extract_play_identifiers function."""

    def test_free_throw(self):
        """Extracts free throw keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Smith makes free throw 1 of 2"}
        identifiers = extract_play_identifiers(play)
        assert "free throw" in identifiers

    def test_jumper(self):
        """Extracts jumper keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Jones makes 18-foot jumper"}
        identifiers = extract_play_identifiers(play)
        assert "jumper" in identifiers

    def test_jump_shot(self):
        """Extracts jump shot keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Brown makes 15-foot jump shot"}
        identifiers = extract_play_identifiers(play)
        assert "jump shot" in identifiers

    def test_foul_extraction(self):
        """Extracts foul keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Davis personal foul on Smith"}
        identifiers = extract_play_identifiers(play)
        assert "foul" in identifiers

    def test_assist(self):
        """Extracts assist keyword."""
        from app.services.pipeline.stages.coverage_helpers import (
            extract_play_identifiers,
        )

        play = {"description": "Smith assist"}
        identifiers = extract_play_identifiers(play)
        assert "assist" in identifiers


class TestLogCoverageResolution:
    """Tests for log_coverage_resolution function."""

    def test_initial_pass(self):
        """Initial pass logs correctly."""
        from app.services.pipeline.stages.coverage_helpers import (
            log_coverage_resolution,
            CoverageResolution,
        )

        # Should not raise
        log_coverage_resolution(
            moment_index=0,
            resolution=CoverageResolution.INITIAL_PASS,
            original_coverage=(True, {1, 2}, set()),
        )

    def test_regeneration_pass(self):
        """Regeneration pass logs correctly."""
        from app.services.pipeline.stages.coverage_helpers import (
            log_coverage_resolution,
            CoverageResolution,
        )

        # Should not raise
        log_coverage_resolution(
            moment_index=0,
            resolution=CoverageResolution.REGENERATION_PASS,
            original_coverage=(True, {1, 2}, set()),
        )

    def test_injection_required(self):
        """Injection required logs correctly."""
        from app.services.pipeline.stages.coverage_helpers import (
            log_coverage_resolution,
            CoverageResolution,
        )

        # Should not raise
        log_coverage_resolution(
            moment_index=0,
            resolution=CoverageResolution.INJECTION_REQUIRED,
            original_coverage=(False, {1}, {2}),
            final_coverage=(True, {1, 2}, set()),
        )

    def test_injection_without_final(self):
        """Injection without final coverage logs correctly."""
        from app.services.pipeline.stages.coverage_helpers import (
            log_coverage_resolution,
            CoverageResolution,
        )

        # Should not raise
        log_coverage_resolution(
            moment_index=0,
            resolution=CoverageResolution.INJECTION_REQUIRED,
            original_coverage=(False, {1}, {2}),
            final_coverage=None,
        )
