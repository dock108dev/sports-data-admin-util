"""OpenAI response caching for narrative generation.

This module provides caching functionality to avoid redundant OpenAI calls
for the same moment batches.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from ....db.cache import OpenAIResponseCache

if TYPE_CHECKING:
    from ....db import AsyncSession

logger = logging.getLogger(__name__)


def get_batch_cache_key(moment_indices: list[int]) -> str:
    """Generate a cache key for a batch of moments.

    Args:
        moment_indices: List of moment indices in the batch

    Returns:
        SHA256 hash of the sorted indices (first 16 chars)
    """
    key_str = ",".join(str(i) for i in sorted(moment_indices))
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


async def get_cached_response(
    session: AsyncSession,
    game_id: int,
    batch_key: str,
) -> dict[str, Any] | None:
    """Check cache for an existing OpenAI response.

    Args:
        session: Database session
        game_id: Game ID
        batch_key: Cache key for the batch

    Returns:
        Cached response data or None if not found
    """
    result = await session.execute(
        select(OpenAIResponseCache).where(
            OpenAIResponseCache.game_id == game_id,
            OpenAIResponseCache.batch_key == batch_key,
        )
    )
    cached = result.scalar_one_or_none()
    if cached:
        logger.info(f"Cache HIT for game {game_id} batch {batch_key}")
        return cached.response_json
    return None


async def store_cached_response(
    session: AsyncSession,
    game_id: int,
    batch_key: str,
    prompt_preview: str,
    response_data: dict[str, Any],
    model: str,
) -> None:
    """Store an OpenAI response in the cache.

    Args:
        session: Database session
        game_id: Game ID
        batch_key: Cache key for the batch
        prompt_preview: Truncated prompt for debugging
        response_data: The parsed response from OpenAI
        model: Model name used
    """
    cache_entry = OpenAIResponseCache(
        game_id=game_id,
        batch_key=batch_key,
        prompt_preview=prompt_preview[:2000] if prompt_preview else None,
        response_json=response_data,
        model=model,
    )
    session.add(cache_entry)
    await session.flush()
    logger.info(f"Cache STORED for game {game_id} batch {batch_key}")
