"""
Unit tests for Header Reset Generator.

These tests validate:
- Every beat_type produces a valid header
- One-sentence enforcement
- Determinism across runs
- Constraint enforcement (no !, no ?, etc.)

ISSUE: Header Reset Generator (Chapters-First Architecture)
"""

from app.services.chapters.beat_classifier import BeatType
from app.services.chapters.story_section import StorySection
from app.services.chapters.header_reset import (
    # Types
    HeaderContext,
    HEADER_TEMPLATES,
    # Functions
    build_header_context,
    generate_header,
    generate_header_for_section,
    generate_all_headers,
    validate_header,
    validate_all_headers,
    format_headers_debug,
    _select_template,
)


# ============================================================================
# TEST HELPERS
# ============================================================================


def make_section(
    section_index: int,
    beat_type: BeatType,
    home_score: int = 50,
    away_score: int = 48,
) -> StorySection:
    """Create a StorySection for testing."""
    return StorySection(
        section_index=section_index,
        beat_type=beat_type,
        chapters_included=[f"ch_{section_index:03d}"],
        start_score={"home": home_score - 10, "away": away_score - 8},
        end_score={"home": home_score, "away": away_score},
    )


def make_context(
    beat_type: BeatType,
    section_index: int = 0,
    is_first_section: bool = False,
    is_overtime: bool = False,
    is_closing: bool = False,
    score_tied: bool = False,
    score_margin: int = 2,
) -> HeaderContext:
    """Create a HeaderContext for testing."""
    return HeaderContext(
        beat_type=beat_type,
        section_index=section_index,
        is_first_section=is_first_section,
        is_overtime=is_overtime,
        is_closing=is_closing,
        score_tied=score_tied,
        score_margin=score_margin,
    )


# ============================================================================
# TEST: TEMPLATE COVERAGE
# ============================================================================


class TestTemplateCoverage:
    """Tests for template coverage of all beat types."""

    def test_all_beat_types_have_templates(self):
        """Every BeatType has at least one template."""
        for beat_type in BeatType:
            assert beat_type in HEADER_TEMPLATES, f"Missing template for {beat_type}"
            assert len(HEADER_TEMPLATES[beat_type]) > 0, (
                f"Empty templates for {beat_type}"
            )

    def test_all_templates_are_valid_sentences(self):
        """Every template is a valid single sentence."""
        for beat_type, templates in HEADER_TEMPLATES.items():
            for template in templates:
                errors = validate_header(template)
                assert not errors, (
                    f"Invalid template for {beat_type}: {template} - {errors}"
                )


# ============================================================================
# TEST: HEADER GENERATION FOR EACH BEAT TYPE
# ============================================================================


class TestHeaderGenerationByBeatType:
    """Tests for header generation for each beat type."""

    def test_fast_start_header(self):
        """FAST_START produces valid header."""
        context = make_context(BeatType.FAST_START)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_missed_shot_fest_header(self):
        """MISSED_SHOT_FEST produces valid header."""
        context = make_context(BeatType.MISSED_SHOT_FEST)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_back_and_forth_header(self):
        """BACK_AND_FORTH produces valid header."""
        context = make_context(BeatType.BACK_AND_FORTH)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_early_control_header(self):
        """EARLY_CONTROL produces valid header."""
        context = make_context(BeatType.EARLY_CONTROL)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_run_header(self):
        """RUN produces valid header."""
        context = make_context(BeatType.RUN)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_response_header(self):
        """RESPONSE produces valid header."""
        context = make_context(BeatType.RESPONSE)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_stall_header(self):
        """STALL produces valid header."""
        context = make_context(BeatType.STALL)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_crunch_setup_header(self):
        """CRUNCH_SETUP produces valid header."""
        context = make_context(BeatType.CRUNCH_SETUP)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_closing_sequence_header(self):
        """CLOSING_SEQUENCE produces valid header."""
        context = make_context(BeatType.CLOSING_SEQUENCE, is_closing=True)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_overtime_header(self):
        """OVERTIME produces valid header."""
        context = make_context(BeatType.OVERTIME, is_overtime=True)
        header = generate_header(context)

        assert header
        assert not validate_header(header)

    def test_overtime_tied_header(self):
        """OVERTIME with tied score produces special header."""
        context = make_context(
            BeatType.OVERTIME,
            is_overtime=True,
            score_tied=True,
        )
        header = generate_header(context)

        assert "tied" in header.lower()
        assert not validate_header(header)


# ============================================================================
# TEST: ONE-SENTENCE ENFORCEMENT
# ============================================================================


class TestOneSentenceEnforcement:
    """Tests for one-sentence constraint."""

    def test_header_ends_with_period(self):
        """All headers end with a period."""
        for beat_type in BeatType:
            context = make_context(beat_type)
            header = generate_header(context)

            assert header.endswith("."), (
                f"{beat_type} header doesn't end with period: {header}"
            )

    def test_header_has_exactly_one_period(self):
        """All headers have exactly one period."""
        for beat_type in BeatType:
            context = make_context(beat_type)
            header = generate_header(context)

            period_count = header.count(".")
            assert period_count == 1, (
                f"{beat_type} header has {period_count} periods: {header}"
            )

    def test_header_no_exclamation(self):
        """No headers contain exclamation points."""
        for beat_type in BeatType:
            context = make_context(beat_type)
            header = generate_header(context)

            assert "!" not in header, f"{beat_type} header has exclamation: {header}"

    def test_header_no_question(self):
        """No headers contain question marks."""
        for beat_type in BeatType:
            context = make_context(beat_type)
            header = generate_header(context)

            assert "?" not in header, f"{beat_type} header has question: {header}"


# ============================================================================
# TEST: DETERMINISM
# ============================================================================


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_context_same_header(self):
        """Same context produces same header every time."""
        context = make_context(BeatType.RUN, section_index=2)

        headers = [generate_header(context) for _ in range(10)]

        # All headers should be identical
        assert len(set(headers)) == 1

    def test_section_index_affects_template(self):
        """Different section indices may select different templates."""
        # For beat types with multiple templates
        beat_type = BeatType.BACK_AND_FORTH
        templates = HEADER_TEMPLATES[beat_type]

        if len(templates) > 1:
            context0 = make_context(beat_type, section_index=0)
            context1 = make_context(beat_type, section_index=1)

            header0 = generate_header(context0)
            header1 = generate_header(context1)

            # Headers may differ due to template rotation
            # But both should be valid
            assert not validate_header(header0)
            assert not validate_header(header1)

    def test_determinism_across_all_beat_types(self):
        """All beat types produce deterministic output."""
        for beat_type in BeatType:
            context = make_context(beat_type, section_index=3)

            headers = [generate_header(context) for _ in range(5)]
            assert len(set(headers)) == 1, f"{beat_type} is not deterministic"


# ============================================================================
# TEST: TEMPLATE SELECTION
# ============================================================================


class TestTemplateSelection:
    """Tests for deterministic template selection."""

    def test_template_selection_uses_index(self):
        """Template selection uses section_index for variation."""
        beat_type = BeatType.BACK_AND_FORTH
        templates = HEADER_TEMPLATES[beat_type]

        selected = [_select_template(beat_type, i) for i in range(len(templates) * 2)]

        # Should cycle through templates
        for i, template in enumerate(templates):
            assert selected[i] == template

    def test_template_selection_wraps(self):
        """Template selection wraps around when index exceeds template count."""
        beat_type = BeatType.FAST_START
        templates = HEADER_TEMPLATES[beat_type]

        # Index way beyond template count
        selected = _select_template(beat_type, 100)

        expected_index = 100 % len(templates)
        assert selected == templates[expected_index]


# ============================================================================
# TEST: CONTEXT BUILDING
# ============================================================================


class TestContextBuilding:
    """Tests for building header context from sections."""

    def test_build_context_from_section(self):
        """Context is built correctly from StorySection."""
        section = make_section(2, BeatType.RUN, home_score=60, away_score=55)
        context = build_header_context(section)

        assert context.beat_type == BeatType.RUN
        assert context.section_index == 2
        assert context.is_first_section is False
        assert context.is_overtime is False
        assert context.score_margin == 5

    def test_context_detects_first_section(self):
        """Context correctly identifies first section."""
        section = make_section(0, BeatType.FAST_START)
        context = build_header_context(section)

        assert context.is_first_section is True

    def test_context_detects_overtime(self):
        """Context correctly identifies overtime."""
        section = make_section(5, BeatType.OVERTIME)
        context = build_header_context(section)

        assert context.is_overtime is True

    def test_context_detects_closing(self):
        """Context correctly identifies closing sequence."""
        section = make_section(4, BeatType.CLOSING_SEQUENCE)
        context = build_header_context(section)

        assert context.is_closing is True

    def test_context_detects_tied_score(self):
        """Context correctly identifies tied score."""
        section = make_section(3, BeatType.CRUNCH_SETUP, home_score=80, away_score=80)
        context = build_header_context(section)

        assert context.score_tied is True
        assert context.score_margin == 0


# ============================================================================
# TEST: BATCH GENERATION
# ============================================================================


class TestBatchGeneration:
    """Tests for batch header generation."""

    def test_generate_all_headers(self):
        """Generate headers for multiple sections."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.BACK_AND_FORTH),
            make_section(2, BeatType.RUN),
            make_section(3, BeatType.CLOSING_SEQUENCE),
        ]

        headers = generate_all_headers(sections)

        assert len(headers) == 4
        for header in headers:
            assert not validate_header(header)

    def test_generate_header_for_section(self):
        """Convenience function works correctly."""
        section = make_section(1, BeatType.RESPONSE)
        header = generate_header_for_section(section)

        assert header
        assert not validate_header(header)


# ============================================================================
# TEST: VALIDATION
# ============================================================================


class TestValidation:
    """Tests for header validation."""

    def test_valid_header_passes(self):
        """Valid header has no errors."""
        errors = validate_header("This is a valid header.")
        assert errors == []

    def test_empty_header_fails(self):
        """Empty header fails validation."""
        errors = validate_header("")
        assert len(errors) > 0

    def test_whitespace_header_fails(self):
        """Whitespace-only header fails validation."""
        errors = validate_header("   ")
        assert len(errors) > 0

    def test_exclamation_fails(self):
        """Header with exclamation fails validation."""
        errors = validate_header("This is exciting!")
        assert any("exclamation" in e.lower() for e in errors)

    def test_question_fails(self):
        """Header with question mark fails validation."""
        errors = validate_header("Is this valid?")
        assert any("question" in e.lower() for e in errors)

    def test_no_period_fails(self):
        """Header without period fails validation."""
        errors = validate_header("This has no period")
        assert any("period" in e.lower() for e in errors)

    def test_multiple_periods_fails(self):
        """Header with multiple periods fails validation."""
        errors = validate_header("Two sentences. Both here.")
        assert any("2 periods" in e for e in errors)

    def test_validate_all_headers(self):
        """Batch validation returns errors by index."""
        headers = [
            "Valid header.",
            "Invalid!",
            "Also valid.",
            "No period",
        ]

        errors = validate_all_headers(headers)

        assert 0 not in errors  # Valid
        assert 1 in errors  # Has !
        assert 2 not in errors  # Valid
        assert 3 in errors  # No period


# ============================================================================
# TEST: DEBUG OUTPUT
# ============================================================================


class TestDebugOutput:
    """Tests for debug output formatting."""

    def test_format_headers_debug(self):
        """Debug output includes all sections."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.RUN),
        ]
        headers = generate_all_headers(sections)

        output = format_headers_debug(sections, headers)

        assert "Section 0" in output
        assert "FAST_START" in output
        assert "Section 1" in output
        assert "RUN" in output


# ============================================================================
# TEST: SERIALIZATION
# ============================================================================


class TestSerialization:
    """Tests for serialization."""

    def test_context_to_dict(self):
        """HeaderContext serializes correctly."""
        context = make_context(
            BeatType.CRUNCH_SETUP,
            section_index=3,
            is_closing=False,
            score_margin=4,
        )

        data = context.to_dict()

        assert data["beat_type"] == "CRUNCH_SETUP"
        assert data["section_index"] == 3
        assert data["score_margin"] == 4


# ============================================================================
# TEST: CONSTRAINT ENFORCEMENT
# ============================================================================


class TestConstraintEnforcement:
    """Tests for header constraint enforcement."""

    def test_no_player_names_in_templates(self):
        """Templates contain no player names."""
        # Common NBA player names that should NOT appear
        forbidden_names = [
            "LeBron",
            "Curry",
            "Durant",
            "Giannis",
            "Doncic",
            "James",
            "Stephen",
            "Kevin",
            "Luka",
        ]

        for beat_type, templates in HEADER_TEMPLATES.items():
            for template in templates:
                for name in forbidden_names:
                    assert name.lower() not in template.lower(), (
                        f"Template for {beat_type} contains player name: {name}"
                    )

    def test_no_numeric_scores_except_allowed(self):
        """Templates don't contain numeric scores (except OT/closing)."""
        # Most templates should not have numbers
        for beat_type, templates in HEADER_TEMPLATES.items():
            if beat_type not in (BeatType.OVERTIME, BeatType.CLOSING_SEQUENCE):
                for template in templates:
                    # Check for score-like patterns (numbers)
                    has_numbers = any(c.isdigit() for c in template)
                    assert not has_numbers, (
                        f"Template for {beat_type} contains numbers: {template}"
                    )

    def test_headers_are_boring(self):
        """Headers don't contain hype words."""
        hype_words = [
            "amazing",
            "incredible",
            "unbelievable",
            "epic",
            "dominant",
            "crushing",
            "explosive",
            "thrilling",
        ]

        for beat_type in BeatType:
            context = make_context(beat_type)
            header = generate_header(context)

            for word in hype_words:
                assert word.lower() not in header.lower(), (
                    f"Header for {beat_type} contains hype word '{word}': {header}"
                )
