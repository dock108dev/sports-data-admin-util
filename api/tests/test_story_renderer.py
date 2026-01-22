"""
Unit tests for Story Renderer.

These tests validate:
- Input building from StorySections
- Prompt construction
- Mock rendering
- Input validation
- Result validation
- Output contract (JSON with compact_story)

ISSUE: AI Story Rendering (Chapters-First Architecture)
"""

import json
import pytest

from app.services.chapters.beat_classifier import BeatType
from app.services.chapters.story_section import (
    StorySection,
    TeamStatDelta,
    PlayerStatDelta,
)
from app.services.chapters.story_renderer import (
    # Types
    ClosingContext,
    SectionRenderInput,
    StoryRenderInput,
    StoryRenderResult,
    StoryRenderError,
    # Functions
    build_section_render_input,
    build_story_render_input,
    build_render_prompt,
    render_story,
    validate_render_input,
    validate_render_result,
    format_render_debug,
    _format_section_for_prompt,
    # Constants
    SYSTEM_INSTRUCTION,
)


# ============================================================================
# TEST HELPERS
# ============================================================================

def make_section(
    section_index: int,
    beat_type: BeatType,
    home_score: int = 50,
    away_score: int = 48,
    notes: list[str] | None = None,
) -> StorySection:
    """Create a StorySection for testing."""
    section = StorySection(
        section_index=section_index,
        beat_type=beat_type,
        chapters_included=[f"ch_{section_index:03d}"],
        start_score={"home": home_score - 10, "away": away_score - 8},
        end_score={"home": home_score, "away": away_score},
        notes=notes or [],
    )

    # Add some team stats
    section.team_stat_deltas["home"] = TeamStatDelta(
        team_key="home",
        team_name="Lakers",
        points_scored=10,
        personal_fouls_committed=2,
    )
    section.team_stat_deltas["away"] = TeamStatDelta(
        team_key="away",
        team_name="Celtics",
        points_scored=8,
        personal_fouls_committed=3,
    )

    # Add a player stat
    section.player_stat_deltas["player1"] = PlayerStatDelta(
        player_key="player1",
        player_name="LeBron James",
        team_key="home",
        points_scored=6,
        fg_made=2,
        three_pt_made=1,
    )

    return section


def make_header(beat_type: BeatType) -> str:
    """Create a deterministic header for testing."""
    headers = {
        BeatType.FAST_START: "Both teams opened at a fast pace.",
        BeatType.BACK_AND_FORTH: "Neither side could separate as play moved back and forth.",
        BeatType.RUN: "A stretch of scoring created separation on the scoreboard.",
        BeatType.RESPONSE: "The opposing side answered to keep the game within reach.",
        BeatType.CRUNCH_SETUP: "The game tightened late as every possession began to matter.",
        BeatType.CLOSING_SEQUENCE: "Late possessions took on added importance down the stretch.",
        BeatType.OVERTIME: "Overtime extended the game into a survival phase.",
    }
    return headers.get(beat_type, "The game continued.")


class MockAIClient:
    """Mock AI client for testing."""

    def __init__(self, response: str | None = None, should_fail: bool = False):
        self.response = response
        self.should_fail = should_fail
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.should_fail:
            raise Exception("AI generation failed")
        if self.response:
            return self.response
        # Default mock response
        return json.dumps({
            "compact_story": "This is a mock story.\n\nIt has two paragraphs."
        })


# ============================================================================
# TEST: CLOSING CONTEXT
# ============================================================================

class TestClosingContext:
    """Tests for ClosingContext."""

    def test_to_dict(self):
        """ClosingContext serializes correctly."""
        closing = ClosingContext(
            final_home_score=105,
            final_away_score=102,
            home_team_name="Lakers",
            away_team_name="Celtics",
            decisive_factors=["Late free throws", "Defensive stops"],
        )

        data = closing.to_dict()

        assert data["final_score"] == "Lakers 105, Celtics 102"
        assert len(data["decisive_factors"]) == 2


# ============================================================================
# TEST: SECTION RENDER INPUT
# ============================================================================

class TestSectionRenderInput:
    """Tests for SectionRenderInput."""

    def test_to_dict(self):
        """SectionRenderInput serializes correctly."""
        section_input = SectionRenderInput(
            header="Both teams opened at a fast pace.",
            beat_type=BeatType.FAST_START,
            team_stat_deltas=[{"team_name": "Lakers", "points_scored": 15}],
            player_stat_deltas=[{"player_name": "LeBron", "points_scored": 8}],
            notes=["Fast start by Lakers"],
        )

        data = section_input.to_dict()

        assert data["header"] == "Both teams opened at a fast pace."
        assert data["beat_type"] == "FAST_START"
        assert len(data["team_stats"]) == 1
        assert len(data["player_stats"]) == 1
        assert len(data["notes"]) == 1


# ============================================================================
# TEST: BUILD SECTION RENDER INPUT
# ============================================================================

class TestBuildSectionRenderInput:
    """Tests for build_section_render_input."""

    def test_builds_from_story_section(self):
        """Builds SectionRenderInput from StorySection."""
        section = make_section(0, BeatType.FAST_START)
        header = "Both teams opened at a fast pace."

        result = build_section_render_input(section, header)

        assert result.header == header
        assert result.beat_type == BeatType.FAST_START
        assert len(result.team_stat_deltas) == 2
        assert len(result.player_stat_deltas) == 1

    def test_includes_notes(self):
        """Notes are included in output."""
        section = make_section(0, BeatType.RUN, notes=["Lakers went on a 10-0 run"])
        header = "A stretch of scoring created separation."

        result = build_section_render_input(section, header)

        assert result.notes == ["Lakers went on a 10-0 run"]


# ============================================================================
# TEST: BUILD STORY RENDER INPUT
# ============================================================================

class TestBuildStoryRenderInput:
    """Tests for build_story_render_input."""

    def test_builds_complete_input(self):
        """Builds complete StoryRenderInput."""
        sections = [
            make_section(0, BeatType.FAST_START, 20, 18),
            make_section(1, BeatType.BACK_AND_FORTH, 50, 48),
            make_section(2, BeatType.CRUNCH_SETUP, 100, 98),
        ]
        headers = [make_header(s.beat_type) for s in sections]

        result = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=["Clutch shooting"],
        )

        assert result.sport == "NBA"
        assert result.home_team_name == "Lakers"
        assert result.away_team_name == "Celtics"
        assert result.target_word_count == 700
        assert len(result.sections) == 3
        assert result.closing.final_home_score == 100
        assert result.closing.final_away_score == 98

    def test_section_header_count_mismatch_raises(self):
        """Raises error if sections and headers count mismatch."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = ["Header 1.", "Header 2."]  # Too many

        with pytest.raises(StoryRenderError, match="Section count"):
            build_story_render_input(
                sections=sections,
                headers=headers,
                sport="NBA",
                home_team_name="Lakers",
                away_team_name="Celtics",
                target_word_count=700,
                decisive_factors=[],
            )

    def test_empty_sections_raises(self):
        """Raises error if no sections provided."""
        with pytest.raises(StoryRenderError, match="No sections"):
            build_story_render_input(
                sections=[],
                headers=[],
                sport="NBA",
                home_team_name="Lakers",
                away_team_name="Celtics",
                target_word_count=700,
                decisive_factors=[],
            )


# ============================================================================
# TEST: PROMPT BUILDING
# ============================================================================

class TestPromptBuilding:
    """Tests for prompt construction."""

    def test_prompt_includes_system_instruction(self):
        """Prompt includes system instruction."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=400,
            decisive_factors=["Close finish"],
        )

        prompt = build_render_prompt(input_data)

        assert SYSTEM_INSTRUCTION in prompt

    def test_prompt_includes_target_word_count(self):
        """Prompt includes target word count."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=[],
        )

        prompt = build_render_prompt(input_data)

        assert "700" in prompt
        assert "target" in prompt.lower()

    def test_prompt_includes_headers(self):
        """Prompt includes section headers."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.RUN),
        ]
        headers = [
            "Both teams opened at a fast pace.",
            "A stretch of scoring created separation.",
        ]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=[],
        )

        prompt = build_render_prompt(input_data)

        assert "Both teams opened at a fast pace." in prompt
        assert "A stretch of scoring created separation." in prompt

    def test_prompt_includes_team_names(self):
        """Prompt includes team names."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=[],
        )

        prompt = build_render_prompt(input_data)

        assert "Lakers" in prompt
        assert "Celtics" in prompt

    def test_prompt_includes_json_output_instruction(self):
        """Prompt specifies JSON output format."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=[],
        )

        prompt = build_render_prompt(input_data)

        assert '"compact_story"' in prompt
        assert "JSON" in prompt


# ============================================================================
# TEST: RENDER STORY
# ============================================================================

class TestRenderStory:
    """Tests for render_story function."""

    def test_render_with_mock_client(self):
        """Renders story with mock AI client."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=400,
            decisive_factors=["Close finish"],
        )

        mock_client = MockAIClient()
        result = render_story(input_data, mock_client)

        assert result.compact_story
        assert result.word_count > 0
        assert result.target_word_count == 400
        assert result.section_count == 1

    def test_render_without_client_returns_mock(self):
        """Returns mock story when no client provided."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.CRUNCH_SETUP),
        ]
        headers = [make_header(s.beat_type) for s in sections]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=[],
        )

        result = render_story(input_data, ai_client=None)

        assert result.compact_story
        # Mock should include headers
        assert "fast pace" in result.compact_story.lower()

    def test_render_captures_prompt(self):
        """Result includes the prompt used."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=400,
            decisive_factors=[],
        )

        mock_client = MockAIClient()
        result = render_story(input_data, mock_client)

        assert result.prompt_used
        assert "Lakers" in result.prompt_used

    def test_render_ai_failure_raises(self):
        """AI failure raises StoryRenderError."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=400,
            decisive_factors=[],
        )

        mock_client = MockAIClient(should_fail=True)

        with pytest.raises(StoryRenderError, match="AI generation failed"):
            render_story(input_data, mock_client)

    def test_render_invalid_json_raises(self):
        """Invalid JSON response raises StoryRenderError."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=400,
            decisive_factors=[],
        )

        mock_client = MockAIClient(response="not valid json")

        with pytest.raises(StoryRenderError, match="parse"):
            render_story(input_data, mock_client)

    def test_render_empty_story_raises(self):
        """Empty story in response raises StoryRenderError."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=400,
            decisive_factors=[],
        )

        mock_client = MockAIClient(response='{"compact_story": ""}')

        with pytest.raises(StoryRenderError, match="empty"):
            render_story(input_data, mock_client)

    def test_render_handles_markdown_fences(self):
        """Handles AI response wrapped in markdown fences."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=400,
            decisive_factors=[],
        )

        # AI sometimes wraps response in markdown
        response = '```json\n{"compact_story": "Story with markdown."}\n```'
        mock_client = MockAIClient(response=response)

        result = render_story(input_data, mock_client)

        assert result.compact_story == "Story with markdown."


# ============================================================================
# TEST: INPUT VALIDATION
# ============================================================================

class TestInputValidation:
    """Tests for validate_render_input."""

    def test_valid_input_passes(self):
        """Valid input has no errors."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=[],
        )

        errors = validate_render_input(input_data)

        assert errors == []

    def test_missing_header_fails(self):
        """Section without header fails validation."""
        input_data = StoryRenderInput(
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            sections=[
                SectionRenderInput(
                    header="",  # Empty header
                    beat_type=BeatType.FAST_START,
                    team_stat_deltas=[],
                    player_stat_deltas=[],
                    notes=[],
                )
            ],
            closing=ClosingContext(
                final_home_score=100,
                final_away_score=98,
                home_team_name="Lakers",
                away_team_name="Celtics",
                decisive_factors=[],
            ),
        )

        errors = validate_render_input(input_data)

        assert any("no header" in e for e in errors)

    def test_header_without_period_fails(self):
        """Header not ending with period fails validation."""
        input_data = StoryRenderInput(
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            sections=[
                SectionRenderInput(
                    header="Header without period",  # No period
                    beat_type=BeatType.FAST_START,
                    team_stat_deltas=[],
                    player_stat_deltas=[],
                    notes=[],
                )
            ],
            closing=ClosingContext(
                final_home_score=100,
                final_away_score=98,
                home_team_name="Lakers",
                away_team_name="Celtics",
                decisive_factors=[],
            ),
        )

        errors = validate_render_input(input_data)

        assert any("period" in e for e in errors)

    def test_invalid_word_count_fails(self):
        """Zero or negative word count fails validation."""
        input_data = StoryRenderInput(
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=0,  # Invalid
            sections=[
                SectionRenderInput(
                    header="Valid header.",
                    beat_type=BeatType.FAST_START,
                    team_stat_deltas=[],
                    player_stat_deltas=[],
                    notes=[],
                )
            ],
            closing=ClosingContext(
                final_home_score=100,
                final_away_score=98,
                home_team_name="Lakers",
                away_team_name="Celtics",
                decisive_factors=[],
            ),
        )

        errors = validate_render_input(input_data)

        assert any("word count" in e for e in errors)


# ============================================================================
# TEST: RESULT VALIDATION
# ============================================================================

class TestResultValidation:
    """Tests for validate_render_result."""

    def test_normal_deviation_passes(self):
        """Normal word count deviation passes."""
        input_data = StoryRenderInput(
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            sections=[
                SectionRenderInput(
                    header="Both teams opened fast.",
                    beat_type=BeatType.FAST_START,
                    team_stat_deltas=[],
                    player_stat_deltas=[],
                    notes=[],
                )
            ],
            closing=ClosingContext(
                final_home_score=100,
                final_away_score=98,
                home_team_name="Lakers",
                away_team_name="Celtics",
                decisive_factors=[],
            ),
        )

        result = StoryRenderResult(
            compact_story="Both teams opened fast. " + "word " * 650,  # ~650 words
            word_count=650,
            target_word_count=700,
            section_count=1,
        )

        errors = validate_render_result(result, input_data)

        assert errors == []

    def test_large_deviation_fails(self):
        """Large word count deviation fails."""
        input_data = StoryRenderInput(
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            sections=[
                SectionRenderInput(
                    header="Header.",
                    beat_type=BeatType.FAST_START,
                    team_stat_deltas=[],
                    player_stat_deltas=[],
                    notes=[],
                )
            ],
            closing=ClosingContext(
                final_home_score=100,
                final_away_score=98,
                home_team_name="Lakers",
                away_team_name="Celtics",
                decisive_factors=[],
            ),
        )

        result = StoryRenderResult(
            compact_story="Very short.",  # Way too short
            word_count=2,
            target_word_count=700,
            section_count=1,
        )

        errors = validate_render_result(result, input_data)

        assert any("deviation" in e.lower() for e in errors)


# ============================================================================
# TEST: DEBUG OUTPUT
# ============================================================================

class TestDebugOutput:
    """Tests for format_render_debug."""

    def test_format_includes_key_info(self):
        """Debug output includes key information."""
        sections = [
            make_section(0, BeatType.FAST_START),
            make_section(1, BeatType.CRUNCH_SETUP),
        ]
        headers = [make_header(s.beat_type) for s in sections]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=["Clutch play"],
        )

        output = format_render_debug(input_data)

        assert "NBA" in output
        assert "Lakers" in output
        assert "Celtics" in output
        assert "700" in output
        assert "FAST_START" in output
        assert "CRUNCH_SETUP" in output

    def test_format_with_result(self):
        """Debug output includes result when provided."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=[],
        )

        result = StoryRenderResult(
            compact_story="Story text.",
            word_count=650,
            target_word_count=700,
            section_count=1,
        )

        output = format_render_debug(input_data, result)

        assert "650" in output
        assert "Deviation" in output


# ============================================================================
# TEST: SERIALIZATION
# ============================================================================

class TestSerialization:
    """Tests for serialization."""

    def test_story_render_input_to_dict(self):
        """StoryRenderInput serializes correctly."""
        sections = [make_section(0, BeatType.FAST_START)]
        headers = [make_header(BeatType.FAST_START)]

        input_data = build_story_render_input(
            sections=sections,
            headers=headers,
            sport="NBA",
            home_team_name="Lakers",
            away_team_name="Celtics",
            target_word_count=700,
            decisive_factors=["Clutch play"],
        )

        data = input_data.to_dict()

        assert data["sport"] == "NBA"
        assert data["target_word_count"] == 700
        assert len(data["sections"]) == 1
        assert "closing" in data

    def test_story_render_result_to_dict(self):
        """StoryRenderResult serializes correctly."""
        result = StoryRenderResult(
            compact_story="The story text.",
            word_count=3,
            target_word_count=700,
            section_count=2,
        )

        data = result.to_dict()

        assert data["compact_story"] == "The story text."
        assert data["word_count"] == 3
        assert data["target_word_count"] == 700
        assert data["section_count"] == 2


# ============================================================================
# TEST: SECTION FORMATTING
# ============================================================================

class TestSectionFormatting:
    """Tests for _format_section_for_prompt."""

    def test_format_includes_header(self):
        """Formatted section includes header."""
        section_input = SectionRenderInput(
            header="Both teams opened at a fast pace.",
            beat_type=BeatType.FAST_START,
            team_stat_deltas=[],
            player_stat_deltas=[],
            notes=[],
        )

        output = _format_section_for_prompt(section_input, 0)

        assert "Both teams opened at a fast pace." in output

    def test_format_includes_beat_type(self):
        """Formatted section includes beat type."""
        section_input = SectionRenderInput(
            header="Header.",
            beat_type=BeatType.RUN,
            team_stat_deltas=[],
            player_stat_deltas=[],
            notes=[],
        )

        output = _format_section_for_prompt(section_input, 0)

        assert "RUN" in output

    def test_format_includes_team_stats(self):
        """Formatted section includes team stats."""
        section_input = SectionRenderInput(
            header="Header.",
            beat_type=BeatType.FAST_START,
            team_stat_deltas=[
                {"team_name": "Lakers", "points_scored": 15, "personal_fouls_committed": 3}
            ],
            player_stat_deltas=[],
            notes=[],
        )

        output = _format_section_for_prompt(section_input, 0)

        assert "Lakers" in output
        assert "15 pts" in output
        assert "3 fouls" in output

    def test_format_includes_player_stats(self):
        """Formatted section includes player stats."""
        section_input = SectionRenderInput(
            header="Header.",
            beat_type=BeatType.FAST_START,
            team_stat_deltas=[],
            player_stat_deltas=[
                {
                    "player_name": "LeBron James",
                    "points_scored": 12,
                    "fg_made": 4,
                    "three_pt_made": 2,
                    "ft_made": 0,
                    "personal_foul_count": 1,
                    "foul_trouble_flag": False,
                }
            ],
            notes=[],
        )

        output = _format_section_for_prompt(section_input, 0)

        assert "LeBron James" in output
        assert "12 pts" in output
        assert "4 FG" in output
        assert "2 3PT" in output

    def test_format_includes_notes(self):
        """Formatted section includes notes."""
        section_input = SectionRenderInput(
            header="Header.",
            beat_type=BeatType.FAST_START,
            team_stat_deltas=[],
            player_stat_deltas=[],
            notes=["Lakers went on 8-0 run", "Timeout called"],
        )

        output = _format_section_for_prompt(section_input, 0)

        assert "8-0 run" in output
        assert "Timeout" in output
