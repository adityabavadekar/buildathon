"""Redis read-through cache seam for expensive aggregate-read endpoints.

Fails open: an unreachable Redis must never break a request. Every helper
here catches its own errors, logs, and returns None/no-ops instead of
raising, so a caller always falls back to computing the real result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis.asyncio as redis_async
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from redis.asyncio import Redis

logger = get_logger(__name__)

_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the process-wide async Redis client."""
    global _client  # noqa: PLW0603
    if _client is None:
        settings = get_settings()
        _client = redis_async.from_url(
            settings.redis_url, decode_responses=True, socket_timeout=2.0
        )
        logger.info("cache.redis_client_initialized")
    return _client


def reset_redis_client() -> None:
    """Drop the process-wide client (useful for testing)."""
    global _client  # noqa: PLW0603
    _client = None


async def get_cached_json(key: str) -> str | None:
    """Return the cached value for key, or None on a miss or Redis failure."""
    try:
        client = get_redis_client()
        result = await client.get(key)
        # decode_responses=True guarantees str at runtime; redis-py's stubs
        # keep the bytes|str union for the sync/async-agnostic signature.
        return result if isinstance(result, str) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache.get_failed", key=key, error=str(exc))
        return None


async def set_cached_json(key: str, value: str, ttl_seconds: int) -> None:
    """Store value under key with a TTL. Silently no-ops on Redis failure."""
    try:
        client = get_redis_client()
        await client.set(key, value, ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache.set_failed", key=key, error=str(exc))


async def flush_all() -> None:
    """Drop every cached entry. Used for full-data resets, where naming a
    handful of keys can't cover every parameterized one.
    """
    try:
        client = get_redis_client()
        await client.flushdb()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache.flush_failed", error=str(exc))


async def check_redis_health() -> bool:
    """Check if Redis is reachable and accepting commands."""
    try:
        client = get_redis_client()
        await client.ping()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("cache.health_check_failed", error=str(exc))
        return False


async def cached_model[ModelT: BaseModel](
    key: str,
    ttl_seconds: int,
    model_cls: type[ModelT],
    compute: Callable[[], Awaitable[ModelT]],
) -> ModelT:
    """Return a cached Pydantic model, computing and storing it on a miss."""
    cached = await get_cached_json(key)
    if cached is not None:
        try:
            return model_cls.model_validate_json(cached)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.deserialize_failed", key=key, error=str(exc))

    result = await compute()
    await set_cached_json(key, result.model_dump_json(), ttl_seconds)
    return result


async def cached_json_value(
    key: str,
    ttl_seconds: int,
    compute: Callable[[], Awaitable[object]],
) -> object:
    """Return a cached plain JSON-serializable value (dict/list), computing
    and storing it on a miss. For handlers that don't return a Pydantic model.
    """
    import json  # noqa: PLC0415

    cached = await get_cached_json(key)
    if cached is not None:
        try:
            return json.loads(cached)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.deserialize_failed", key=key, error=str(exc))

    result = await compute()
    try:
        await set_cached_json(key, json.dumps(result), ttl_seconds)
    except (TypeError, ValueError) as exc:
        logger.warning("cache.serialize_failed", key=key, error=str(exc))
    return result
