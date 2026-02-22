"""Tests for RENDER_BLOCKS stage."""

from __future__ import annotations

from app.services.pipeline.stages.block_types import (
    MAX_WORDS_PER_BLOCK,
    SemanticRole,
)
from app.services.pipeline.stages.render_helpers import (
    check_overtime_mention,
    detect_overtime_info,
    inject_overtime_mention,
)
from app.services.pipeline.stages.render_prompts import (
    GAME_FLOW_PASS_PROMPT,
    _detect_big_lead_comeback,
    _detect_close_game,
    _format_contributors_line,
    _format_lead_line,
    build_block_prompt,
    build_game_flow_pass_prompt,
)
from app.services.pipeline.stages.render_validation import (
    FORBIDDEN_WORDS,
    validate_block_narrative,
    validate_style_constraints,
)


class TestBuildBlockPrompt:
    """Tests for block prompt building."""

    def test_prompt_includes_team_names(self) -> None:
        """Prompt includes home and away team names."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1],
            }
        ]
        game_context = {
            "home_team_name": "Lakers",
            "away_team_name": "Celtics",
        }
        pbp_events: list[dict] = []

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        assert "Lakers" in prompt
        assert "Celtics" in prompt

    def test_prompt_includes_forbidden_words_list(self) -> None:
        """Prompt includes list of forbidden words."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}
        pbp_events: list[dict] = []

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        for word in FORBIDDEN_WORDS:
            assert word in prompt.lower()

    def test_prompt_includes_role_info(self) -> None:
        """Prompt includes semantic role for each block."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            },
            {
                "block_index": 1,
                "role": SemanticRole.RESOLUTION.value,
                "score_before": [10, 8],
                "score_after": [20, 18],
                "key_play_ids": [],
            },
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}
        pbp_events: list[dict] = []

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        assert "SETUP" in prompt
        assert "RESOLUTION" in prompt

    def test_prompt_includes_key_play_descriptions(self) -> None:
        """Prompt includes descriptions of key plays with team names."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1, 2],
            }
        ]
        game_context = {
            "home_team_name": "Lakers",
            "away_team_name": "Celtics",
            "home_team_abbrev": "LAL",
            "away_team_abbrev": "BOS",
        }
        pbp_events = [
            {"play_index": 1, "description": "[LAL] LeBron James makes 3-pointer", "team_abbreviation": "LAL"},
            {"play_index": 2, "description": "[LAL] Anthony Davis dunks", "team_abbreviation": "LAL"},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        # Key plays should have team name in parentheses, not brackets
        assert "(Lakers) LeBron James makes 3-pointer" in prompt
        assert "(Lakers) Anthony Davis dunks" in prompt
        assert "[LAL]" not in prompt

    def test_prompt_key_plays_include_team_name(self) -> None:
        """Key plays from different teams render with full team names in parentheses."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1, 2],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "home_team_abbrev": "ATL",
            "away_team_abbrev": "BOS",
        }
        pbp_events = [
            {"play_index": 1, "description": "[ATL] Young makes 3-pointer", "team_abbreviation": "ATL"},
            {"play_index": 2, "description": "[BOS] Tatum drives for layup", "team_abbreviation": "BOS"},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        # Full team names should appear in parentheses
        assert "(Hawks) Young makes 3-pointer" in prompt
        assert "(Celtics) Tatum drives for layup" in prompt
        # Abbreviation brackets should NOT appear
        assert "[ATL]" not in prompt
        assert "[BOS]" not in prompt

    def test_prompt_key_plays_without_team_abbreviation(self) -> None:
        """Plays without team_abbreviation render without empty brackets."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1, 2],
            }
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}
        pbp_events = [
            {"play_index": 1, "description": "End of period"},
            {"play_index": 2, "description": "Timeout called", "team_abbreviation": ""},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        assert "- End of period" in prompt
        assert "- Timeout called" in prompt
        assert "[]" not in prompt


class TestValidateBlockNarrative:
    """Tests for block narrative validation."""

    def test_empty_narrative_is_error(self) -> None:
        """Empty narrative produces error."""
        errors, warnings = validate_block_narrative("", 0)
        assert len(errors) > 0
        assert "Empty" in errors[0]

    def test_whitespace_only_is_error(self) -> None:
        """Whitespace-only narrative produces error."""
        errors, warnings = validate_block_narrative("   \n\t  ", 0)
        assert len(errors) > 0

    def test_too_short_is_warning(self) -> None:
        """Narrative shorter than minimum produces warning."""
        short_narrative = "Short text."  # ~2 words
        errors, warnings = validate_block_narrative(short_narrative, 0)
        assert len(warnings) > 0
        assert "short" in warnings[0].lower()

    def test_too_long_is_warning(self) -> None:
        """Narrative longer than maximum produces warning."""
        long_narrative = " ".join(["word"] * (MAX_WORDS_PER_BLOCK + 10))
        errors, warnings = validate_block_narrative(long_narrative, 0)
        assert len(warnings) > 0
        assert "long" in warnings[0].lower()

    def test_valid_length_no_warnings(self) -> None:
        """Narrative of valid length produces no word count warnings."""
        valid_narrative = " ".join(["word"] * 30)  # 30 words, within limits
        errors, warnings = validate_block_narrative(valid_narrative, 0)
        assert len(errors) == 0
        word_count_warnings = [w for w in warnings if "short" in w.lower() or "long" in w.lower()]
        assert len(word_count_warnings) == 0

    def test_forbidden_word_is_warning(self) -> None:
        """Narrative containing forbidden word produces warning."""
        narrative = "The team built momentum and scored 10 points in a row."
        errors, warnings = validate_block_narrative(narrative, 0)
        assert any("momentum" in w.lower() for w in warnings)

    def test_multiple_forbidden_words(self) -> None:
        """Multiple forbidden words produce multiple warnings."""
        narrative = "This was a huge momentum shift and a turning point in the game."
        errors, warnings = validate_block_narrative(narrative, 0)
        forbidden_warnings = [w for w in warnings if "forbidden" in w.lower()]
        assert len(forbidden_warnings) >= 2


class TestForbiddenWords:
    """Tests for forbidden words list."""

    def test_forbidden_words_are_defined(self) -> None:
        """Forbidden words list is not empty."""
        assert len(FORBIDDEN_WORDS) > 0

    def test_expected_forbidden_words(self) -> None:
        """Expected forbidden words are in the list."""
        expected = ["momentum", "turning point", "dominant", "huge", "clutch"]
        for word in expected:
            assert word in FORBIDDEN_WORDS, f"Expected '{word}' to be forbidden"

    def test_validation_catches_all_forbidden_words(self) -> None:
        """Validation catches each forbidden word."""
        for word in FORBIDDEN_WORDS:
            narrative = f"The team showed {word} in this stretch."
            errors, warnings = validate_block_narrative(narrative, 0)
            assert any(word.lower() in w.lower() for w in warnings), f"'{word}' not caught"



class TestStyleConstraints:
    """Tests for sentence style constraints."""

    def test_detects_stat_feed_pattern(self) -> None:
        """Detects 'X had Y points' patterns."""
        narrative = "James had 32 points in the game."
        errors, warnings = validate_style_constraints(narrative, 0)
        assert len(warnings) > 0

    def test_detects_finished_with_pattern(self) -> None:
        """Detects 'finished with X' patterns."""
        narrative = "Davis finished with 28 in the quarter."
        errors, warnings = validate_style_constraints(narrative, 0)
        assert len(warnings) > 0

    def test_detects_subjective_adjectives(self) -> None:
        """Detects subjective adjectives."""
        narrative = "An incredible performance by the team."
        errors, warnings = validate_style_constraints(narrative, 0)
        assert len(warnings) > 0

    def test_valid_broadcast_style_passes(self) -> None:
        """Valid broadcast-style narrative passes."""
        narrative = "James drove to the basket and scored. The Lakers extended their lead to ten."
        errors, warnings = validate_style_constraints(narrative, 0)
        # May have some warnings but should not be stat-feed related
        stat_warnings = [w for w in warnings if "stat" in w.lower() or "pattern" in w.lower()]
        assert len(stat_warnings) == 0

    def test_detects_too_many_numbers(self) -> None:
        """Detects stat-feed style from excessive numbers."""
        narrative = "He scored 10, 15, 8, 12, 7, 9, 11 points across stretches."
        errors, warnings = validate_style_constraints(narrative, 0)
        assert any("numbers" in w.lower() for w in warnings)


class TestGameLevelFlowPass:
    """Tests for game-level flow pass functionality."""

    def test_flow_prompt_includes_game_context(self) -> None:
        """Flow pass prompt includes team names."""
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "period_start": 1,
                "period_end": 1,
                "score_before": [0, 0],
                "score_after": [12, 10],
                "narrative": "The Lakers set the early tone with quick ball movement.",
            },
            {
                "block_index": 1,
                "role": "RESOLUTION",
                "period_start": 4,
                "period_end": 4,
                "score_before": [95, 92],
                "score_after": [102, 98],
                "narrative": "The Lakers closed out the game at the free throw line.",
            },
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics"}

        prompt = build_game_flow_pass_prompt(blocks, game_context)

        assert "Lakers" in prompt
        assert "Celtics" in prompt
        assert "SETUP" in prompt
        assert "RESOLUTION" in prompt

    def test_flow_prompt_includes_all_blocks(self) -> None:
        """Flow pass prompt includes narratives from all blocks."""
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "period_start": 1,
                "period_end": 1,
                "score_before": [0, 0],
                "score_after": [12, 10],
                "narrative": "First block narrative here.",
            },
            {
                "block_index": 1,
                "role": "MOMENTUM_SHIFT",
                "period_start": 2,
                "period_end": 2,
                "score_before": [12, 10],
                "score_after": [25, 28],
                "narrative": "Second block narrative here.",
            },
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}

        prompt = build_game_flow_pass_prompt(blocks, game_context)

        assert "First block narrative here" in prompt
        assert "Second block narrative here" in prompt
        assert "Block 0" in prompt
        assert "Block 1" in prompt

    def test_flow_prompt_includes_period_labels(self) -> None:
        """Flow pass prompt includes period labels."""
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "period_start": 1,
                "period_end": 1,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "narrative": "Opening narrative.",
            },
            {
                "block_index": 1,
                "role": "RESOLUTION",
                "period_start": 5,  # OT1
                "period_end": 5,
                "score_before": [100, 100],
                "score_after": [108, 105],
                "narrative": "Overtime narrative.",
            },
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}

        prompt = build_game_flow_pass_prompt(blocks, game_context)

        assert "Q1" in prompt
        assert "OT1" in prompt

    def test_flow_pass_prompt_constant_exists(self) -> None:
        """The game flow pass prompt constant is defined."""
        assert GAME_FLOW_PASS_PROMPT is not None
        assert "flow naturally" in GAME_FLOW_PASS_PROMPT.lower()
        assert "preserve" in GAME_FLOW_PASS_PROMPT.lower()

    def test_flow_prompt_includes_scores(self) -> None:
        """Flow pass prompt includes score transitions."""
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "period_start": 1,
                "period_end": 1,
                "score_before": [0, 0],
                "score_after": [15, 12],
                "narrative": "Test narrative.",
            },
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}

        prompt = build_game_flow_pass_prompt(blocks, game_context)

        # Should show score transition
        assert "0-0" in prompt or "0" in prompt
        assert "15" in prompt
        assert "12" in prompt


class TestOvertimeDetection:
    """Tests for overtime detection functionality."""

    def test_nba_regulation_no_overtime(self) -> None:
        """NBA Q1-Q4 is not overtime."""
        block = {"period_start": 1, "period_end": 4}
        info = detect_overtime_info(block, "NBA")
        assert info["has_overtime"] is False
        assert info["enters_overtime"] is False
        assert info["ot_label"] == ""

    def test_nba_overtime_detected(self) -> None:
        """NBA period 5 is OT1."""
        block = {"period_start": 5, "period_end": 5}
        info = detect_overtime_info(block, "NBA")
        assert info["has_overtime"] is True
        assert info["enters_overtime"] is False  # Starts in OT, doesn't enter
        assert info["ot_label"] == "overtime"

    def test_nba_enters_overtime(self) -> None:
        """Block spanning Q4 to OT1 enters overtime."""
        block = {"period_start": 4, "period_end": 5}
        info = detect_overtime_info(block, "NBA")
        assert info["has_overtime"] is True
        assert info["enters_overtime"] is True
        assert info["ot_label"] == "overtime"

    def test_nba_double_overtime(self) -> None:
        """NBA period 6 is OT2."""
        block = {"period_start": 6, "period_end": 6}
        info = detect_overtime_info(block, "NBA")
        assert info["has_overtime"] is True
        assert info["ot_label"] == "OT2"

    def test_nhl_regulation_no_overtime(self) -> None:
        """NHL periods 1-3 are regulation."""
        block = {"period_start": 1, "period_end": 3}
        info = detect_overtime_info(block, "NHL")
        assert info["has_overtime"] is False
        assert info["regulation_end_period"] == 3

    def test_nhl_enters_overtime(self) -> None:
        """NHL block spanning P3 to OT enters overtime."""
        block = {"period_start": 3, "period_end": 4}
        info = detect_overtime_info(block, "NHL")
        assert info["has_overtime"] is True
        assert info["enters_overtime"] is True
        assert info["ot_label"] == "overtime"

    def test_nhl_shootout(self) -> None:
        """NHL period 5 is shootout."""
        block = {"period_start": 5, "period_end": 5}
        info = detect_overtime_info(block, "NHL")
        assert info["has_overtime"] is True
        assert info["is_shootout"] is True
        assert info["ot_label"] == "shootout"

    def test_nhl_enters_shootout_from_regulation(self) -> None:
        """NHL block entering shootout directly from P3 (rare but possible)."""
        # Note: This represents a block spanning end of regulation through shootout
        block = {"period_start": 3, "period_end": 5}
        info = detect_overtime_info(block, "NHL")
        assert info["has_overtime"] is True
        assert info["enters_overtime"] is True  # Enters from regulation
        assert info["is_shootout"] is True  # Ends in shootout

    def test_nhl_ot_to_shootout_not_enters(self) -> None:
        """NHL block from OT to shootout doesn't 'enter' OT (already in OT)."""
        block = {"period_start": 4, "period_end": 5}
        info = detect_overtime_info(block, "NHL")
        assert info["has_overtime"] is True
        assert info["enters_overtime"] is False  # Starts in OT, not entering
        assert info["is_shootout"] is True

    def test_ncaab_halves(self) -> None:
        """NCAAB uses 2 halves."""
        block = {"period_start": 1, "period_end": 2}
        info = detect_overtime_info(block, "NCAAB")
        assert info["has_overtime"] is False
        assert info["regulation_end_period"] == 2

    def test_ncaab_overtime(self) -> None:
        """NCAAB period 3 is OT1."""
        block = {"period_start": 2, "period_end": 3}
        info = detect_overtime_info(block, "NCAAB")
        assert info["has_overtime"] is True
        assert info["enters_overtime"] is True
        assert info["ot_label"] == "overtime"


class TestOvertimeMention:
    """Tests for overtime mention checking and injection."""

    def test_mention_not_required_for_regulation(self) -> None:
        """Regulation blocks don't need OT mention."""
        ot_info = {"has_overtime": False, "enters_overtime": False}
        assert check_overtime_mention("Any narrative text.", ot_info) is True

    def test_mention_detected_overtime(self) -> None:
        """Detects 'overtime' word in narrative."""
        ot_info = {"enters_overtime": True, "is_shootout": False}
        assert check_overtime_mention("The game headed to overtime.", ot_info) is True

    def test_mention_detected_ot(self) -> None:
        """Detects 'OT' abbreviation in narrative."""
        ot_info = {"enters_overtime": True, "is_shootout": False}
        assert check_overtime_mention("Tied at 100, sending it to OT.", ot_info) is True

    def test_mention_detected_extra_period(self) -> None:
        """Detects 'extra period' phrase."""
        ot_info = {"enters_overtime": True, "is_shootout": False}
        assert check_overtime_mention("Forcing an extra period.", ot_info) is True

    def test_mention_detected_shootout(self) -> None:
        """Detects shootout mention for NHL."""
        ot_info = {"enters_overtime": True, "is_shootout": True}
        assert check_overtime_mention("The game went to a shootout.", ot_info) is True

    def test_mention_missing(self) -> None:
        """Missing OT mention is detected."""
        ot_info = {"enters_overtime": True, "is_shootout": False}
        assert check_overtime_mention("The teams remained tied at 100.", ot_info) is False

    def test_injection_adds_overtime(self) -> None:
        """Injects overtime mention when missing."""
        ot_info = {"enters_overtime": True, "is_shootout": False, "ot_label": "overtime"}
        narrative = "The teams remained tied at 100"
        result = inject_overtime_mention(narrative, ot_info)
        assert "overtime" in result.lower()
        assert result.endswith(".")

    def test_injection_adds_shootout(self) -> None:
        """Injects shootout mention for NHL."""
        ot_info = {"enters_overtime": True, "is_shootout": True, "ot_label": "shootout"}
        narrative = "The teams remained tied."
        result = inject_overtime_mention(narrative, ot_info)
        assert "shootout" in result.lower()

    def test_injection_skipped_when_already_mentioned(self) -> None:
        """No injection when OT already mentioned."""
        ot_info = {"enters_overtime": True, "is_shootout": False, "ot_label": "overtime"}
        narrative = "The game headed to overtime."
        result = inject_overtime_mention(narrative, ot_info)
        # Should not add duplicate mention
        assert result.count("overtime") == 1

    def test_injection_not_needed_for_regulation(self) -> None:
        """No injection for regulation blocks."""
        ot_info = {"enters_overtime": False, "is_shootout": False}
        narrative = "A normal regulation narrative."
        result = inject_overtime_mention(narrative, ot_info)
        assert result == narrative


class TestOvertimeInPrompt:
    """Tests for overtime mentions in prompts."""

    def test_block_prompt_includes_ot_guidance_when_needed(self) -> None:
        """Block prompt includes OT guidance for overtime games."""
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "period_start": 1,
                "period_end": 1,
                "score_before": [0, 0],
                "score_after": [25, 22],
                "key_play_ids": [],
            },
            {
                "block_index": 1,
                "role": "RESOLUTION",
                "period_start": 4,
                "period_end": 5,  # Enters OT
                "score_before": [100, 100],
                "score_after": [108, 105],
                "key_play_ids": [],
            },
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics", "sport": "NBA"}
        prompt = build_block_prompt(blocks, game_context, [])

        assert "OVERTIME" in prompt.upper() or "overtime" in prompt.lower()
        assert "MUST mention" in prompt or "must mention" in prompt.lower()

    def test_block_prompt_no_ot_guidance_for_regulation(self) -> None:
        """Block prompt omits OT guidance for regulation games."""
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "period_start": 1,
                "period_end": 1,
                "score_before": [0, 0],
                "score_after": [25, 22],
                "key_play_ids": [],
            },
            {
                "block_index": 1,
                "role": "RESOLUTION",
                "period_start": 4,
                "period_end": 4,  # Regulation only
                "score_before": [95, 92],
                "score_after": [102, 98],
                "key_play_ids": [],
            },
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics", "sport": "NBA"}
        prompt = build_block_prompt(blocks, game_context, [])

        # Should not have OT-specific requirements section
        assert "OVERTIME/EXTRA PERIOD REQUIREMENTS" not in prompt

    def test_flow_prompt_flags_ot_blocks(self) -> None:
        """Flow pass prompt flags blocks that enter OT."""
        blocks = [
            {
                "block_index": 0,
                "role": "DECISION_POINT",
                "period_start": 4,
                "period_end": 5,  # Enters OT
                "score_before": [100, 100],
                "score_after": [108, 105],
                "narrative": "The teams battled to a tie.",
            },
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Celtics", "sport": "NBA"}
        prompt = build_game_flow_pass_prompt(blocks, game_context)

        assert "MUST MENTION" in prompt.upper()
        assert "overtime" in prompt.lower()


class TestFormatLeadLine:
    """Tests for _format_lead_line helper."""

    def test_home_takes_lead(self) -> None:
        """Home team taking the lead produces correct line."""
        result = _format_lead_line([0, 0], [5, 0], "Hawks", "Celtics")
        assert result is not None
        assert "Lead:" in result
        assert "Hawks" in result
        assert "5" in result

    def test_away_takes_lead(self) -> None:
        """Away team taking the lead produces correct line."""
        result = _format_lead_line([0, 0], [0, 5], "Hawks", "Celtics")
        assert result is not None
        assert "Lead:" in result
        assert "Celtics" in result

    def test_tie_game(self) -> None:
        """Score going to a tie produces tie description."""
        result = _format_lead_line([5, 0], [5, 5], "Hawks", "Celtics")
        assert result is not None
        assert "Lead:" in result
        assert "tie" in result.lower()

    def test_no_change_returns_none(self) -> None:
        """No scoring change returns None."""
        result = _format_lead_line([10, 8], [10, 8], "Hawks", "Celtics")
        assert result is None

    def test_extend_lead(self) -> None:
        """Extending a lead produces extend description."""
        result = _format_lead_line([5, 2], [8, 2], "Hawks", "Celtics")
        assert result is not None
        assert "extend" in result.lower()
        assert "Hawks" in result


class TestFormatContributorsLine:
    """Tests for _format_contributors_line helper."""

    def test_none_mini_box_returns_none(self) -> None:
        """None mini_box returns None."""
        assert _format_contributors_line(None, "NBA") is None

    def test_empty_mini_box_returns_none(self) -> None:
        """Empty dict returns None."""
        assert _format_contributors_line({}, "NBA") is None

    def test_empty_stars_returns_none(self) -> None:
        """Mini box with no blockStars returns None."""
        mini_box = {
            "blockStars": [],
            "home": {"team": "Hawks", "players": []},
            "away": {"team": "Celtics", "players": []},
        }
        assert _format_contributors_line(mini_box, "NBA") is None

    def test_nba_format(self) -> None:
        """NBA contributors formatted with pts, grouped by team."""
        mini_box = {
            "blockStars": ["Young", "Tatum"],
            "home": {
                "team": "Hawks",
                "players": [
                    {"name": "Trae Young", "deltaPts": 8, "pts": 18},
                ],
            },
            "away": {
                "team": "Celtics",
                "players": [
                    {"name": "Jayson Tatum", "deltaPts": 5, "pts": 12},
                ],
            },
        }
        result = _format_contributors_line(mini_box, "NBA")
        assert result is not None
        assert "Contributors:" in result
        assert "Hawks" in result
        assert "Celtics" in result
        assert "Young +8 pts" in result
        assert "Tatum +5 pts" in result
        assert "|" in result  # team separator

    def test_nhl_format(self) -> None:
        """NHL contributors formatted with goals and assists, grouped by team."""
        mini_box = {
            "blockStars": ["Pastrnak", "Marchand"],
            "home": {
                "team": "Bruins",
                "players": [
                    {"name": "David Pastrnak", "deltaGoals": 1, "deltaAssists": 1},
                    {"name": "Brad Marchand", "deltaGoals": 1, "deltaAssists": 0},
                ],
            },
            "away": {"team": "Rangers", "players": []},
        }
        result = _format_contributors_line(mini_box, "NHL")
        assert result is not None
        assert "Contributors:" in result
        assert "Bruins" in result
        assert "Pastrnak +1g/+1a" in result
        assert "Marchand +1g" in result

    def test_star_not_in_players_skipped(self) -> None:
        """Block star not found in player list is skipped."""
        mini_box = {
            "blockStars": ["Unknown"],
            "home": {"team": "Hawks", "players": []},
            "away": {"team": "Celtics", "players": []},
        }
        assert _format_contributors_line(mini_box, "NBA") is None


class TestLeadAndContributorsInPrompt:
    """Integration tests verifying lead and contributors lines in full prompt."""

    def test_lead_line_appears_in_prompt(self) -> None:
        """Lead context line appears in block prompt when scores change."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [12, 5],
                "key_play_ids": [],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "sport": "NBA",
        }
        prompt = build_block_prompt(blocks, game_context, [])
        assert "Lead:" in prompt

    def test_contributors_line_appears_in_prompt(self) -> None:
        """Contributors line appears when mini_box has block stars, grouped by team."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
                "mini_box": {
                    "blockStars": ["Young"],
                    "home": {
                        "team": "Hawks",
                        "players": [
                            {"name": "Trae Young", "deltaPts": 6, "pts": 6},
                        ],
                    },
                    "away": {"team": "Celtics", "players": []},
                },
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "sport": "NBA",
        }
        prompt = build_block_prompt(blocks, game_context, [])
        assert "Contributors:" in prompt
        assert "Hawks" in prompt
        assert "Young +6 pts" in prompt

    def test_no_lead_line_when_scores_unchanged(self) -> None:
        """No Lead line when block scores don't change."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [10, 8],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "sport": "NBA",
        }
        prompt = build_block_prompt(blocks, game_context, [])
        # "Lead:" should only appear in the instruction section, not per-block
        blocks_section = prompt.split("BLOCKS:")[-1]
        assert "Lead:" not in blocks_section

    def test_no_contributors_without_mini_box(self) -> None:
        """No Contributors line when block has no mini_box."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "sport": "NBA",
        }
        prompt = build_block_prompt(blocks, game_context, [])
        blocks_section = prompt.split("BLOCKS:")[-1]
        assert "Contributors:" not in blocks_section

    def test_contextual_data_usage_in_system_prompt(self) -> None:
        """CONTEXTUAL DATA USAGE section present in prompt."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {
            "home_team_name": "Home",
            "away_team_name": "Away",
            "sport": "NBA",
        }
        prompt = build_block_prompt(blocks, game_context, [])
        assert "CONTEXTUAL DATA USAGE:" in prompt
        assert "narrative fuel" in prompt


class TestContributorsGroupedByTeam:
    """Tests for team-grouped contributors formatting."""

    def test_single_team_contributors(self) -> None:
        """Only home-side contributors produce single-team output without separator."""
        mini_box = {
            "blockStars": ["Young", "Hunter"],
            "home": {
                "team": "Hawks",
                "players": [
                    {"name": "Trae Young", "deltaPts": 8, "pts": 18},
                    {"name": "De'Andre Hunter", "deltaPts": 4, "pts": 10},
                ],
            },
            "away": {"team": "Celtics", "players": []},
        }
        result = _format_contributors_line(mini_box, "NBA")
        assert result is not None
        assert "Hawks" in result
        assert "Young +8 pts" in result
        assert "Hunter +4 pts" in result
        # No pipe separator since only one team
        assert "|" not in result

    def test_both_teams_contributors(self) -> None:
        """Contributors from both teams produce pipe-separated output."""
        mini_box = {
            "blockStars": ["Young", "Tatum"],
            "home": {
                "team": "Hawks",
                "players": [
                    {"name": "Trae Young", "deltaPts": 8, "pts": 18},
                ],
            },
            "away": {
                "team": "Celtics",
                "players": [
                    {"name": "Jayson Tatum", "deltaPts": 5, "pts": 12},
                ],
            },
        }
        result = _format_contributors_line(mini_box, "NBA")
        assert result is not None
        assert "Hawks" in result
        assert "Celtics" in result
        assert "|" in result

    def test_name_collision_across_teams(self) -> None:
        """Two players with same last name on different teams both appear."""
        mini_box = {
            "blockStars": ["Williams"],
            "home": {
                "team": "Hawks",
                "players": [
                    {"name": "Patrick Williams", "deltaPts": 6, "pts": 14},
                ],
            },
            "away": {
                "team": "Celtics",
                "players": [
                    {"name": "Grant Williams", "deltaPts": 4, "pts": 8},
                ],
            },
        }
        result = _format_contributors_line(mini_box, "NBA")
        assert result is not None
        # Both teams should have a Williams entry
        assert "Hawks" in result
        assert "Celtics" in result


class TestPlayerRosterInPrompt:
    """Tests for the ROSTERS section in block prompts."""

    def test_prompt_includes_player_roster(self) -> None:
        """ROSTERS section present when PBP events have player/team data."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {
            "home_team_name": "Rutgers Scarlet Knights",
            "away_team_name": "Penn State Nittany Lions",
            "home_team_abbrev": "RUT",
            "away_team_abbrev": "PSU",
            "sport": "NCAAB",
        }
        pbp_events = [
            {"play_index": 1, "player_name": "Emmanuel Ogbole", "team_abbreviation": "RUT", "description": "dunk"},
            {"play_index": 2, "player_name": "Dylan Grant", "team_abbreviation": "RUT", "description": "3pt"},
            {"play_index": 3, "player_name": "Kayden Mingo", "team_abbreviation": "PSU", "description": "layup"},
            {"play_index": 4, "player_name": "Freddie Dilione V", "team_abbreviation": "PSU", "description": "jumper"},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        assert "ROSTERS:" in prompt
        assert "Rutgers Scarlet Knights (home):" in prompt
        assert "Penn State Nittany Lions (away):" in prompt
        assert "Emmanuel Ogbole" in prompt
        assert "Dylan Grant" in prompt
        assert "Kayden Mingo" in prompt
        assert "Freddie Dilione V" in prompt

    def test_no_roster_without_abbrevs(self) -> None:
        """No ROSTERS section when game_context lacks abbreviations."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {
            "home_team_name": "Home",
            "away_team_name": "Away",
            "sport": "NBA",
        }
        pbp_events = [
            {"play_index": 1, "player_name": "LeBron James", "team_abbreviation": "LAL", "description": "dunk"},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        # No roster because abbreviations are empty strings by default
        assert "ROSTERS:" not in prompt

    def test_roster_limits_to_10_players(self) -> None:
        """Roster is limited to 10 players per team."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "home_team_abbrev": "ATL",
            "away_team_abbrev": "BOS",
            "sport": "NBA",
        }
        # Create 15 unique home players
        pbp_events = [
            {"play_index": i, "player_name": f"Player{i}", "team_abbreviation": "ATL", "description": "play"}
            for i in range(15)
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        assert "ROSTERS:" in prompt
        # Count how many "Player" entries appear in the home roster line
        roster_section = prompt.split("ROSTERS:")[1].split("\n\n")[0]
        home_line = [l for l in roster_section.split("\n") if "Hawks" in l][0]
        player_count = home_line.count("Player")
        assert player_count == 10


class TestDetectBigLeadComeback:
    """Tests for _detect_big_lead_comeback function."""

    def test_comeback_detected(self) -> None:
        """Detects comeback when peak margin >= 15 and final margin < half peak."""
        blocks = [
            {
                "block_index": 0,
                "score_before": [0, 0],
                "score_after": [25, 18],
                "peak_margin": 25,  # Home led by 25
            },
            {
                "block_index": 1,
                "score_before": [25, 18],
                "score_after": [50, 43],
                "peak_margin": 10,
            },
            {
                "block_index": 2,
                "score_before": [50, 43],
                "score_after": [70, 68],
                "peak_margin": 7,  # Final margin 2
            },
        ]
        is_comeback, peak, final = _detect_big_lead_comeback(blocks)
        assert is_comeback is True
        assert peak == 25
        assert final == 2

    def test_no_comeback_when_margin_holds(self) -> None:
        """No comeback when final margin >= half of peak margin."""
        blocks = [
            {
                "block_index": 0,
                "score_before": [0, 0],
                "score_after": [20, 0],
                "peak_margin": 20,
            },
            {
                "block_index": 1,
                "score_before": [20, 0],
                "score_after": [40, 25],
                "peak_margin": 20,  # Final margin 15 >= 20*0.5
            },
        ]
        is_comeback, peak, final = _detect_big_lead_comeback(blocks)
        assert is_comeback is False

    def test_no_comeback_small_peak(self) -> None:
        """No comeback when peak margin < 15."""
        blocks = [
            {
                "block_index": 0,
                "score_before": [0, 0],
                "score_after": [12, 2],
                "peak_margin": 12,
            },
            {
                "block_index": 1,
                "score_before": [12, 2],
                "score_after": [15, 14],
                "peak_margin": 10,
            },
        ]
        is_comeback, peak, final = _detect_big_lead_comeback(blocks)
        assert is_comeback is False
        assert peak == 12

    def test_empty_blocks(self) -> None:
        """Empty blocks returns no comeback."""
        is_comeback, peak, final = _detect_big_lead_comeback([])
        assert is_comeback is False


class TestDetectCloseGameWithPeakMargin:
    """Tests for _detect_close_game including peak_margin."""

    def test_peak_margin_prevents_close_game_misclassification(self) -> None:
        """Game with hidden mid-block lead not misclassified as close."""
        blocks = [
            {
                "score_before": [0, 0],
                "score_after": [25, 22],
                "peak_margin": 15,  # Home led by 15 mid-block
            },
            {
                "score_before": [25, 22],
                "score_after": [50, 48],
                "peak_margin": 5,
            },
        ]
        is_close, max_margin = _detect_close_game(blocks)
        assert is_close is False
        assert max_margin == 15

    def test_truly_close_game_still_detected(self) -> None:
        """Truly close game (peak_margin <= 7) still detected."""
        blocks = [
            {
                "score_before": [0, 0],
                "score_after": [10, 8],
                "peak_margin": 5,
            },
            {
                "score_before": [10, 8],
                "score_after": [20, 18],
                "peak_margin": 4,
            },
        ]
        is_close, max_margin = _detect_close_game(blocks)
        assert is_close is True


class TestPeakLineInPrompt:
    """Tests for Peak: line appearing in block prompt."""

    def test_peak_line_appears_when_threshold_met(self) -> None:
        """Peak: line appears when peak_margin >= boundary_margin + 6."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [50, 43],  # boundary margin = 7
                "key_play_ids": [],
                "peak_margin": 22,  # 22 >= 7 + 6
                "peak_leader": 1,
            }
        ]
        game_context = {
            "home_team_name": "Illinois",
            "away_team_name": "UCLA",
            "sport": "NCAAB",
        }
        prompt = build_block_prompt(blocks, game_context, [])

        assert "Peak: Illinois led by as many as 22 during this stretch" in prompt

    def test_peak_line_suppressed_when_below_threshold(self) -> None:
        """Peak: line suppressed when peak_margin < boundary_margin + 6."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [25, 18],  # boundary margin = 7
                "key_play_ids": [],
                "peak_margin": 10,  # 10 < 7 + 6
                "peak_leader": 1,
            }
        ]
        game_context = {
            "home_team_name": "Illinois",
            "away_team_name": "UCLA",
            "sport": "NCAAB",
        }
        prompt = build_block_prompt(blocks, game_context, [])
        blocks_section = prompt.split("BLOCKS:")[-1]

        assert "Peak:" not in blocks_section

    def test_peak_line_away_team(self) -> None:
        """Peak: line uses away team name when away led."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 12],  # boundary margin = 2
                "key_play_ids": [],
                "peak_margin": 15,
                "peak_leader": -1,  # Away led
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "sport": "NBA",
        }
        prompt = build_block_prompt(blocks, game_context, [])

        assert "Peak: Celtics led by as many as 15 during this stretch" in prompt

    def test_comeback_guidance_appears(self) -> None:
        """BIG LEAD / COMEBACK guidance appears for comeback games."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [50, 43],
                "key_play_ids": [],
                "peak_margin": 22,
                "peak_leader": 1,
            },
            {
                "block_index": 1,
                "role": SemanticRole.RESOLUTION.value,
                "score_before": [50, 43],
                "score_after": [70, 68],
                "key_play_ids": [],
                "peak_margin": 7,
                "peak_leader": 1,
            },
        ]
        game_context = {
            "home_team_name": "Illinois",
            "away_team_name": "UCLA",
            "sport": "NCAAB",
        }
        prompt = build_block_prompt(blocks, game_context, [])

        assert "BIG LEAD / COMEBACK" in prompt
        assert "Do NOT describe this as a 'modest' or 'slim' lead" in prompt

    def test_no_comeback_guidance_for_normal_game(self) -> None:
        """No BIG LEAD / COMEBACK guidance for normal games."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
                "peak_margin": 5,
                "peak_leader": 1,
            },
            {
                "block_index": 1,
                "role": SemanticRole.RESOLUTION.value,
                "score_before": [10, 8],
                "score_after": [20, 18],
                "key_play_ids": [],
                "peak_margin": 3,
                "peak_leader": 1,
            },
        ]
        game_context = {
            "home_team_name": "Home",
            "away_team_name": "Away",
            "sport": "NBA",
        }
        prompt = build_block_prompt(blocks, game_context, [])

        assert "BIG LEAD / COMEBACK" not in prompt


class TestKeyPlayTeamNames:
    """Tests for team name replacement in key play descriptions."""

    def test_bracket_replaced_with_team_name(self) -> None:
        """[ATL] bracket replaced with (Hawks) in key play."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "home_team_abbrev": "ATL",
            "away_team_abbrev": "BOS",
        }
        pbp_events = [
            {"play_index": 1, "description": "[ATL] Young makes 3-pointer"},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        assert "(Hawks) Young makes 3-pointer" in prompt
        assert "[ATL]" not in prompt

    def test_unknown_bracket_falls_back_to_raw(self) -> None:
        """Unknown abbreviation in brackets falls back to raw abbreviation text."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "home_team_abbrev": "ATL",
            "away_team_abbrev": "BOS",
        }
        pbp_events = [
            {"play_index": 1, "description": "[UNK] Player does something"},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        # Falls back to raw bracket content
        assert "(UNK) Player does something" in prompt
        assert "[UNK]" not in prompt

    def test_no_bracket_passes_through(self) -> None:
        """Play without brackets passes through unchanged."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1],
            }
        ]
        game_context = {
            "home_team_name": "Hawks",
            "away_team_name": "Celtics",
            "home_team_abbrev": "ATL",
            "away_team_abbrev": "BOS",
        }
        pbp_events = [
            {"play_index": 1, "description": "End of period"},
        ]

        prompt = build_block_prompt(blocks, game_context, pbp_events)

        assert "- End of period" in prompt
