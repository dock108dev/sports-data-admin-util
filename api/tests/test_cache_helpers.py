"""Tests for cache_helpers module."""

import hashlib
from unittest.mock import AsyncMock, MagicMock
import pytest


class TestGetBatchCacheKey:
    """Tests for get_batch_cache_key function."""

    def test_generates_hash(self):
        """Generates a valid hash string."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        result = get_batch_cache_key([1, 2, 3])
        assert isinstance(result, str)
        assert len(result) == 16

    def test_consistent_for_same_input(self):
        """Same input produces same hash."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        result1 = get_batch_cache_key([1, 2, 3])
        result2 = get_batch_cache_key([1, 2, 3])
        assert result1 == result2

    def test_different_for_different_input(self):
        """Different input produces different hash."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        result1 = get_batch_cache_key([1, 2, 3])
        result2 = get_batch_cache_key([1, 2, 4])
        assert result1 != result2

    def test_order_independent(self):
        """Order of indices doesn't matter (sorted internally)."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        result1 = get_batch_cache_key([3, 1, 2])
        result2 = get_batch_cache_key([1, 2, 3])
        assert result1 == result2

    def test_empty_list(self):
        """Empty list produces a valid hash."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        result = get_batch_cache_key([])
        assert isinstance(result, str)
        assert len(result) == 16

    def test_single_element(self):
        """Single element produces valid hash."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        result = get_batch_cache_key([42])
        assert isinstance(result, str)
        assert len(result) == 16

    def test_large_indices(self):
        """Large indices work correctly."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        result = get_batch_cache_key([1000000, 2000000, 3000000])
        assert isinstance(result, str)
        assert len(result) == 16

    def test_matches_expected_hash(self):
        """Verify hash matches expected algorithm."""
        from app.services.pipeline.stages.cache_helpers import get_batch_cache_key

        # Manually compute expected hash
        key_str = "1,2,3"
        expected = hashlib.sha256(key_str.encode()).hexdigest()[:16]

        result = get_batch_cache_key([1, 2, 3])
        assert result == expected


class TestGetCachedResponse:
    """Tests for get_cached_response function."""

    @pytest.mark.asyncio
    async def test_returns_cached_data_on_hit(self):
        """Returns cached response when found."""
        from app.services.pipeline.stages.cache_helpers import get_cached_response

        # Create mock cache entry
        cached_entry = MagicMock()
        cached_entry.response_json = {"narratives": ["test narrative"]}

        # Create mock session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = cached_entry

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        result = await get_cached_response(mock_session, game_id=123, batch_key="abc123")

        assert result == {"narratives": ["test narrative"]}
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_miss(self):
        """Returns None when cache miss."""
        from app.services.pipeline.stages.cache_helpers import get_cached_response

        # Create mock session with no result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        result = await get_cached_response(mock_session, game_id=123, batch_key="abc123")

        assert result is None


class TestStoreCachedResponse:
    """Tests for store_cached_response function."""

    @pytest.mark.asyncio
    async def test_stores_cache_entry(self):
        """Stores cache entry in database."""
        from app.services.pipeline.stages.cache_helpers import store_cached_response

        mock_session = AsyncMock()

        await store_cached_response(
            mock_session,
            game_id=123,
            batch_key="abc123",
            prompt_preview="Test prompt",
            response_data={"narratives": ["test"]},
            model="gpt-4",
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_truncates_long_prompt(self):
        """Truncates prompt preview to 2000 chars."""
        from app.services.pipeline.stages.cache_helpers import store_cached_response

        mock_session = AsyncMock()
        long_prompt = "x" * 5000

        await store_cached_response(
            mock_session,
            game_id=123,
            batch_key="abc123",
            prompt_preview=long_prompt,
            response_data={"narratives": ["test"]},
            model="gpt-4",
        )

        # Verify add was called
        mock_session.add.assert_called_once()
        # Get the cache entry that was added
        cache_entry = mock_session.add.call_args[0][0]
        assert len(cache_entry.prompt_preview) == 2000

    @pytest.mark.asyncio
    async def test_handles_none_prompt(self):
        """Handles None prompt preview."""
        from app.services.pipeline.stages.cache_helpers import store_cached_response

        mock_session = AsyncMock()

        await store_cached_response(
            mock_session,
            game_id=123,
            batch_key="abc123",
            prompt_preview=None,
            response_data={"narratives": ["test"]},
            model="gpt-4",
        )

        mock_session.add.assert_called_once()
        cache_entry = mock_session.add.call_args[0][0]
        assert cache_entry.prompt_preview is None
