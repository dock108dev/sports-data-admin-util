"""Tests for Stage 2: Factual validation."""

from __future__ import annotations

import pytest

from app.services.pipeline.stages.factual_validation import (
    FactualValidationResult,
    StatClaim,
    detect_training_data_bleed,
    extract_stat_claims,
    run_factual_validation,
    validate_entity_allowlist,
    verify_stat_claims,
)


class TestExtractStatClaims:
    """Tests for stat claim extraction from narratives."""

    def test_extract_points_scored(self) -> None:
        claims = extract_stat_claims(
            "James scored 25 in the second quarter.", 0, "NBA"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "pts"
        assert claims[0].claimed_value == 25

    def test_extract_possessive_points(self) -> None:
        claims = extract_stat_claims(
            "Young's 30 points led the Hawks.", 0, "NBA"
        )
        assert len(claims) == 1
        assert claims[0].claimed_value == 30

    def test_extract_assists(self) -> None:
        claims = extract_stat_claims(
            "Paul had 12 assists in the game.", 0, "NBA"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "ast"
        assert claims[0].claimed_value == 12

    def test_extract_rebounds(self) -> None:
        claims = extract_stat_claims(
            "Davis grabbed 15 rebounds.", 0, "NBA"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "reb"

    def test_extract_three_pointers(self) -> None:
        claims = extract_stat_claims(
            "Curry hit 8 three-pointers.", 0, "NBA"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "3pm"

    def test_extract_hockey_goals(self) -> None:
        claims = extract_stat_claims(
            "Ovechkin scored 2 goals.", 0, "NHL"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "goals"
        assert claims[0].claimed_value == 2

    def test_extract_hockey_saves(self) -> None:
        claims = extract_stat_claims(
            "Vasilevskiy made 35 saves.", 0, "NHL"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "saves"

    def test_extract_baseball_rbi(self) -> None:
        claims = extract_stat_claims(
            "Judge drove in 3 runs.", 0, "MLB"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "rbi"

    def test_extract_baseball_hr(self) -> None:
        claims = extract_stat_claims(
            "Ohtani hit 2 home runs.", 0, "MLB"
        )
        assert len(claims) == 1
        assert claims[0].stat_key == "hr"

    def test_no_claims_in_clean_text(self) -> None:
        claims = extract_stat_claims(
            "The team played well in the fourth quarter.", 0, "NBA"
        )
        assert len(claims) == 0

    def test_sport_filtering(self) -> None:
        """NBA patterns should not match for NHL sport."""
        claims = extract_stat_claims(
            "Player scored 25 points.", 0, "NHL"
        )
        # "scored 25" without "goals" is NBA-only (pts pattern)
        # The "scored 25 goals" pattern requires "goals" keyword
        assert all(c.stat_key != "pts" for c in claims)

    def test_empty_narrative(self) -> None:
        assert extract_stat_claims("", 0, "NBA") == []
        assert extract_stat_claims(None, 0, "NBA") == []

    def test_multiple_claims_single_narrative(self) -> None:
        claims = extract_stat_claims(
            "Young scored 30 and grabbed 8 rebounds.", 0, "NBA"
        )
        stat_keys = {c.stat_key for c in claims}
        assert "pts" in stat_keys
        assert "reb" in stat_keys


class TestVerifyStatClaims:
    """Tests for stat claim verification against mini_box data."""

    def _make_block(self, players: list[dict]) -> dict:
        return {
            "block_index": 0,
            "mini_box": {
                "home": {"team": "Hawks", "players": players},
                "away": {"team": "Celtics", "players": []},
            },
        }

    def test_correct_claim_verified(self) -> None:
        block = self._make_block([{"name": "Trae Young", "pts": 30}])
        claim = StatClaim("Trae Young", "pts", 30, 0, "Young scored 30")
        errors, warnings, verified, failed = verify_stat_claims([claim], [block])
        assert verified == 1
        assert failed == 0
        assert len(errors) == 0

    def test_incorrect_claim_flagged(self) -> None:
        block = self._make_block([{"name": "Trae Young", "pts": 25}])
        claim = StatClaim("Trae Young", "pts", 30, 0, "Young scored 30")
        errors, warnings, verified, failed = verify_stat_claims([claim], [block])
        assert failed == 1
        assert len(errors) == 1
        assert "claimed 30, actual 25" in errors[0]

    def test_last_name_matching(self) -> None:
        block = self._make_block([{"name": "Trae Young", "pts": 30}])
        claim = StatClaim("Young", "pts", 30, 0, "Young scored 30")
        errors, warnings, verified, failed = verify_stat_claims([claim], [block])
        assert verified == 1

    def test_missing_mini_box_warns(self) -> None:
        block = {"block_index": 0}
        claim = StatClaim("Young", "pts", 30, 0, "Young scored 30")
        errors, warnings, verified, failed = verify_stat_claims([claim], [block])
        assert len(warnings) == 1
        assert "no mini_box" in warnings[0]

    def test_player_not_found_warns(self) -> None:
        block = self._make_block([{"name": "Other Smith", "pts": 20}])
        claim = StatClaim("Unknown Jones", "pts", 30, 0, "Unknown Jones scored 30")
        errors, warnings, verified, failed = verify_stat_claims([claim], [block])
        assert len(warnings) == 1
        assert "not found" in warnings[0]


class TestDetectTrainingDataBleed:
    """Tests for training-data bleed detection."""

    def test_season_average_detected(self) -> None:
        errors = detect_training_data_bleed(
            "He is averaging 25.3 points this season.", 0
        )
        assert len(errors) >= 1
        assert any("season" in e.lower() for e in errors)

    def test_injury_reference_detected(self) -> None:
        errors = detect_training_data_bleed(
            "He returned from an injury to score 20.", 0
        )
        assert len(errors) >= 1
        assert any("injury" in e.lower() for e in errors)

    def test_streak_reference_detected(self) -> None:
        errors = detect_training_data_bleed(
            "He extended his winning streak to 8 games.", 0
        )
        assert len(errors) >= 1
        assert any("streak" in e.lower() for e in errors)

    def test_career_high_detected(self) -> None:
        errors = detect_training_data_bleed("A new career-high for the guard.", 0)
        assert len(errors) >= 1

    def test_mvp_reference_detected(self) -> None:
        errors = detect_training_data_bleed("The MVP candidate was dominant.", 0)
        assert len(errors) >= 1

    def test_clean_narrative_no_bleed(self) -> None:
        errors = detect_training_data_bleed(
            "Young scored from the corner to extend the lead to 85-72.", 0
        )
        assert len(errors) == 0

    def test_empty_narrative(self) -> None:
        assert detect_training_data_bleed("", 0) == []


class TestValidateEntityAllowlist:
    """Tests for entity allowlist validation."""

    def test_known_player_passes(self) -> None:
        context = {"player_names": {"T. Young": "Trae Young"}}
        blocks = [{"mini_box": {"home": {"team": "Hawks", "players": [{"name": "Trae Young"}]}, "away": {"team": "Celtics", "players": []}}}]
        warnings = validate_entity_allowlist(
            "Trae Young led the Hawks.", 0, context, blocks
        )
        assert len(warnings) == 0

    def test_unknown_entity_warned(self) -> None:
        context = {"player_names": {}}
        blocks = [{"mini_box": {"home": {"team": "Hawks", "players": []}, "away": {"team": "Celtics", "players": []}}}]
        warnings = validate_entity_allowlist(
            "Michael Jordan stepped onto the court.", 0, context, blocks
        )
        assert len(warnings) >= 1
        assert "Michael Jordan" in warnings[0]

    def test_team_name_allowed(self) -> None:
        context = {"home_team_name": "Atlanta Hawks", "away_team_name": "Boston Celtics"}
        blocks = [{"mini_box": {}}]
        warnings = validate_entity_allowlist(
            "Atlanta Hawks took control.", 0, context, blocks
        )
        assert len(warnings) == 0


class TestRunFactualValidation:
    """Integration tests for full factual validation."""

    def test_clean_blocks_pass(self) -> None:
        blocks = [
            {
                "block_index": 0,
                "narrative": "The Hawks took an early lead in the opening minutes.",
                "mini_box": {
                    "home": {"team": "Hawks", "players": []},
                    "away": {"team": "Celtics", "players": []},
                },
            }
        ]
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = run_factual_validation(blocks, context, "NBA")
        assert result.passed is True
        assert result.claims_failed == 0

    def test_factual_error_fails(self) -> None:
        blocks = [
            {
                "block_index": 0,
                "narrative": "Young scored 30 in the first quarter.",
                "mini_box": {
                    "home": {"team": "Hawks", "players": [{"name": "Trae Young", "pts": 20}]},
                    "away": {"team": "Celtics", "players": []},
                },
            }
        ]
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = run_factual_validation(blocks, context, "NBA")
        assert result.passed is False
        assert result.claims_failed > 0

    def test_training_bleed_fails(self) -> None:
        blocks = [
            {
                "block_index": 0,
                "narrative": "Young, averaging 28.5 points this season, scored early.",
                "mini_box": {
                    "home": {"team": "Hawks", "players": []},
                    "away": {"team": "Celtics", "players": []},
                },
            }
        ]
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = run_factual_validation(blocks, context, "NBA")
        assert result.passed is False
        assert result.bleed_detections > 0
