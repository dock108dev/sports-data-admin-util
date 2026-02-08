"""Tests for Phase 6: Guardrails & Invariant Enforcement.

Tests ensure that guardrails enforce hard limits correctly:
- Block count ≤ 7
- Embedded tweets ≤ 5
- Zero required social dependencies
"""

import pytest

from app.services.pipeline.stages.guardrails import (
    # Constants
    MAX_BLOCKS,
    MIN_BLOCKS,
    MAX_EMBEDDED_TWEETS,
    MAX_TWEETS_PER_BLOCK,
    # Functions
    validate_blocks_post_generation,
    validate_blocks_pre_render,
    validate_social_independence,
    enforce_guardrails,
    assert_guardrails,
    GuardrailViolationError,
)


class TestConstants:
    """Tests for guardrail constants."""

    def test_max_blocks(self):
        """Max blocks is 7."""
        assert MAX_BLOCKS == 7

    def test_min_blocks(self):
        """Min blocks is 4."""
        assert MIN_BLOCKS == 4

    def test_max_embedded_tweets(self):
        """Max embedded tweets is 5."""
        assert MAX_EMBEDDED_TWEETS == 5

    def test_max_tweets_per_block(self):
        """Max tweets per block is 1."""
        assert MAX_TWEETS_PER_BLOCK == 1


class TestValidateBlocksPostGeneration:
    """Tests for validate_blocks_post_generation function."""

    def test_valid_blocks_pass(self):
        """Valid blocks pass validation."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i} narrative."}
            for i in range(5)
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)

        assert result.passed is True
        assert len(result.violations) == 0
        assert result.block_count == 5

    def test_exceeds_max_blocks_fails(self):
        """Exceeding max blocks fails validation."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(10)  # Exceeds MAX_BLOCKS (7)
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)

        assert result.passed is False
        assert any(v.invariant == "MAX_BLOCKS" for v in result.violations)
        assert result.block_count == 10

    def test_below_min_blocks_warns(self):
        """Below min blocks generates warning but passes."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(2)  # Below MIN_BLOCKS (4)
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)

        # Should pass because MIN_BLOCKS is a warning, not error
        assert result.passed is True
        assert any(v.invariant == "MIN_BLOCKS" and v.severity == "warning" for v in result.violations)

    def test_exceeds_max_embedded_tweets_fails(self):
        """Exceeding max embedded tweets fails validation."""
        blocks = [
            {
                "block_index": i,
                "role": "SETUP",
                "narrative": f"Block {i}.",
                "embedded_social_post_id": i,
            }
            for i in range(7)  # 7 tweets exceeds MAX_EMBEDDED_TWEETS (5)
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)

        assert result.passed is False
        assert any(v.invariant == "MAX_EMBEDDED_TWEETS" for v in result.violations)
        assert result.embedded_tweet_count == 7

    def test_exactly_max_embedded_tweets_passes(self):
        """Exactly max embedded tweets passes."""
        blocks = [
            {
                "block_index": i,
                "role": "SETUP",
                "narrative": f"Block {i}.",
                "embedded_social_post_id": i if i < 5 else None,
            }
            for i in range(7)  # Exactly 5 tweets
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)

        assert result.passed is True
        assert result.embedded_tweet_count == 5

    def test_empty_blocks_pass(self):
        """Empty blocks list passes (edge case)."""
        result = validate_blocks_post_generation([], game_id=123)

        assert result.passed is True
        assert result.block_count == 0

    def test_no_social_data_passes(self):
        """Blocks without social data pass."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)

        assert result.passed is True
        assert result.has_social_data is False
        assert result.embedded_tweet_count == 0

    def test_word_count_warning(self):
        """High word count generates warning but passes."""
        # Create blocks with lots of words
        long_narrative = " ".join(["word"] * 100)  # 100 words per block
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": long_narrative}
            for i in range(5)  # 500 words total, likely over limit
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)

        # Should pass because word count is a warning
        assert result.passed is True
        assert result.total_words == 500


class TestValidateBlocksPreRender:
    """Tests for validate_blocks_pre_render function."""

    def test_missing_required_fields_fails(self):
        """Missing required fields fails validation."""
        blocks = [
            {"block_index": 0, "role": "SETUP"},  # Missing narrative
            {"block_index": 1, "narrative": "Text"},  # Missing role
        ]
        result = validate_blocks_pre_render(blocks, game_id=123)

        assert result.passed is False
        assert any(v.invariant == "BLOCK_STRUCTURE" for v in result.violations)

    def test_complete_blocks_pass(self):
        """Complete blocks pass pre-render validation."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        result = validate_blocks_pre_render(blocks, game_id=123)

        assert result.passed is True


class TestValidateSocialIndependence:
    """Tests for validate_social_independence function."""

    def test_identical_blocks_pass(self):
        """Identical blocks with/without social pass."""
        blocks_with = [
            {
                "block_index": i,
                "role": "SETUP",
                "narrative": f"Block {i}.",
                "embedded_social_post_id": 1 if i == 0 else None,
            }
            for i in range(5)
        ]
        blocks_without = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        result = validate_social_independence(blocks_with, blocks_without, game_id=123)

        assert result.passed is True
        assert result.social_required is False

    def test_different_block_count_fails(self):
        """Different block count with/without social fails."""
        blocks_with = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        blocks_without = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(4)  # Different count
        ]
        result = validate_social_independence(blocks_with, blocks_without, game_id=123)

        assert result.passed is False
        assert result.social_required is True
        assert any(v.invariant == "SOCIAL_INDEPENDENCE" for v in result.violations)

    def test_different_narrative_fails(self):
        """Different narrative with/without social fails."""
        blocks_with = [
            {"block_index": 0, "role": "SETUP", "narrative": "With social."},
        ]
        blocks_without = [
            {"block_index": 0, "role": "SETUP", "narrative": "Without social."},
        ]
        result = validate_social_independence(blocks_with, blocks_without, game_id=123)

        assert result.passed is False
        assert result.social_required is True

    def test_null_comparison_skips(self):
        """Null comparison blocks skips independence check."""
        blocks_with = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        result = validate_social_independence(blocks_with, None, game_id=123)

        assert result.passed is True


class TestEnforceGuardrails:
    """Tests for enforce_guardrails convenience function."""

    def test_post_generation_checkpoint(self):
        """Post-generation checkpoint works."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        result = enforce_guardrails(blocks, game_id=123, checkpoint="post_generation")

        assert result.passed is True

    def test_pre_render_checkpoint(self):
        """Pre-render checkpoint works."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        result = enforce_guardrails(blocks, game_id=123, checkpoint="pre_render")

        assert result.passed is True


class TestAssertGuardrails:
    """Tests for assert_guardrails function."""

    def test_passes_silently(self):
        """Valid blocks don't raise."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        # Should not raise
        assert_guardrails(blocks, game_id=123)

    def test_raises_on_violation(self):
        """Violations raise GuardrailViolationError."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(10)  # Exceeds MAX_BLOCKS
        ]
        with pytest.raises(GuardrailViolationError) as exc_info:
            assert_guardrails(blocks, game_id=123)

        assert exc_info.value.result.game_id == 123
        assert not exc_info.value.result.passed


class TestGuardrailResult:
    """Tests for GuardrailResult dataclass."""

    def test_to_dict(self):
        """to_dict returns serializable dict."""
        blocks = [
            {"block_index": i, "role": "SETUP", "narrative": f"Block {i}."}
            for i in range(5)
        ]
        result = validate_blocks_post_generation(blocks, game_id=123)
        result_dict = result.to_dict()

        assert result_dict["game_id"] == 123
        assert result_dict["passed"] is True
        assert "metrics" in result_dict
        assert result_dict["metrics"]["block_count"] == 5
