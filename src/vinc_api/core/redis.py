from __future__ import annotations

from typing import Optional

from .config import get_settings, Settings

try:
    from redis.asyncio import Redis as AsyncRedis
except Exception:  # pragma: no cover - optional dependency at scaffold time
    AsyncRedis = None  # type: ignore

_redis: Optional["AsyncRedis"] = None


def init_redis(url: str | None = None, settings: Settings | None = None) -> None:
    global _redis
    if AsyncRedis is None:
        return
    settings = settings or get_settings()
    url = url or settings.REDIS_URL
    if not url:
        return
    # redis-py asyncio client manages a connection pool internally
    _redis = AsyncRedis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    )


def get_redis() -> Optional["AsyncRedis"]:
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:  # pragma: no cover - runtime cleanup
        await _redis.close()
        try:
            await _redis.connection_pool.disconnect()
        except Exception:
            pass
        _redis = None

