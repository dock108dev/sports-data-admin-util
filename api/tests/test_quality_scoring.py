"""Tests for Stage 3: Quality scoring."""

from __future__ import annotations

from app.services.pipeline.stages.quality_scoring import (
    QualityScoreResult,
    compute_quality_score,
    _compute_cliche_score,
    _compute_readability_score,
    _compute_repetition_score,
    _compute_vocabulary_score,
)


class TestRepetitionScore:
    """Tests for n-gram repetition scoring."""

    def test_no_repetition_scores_high(self) -> None:
        narratives = [
            "The Hawks started strong with quick ball movement.",
            "Boston responded with a defensive adjustment in the second quarter.",
            "Atlanta closed out the game at the free throw line.",
        ]
        score, details = _compute_repetition_score(narratives)
        assert score >= 80

    def test_heavy_repetition_scores_low(self) -> None:
        narratives = [
            "The team scored a basket and the team scored a basket again.",
            "The team scored a basket in the second half and the team scored a basket.",
        ]
        score, details = _compute_repetition_score(narratives)
        assert score < 80

    def test_empty_narratives(self) -> None:
        score, details = _compute_repetition_score([])
        assert score == 100.0

    def test_single_word_narrative(self) -> None:
        score, details = _compute_repetition_score(["Hi."])
        assert score == 100.0


class TestVocabularyScore:
    """Tests for vocabulary diversity scoring."""

    def test_diverse_vocabulary_scores_high(self) -> None:
        narratives = [
            "Young ignited the offense with precise passing and aggressive drives.",
            "Mitchell countered through mid-range excellence and defensive tenacity.",
            "The decisive stretch featured clutchless execution from both backcourts.",
        ]
        score, details = _compute_vocabulary_score(narratives)
        assert score > 0
        assert details["type_token_ratio"] > 0.5

    def test_repetitive_vocabulary_scores_lower(self) -> None:
        narratives = [
            "The team scored and the team scored and the team scored again.",
            "The team scored and the team scored and the team scored more.",
        ]
        score_low, details_low = _compute_vocabulary_score(narratives)

        diverse = [
            "Hawks ignited their offense with precise passes and aggressive drives.",
            "Celtics countered through mid-range excellence and tenacious defense.",
        ]
        score_high, details_high = _compute_vocabulary_score(diverse)
        # Diverse text should have higher type-token ratio
        assert details_high["type_token_ratio"] > details_low["type_token_ratio"]

    def test_empty_narratives(self) -> None:
        score, details = _compute_vocabulary_score([])
        assert score == 100.0


class TestReadabilityScore:
    """Tests for readability scoring."""

    def test_normal_sports_writing_scores_well(self) -> None:
        narratives = [
            "Young found his rhythm early, connecting on three straight jumpers to push the lead to double digits. "
            "The Celtics called timeout but the damage was done.",
            "Mitchell answered with a personal six-point run, capped by a driving layup that cut the deficit to four.",
        ]
        score, details = _compute_readability_score(narratives)
        assert score >= 50
        assert details["ari"] > 0

    def test_very_simple_text_scores_lower(self) -> None:
        narratives = ["He ran. He shot. He scored. Good game."]
        score, details = _compute_readability_score(narratives)
        # Very short sentences = low ARI = lower score
        assert details["avg_sentence_len"] < 5

    def test_empty_narratives(self) -> None:
        score, details = _compute_readability_score([])
        assert score == 100.0


class TestClicheScore:
    """Tests for cliché detection scoring."""

    def test_no_cliches_scores_perfect(self) -> None:
        narratives = [
            "Young connected on three consecutive jumpers to extend the lead.",
            "Mitchell cut the deficit with a baseline drive and a pull-up three.",
        ]
        score, count, details = _compute_cliche_score(narratives)
        assert score == 100.0
        assert count == 0

    def test_cliches_reduce_score(self) -> None:
        narratives = [
            "Young stepped up big when it mattered most.",
            "He put the team on his back and sealed the deal.",
        ]
        score, count, details = _compute_cliche_score(narratives)
        assert count >= 3
        assert score < 60

    def test_single_cliche_moderate_penalty(self) -> None:
        narratives = ["The team rose to the occasion in the fourth quarter."]
        score, count, details = _compute_cliche_score(narratives)
        assert count == 1
        assert score == 85

    def test_empty_narratives(self) -> None:
        score, count, details = _compute_cliche_score([])
        assert score == 100.0
        assert count == 0


class TestComputeQualityScore:
    """Tests for composite quality score computation."""

    def test_good_content_scores_above_threshold(self) -> None:
        blocks = [
            {
                "block_index": 0,
                "narrative": (
                    "Young ignited the offense early, connecting on three straight jumpers "
                    "from beyond the arc to push Atlanta's advantage to double digits before "
                    "the first timeout."
                ),
            },
            {
                "block_index": 1,
                "narrative": (
                    "Mitchell responded with a personal eight-point burst, capping a "
                    "driving layup through contact that trimmed the deficit to four and "
                    "silenced the home crowd."
                ),
            },
            {
                "block_index": 2,
                "narrative": (
                    "The final three minutes belonged to Atlanta's defense, which forced "
                    "consecutive turnovers and converted them into transition baskets "
                    "that removed any remaining doubt."
                ),
            },
        ]
        result = compute_quality_score(blocks)
        assert isinstance(result, QualityScoreResult)
        assert result.composite_score > 0
        assert result.cliche_count == 0

    def test_empty_blocks_return_perfect_score(self) -> None:
        result = compute_quality_score([])
        assert result.composite_score == 100.0

    def test_result_has_all_subscores(self) -> None:
        blocks = [{"block_index": 0, "narrative": "A solid performance from both teams in the opening quarter."}]
        result = compute_quality_score(blocks)
        assert hasattr(result, "repetition_score")
        assert hasattr(result, "vocabulary_score")
        assert hasattr(result, "readability_score")
        assert hasattr(result, "cliche_score")

    def test_to_dict_format(self) -> None:
        blocks = [{"block_index": 0, "narrative": "The game started with an early exchange of baskets."}]
        result = compute_quality_score(blocks)
        d = result.to_dict()
        assert "composite_score" in d
        assert "repetition_score" in d
        assert "vocabulary_score" in d
        assert "readability_score" in d
        assert "cliche_score" in d
        assert "cliche_count" in d
        assert "details" in d
