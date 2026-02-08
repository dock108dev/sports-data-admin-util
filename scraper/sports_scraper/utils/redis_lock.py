"""Shared Redis distributed lock helpers."""
from __future__ import annotations

from ..logging import logger

# Named lock timeout constants — use these instead of bare integers
LOCK_TIMEOUT_5MIN = 300
LOCK_TIMEOUT_10MIN = 600
LOCK_TIMEOUT_1HOUR = 3600


def acquire_redis_lock(lock_name: str, timeout: int = LOCK_TIMEOUT_5MIN) -> bool:
    """Try to acquire a Redis lock. Returns True if acquired."""
    try:
        from ..config import settings
        import redis

        r = redis.from_url(settings.redis_url)
        return bool(r.set(lock_name, "1", nx=True, ex=timeout))
    except Exception as exc:
        logger.warning("redis_lock_failed", lock=lock_name, error=str(exc))
        return True  # Proceed anyway if Redis is down


def release_redis_lock(lock_name: str) -> None:
    """Release a Redis lock."""
    try:
        from ..config import settings
        import redis

        r = redis.from_url(settings.redis_url)
        r.delete(lock_name)
    except Exception as exc:
        logger.warning("redis_unlock_failed", lock=lock_name, error=str(exc))
